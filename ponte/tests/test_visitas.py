"""Visitas: duas pontes (Sheila e Talita) no mesmo arquivo de vizinhança, cada uma com o seu pet."""
import pytest
from fastapi.testclient import TestClient

from ponte import config, hermes
from ponte import vizinhanca as viz
from ponte.app import criar_app

TOKEN_S, TOKEN_T = "s" * 64, "t" * 64
PC_S, PC_T = "a" * 32, "b" * 32


def cab(token, cliente, pet="bryan", visitas=True, quem=""):
    return {"Authorization": f"Bearer {token}", "X-Pestinha-Cliente": cliente, "X-Pestinha-Pet": pet,
            "X-Pestinha-Visitas": "1" if visitas else "0", "X-Pestinha-Quem": quem}


@pytest.fixture
def vila(tmp_path, monkeypatch):
    relogio = [1_800_000_000.0]
    monkeypatch.setattr(hermes, "perguntar", lambda c, texto, historico=(): "Oi, cheguei! | Tchau, fui!"
                        if texto.startswith("[Visita]") else "Bora!")

    def ponte(nome, token, jeito="travesso", equipe=False):
        env = {"PONTE_TOKEN": token, "PONTE_BANCO": str(tmp_path / f"{nome}.db"), "PONTE_DONO": nome,
               "PONTE_VIZINHANCA": str(tmp_path / "vizinhanca.db"), "PONTE_JEITO": jeito}
        if equipe:
            env["PONTE_EQUIPE"] = "1"
        return TestClient(criar_app(config.carregar(env), buscar_previsao=lambda l: None, relogio=lambda: relogio[0]))

    return ponte("Sheila", TOKEN_S), ponte("Talita", TOKEN_T, "zoeiro"), relogio, ponte


def eventos(cliente, token, pc, desde=0, **kw):
    return cliente.get(f"/api/eventos?desde={desde}", headers=cab(token, pc, **kw)).json()["eventos"]


def test_visita_completa(vila):
    sheila, talita, relogio, _ = vila
    eventos(talita, TOKEN_T, PC_T, pet="uptime")                       # a Talita está em casa
    vizinhos = sheila.get("/api/vizinhos", headers=cab(TOKEN_S, PC_S)).json()["vizinhos"]
    assert [(v["nome"], v["pet"], v["recebe"]) for v in vizinhos] == [("Talita", "uptime", True)]

    r = sheila.post("/api/visitar", headers=cab(TOKEN_S, PC_S, pet="jorge"), json={"para": vizinhos[0]["id"]})
    assert r.status_code == 200 and r.json()["nome"] == "Talita" and "da Talita" in r.json()["fala"]

    chegada = [e for e in eventos(talita, TOKEN_T, PC_T) if e["tipo"] == "visita"]
    assert len(chegada) == 1 and chegada[0]["para"] == PC_T
    assert chegada[0]["pet"] == "jorge" and chegada[0]["nome"] == "Sheila"
    assert chegada[0]["cumprimento"] == "Oi, cheguei!" and chegada[0]["despedida"] == "Tchau, fui!"
    assert not [e for e in eventos(talita, TOKEN_T, PC_T, desde=chegada[0]["id"]) if e["tipo"] == "visita"]

    assert talita.post("/api/visita/fim", headers=cab(TOKEN_T, PC_T),
                       json={"id": chegada[0]["visita"], "emocao": "feliz"}).status_code == 200
    voltou = [e for e in eventos(sheila, TOKEN_S, PC_S) if e["tipo"] == "voltou"]
    assert len(voltou) == 1 and voltou[0]["para"] == PC_S and "Talita me recebeu todo feliz" in voltou[0]["texto"]
    assert not [e for e in eventos(sheila, TOKEN_S, PC_S, desde=voltou[0]["id"]) if e["tipo"] == "voltou"]


def test_quem_nao_recebe_visita(vila):
    sheila, talita, *_ = vila
    eventos(talita, TOKEN_T, PC_T, visitas=False)
    alvo = sheila.get("/api/vizinhos", headers=cab(TOKEN_S, PC_S)).json()["vizinhos"][0]
    assert alvo["recebe"] is False
    r = sheila.post("/api/visitar", headers=cab(TOKEN_S, PC_S), json={"para": alvo["id"]})
    assert r.status_code == 409 and "não está recebendo visitas" in r.json()["detail"]


