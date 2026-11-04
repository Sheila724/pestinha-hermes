import pytest
from fastapi.testclient import TestClient

from ponte import config, hermes
from ponte.app import criar_app

TOKEN = "t" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def sem_mundo(texto):
    """Tira a linha "[Lado de fora agora: ...]" que toda pergunta leva (testada em test_mundo.py)."""
    linhas = texto.split("\n")
    return "\n".join(linhas[1:]) if linhas[0].startswith("[Lado de fora agora:") else texto


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

    def falso(cfg, texto, historico=()):
        recebido["texto"] = sem_mundo(texto)
        return "Miau, sou o Pestinha!"

    monkeypatch.setattr(hermes, "perguntar", falso)
    r = cliente.post("/api/perguntar", headers=AUTH, json={"texto": "quem é você?"})
    assert r.status_code == 200 and r.json() == {"resposta": "Miau, sou o Pestinha!"}
    assert recebido["texto"] == "quem é você?"


def test_perguntar_com_hermes_fora(cliente, monkeypatch):
    def quebrado(cfg, texto, historico=()):
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


# ---------------- dois cérebros: ações e estado ----------------

from ponte import acoes  # noqa: E402


@pytest.mark.parametrize("bruta, texto, acao", [
    ("Tá bom, vou cochilar.\n[acao: dormir]", "Tá bom, vou cochilar.", "dormir"),
    ("Bolinha! [Ação: BOLINHA]", "Bolinha!", "bolinha"),
    ("Hmm [acao: voar]", "Hmm", None),
    ("Só conversa.", "Só conversa.", None),
    ("[acao: dormir] não, melhor [acao: trabalhar]", "não, melhor", "trabalhar"),
])
def test_separar_acao(bruta, texto, acao):
    assert acoes.separar_acao(bruta) == (texto, acao)


def test_descrever_estado():
    assert acoes.descrever_estado(None) == ""
    assert acoes.descrever_estado({"emocao": "inventada"}) == ""
    linha = acoes.descrever_estado({"emocao": "bravo", "energia": 0.3, "dormindo": False})
    assert linha == "[Como o pet está agora: emoção bravo, energia 30%]"


def test_perguntar_com_estado_e_acao(cliente, monkeypatch):
    recebido = {}

    def falso(cfg, texto, historico=()):
        recebido["texto"] = sem_mundo(texto)
        return "Hmpf, tá bom.\n[acao: dormir]"

    monkeypatch.setattr(hermes, "perguntar", falso)
    r = cliente.post("/api/perguntar", headers=AUTH,
                     json={"texto": "vai dormir", "estado": {"emocao": "bravo", "energia": 0.2}})
    assert r.json() == {"resposta": "Hmpf, tá bom.", "acao": "dormir"}
    assert recebido["texto"] == "[Como o pet está agora: emoção bravo, energia 20%]\nvai dormir"


def test_perguntar_sem_estado_continua_igual(cliente, monkeypatch):
    monkeypatch.setattr(hermes, "perguntar", lambda cfg, texto, historico=(): "oi")
    assert cliente.post("/api/perguntar", headers=AUTH, json={"texto": "oi"}).json() == {"resposta": "oi"}


def test_estado_invalido_recusado(cliente):
    r = cliente.post("/api/perguntar", headers=AUTH, json={"texto": "oi", "estado": {"energia": 3}})
    assert r.status_code == 422


def test_evento_de_acao(cliente):
    ok = cliente.post("/interno/eventos", headers=AUTH, json={"tipo": "acao", "acao": "bolinha"})
    assert ok.status_code == 200
    ev = cliente.get("/api/eventos", headers=AUTH).json()["eventos"][-1]
    assert ev["tipo"] == "acao" and ev["acao"] == "bolinha"
    assert cliente.post("/interno/eventos", headers=AUTH, json={"tipo": "acao", "acao": "voar"}).status_code == 422


@pytest.mark.parametrize("bruta, limpo", [
    ("Vai, cochilo no lugar! Tchê... ótimo,", "Vai, cochilo no lugar! Tchê... ótimo"),
    ("[Petição atendida] Pega meu bOCALzinho e vai embora... }|", "Pega meu bOCALzinho e vai embora..."),
    ("**Oba!** Bolinha!", "Oba! Bolinha!"),
    ("Quatro… tá?", "Quatro… tá?"),
])
def test_limpa_lixo_do_modelo(bruta, limpo):
    assert acoes.separar_acao(bruta + "\n[acao: dormir]") == (limpo, "dormir")
