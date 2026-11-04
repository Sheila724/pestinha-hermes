import datetime as dt
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from ponte import calendario, clima, config, hermes, lado_de_fora
from ponte.app import criar_app
from ponte.eventos import Eventos
from ponte.perfil import Perfil, hora_valida

TOKEN = "t" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SP = ZoneInfo("America/Sao_Paulo")
FRANCA = {"nome": "Franca, São Paulo", "lat": -20.54, "lon": -47.4, "fuso": "America/Sao_Paulo", "pais": "BR",
          "cidade": "Franca, SP", "entrada": "08:00", "saida": "18:00"}


@pytest.fixture
def cfg(tmp_path):
    return config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db")})


def quando(texto):
    """'2026-11-04 17:31' no horário de São Paulo, em UTC (como o timer recebe)."""
    return dt.datetime.fromisoformat(texto).replace(tzinfo=SP).astimezone(dt.timezone.utc)


# ---------------- calendário ----------------

def test_pascoa_e_moveis_de_2026():
    assert calendario.pascoa(2026) == dt.date(2026, 4, 5)
    f = calendario.feriados(2026)
    assert f[dt.date(2026, 2, 16)] == f[dt.date(2026, 2, 17)] == "Carnaval"
    assert f[dt.date(2026, 4, 3)] == "Sexta-feira Santa"
    assert f[dt.date(2026, 6, 4)] == "Corpus Christi"
    assert f[dt.date(2026, 11, 20)] == "Dia da Consciência Negra"


@pytest.mark.parametrize("ano, pascoa", [(2025, dt.date(2025, 4, 20)), (2027, dt.date(2027, 3, 28))])
def test_pascoa_outros_anos(ano, pascoa):
    assert calendario.pascoa(ano) == pascoa


def test_fatos_do_dia():
    assert calendario.fatos_do_dia(dt.date(2026, 11, 6)) == ["hoje é sexta-feira"]
    assert calendario.fatos_do_dia(dt.date(2026, 11, 19)) == [
        "amanhã é feriado (Dia da Consciência Negra)", "vai ser feriado prolongado"]
    assert calendario.fatos_do_dia(dt.date(2026, 11, 4)) == []
    assert calendario.dia_util(dt.date(2026, 11, 4)) and not calendario.dia_util(dt.date(2026, 11, 2))
    assert calendario.feriado(dt.date(2026, 12, 25), pais="PT") is None


# ---------------- clima (Open-Meteo de mentira) ----------------

def cliente_falso(rotas):
    def responder(req):
        for trecho, corpo in rotas.items():
            if trecho in str(req.url):
                return httpx.Response(200, json=corpo)
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(responder))


BUSCA = {"results": [
    {"name": "Franca", "latitude": 39.5, "longitude": -8.0, "timezone": "Europe/Lisbon",
     "country": "Portugal", "country_code": "PT", "admin1": "Santarém"},
    {"name": "Franca", "latitude": -20.54, "longitude": -47.4, "timezone": "America/Sao_Paulo",
     "country": "Brasil", "country_code": "BR", "admin1": "São Paulo"},
]}


def test_geocodificar_desempata_pela_sigla():
    lugar = clima.geocodificar("Franca, SP", cliente_falso({"geocoding": BUSCA}))
    assert lugar == {"nome": "Franca, São Paulo", "lat": -20.54, "lon": -47.4,
                     "fuso": "America/Sao_Paulo", "pais": "BR"}
    assert clima.geocodificar("Franca", cliente_falso({"geocoding": BUSCA}))["pais"] == "PT"
    assert clima.geocodificar("Franca, Portugal", cliente_falso({"geocoding": BUSCA}))["pais"] == "PT"


@pytest.mark.parametrize("cidade", ["", "Franca, RJ", "Xyzzy"])
def test_geocodificar_falha_clara(cidade):
    with pytest.raises(clima.ClimaErro):
        clima.geocodificar(cidade, cliente_falso({"geocoding": BUSCA if "Franca" in cidade else {}}))


PREVISAO = {
    "daily": {"time": ["2026-11-04", "2026-11-05"], "temperature_2m_max": [31.4, 27.0],
              "temperature_2m_min": [18.6, 17.2], "precipitation_probability_max": [80, 30]},
    "hourly": {"time": [f"2026-11-04T{h:02d}:00" for h in range(24)],
               "precipitation_probability": [0] * 17 + [70, 85, 40] + [0] * 4},
}


def test_previsao_e_chuva_na_volta():
    prev = clima.previsao(FRANCA, cliente_falso({"forecast": PREVISAO}))
    assert prev["dias"][0] == {"data": "2026-11-04", "max": 31.4, "min": 18.6, "chuva": 80}
    inicio = dt.datetime(2026, 11, 4, 17, 30, tzinfo=SP)
    assert clima.chuva_entre(prev, inicio, inicio + dt.timedelta(hours=3)) == 85
    manha = dt.datetime(2026, 11, 4, 8, 5, tzinfo=SP)
    assert clima.chuva_entre(prev, manha, manha + dt.timedelta(hours=3)) == 0


# ---------------- avisos ----------------