def test_ninguem_em_casa(vila):
    sheila, talita, relogio, _ = vila
    eventos(talita, TOKEN_T, PC_T)
    alvo = sheila.get("/api/vizinhos", headers=cab(TOKEN_S, PC_S)).json()["vizinhos"][0]
    relogio[0] += viz.ONLINE_S + 1                                     # a Talita fechou o pet
    assert sheila.get("/api/vizinhos", headers=cab(TOKEN_S, PC_S)).json()["vizinhos"] == []
    assert sheila.post("/api/visitar", headers=cab(TOKEN_S, PC_S), json={"para": alvo["id"]}).status_code == 404


def test_ninguem_abriu_a_porta(vila):
    sheila, talita, relogio, _ = vila
    eventos(talita, TOKEN_T, PC_T)
    alvo = sheila.get("/api/vizinhos", headers=cab(TOKEN_S, PC_S)).json()["vizinhos"][0]
    sheila.post("/api/visitar", headers=cab(TOKEN_S, PC_S), json={"para": alvo["id"]})
    relogio[0] += viz.ESPERA_PORTA_S + 1                               # a Talita fechou antes de ver
    voltou = [e for e in eventos(sheila, TOKEN_S, PC_S) if e["tipo"] == "voltou"]
    assert "ninguém atendeu" in voltou[0]["texto"]
    assert not [e for e in eventos(talita, TOKEN_T, PC_T) if e["tipo"] == "visita"]   # chegou tarde: não aparece


def test_uma_visita_por_vez(vila):
    sheila, talita, relogio, ponte = vila
    beto = ponte("Beto", "x" * 64)
    eventos(talita, TOKEN_T, PC_T)
    eventos(beto, "x" * 64, "c" * 32)
    alvo = next(v for v in sheila.get("/api/vizinhos", headers=cab(TOKEN_S, PC_S)).json()["vizinhos"]
                if v["nome"] == "Talita")
    assert sheila.post("/api/visitar", headers=cab(TOKEN_S, PC_S), json={"para": alvo["id"]}).status_code == 200
    r = beto.post("/api/visitar", headers=cab("x" * 64, "c" * 32), json={"para": alvo["id"]})
    assert r.status_code == 409 and "já está com visita" in r.json()["detail"]
    r = sheila.post("/api/visitar", headers=cab(TOKEN_S, PC_S), json={"para": alvo["id"]})
    assert r.status_code == 409 and "no meio de uma visita" in r.json()["detail"]


def test_pedido_pelo_balao(vila):
    sheila, talita, *_ = vila
    eventos(talita, TOKEN_T, PC_T)
    r = sheila.post("/api/perguntar", headers=cab(TOKEN_S, PC_S), json={"texto": "vai visitar a Talita"}).json()
    assert r["resposta"] == "Bora!" and r["visitar"] == {"nome": "Talita"}
    r = sheila.post("/api/perguntar", headers=cab(TOKEN_S, PC_S), json={"texto": "vai visitar o Zé"}).json()
    assert "visitar" not in r and "não achei ninguém" in r["resposta"]


def test_equipe_mostra_cada_pessoa(vila):
    sheila, _t, _r, ponte = vila
    suporte = ponte("equipe do suporte", "e" * 64, jeito="suporte", equipe=True)
    eventos(suporte, "e" * 64, "d" * 32, quem="ana.lima")
    eventos(suporte, "e" * 64, "f" * 32, quem="beto")
    nomes = [v["nome"] for v in suporte.get("/api/vizinhos", headers=cab("e" * 64, "d" * 32, quem="ana.lima"))
             .json()["vizinhos"]]
    assert nomes == ["Beto (equipe do suporte)"]                       # sem ela mesma
    nomes = [v["nome"] for v in sheila.get("/api/vizinhos", headers=cab(TOKEN_S, PC_S)).json()["vizinhos"]]
    assert nomes == ["Ana (equipe do suporte)", "Beto (equipe do suporte)"]


def test_pet_antigo_sem_id_nao_entra_na_vizinhanca(vila):
    sheila, talita, *_ = vila
    talita.get("/api/eventos?desde=0", headers={"Authorization": f"Bearer {TOKEN_T}"})
    assert sheila.get("/api/vizinhos", headers=cab(TOKEN_S, PC_S)).json()["vizinhos"] == []


def test_fim_de_visita_alheia_nao_vale(vila):
    sheila, talita, *_ = vila
    eventos(talita, TOKEN_T, PC_T)
    alvo = sheila.get("/api/vizinhos", headers=cab(TOKEN_S, PC_S)).json()["vizinhos"][0]
    sheila.post("/api/visitar", headers=cab(TOKEN_S, PC_S), json={"para": alvo["id"]})
    eventos(talita, TOKEN_T, PC_T)
    assert sheila.post("/api/visita/fim", headers=cab(TOKEN_S, PC_S), json={"id": 1}).status_code == 404
