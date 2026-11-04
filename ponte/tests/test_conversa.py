import pytest
from fastapi.testclient import TestClient

from ponte import config, conversa, hermes
from ponte.app import criar_app

TOKEN = "t" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def cfg(tmp_path):
    return config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db")})


def test_memoria_curta_guarda_e_esquece(cfg):
    agora = [1000.0]
    c = conversa.Conversa(cfg.banco, relogio=lambda: agora[0])
    c.anotar("user", "oi")
    c.anotar("assistant", "Oi, Sheila!")
    c.anotar("sistema", "ignorado")
    c.anotar("user", "   ")
    assert c.recente() == [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "Oi, Sheila!"}]
    agora[0] += conversa.ESQUECE_DEPOIS + 1
    assert c.recente() == []


def test_memoria_curta_limita_o_tamanho(cfg):
    c = conversa.Conversa(cfg.banco)
    for i in range(20):
        c.anotar("user", f"msg {i}")
    recente = c.recente()
    assert len(recente) == conversa.MAX_TROCAS and recente[-1]["content"] == "msg 19"


@pytest.fixture
def chat(cfg, monkeypatch):
    chamadas = []

    def falso(cfg_, texto, historico=()):
        chamadas.append((texto, list(historico)))
        return f"resposta {len(chamadas)}"

    monkeypatch.setattr(hermes, "perguntar", falso)
    return TestClient(criar_app(cfg)), chamadas


def test_segunda_pergunta_leva_a_primeira(chat):
    c, chamadas = chat
    c.post("/api/perguntar", headers=AUTH, json={"texto": "vai chover?"})
    c.post("/api/perguntar", headers=AUTH, json={"texto": "e amanhã?"})
    assert chamadas[0][1] == []
    assert chamadas[1] == ("e amanhã?", [{"role": "user", "content": "vai chover?"},
                                         {"role": "assistant", "content": "resposta 1"}])


def test_responder_ao_aviso_que_ele_mandou_sozinho(chat):
    c, chamadas = chat
    c.post("/interno/eventos", headers=AUTH, json={"texto": "Leva o guarda-chuva!"})
    c.post("/api/perguntar", headers=AUTH, json={"texto": "e amanhã?", "respondendo": "Leva o guarda-chuva!"})
    texto, historico = chamadas[0]
    assert texto == "e amanhã?"                                    # já está no histórico: sem marca extra
    assert historico == [{"role": "assistant", "content": "Leva o guarda-chuva!"}]


def test_responder_post_it_esquecido_vai_como_contexto(chat):
    c, chamadas = chat
    c.post("/api/perguntar", headers=AUTH, json={"texto": "sério?", "respondendo": "Hoje é sexta!"})
    assert chamadas[0][0] == '[Respondendo ao seu post-it: "Hoje é sexta!"]\nsério?'
    c.post("/api/perguntar", headers=AUTH, json={"texto": "e daí?"})
    assert chamadas[1][1][0] == {"role": "assistant", "content": "Hoje é sexta!"}


def test_esquecer_a_conversa(chat):
    c, chamadas = chat
    c.post("/api/perguntar", headers=AUTH, json={"texto": "oi"})
    assert c.post("/api/conversa/esquecer", headers=AUTH).json() == {"ok": True}
    c.post("/api/perguntar", headers=AUTH, json={"texto": "lembra?"})
    assert chamadas[1][1] == []
    assert c.post("/api/conversa/esquecer").status_code == 401
