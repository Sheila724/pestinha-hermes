import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from ponte import config, diario, hermes
from ponte.app import criar_app
from ponte.eventos import Eventos
from ponte.perfil import Perfil

TOKEN = "t" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SP = ZoneInfo("America/Sao_Paulo")
RESUMO = {"emocoes": {"bravo": 42.0, "feliz": 95.5, "observando": 300.0, "dormindo": 0.4},
          "contagens": {"cutucadas": 12, "carinhos": 3, "castigos": 1, "fugas": 1, "recusou": 2}}


@pytest.fixture
def cfg(tmp_path):
    return config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db")})


def quando(texto):
    return dt.datetime.fromisoformat(texto).replace(tzinfo=SP).astimezone(dt.timezone.utc)


def test_limpar_resumo_descarta_lixo():
    sujo = {"emocoes": {"feliz": 10, "inventada": 5, "bravo": -3, "triste": "muito"},
            "contagens": {"cutucadas": 4.0, "hackear": 1, "carinhos": 10**9}}
    assert diario.limpar_resumo(sujo) == {"emocoes": {"feliz": 10.0}, "contagens": {"cutucadas": 4}}


def test_fatos_do_dia():
    lista = diario.fatos(RESUMO)
    assert lista[0] == "passei o dia mais observando (300 min), depois feliz (96 min), depois bravo (42 min)"
    assert "levei 12 cutucada(s)" in lista and "fugi do castigo 1 vez(es)" in lista
    assert "recusei 2 pedido(s)" in lista
    assert diario.fatos({}) == []


@pytest.fixture
def mundo(cfg):
    d, p, e = diario.Diario(cfg.banco), Perfil(cfg.banco), Eventos(cfg.banco)
    pedidos = []

    def perguntar(c, texto):
        pedidos.append(texto)
        return "Querido diário, hoje me cutucaram DOZE vezes. Fugi do castigo e não me arrependo."

    def rodar(texto, **kw):
        return diario.verificar(cfg, d, p, e, quando(texto), perguntar=kw.pop("perguntar", perguntar), **kw)
    return d, e, pedidos, rodar


def test_escreve_a_pagina_a_noite_uma_vez(mundo):
    d, e, pedidos, rodar = mundo
    d.guardar_dia("2026-11-04", RESUMO)
    assert rodar("2026-11-04 18:00") is None                 # cedo
    assert rodar("2026-11-04 21:05") == "2026-11-04"
    assert rodar("2026-11-04 21:20") is None                 # já escreveu
    assert d.paginas()[0]["texto"].startswith("Querido diário, hoje me cutucaram DOZE")
    assert "levei 12 cutucada(s)" in pedidos[0] and "até 5 frases" in pedidos[0]
    assert "Ler meu diário" in e.depois_de(0)[0][-1]["texto"]


def test_sem_dados_nao_escreve(mundo):
    _, _, _, rodar = mundo
    assert rodar("2026-11-04 21:05") is None


def test_hermes_fora_escreve_pagina_simples(mundo):
    d, _, _, rodar = mundo
    d.guardar_dia("2026-11-04", RESUMO)

    def quebrado(c, t):
        raise hermes.HermesErro("fora")

    assert rodar("2026-11-04 21:05", perguntar=quebrado)
    assert d.paginas()[0]["texto"].startswith("Querido diário: hoje passei o dia mais observando")


def test_forcar_escreve_antes_da_hora(mundo):
    d, _, _, rodar = mundo
    d.guardar_dia("2026-11-04", RESUMO)
    assert rodar("2026-11-04 10:00", forcar=True) == "2026-11-04"


def test_pagina_longa_e_cortada(mundo):
    d, _, _, rodar = mundo
    d.guardar_dia("2026-11-04", RESUMO)
    assert rodar("2026-11-04 21:05", perguntar=lambda c, t: "a" * 5000)
    assert len(d.paginas()[0]["texto"]) == diario.MAX_PAGINA


def test_rotas_do_diario(cfg):
    c = TestClient(criar_app(cfg))
    r = c.post("/api/dia", headers=AUTH, json={"data": "2026-11-04", **RESUMO})
    assert r.status_code == 200
    assert diario.Diario(cfg.banco).dia("2026-11-04")["contagens"]["cutucadas"] == 12
    assert c.post("/api/dia", headers=AUTH, json={"data": "ontem"}).status_code == 422
    assert c.post("/api/dia", json={"data": "2026-11-04"}).status_code == 401
    diario.Diario(cfg.banco).guardar_pagina("2026-11-03", "antes")
    diario.Diario(cfg.banco).guardar_pagina("2026-11-04", "hoje")
    assert [p["texto"] for p in c.get("/api/diario", headers=AUTH).json()["paginas"]] == ["hoje", "antes"]
