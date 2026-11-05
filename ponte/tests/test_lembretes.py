"""Lembretes: o Hermes marca com [lembrete: QUANDO | o que], a ponte calcula a hora, guarda e dispara na fila."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from ponte import config, hermes
from ponte import lembretes as lemb
from ponte.app import NAO_ENTENDI_LEMBRETE, criar_app

TOKEN = "t" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SP = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 11, 5, 10, 36, 20, tzinfo=SP)          # quinta


@pytest.mark.parametrize("quando, esperado", [
    ("+30", dt.datetime(2026, 11, 5, 11, 6, 20, tzinfo=SP)),
    ("+30min", dt.datetime(2026, 11, 5, 11, 6, 20, tzinfo=SP)),
    ("+ 30 minutos", dt.datetime(2026, 11, 5, 11, 6, 20, tzinfo=SP)),
    ("+2h", dt.datetime(2026, 11, 5, 12, 36, 20, tzinfo=SP)),
    ("+1h30", dt.datetime(2026, 11, 5, 12, 6, 20, tzinfo=SP)),
    ("+0", dt.datetime(2026, 11, 5, 10, 36, 50, tzinfo=SP)),
    ("16:00", dt.datetime(2026, 11, 5, 16, 0, tzinfo=SP)),
    ("16h", dt.datetime(2026, 11, 5, 16, 0, tzinfo=SP)),
    ("9h30", dt.datetime(2026, 11, 6, 9, 30, tzinfo=SP)),               # já passou: amanhã
    ("06/11 09:00", dt.datetime(2026, 11, 6, 9, 0, tzinfo=SP)),
    ("01/01 08:00", dt.datetime(2027, 1, 1, 8, 0, tzinfo=SP)),
    ("2026-12-24 18:00", dt.datetime(2026, 12, 24, 18, 0, tzinfo=SP)),
])
def test_interpretar(quando, esperado):
    assert lemb.interpretar(quando, AGORA) == esperado


@pytest.mark.parametrize("quando", ["amanhã", "+", "25:00", "31/02 10:00", "2026-11-01 10:00", "2030-01-01 10:00",
                                    "+abc", "", "10:61"])
def test_interpretar_recusa(quando):
    assert lemb.interpretar(quando, AGORA) is None


def test_separar_tira_as_linhas():
    texto, pedidos, cancelar = lemb.separar("Deixa comigo!\n[lembrete: +30 | ligar   para o cliente]\n[cancelar: #4]")
    assert texto.strip() == "Deixa comigo!" and pedidos == [("+30", "ligar para o cliente")] and cancelar == [4]


@pytest.mark.parametrize("texto, pediu", [
    ("me lembra daqui a 30 min de ligar", True),
    ("Me avisa às 16h da reunião", True),
    ("me cutuca amanhã cedo", True),
    ("põe um despertador pra 15h", True),
    ("me lembra de ligar pro cliente", False),                          # sem hora: ele pergunta quando
    ("me avisa se chover amanhã", False),
    ("quais lembretes eu tenho?", False),
    ("vai chover hoje?", False),
])
def test_pediu_lembrete(texto, pediu):
    assert lemb.pediu_lembrete(texto) is pediu


def test_descrever_horario():
    assert lemb.descrever_horario(AGORA.replace(hour=11, minute=6), AGORA) == "11:06"
    assert lemb.descrever_horario(AGORA + dt.timedelta(days=1), AGORA) == "amanhã às 10:36"
    assert lemb.descrever_horario(AGORA + dt.timedelta(days=3), AGORA) == "08/11 às 10:36"


def test_guardar_vencer_uma_vez_e_cancelar(tmp_path):
    t = [AGORA.timestamp()]
    l = lemb.Lembretes(tmp_path / "p.db", relogio=lambda: t[0])
    a = l.criar(AGORA + dt.timedelta(minutes=30), "ligar")
    b = l.criar(AGORA + dt.timedelta(hours=2), "almoço")
    assert [r["texto"] for r in l.pendentes()] == ["ligar", "almoço"] and l.vencidos() == []
    assert "#%d 11:06 ligar" % a in l.contexto("America/Sao_Paulo")
    t[0] += 31 * 60
    assert [r["id"] for r in l.vencidos()] == [a] and l.vencidos() == []      # sai uma vez só
    assert l.cancelar(b) and not l.cancelar(b) and l.contexto("America/Sao_Paulo") == ""


def test_limite_de_pendentes(tmp_path):
    l = lemb.Lembretes(tmp_path / "p.db", relogio=lambda: AGORA.timestamp())
    for i in range(lemb.MAX_PENDENTES):
        assert l.criar(AGORA + dt.timedelta(hours=1), f"x{i}")
    assert l.criar(AGORA + dt.timedelta(hours=1), "demais") is None


def test_fala_no_horario_e_atrasada():
    r = {"quando": AGORA.timestamp(), "texto": "ligar"}
    primeira = lambda opcoes: opcoes[0]                                   # noqa: E731
    assert lemb.fala_do_lembrete(r, "America/Sao_Paulo", AGORA.timestamp() + 10, primeira) == "Ei, psiu! Hora de: ligar"
    assert lemb.fala_do_lembrete(r, "America/Sao_Paulo", AGORA.timestamp() + 3600, primeira) == \
        "Era para te lembrar às 10:36: ligar"


# ---------------- pela ponte ----------------

@pytest.fixture
def ponte(tmp_path, monkeypatch):
    cfg = config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db")})
    relogio = [AGORA.timestamp()]
    respostas, recebidos, historicos = [], [], []

    def falso(c, texto, historico=()):
        recebidos.append(texto)
        historicos.append(list(historico))
        return respostas.pop(0)

    monkeypatch.setattr(hermes, "perguntar", falso)
    cliente = TestClient(criar_app(cfg, buscar_previsao=lambda l: None, relogio=lambda: relogio[0]))
    cliente.historicos = historicos
    return cliente, relogio, respostas, recebidos


def _perguntar(cliente, texto):
    return cliente.post("/api/perguntar", headers=AUTH, json={"texto": texto}).json()


def test_marca_confirma_e_dispara_na_fila(ponte):
    cliente, relogio, respostas, recebidos = ponte
    respostas.append("Deixa comigo!\n[lembrete: +30 | ligar para o cliente]")
    r = _perguntar(cliente, "me lembra daqui a 30 min de ligar para o cliente")
    assert r["resposta"] == "Deixa comigo! Anotado para 11:06."
    assert cliente.get("/api/eventos", headers=AUTH).json()["eventos"] == []
    relogio[0] += 30 * 60 + 1
    eventos = cliente.get("/api/eventos", headers=AUTH).json()["eventos"]
    assert len(eventos) == 1 and "ligar para o cliente" in eventos[0]["texto"]
    assert eventos[0]["tipo"] == "falar" and eventos[0]["efeitos"] == ["lembrete"]
    assert len(cliente.get("/api/eventos", headers=AUTH).json()["eventos"]) == 1     # não duplica
    respostas.append("Tá bom, mais dez minutinhos.\n[lembrete: +10 | ligar para o cliente]")
    _perguntar(cliente, "adia 10 min")
    assert any(m["role"] == "assistant" and m["content"] == eventos[0]["texto"]     # dá para responder ao lembrete
               for m in cliente.historicos[-1])


def test_pergunta_seguinte_ve_os_lembretes_marcados(ponte):
    cliente, relogio, respostas, recebidos = ponte
    respostas += ["Combinado!\n[lembrete: 16:00 | reunião]", "Você tem a reunião às 16h."]
    _perguntar(cliente, "me avisa às 16h da reunião")
    _perguntar(cliente, "quais lembretes eu tenho?")
    assert "[Lembretes marcados: #1 16:00 reunião]" in recebidos[-1]


def test_cancelar(ponte):
    cliente, relogio, respostas, recebidos = ponte
    respostas += ["Ok!\n[lembrete: 16:00 | reunião]", "Pronto, desmarquei.\n[cancelar: 1]", "Hein?\n[cancelar: 99]"]
    _perguntar(cliente, "me avisa às 16h da reunião")
    assert _perguntar(cliente, "cancela o da reunião")["resposta"] == "Pronto, desmarquei."
    assert _perguntar(cliente, "cancela o outro")["resposta"] == "Hein? Esse lembrete eu não achei."
    relogio[0] += 8 * 3600
    assert cliente.get("/api/eventos", headers=AUTH).json()["eventos"] == []


def test_nao_promete_sem_marcar(ponte):
    cliente, relogio, respostas, recebidos = ponte
    respostas += ["Claro, te lembro sim!", "Lembro, mas que horas?", "Claro!\n[lembrete: ontem | x]"]
    assert _perguntar(cliente, "me lembra daqui a 30 min de beber água")["resposta"] == NAO_ENTENDI_LEMBRETE
    assert _perguntar(cliente, "me lembra às 16h")["resposta"] == "Lembro, mas que horas?"   # perguntou: deixa
    assert _perguntar(cliente, "me lembra amanhã")["resposta"] == NAO_ENTENDI_LEMBRETE      # hora inválida


def test_atrasado_diz_a_hora_combinada(ponte):
    cliente, relogio, respostas, recebidos = ponte
    respostas.append("Ok!\n[lembrete: +5 | alongar]")
    _perguntar(cliente, "me lembra daqui a 5 min de alongar")
    relogio[0] += 3 * 3600                                            # pet fechado esse tempo todo
    texto = cliente.get("/api/eventos", headers=AUTH).json()["eventos"][0]["texto"]
    assert "10:41" in texto and "alongar" in texto
