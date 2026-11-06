"""Pet da equipe: uma ponte para várias pessoas, com conversa por computador, nome de quem fala e diário somado."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from ponte import config, hermes
from ponte.app import criar_app, nome_de_usuario
from ponte.conversa import Conversa
from ponte.diario import Diario, somar

TOKEN = "t" * 64
SP = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 11, 6, 15, 0, tzinfo=SP)
ANA, BETO = "a" * 32, "b" * 32


def cabecalhos(cliente, quem):
    return {"Authorization": f"Bearer {TOKEN}", "X-Pestinha-Cliente": cliente, "X-Pestinha-Quem": quem}


@pytest.fixture
def equipe(tmp_path, monkeypatch):
    cfg = config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db"), "PONTE_EQUIPE": "1",
                           "PONTE_DONO": "equipe do suporte", "PONTE_JEITO": "suporte"})
    relogio = [AGORA.timestamp()]
    chamadas = []

    def falso(c, texto, historico=()):
        chamadas.append((texto, list(historico)))
        return chamadas_respostas.pop(0) if chamadas_respostas else "Ok!"

    chamadas_respostas = []
    monkeypatch.setattr(hermes, "perguntar", falso)
    cliente = TestClient(criar_app(cfg, buscar_previsao=lambda l: None, relogio=lambda: relogio[0]))
    return cliente, cfg, chamadas, chamadas_respostas, relogio


@pytest.mark.parametrize("bruto, nome", [
    ("sheila.alves", "Sheila"), ("talita_souza", "Talita"), ("EMPRESA\\joao", "Joao"), ("joao@empresa.local", "Joao"), ("", ""),
    ("1234", ""), ("maria-clara", "Maria"),
])
def test_nome_de_usuario(bruto, nome):
    assert nome_de_usuario(bruto) == nome


def test_persona_da_equipe(equipe):
    _c, cfg, *_ = equipe
    assert cfg.equipe and "pet da equipe inteira" in cfg.persona and "computador da equipe do suporte" in cfg.persona
    assert "suporte técnico" in cfg.persona and "dados de clientes" in cfg.persona
    assert not config.carregar({"PONTE_TOKEN": TOKEN}).equipe
    assert "pet da equipe inteira" not in config.carregar({"PONTE_TOKEN": TOKEN}).persona


def test_cada_um_com_a_sua_conversa_e_o_seu_nome(equipe):
    c, _cfg, chamadas, _r, _t = equipe
    c.post("/api/perguntar", headers=cabecalhos(ANA, "ana.lima"), json={"texto": "o chamado 12 travou"})
    c.post("/api/perguntar", headers=cabecalhos(BETO, "beto"), json={"texto": "bom dia"})
    texto_beto, historico_beto = chamadas[-1]
    assert "[Quem está falando: Beto]" in texto_beto
    assert not any("chamado 12" in m["content"] for m in historico_beto)          # não vê a conversa da Ana
    c.post("/api/perguntar", headers=cabecalhos(ANA, "ana.lima"), json={"texto": "e agora?"})
    texto_ana, historico_ana = chamadas[-1]
    assert "[Quem está falando: Ana]" in texto_ana
    assert any("chamado 12" in m["content"] for m in historico_ana)


def test_aviso_para_todos_entra_na_conversa_de_todo_mundo(tmp_path):
    conversa = Conversa(tmp_path / "p.db", relogio=lambda: AGORA.timestamp())
    conversa.anotar("assistant", "Vai chover às 17h!")
    conversa.anotar("user", "oi", ANA)
    assert [m["content"] for m in conversa.recente(BETO)] == ["Vai chover às 17h!"]
    assert [m["content"] for m in conversa.recente(ANA)] == ["Vai chover às 17h!", "oi"]
    conversa.esquecer(ANA)
    assert [m["content"] for m in conversa.recente(ANA)] == ["Vai chover às 17h!"]


def test_conversa_de_banco_antigo_ganha_a_coluna(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "velho.db")
    db.execute("CREATE TABLE conversa (id INTEGER PRIMARY KEY AUTOINCREMENT, criado REAL NOT NULL,"
               " papel TEXT NOT NULL, texto TEXT NOT NULL)")
    db.execute("INSERT INTO conversa (criado, papel, texto) VALUES (?, 'user', 'antes')", (AGORA.timestamp(),))
    db.commit()
    db.close()
    conversa = Conversa(tmp_path / "velho.db", relogio=lambda: AGORA.timestamp())
    assert [m["content"] for m in conversa.recente(ANA)] == ["antes"]


def test_sem_modo_equipe_nao_manda_nome(tmp_path, monkeypatch):
    cfg = config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db")})
    recebidos = []
    monkeypatch.setattr(hermes, "perguntar", lambda c, texto, historico=(): recebidos.append(texto) or "Oi!")
    c = TestClient(criar_app(cfg, buscar_previsao=lambda l: None))
    c.post("/api/perguntar", headers=cabecalhos(ANA, "sheila.alves"), json={"texto": "oi"})
    assert "Quem está falando" not in recebidos[0]


def test_diario_soma_os_computadores(tmp_path):
    d = Diario(tmp_path / "p.db")
    d.guardar_dia("2026-11-06", {"emocoes": {"feliz": 30.0}, "contagens": {"cutucadas": 2}}, ANA)
    d.guardar_dia("2026-11-06", {"emocoes": {"feliz": 10.0, "bravo": 5.0}, "contagens": {"cutucadas": 1}}, BETO)
    d.guardar_dia("2026-11-06", {"emocoes": {"feliz": 40.0}, "contagens": {"cutucadas": 3}}, ANA)   # acumulado novo
    assert d.dia("2026-11-06") == {"emocoes": {"feliz": 50.0, "bravo": 5.0}, "contagens": {"cutucadas": 4}}
    assert somar([]) == {"emocoes": {}, "contagens": {}}


def test_diario_pela_rota_com_dois_computadores(equipe):
    c, cfg, *_ = equipe
    corpo = {"data": "2026-11-06", "emocoes": {"feliz": 20}, "contagens": {"perguntas": 1}}
    c.post("/api/dia", headers=cabecalhos(ANA, "ana"), json=corpo)
    c.post("/api/dia", headers=cabecalhos(BETO, "beto"), json=corpo)
    assert Diario(cfg.banco).dia("2026-11-06")["contagens"]["perguntas"] == 2


def test_lembrete_diz_quem_pediu(equipe):
    c, _cfg, chamadas, respostas, relogio = equipe
    respostas.append("Anotado!\n[lembrete: +30 | reunião da equipe]")
    c.post("/api/perguntar", headers=cabecalhos(ANA, "ana.lima"), json={"texto": "me lembra daqui a 30 min da reunião"})
    c.post("/api/perguntar", headers=cabecalhos(BETO, "beto"), json={"texto": "tem lembrete?"})
    assert "reunião da equipe (pedido por Ana)" in chamadas[-1][0]
    relogio[0] += 31 * 60
    eventos = c.get("/api/eventos", headers=cabecalhos(BETO, "beto")).json()["eventos"]
    assert eventos[0]["texto"].endswith("(pedido por Ana)")


def test_cliente_invalido_vira_conversa_comum(equipe):
    c, _cfg, chamadas, _r, _t = equipe
    c.post("/api/perguntar", headers=cabecalhos("../../etc", "x"), json={"texto": "primeira"})
    c.post("/api/perguntar", headers=cabecalhos("nada", "y"), json={"texto": "segunda"})
    assert any(m["content"] == "primeira" for m in chamadas[-1][1])
