"""Visitas do lado do pet: sair de casa, voltar, receber o pet de alguém e o que chega da ponte."""
import io
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pestinha.body.desenho_rosto import PADRAO  # noqa: E402
from pestinha.sense import hermes  # noqa: E402
from pestinha.world import visitante as vis  # noqa: E402

QT = QApplication.instance() or QApplication([])
VISITA = {"visita": 7, "nome": "Sheila", "pet": "jorge", "cumprimento": "Oi!", "despedida": "Tchau!", "duracao": 30}
BOUNDS = (0, 0, 1600, 900)


# ---------------- o visitante na tela ----------------

def test_visitante_chega_brinca_se_despede_e_vai():
    v = vis.Visitante(VISITA, PADRAO, casa_x=1200, chao_y=800, bounds=BOUNDS, agora=100.0)
    assert v.x < 0                                                    # vem pelo lado com mais espaço
    assert v.tick(100.5, 1200, 800) == []
    vistos = []
    t = 100.0
    while t < 100.0 + 31:
        t += 0.1
        vistos += v.tick(t, 1200, 800)
    assert vistos == ["cumprimentar", "despedir", "acabou"] and v.terminou
    assert v.tick(t + 1, 1200, 800) == []


def test_visitante_para_ao_lado_e_olha_para_o_pet():
    v = vis.Visitante(VISITA, PADRAO, casa_x=300, chao_y=800, bounds=BOUNDS, agora=0.0)
    assert v.x > 1600                                                 # pet perto da esquerda: vem da direita
    v.tick(vis.CHEGADA_S + 1.0, 300, 800)
    assert v.x == pytest.approx(300 + vis.DISTANCIA)
    assert v.janela.state.gaze[0] < 0                                 # olhando para o pet, à esquerda
    v.fechar()


def test_duracao_absurda_fica_num_limite():
    assert vis.Visitante({**VISITA, "duracao": 9999}, PADRAO, 800, 800, BOUNDS, 0.0).duracao == 180
    assert vis.Visitante({**VISITA, "duracao": 1}, PADRAO, 800, 800, BOUNDS, 0.0).duracao == 20


# ---------------- o que chega da ponte ----------------

class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _cliente(tmp_path, monkeypatch, eventos=None, resposta=None):
    pedidos = []

    def abrir(req, timeout=None):
        pedidos.append((req.full_url, {k.lower(): v for k, v in req.header_items()}))
        return _Resposta(json.dumps(resposta if resposta is not None else {"eventos": eventos, "ultimo": 99}).encode())

    monkeypatch.setattr(hermes.urllib.request, "urlopen", abrir)
    ultimo = tmp_path / "memory" / "hermes_ultimo.txt"
    ultimo.parent.mkdir(parents=True, exist_ok=True)
    ultimo.write_text("1", encoding="utf-8")
    c = hermes.ClienteHermes("https://x.exemplo", "t" * 64, ultimo)
    return c, pedidos


def test_consulta_avisa_personagem_e_visitas(tmp_path, monkeypatch):
    c, pedidos = _cliente(tmp_path, monkeypatch, eventos=[])
    c.pet_id, c.recebe_visitas = "uptime", False
    c.consultar()
    cab = pedidos[0][1]
    assert cab["x-pestinha-pet"] == "uptime" and cab["x-pestinha-visitas"] == "0"


def test_so_pega_visita_deste_computador(tmp_path, monkeypatch):
    c, _ = _cliente(tmp_path, monkeypatch, eventos=[])
    meu = c._cliente
    eventos = [
        {"id": 2, "tipo": "visita", "para": "outro" * 6, **VISITA},
        {"id": 3, "tipo": "visita", "para": meu, **VISITA},
        {"id": 4, "tipo": "visita", "para": meu, **{**VISITA, "visita": "x"}},     # malformada
        {"id": 5, "tipo": "voltou", "para": meu, "texto": "Voltei da casa da Talita!"},
        {"id": 6, "tipo": "voltou", "para": "outro", "texto": "não é meu"},
    ]
    c2, _ = _cliente(tmp_path, monkeypatch, eventos=eventos)
    c2._cliente = meu
    c2.consultar()
    assert c2.coletar() == [("visita", VISITA), ("voltou", "Voltei da casa da Talita!")]


def test_vizinhos_e_visitar(tmp_path, monkeypatch):
    lista = [{"id": "abc:def", "nome": "Talita", "pet": "uptime", "recebe": True}, {"sem": "id"}]
    c, _ = _cliente(tmp_path, monkeypatch, resposta={"vizinhos": lista})
    c._vizinhos()
    assert c.coletar() == [("vizinhos", lista[:1])]
    c, pedidos = _cliente(tmp_path, monkeypatch, resposta={"ok": True, "nome": "Talita", "fala": "Fui!"})
    c._visitar("abc:def")
    assert c.coletar() == [("saiu", {"nome": "Talita", "fala": "Fui!"})] and pedidos[0][0].endswith("/api/visitar")


