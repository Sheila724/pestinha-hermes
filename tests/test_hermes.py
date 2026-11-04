"""
Cliente do Hermes (pestinha/sense/hermes.py) contra uma ponte de mentira, num servidor HTTP local.
E a ligação com o app: sem memory/hermes.json fica desligado; com ele, falas viram post-its.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from pestinha.sense import hermes  # noqa: E402

TOKEN = "segredo-de-teste"


class PonteFalsa:
    """Imita a ponte: fila de eventos por id e /api/perguntar."""

    def __init__(self):
        self.eventos = []
        self.resposta = "Miau! Sou o Pestinha."
        self.status_pergunta = 200
        self.perguntas = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, status, dados):
                corpo = json.dumps(dados).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def _autorizado(self):
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    self._json(401, {"detail": "token inválido"})
                    return False
                return True

            def do_GET(self):
                if not self._autorizado():
                    return
                desde = int(self.path.split("desde=")[1])
                novos = [e for e in fake.eventos if e["id"] > desde][:50]
                ultimo = max([0] + [e["id"] for e in fake.eventos])
                self._json(200, {"eventos": novos, "ultimo": ultimo})

            def do_POST(self):
                if not self._autorizado():
                    return
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.perguntas.append(corpo["texto"])
                if fake.status_pergunta != 200:
                    self._json(fake.status_pergunta, {"detail": "falhou"})
                else:
                    self._json(200, {"resposta": fake.resposta})

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def falar(self, texto):
        self.eventos.append({"id": len(self.eventos) + 1, "tipo": "falar", "texto": texto})

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()


@pytest.fixture
def ponte():
    p = PonteFalsa()
    yield p
    p.fechar()


def cliente(ponte, tmp_path, token=TOKEN):
    return hermes.ClienteHermes(ponte.url, token, tmp_path / "ultimo.txt")


def esperar(c, n=1, segundos=5.0):
    import time
    fim = time.monotonic() + segundos
    itens = []
    while time.monotonic() < fim and len(itens) < n:
        itens += c.coletar()
        time.sleep(0.02)
    return itens


# ---------------- configuração ----------------

def test_sem_arquivo_fica_desligado(tmp_path):
    assert hermes.ClienteHermes.de_arquivo(tmp_path / "hermes.json", tmp_path / "u.txt") is None


@pytest.mark.parametrize("conteudo", ["", "[]", '{"url": "ftp://x", "token": "t"}', '{"url": "https://x"}'])
def test_config_incompleta_fica_desligado(tmp_path, conteudo):
    (tmp_path / "hermes.json").write_text(conteudo, encoding="utf-8")
    assert hermes.carregar_config(tmp_path / "hermes.json") is None


def test_config_valida(tmp_path):
    (tmp_path / "hermes.json").write_text('{"url": "https://pet.exemplo/", "token": " abc "}', encoding="utf-8")
    assert hermes.carregar_config(tmp_path / "hermes.json") == {"url": "https://pet.exemplo", "token": "abc"}


def test_config_com_bom_do_powershell(tmp_path):
    arquivo = tmp_path / "hermes.json"
    arquivo.write_bytes(b"\xef\xbb\xbf" + b'{"url": "https://pet.exemplo", "token": "abc"}')
    assert hermes.carregar_config(arquivo) == {"url": "https://pet.exemplo", "token": "abc"}


@pytest.mark.parametrize("conteudo, trecho", [("{quebrado", "ilegível"), ('{"url": "pet.exemplo"}', "precisa de")])
def test_config_ruim_avisa_no_log(tmp_path, conteudo, trecho):
    arquivo = tmp_path / "hermes.json"
    arquivo.write_text(conteudo, encoding="utf-8")
    avisos = []
    assert hermes.ClienteHermes.de_arquivo(arquivo, tmp_path / "u.txt", avisar=avisos.append) is None
    assert len(avisos) == 1 and trecho in avisos[0]


def test_sem_arquivo_nao_avisa(tmp_path):
    avisos = []
    assert hermes.carregar_config(tmp_path / "nao_existe.json", avisos.append) is None
    assert avisos == []


def test_encurtar_cabe_no_post_it():
    assert hermes.encurtar("  oi\n  tudo   bem? ") == "oi tudo bem?"
    longo = hermes.encurtar("palavra " * 100)
    assert len(longo) <= hermes.MAX_TEXTO and longo.endswith("…")


# ---------------- fila de eventos ----------------

def test_primeira_conexao_nao_despeja_historico(ponte, tmp_path):
    ponte.falar("mensagem antiga")
    c = cliente(ponte, tmp_path)
    assert c.consultar() and c.online
    assert c.coletar() == []
    ponte.falar("bom dia!")
    assert c.consultar()
    assert c.coletar() == [("falar", "bom dia!")]


def test_lembra_o_ultimo_lido_ao_reabrir(ponte, tmp_path):
    c = cliente(ponte, tmp_path)
    c.consultar()
    ponte.falar("um")
    c.consultar()
    assert c.coletar() == [("falar", "um")]
    ponte.falar("dois")                       # chegou com o pet fechado
    reaberto = cliente(ponte, tmp_path)
    reaberto.consultar()
    assert reaberto.coletar() == [("falar", "dois")]


def test_humor_e_eventos_estranhos(ponte, tmp_path):
    c = cliente(ponte, tmp_path)
    c.consultar()
    ponte.eventos += [{"id": 1, "tipo": "humor", "humor": "feliz"}, {"id": 2, "tipo": "dancar"},
                      {"id": 3, "tipo": "falar", "texto": ""}]
    c.consultar()
    assert c.coletar() == [("humor", "feliz")]
    assert c._ultimo == 3


def test_vps_fora_do_ar(tmp_path):
    c = hermes.ClienteHermes("http://127.0.0.1:9", TOKEN, tmp_path / "u.txt")
    assert c.consultar() is False and c.online is False
    assert c.coletar() == []


def test_token_errado_conta_como_fora(ponte, tmp_path):
    c = cliente(ponte, tmp_path, token="outro")
    assert c.consultar() is False and c.online is False


def test_laco_em_segundo_plano(ponte, tmp_path):
    c = hermes.ClienteHermes(ponte.url, TOKEN, tmp_path / "u.txt", intervalo=0.05)
    c.consultar()
    c.iniciar()
    try:
        ponte.falar("oi do cron")
        assert esperar(c) == [("falar", "oi do cron")]
    finally:
        c.parar()


# ---------------- perguntas ----------------

def test_pergunta_e_resposta(ponte, tmp_path):
    c = cliente(ponte, tmp_path)
    c.perguntar("  quem é você?  ")
    assert esperar(c) == [("resposta", "Miau! Sou o Pestinha.")]
    assert ponte.perguntas == ["quem é você?"]


def test_pergunta_vazia_nao_sai(ponte, tmp_path):
    c = cliente(ponte, tmp_path)
    c.perguntar("   ")
    assert esperar(c, segundos=0.3) == [] and ponte.perguntas == []


def test_pergunta_com_hermes_fora(ponte, tmp_path):
    ponte.status_pergunta = 502
    c = cliente(ponte, tmp_path)
    c.perguntar("oi")
    assert esperar(c) == [("erro", "Meu cérebro não respondeu agora…")]


def test_pergunta_com_token_errado(ponte, tmp_path):
    c = cliente(ponte, tmp_path, token="errado")
    c.perguntar("oi")
    assert esperar(c) == [("erro", "A VPS não me reconheceu (token?).")]


def test_pergunta_sem_vps(tmp_path):
    c = hermes.ClienteHermes("http://127.0.0.1:9", TOKEN, tmp_path / "u.txt")
    c.perguntar("oi")
    assert esperar(c) == [("erro", "Não consegui falar com a VPS.")]


# ---------------- no app ----------------

def _app(tmp_path, com_hermes, url=""):
    from PySide6.QtWidgets import QApplication
    from pestinha import config
    from pestinha.app import PestinhaApp
    from pestinha.paths import Paths
    from pestinha.settings_store import SettingsStore

    qt = QApplication.instance() or QApplication([])
    qt.setQuitOnLastWindowClosed(False)
    paths = Paths(root=tmp_path)
    if com_hermes:
        paths.hermes.parent.mkdir(parents=True, exist_ok=True)
        paths.hermes.write_text(json.dumps({"url": url, "token": TOKEN}), encoding="utf-8")
    store = SettingsStore(paths)
    store.update(dict(config.DEFAULT_PERMISSIONS))
    return PestinhaApp(store, paths)


def _fechar(app):
    if app.hermes:
        app.hermes.parar()
    app.mischief.clear()
    app.tray.icon.hide()


def test_app_sem_hermes_json_funciona_como_antes(tmp_path):
    app = _app(tmp_path, com_hermes=False)
    try:
        assert app.hermes is None
    finally:
        _fechar(app)


def test_app_mostra_fala_como_post_it(ponte, tmp_path):
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        assert app.hermes is not None
        app.hermes._chegou.put(("falar", "Hora do café!"))
        app.receber_hermes()
        textos = [getattr(t, "text", None) for t in app.mischief.things]
        assert "Hora do café!" in textos
        left, top, right, bottom = app.bounds()
        for t in app.mischief.things:
            assert left <= t.x - t.width() / 2 and t.x + t.width() / 2 <= right
            assert top <= t.y - t.height() / 2 and t.y + t.height() / 2 <= bottom
    finally:
        _fechar(app)


def test_app_pausado_guarda_a_fala_para_depois(ponte, tmp_path):
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        app.paused = True
        app.hermes._chegou.put(("falar", "depois"))
        app.receber_hermes()
        assert not app.mischief.things
        app.paused = False
        app.receber_hermes()
        assert [t.text for t in app.mischief.things] == ["depois"]
    finally:
        _fechar(app)


def test_fala_longa_usa_post_it_grande(ponte, tmp_path):
    from pestinha.world.objetos import NOTE_SIZE, NOTE_SIZE_FALA
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        app.mostrar_fala("curta")
        app.mostrar_fala(hermes.encurtar("frase comprida " * 20))
        curta, longa = app.mischief.things
        assert curta.note_w == NOTE_SIZE[0] and longa.note_w == NOTE_SIZE_FALA[0]
    finally:
        _fechar(app)
