import pytest
from fastapi.testclient import TestClient

from ponte import config, hermes
from ponte.app import criar_app

TOKEN = "t" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def cfg(tmp_path):
    return config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db")})


@pytest.fixture
def cliente(cfg):
    return TestClient(criar_app(cfg))


def test_token_curto_impede_subir():
    with pytest.raises(RuntimeError):
        config.carregar({"PONTE_TOKEN": "curto"})


def test_persona_padrao_carregada(cfg):
    assert "Pestinha" in cfg.persona


def test_saude_sem_token(cliente):
    assert cliente.get("/saude").json() == {"ok": True}


@pytest.mark.parametrize("cabecalho", [{}, {"Authorization": "Bearer errado"}, {"Authorization": TOKEN}])
def test_api_exige_token(cliente, cabecalho):
    assert cliente.get("/api/eventos", headers=cabecalho).status_code == 401
    assert cliente.post("/api/perguntar", headers=cabecalho, json={"texto": "oi"}).status_code == 401


def test_fila_de_eventos_por_id(cliente):
    assert cliente.get("/api/eventos", headers=AUTH).json() == {"eventos": [], "ultimo": 0}
    a = cliente.post("/interno/eventos", headers=AUTH, json={"texto": "bom dia!"}).json()["id"]
    b = cliente.post("/interno/eventos", headers=AUTH, json={"tipo": "humor", "humor": "feliz"}).json()["id"]
    todos = cliente.get("/api/eventos", headers=AUTH).json()
    assert [e["id"] for e in todos["eventos"]] == [a, b]
    assert todos["eventos"][0]["texto"] == "bom dia!"
    assert todos["eventos"][1]["humor"] == "feliz"
    novos = cliente.get(f"/api/eventos?desde={a}", headers=AUTH).json()
    assert [e["id"] for e in novos["eventos"]] == [b] and novos["ultimo"] == b


def test_fila_sobrevive_reinicio(cfg):
    TestClient(criar_app(cfg)).post("/interno/eventos", headers=AUTH, json={"texto": "oi"})
    depois = TestClient(criar_app(cfg)).get("/api/eventos", headers=AUTH).json()
    assert depois["eventos"][0]["texto"] == "oi"


@pytest.mark.parametrize("corpo", [{"texto": "  "}, {"tipo": "dancar", "texto": "x"}, {"tipo": "humor"}])
def test_evento_invalido(cliente, corpo):
    assert cliente.post("/interno/eventos", headers=AUTH, json=corpo).status_code == 422


def test_interno_recusa_quem_nao_e_local(cfg):
    de_fora = TestClient(criar_app(cfg), client=("203.0.113.9", 5000))
    assert de_fora.post("/interno/eventos", headers=AUTH, json={"texto": "x"}).status_code == 403


def test_perguntar_repassa_ao_hermes(cliente, monkeypatch):
    recebido = {}

    def falso(cfg, texto):
        recebido["texto"] = texto
        return "Miau, sou o Pestinha!"

    monkeypatch.setattr(hermes, "perguntar", falso)
    r = cliente.post("/api/perguntar", headers=AUTH, json={"texto": "quem é você?"})
    assert r.status_code == 200 and r.json() == {"resposta": "Miau, sou o Pestinha!"}
    assert recebido["texto"] == "quem é você?"


def test_perguntar_com_hermes_fora(cliente, monkeypatch):
    def quebrado(cfg, texto):
        raise hermes.HermesErro("conexão recusada")

    monkeypatch.setattr(hermes, "perguntar", quebrado)
    r = cliente.post("/api/perguntar", headers=AUTH, json={"texto": "oi"})
    assert r.status_code == 502


@pytest.mark.parametrize("texto", ["", "x" * 501])
def test_pergunta_tamanho(cliente, texto):
    assert cliente.post("/api/perguntar", headers=AUTH, json={"texto": texto}).status_code == 422


def test_cliente_hermes_le_resposta(cfg, monkeypatch):
    import httpx

    def transporte(request):
        assert request.url.path == "/v1/chat/completions"
        corpo = request.read().decode()
        assert '"role": "system"' in corpo or '"role":"system"' in corpo
        return httpx.Response(200, json={"choices": [{"message": {"content": " Oi! "}}]})

    real = httpx.post
    monkeypatch.setattr(
        httpx, "post",
        lambda url, **kw: httpx.Client(transport=httpx.MockTransport(transporte)).post(url, **kw),
    )
    assert hermes.perguntar(cfg, "oi") == "Oi!"
    monkeypatch.setattr(httpx, "post", real)


def test_cliente_hermes_resposta_ruim(cfg, monkeypatch):
    import httpx

    transporte = httpx.MockTransport(lambda req: httpx.Response(200, json={"nada": 1}))
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: httpx.Client(transport=transporte).post(url, **kw)
    )
    with pytest.raises(hermes.HermesErro):
        hermes.perguntar(cfg, "oi")