@pytest.fixture
def mundo(cfg):
    perfil, eventos = Perfil(cfg.banco), Eventos(cfg.banco)
    perfil.gravar(FRANCA)
    pedidos = []

    def perguntar(cfg_, texto):
        pedidos.append(texto)
        return "Leva o guarda-chuva, hein!\n[acao: dormir]"

    def rodar(texto, **kw):
        return lado_de_fora.verificar(cfg, perfil, eventos, quando(texto),
                                      buscar_previsao=lambda lugar: clima.previsao(
                                          lugar, cliente_falso({"forecast": PREVISAO})),
                                      perguntar=kw.pop("perguntar", perguntar), **kw)
    return rodar, eventos, pedidos


def test_aviso_de_saida_uma_vez_por_dia(mundo):
    rodar, eventos, pedidos = mundo
    assert rodar("2026-11-04 17:15") is None            # cedo demais
    novo = rodar("2026-11-04 17:31")
    assert novo and rodar("2026-11-04 17:45") is None    # mesma janela: não repete
    ev = eventos.depois_de(0)[0][-1]
    assert ev["texto"] == "Leva o guarda-chuva, hein!"    # a ação que o modelo pôs é descartada
    assert "85% de chance de chuva" in pedidos[0] and "Franca, São Paulo" in pedidos[0]


def test_aviso_de_manha_com_a_previsao(mundo):
    rodar, _, pedidos = mundo
    assert rodar("2026-11-04 08:06")
    assert "mínima 19°C, máxima 31°C" in pedidos[0] and "80% de chance de chuva hoje" in pedidos[0]


def test_sem_aviso_no_feriado_e_no_fim_de_semana(mundo):
    rodar, _, _ = mundo
    assert rodar("2026-11-02 17:31") is None             # Finados
    assert rodar("2026-11-07 17:31") is None             # sábado


def test_hermes_fora_usa_frase_pronta(mundo):
    rodar, eventos, _ = mundo

    def quebrado(cfg_, texto):
        raise hermes.HermesErro("fora")

    assert rodar("2026-11-04 17:31", perguntar=quebrado)
    texto = eventos.depois_de(0)[0][-1]["texto"]
    assert texto.startswith("Quase hora de ir embora!") and "85%" in texto


def test_sem_perfil_nao_faz_nada(cfg):
    assert lado_de_fora.verificar(cfg, Perfil(cfg.banco), Eventos(cfg.banco), quando("2026-11-04 17:31")) is None


def test_forcar_manda_na_hora(mundo):
    rodar, _, _ = mundo
    assert rodar("2026-11-07 11:00", forcar=True)        # sábado, mas forçado (para testar)


def test_cidade_em_outro_fuso(cfg):
    perfil, eventos = Perfil(cfg.banco), Eventos(cfg.banco)
    perfil.gravar({**FRANCA, "nome": "Lisboa, Lisboa", "fuso": "Europe/Lisbon", "pais": "PT"})
    # 17:31 em Lisboa = 14:31 em São Paulo
    agora = dt.datetime(2026, 11, 4, 17, 31, tzinfo=ZoneInfo("Europe/Lisbon")).astimezone(dt.timezone.utc)
    novo = lado_de_fora.verificar(cfg, perfil, eventos, agora, buscar_previsao=lambda l: None,
                                  perguntar=lambda c, t: "Olá de Lisboa!")
    assert novo and eventos.depois_de(0)[0][-1]["texto"] == "Olá de Lisboa!"


# ---------------- rotas do perfil ----------------

def test_hora_valida():
    assert hora_valida("8:00") == "08:00" and hora_valida("18:30") == "18:30"
    assert hora_valida("25:00") is None and hora_valida("oito") is None


def test_rota_perfil(cfg):
    def geo(cidade):
        if "Franca" not in cidade:
            raise clima.ClimaErro("não achei")
        return {k: FRANCA[k] for k in ("nome", "lat", "lon", "fuso", "pais")}

    c = TestClient(criar_app(cfg, geocodificar=geo))
    assert c.get("/api/perfil", headers=AUTH).json() == {}
    r = c.post("/api/perfil", headers=AUTH, json={"cidade": "Franca, SP", "entrada": "8:30", "saida": "17:30"})
    assert r.status_code == 200 and r.json()["nome"] == "Franca, São Paulo" and r.json()["entrada"] == "08:30"
    assert c.get("/api/perfil", headers=AUTH).json()["saida"] == "17:30"
    assert c.post("/api/perfil", headers=AUTH, json={"cidade": "Atlântida"}).status_code == 404
    assert c.post("/api/perfil", headers=AUTH,
                  json={"cidade": "Franca", "entrada": "18:00", "saida": "08:00"}).status_code == 422
    assert c.post("/api/perfil", json={"cidade": "Franca"}).status_code == 401


def test_aviso_entra_na_memoria_da_conversa(cfg):
    from ponte.conversa import Conversa
    perfil, eventos, conversa = Perfil(cfg.banco), Eventos(cfg.banco), Conversa(cfg.banco)
    perfil.gravar(FRANCA)
    lado_de_fora.verificar(cfg, perfil, eventos, quando("2026-11-04 17:31"), buscar_previsao=lambda l: None,
                           perguntar=lambda c, t, h=(): "Leva o guarda-chuva!", conversa=conversa)
    assert conversa.recente() == [{"role": "assistant", "content": "Leva o guarda-chuva!"}]
