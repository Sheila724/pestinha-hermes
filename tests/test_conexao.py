"""Conectar ao Hermes pelo menu: limpar o que foi colado, testar na ponte, gravar e ligar sem reabrir."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from pestinha.sense import hermes  # noqa: E402
from pestinha.ui.conexao import ConexaoHermesDialog  # noqa: E402

QT = QApplication.instance() or QApplication([])
TOKEN = "a" * 64


@pytest.mark.parametrize("url, token, esperado", [
    ("pestinha2.gapsaa.com.br/", TOKEN, ("https://pestinha2.gapsaa.com.br", TOKEN)),
    (" https://x.com.br ", f" PONTE_TOKEN={TOKEN}\n", ("https://x.com.br", TOKEN)),
    ("http://127.0.0.1:8765", f'"{TOKEN}"', ("http://127.0.0.1:8765", TOKEN)),
])
def test_normalizar(url, token, esperado):
    assert hermes.normalizar(url, token) == esperado


@pytest.fixture
def ponte_falsa():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not self.path.startswith("/api/eventos"):
                self.send_response(404)
                self.end_headers()
                return
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                self.send_response(401)
                self.end_headers()
                return
            corpo = json.dumps({"eventos": [], "ultimo": 0}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://localhost:{servidor.server_port}"
    servidor.shutdown()


def test_testar_conexao(ponte_falsa):
    assert hermes.testar_conexao(ponte_falsa, TOKEN) == (True, "")
    ok, msg = hermes.testar_conexao(ponte_falsa, "b" * 64)
    assert not ok and "token" in msg
    ok, msg = hermes.testar_conexao(ponte_falsa + "/outra", TOKEN)
    assert not ok and "não parece" in msg


@pytest.mark.parametrize("url, token, trecho", [
    ("http://localhost:1", TOKEN, "Não consegui chegar"),
    ("https://semponto", TOKEN, "não parece certo"),
    ("https://x.com.br", "curto", "curto demais"),
])
def test_testar_conexao_recusa(url, token, trecho):
    ok, msg = hermes.testar_conexao(url, token, timeout=2)
    assert not ok and trecho in msg


def test_salvar_e_carregar(tmp_path):
    arquivo = tmp_path / "memory" / "hermes.json"
    hermes.salvar_config(arquivo, "https://x.com.br", TOKEN)
    assert not arquivo.read_bytes().startswith(b"\xef\xbb\xbf")
    assert hermes.carregar_config(arquivo) == {"url": "https://x.com.br", "token": TOKEN}


def test_janela_so_aceita_depois_do_teste():
    tentativas = []

    def testar(url, token):
        tentativas.append((url, token))
        return (len(tentativas) > 1, "A ponte não aceitou esse token.")

    j = ConexaoHermesDialog("Pestinha", "", testar, hermes.normalizar)
    j.campo_url.setText("pestinha2.gapsaa.com.br")
    j.campo_token.setText(f"PONTE_TOKEN={TOKEN}")
    j.conectar()
    assert j.result() != QDialog.Accepted and "não aceitou" in j.erro.text()
    j.conectar()
    assert j.result() == QDialog.Accepted
    assert (j.url, j.token) == ("https://pestinha2.gapsaa.com.br", TOKEN) == tentativas[-1]


# ---------------- no app ----------------

def _app(tmp_path):
    from pestinha import config
    from pestinha.app import PestinhaApp
    from pestinha.paths import Paths
    from pestinha.settings_store import SettingsStore
    QT.setQuitOnLastWindowClosed(False)
    paths = Paths(root=tmp_path)
    store = SettingsStore(paths)
    store.update(dict(config.DEFAULT_PERMISSIONS))
    return PestinhaApp(store, paths)


def _fechar(app):
    if app.hermes:
        app.hermes.parar()
    if app.palco:
        app.palco.close()
    app.mischief.clear()
    app.tray.icon.hide()


class JanelaFalsa:
    resposta = QDialog.Accepted
    url, token = "https://pestinha2.gapsaa.com.br", TOKEN

    def __init__(self, *a, **k):
        pass

    def exec(self):
        return self.resposta


def test_conectar_pelo_menu_liga_na_hora_e_troca_depois(tmp_path, monkeypatch):
    from pestinha.controle import interacao
    monkeypatch.setattr(interacao, "ConexaoHermesDialog", JanelaFalsa)
    monkeypatch.setattr(hermes.ClienteHermes, "iniciar", lambda self: None)     # sem rede no teste
    app = _app(tmp_path)
    try:
        assert app.hermes is None and app.balao is None
        app.menu_conectar_hermes()
        assert app.hermes is not None and app.hermes.url == "https://pestinha2.gapsaa.com.br"
        assert app.balao is not None and app.palco is not None and app.diario is not None
        assert hermes.carregar_config(app.paths.hermes)["token"] == TOKEN
        assert [t.text for t in app.mischief.things][0].startswith("Conectado!")
        balao, antigo = app.balao, app.hermes
        app.paths.hermes_ultimo.write_text("42", encoding="utf-8")
        JanelaFalsa.url = "https://outra.com.br"
        try:
            app.menu_conectar_hermes()
        finally:
            JanelaFalsa.url = "https://pestinha2.gapsaa.com.br"
        assert app.hermes is not antigo and app.hermes.url == "https://outra.com.br"
        assert app.balao is balao                                              # não duplica o balão
        assert not app.paths.hermes_ultimo.exists()                            # outra ponte: fila do zero
    finally:
        _fechar(app)


def test_cancelar_nao_muda_nada(tmp_path, monkeypatch):
    from pestinha.controle import interacao

    class Cancela(JanelaFalsa):
        resposta = QDialog.Rejected

    monkeypatch.setattr(interacao, "ConexaoHermesDialog", Cancela)
    app = _app(tmp_path)
    try:
        app.menu_conectar_hermes()
        assert app.hermes is None and not app.paths.hermes.exists()
    finally:
        _fechar(app)