def test_visitar_recusado_vira_info(tmp_path, monkeypatch):
    def abrir(req, timeout=None):
        raise hermes.urllib.error.HTTPError(req.full_url, 409, "x", {},
                                            io.BytesIO(json.dumps({"detail": "A Talita não está recebendo visitas."}).encode()))
    c, _ = _cliente(tmp_path, monkeypatch, eventos=[])
    monkeypatch.setattr(hermes.urllib.request, "urlopen", abrir)
    c._visitar("abc:def")
    assert c.coletar() == [("info", "A Talita não está recebendo visitas.")]


# ---------------- no app ----------------

def _app(tmp_path):
    from pestinha import config
    from pestinha.app import PestinhaApp
    from pestinha.paths import Paths
    from pestinha.settings_store import SettingsStore
    QT.setQuitOnLastWindowClosed(False)
    paths = Paths(root=tmp_path)
    paths.hermes.parent.mkdir(parents=True, exist_ok=True)
    paths.hermes.write_text(json.dumps({"url": "http://127.0.0.1:9", "token": "t" * 64}), encoding="utf-8")
    SettingsStore(paths).update(dict(config.DEFAULT_PERMISSIONS))
    return PestinhaApp(SettingsStore(paths), paths)


def _fechar(app):
    app.hermes.parar()
    app.fechar_visitas()
    if app.palco:
        app.palco.close()
    app.mischief.clear()
    app.tray.icon.hide()


@pytest.fixture
def app(tmp_path):
    a = _app(tmp_path)
    a.hermes.fim_da_visita = lambda id_, emocao: a._fins.append((id_, emocao))
    a._fins = []
    yield a
    _fechar(a)


def test_sai_de_casa_e_volta(app):
    agora = time.monotonic()
    app.sair_de_casa({"nome": "Talita", "fala": ""}, agora)
    assert "visitar o pet da Talita" in app.mischief.things[-1].text and app.pet.isVisible()
    app.rodar_agenda(agora + 1)
    assert app.fora_de_casa == "Talita" and not app.pet.isVisible()
    assert app.motivo_para_nao_sair() == "Eu já estou na rua!"
    app.voltar_para_casa("Voltei! A Talita me recebeu feliz.", agora + 2)
    assert app.fora_de_casa is None and app.pet.isVisible()
    app.rodar_agenda(agora + 3)
    assert app.mischief.things[-1].text == "Voltei! A Talita me recebeu feliz."


def test_volta_sozinho_se_a_ponte_sumir(app):
    from pestinha.controle import visitas
    agora = time.monotonic()
    app.sair_de_casa({"nome": "Talita", "fala": ""}, agora)
    app.rodar_agenda(agora + 1)
    app.tick_visitas(time.monotonic() + visitas.VOLTA_SOZINHO_S + 1)
    assert app.fora_de_casa is None and app.pet.isVisible()


def test_nao_sai_dormindo_nem_com_visita(app):
    app.sleep.fall_asleep()
    assert "dormindo" in app.motivo_para_nao_sair()
    app.sleep.wake(startled=False)
    app.receber_visita(dict(VISITA), time.monotonic())
    assert "com visita" in app.motivo_para_nao_sair()


def test_recebe_visita_ate_o_fim(app):
    agora = time.monotonic()
    app.pet_state.emotion = "curioso"
    app.receber_visita(dict(VISITA), agora)
    v = app.visitante
    assert v is not None and v.janela.isVisible() and app.palco.ativo("exclamacao", agora)
    t = agora
    while app.visitante is not None and t < agora + 40:
        t += 0.2
        app.tick_visitas(t)
    falas = [x.text for x in app.mischief.things]
    assert "Oi!" in falas and "Tchau!" in falas
    assert app._fins == [(7, "curioso")] and not v.janela.isVisible()


def test_visita_de_personagem_desconhecido_vira_o_padrao(app):
    app.receber_visita({**VISITA, "pet": "dragao"}, time.monotonic())
    assert app.visitante is not None


def test_sem_receber_visitas_dispensa_na_porta(app):
    app.apply_perms({**app.perms, "visitas": False})
    assert app.hermes.recebe_visitas is False
    app.receber_visita(dict(VISITA), time.monotonic())
    assert app.visitante is None and app._fins == [(7, "")]
    app.apply_perms({**app.perms, "visitas": True})
    assert app.hermes.recebe_visitas is True


def test_o_cliente_sabe_o_personagem(app):
    assert app.hermes.pet_id == app.perms["pet"]
