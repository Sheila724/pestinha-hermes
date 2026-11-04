import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from ponte import clima, config, hermes
from ponte.app import criar_app
from ponte.mundo import CACHE_S, Mundo
from ponte.perfil import Perfil

TOKEN = "t" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SP = ZoneInfo("America/Sao_Paulo")
FRANCA = {"nome": "Franca, São Paulo", "lat": -20.54, "lon": -47.4, "fuso": "America/Sao_Paulo", "pais": "BR",
          "cidade": "Franca, SP", "entrada": "08:00", "saida": "18:00"}
PREV = {"dias": [{"data": "2026-11-04", "max": 31.4, "min": 18.6, "chuva": 80},
                 {"data": "2026-11-05", "max": 27.0, "min": 17.2, "chuva": 30}],
        "horas": {"2026-11-04T18:00": 85, "2026-11-04T19:00": 40}}


@pytest.fixture
def perfil(tmp_path):
    return Perfil(config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db")}).banco)


def quando(texto):
    return dt.datetime.fromisoformat(texto).replace(tzinfo=SP).astimezone(dt.timezone.utc)


def test_contexto_com_cidade_e_previsao(perfil):
    perfil.gravar(FRANCA)
    linha = Mundo(perfil, lambda lugar: PREV).contexto(quando("2026-11-04 17:41"))
    assert linha == ("[Lado de fora agora: quarta-feira, 04/11, 17:41 em Franca, São Paulo; "
                     "hoje 19 a 31°C, chance de chuva 80%; amanhã 17 a 27°C, chance de chuva 30%; "
                     "chance de chuva nas próximas 3 horas 85%]")


def test_contexto_sem_cidade_so_data_e_hora(perfil):
    assert Mundo(perfil, lambda l: PREV).contexto(quando("2026-11-04 09:00")) == \
        "[Lado de fora agora: quarta-feira, 04/11, 09:00]"


def test_contexto_com_feriado_e_clima_fora(perfil):
    perfil.gravar(FRANCA)

    def quebrado(lugar):
        raise clima.ClimaErro("fora")

    linha = Mundo(perfil, quebrado).contexto(quando("2026-11-19 10:00"))
    assert "previsão do tempo indisponível agora" in linha
    assert "amanhã é feriado (Dia da Consciência Negra)" in linha


def test_previsao_fica_em_cache(perfil):
    perfil.gravar(FRANCA)
    agora = [0.0]
    buscas = []
    m = Mundo(perfil, lambda l: buscas.append(1) or PREV, relogio=lambda: agora[0])
    m.contexto(quando("2026-11-04 10:00"))
    m.contexto(quando("2026-11-04 10:05"))
    assert len(buscas) == 1
    agora[0] += CACHE_S + 1
    m.contexto(quando("2026-11-04 10:40"))
    assert len(buscas) == 2


def test_toda_pergunta_leva_o_lado_de_fora(tmp_path, monkeypatch):
    cfg = config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db")})
    Perfil(cfg.banco).gravar(FRANCA)
    recebido = []
    monkeypatch.setattr(hermes, "perguntar", lambda c, texto, historico=(): recebido.append(texto) or "Vai chover!")
    c = TestClient(criar_app(cfg, buscar_previsao=lambda lugar: PREV))
    c.post("/api/perguntar", headers=AUTH, json={"texto": "vai chover hoje?"})
    primeira, pergunta = recebido[0].split("\n")
    assert primeira.startswith("[Lado de fora agora:") and "Franca, São Paulo" in primeira
    assert pergunta == "vai chover hoje?"
