"""
Cliente do Hermes (pestinha/sense/hermes.py) contra uma ponte de mentira, num servidor HTTP local.
E a ligação com o app: sem memory/hermes.json fica desligado; com ele, falas viram post-its.
"""
import json
import os
import sys
import threading
import time
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
        self.corpos = []
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
                fake.corpos.append(corpo)
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


def deixar_rolar(app, segundos=10.0):
    """Roda a agenda (o "!" antes da fala, o "puf" antes da resposta) e termina os voos dos post-its."""
    import time as _t
    futuro = _t.monotonic() + segundos
    app.rodar_agenda(futuro)
    for coisa in app.mischief.things:
        coisa.animar(futuro)
        coisa.animar(futuro + 5)


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
        assert app.palco.ativo("exclamacao", time.monotonic()) and not app.mischief.things   # primeiro o "!"
        deixar_rolar(app)
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
        deixar_rolar(app)
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


# ---------------- dois cérebros: o instinto decide ----------------

import random  # noqa: E402

from pestinha.mind import obediencia  # noqa: E402


class SorteFixa(random.Random):
    """random() sempre devolve o mesmo valor; choice pega o primeiro."""
    def __init__(self, valor):
        super().__init__(0)
        self.valor = valor

    def random(self):
        return self.valor

    def choice(self, seq):
        return seq[0]


@pytest.mark.parametrize("emocao", ["feliz", "contente", "curioso", "observando"])
def test_de_bom_humor_obedece(emocao):
    for acao in obediencia.ACOES:
        assert obediencia.decidir(acao, emocao, 0.8, False, SorteFixa(0.0)) == (True, None)


def test_bravo_quase_sempre_recusa():
    obedece, fala = obediencia.decidir("bolinha", "bravo", 0.8, False, SorteFixa(0.5))
    assert not obedece and fala in obediencia.FALAS_RECUSA["bravo"]
    assert obediencia.decidir("bolinha", "bravo", 0.8, False, SorteFixa(0.95)) == (True, None)


def test_triste_metade_das_vezes():
    assert obediencia.decidir("trabalhar", "triste", 0.8, False, SorteFixa(0.4))[0] is False
    assert obediencia.decidir("trabalhar", "triste", 0.8, False, SorteFixa(0.6))[0] is True


def test_cansado_nao_brinca_mas_dorme():
    assert obediencia.decidir("bolinha", "feliz", 0.1, False, SorteFixa(0.0)) == (False, obediencia.FALA_CANSADO[0])
    assert obediencia.decidir("dormir", "feliz", 0.1, False, SorteFixa(0.0)) == (True, None)


def test_dormindo_nao_ouve():
    assert obediencia.decidir("bolinha", "dormindo", 0.5, True, SorteFixa(0.0)) == (False, "Zzz…")
    assert obediencia.decidir("dormir", "dormindo", 0.5, True, SorteFixa(0.0))[0] is False


def test_acao_desconhecida_ignorada():
    assert obediencia.decidir("voar", "feliz", 1.0, False, SorteFixa(0.0)) == (False, None)


def test_recusas_cabem_no_post_it():
    falas = [f for grupo in obediencia.FALAS_RECUSA.values() for f in grupo]
    falas += list(obediencia.FALA_CANSADO) + list(obediencia.FALA_DORMINDO) + list(obediencia.FALA_JA_DORMINDO)
    assert all(len(f) <= 60 for f in falas)


# ---------------- cliente: estado vai, ação volta ----------------

def test_pergunta_leva_o_estado(ponte, tmp_path):
    ponte.resposta = "Tá bom…"
    c = cliente(ponte, tmp_path)
    c.perguntar("vai dormir", {"emocao": "bravo", "energia": 0.3, "dormindo": False})
    assert esperar(c) == [("resposta", "Tá bom…")]
    assert ponte.corpos[0]["estado"] == {"emocao": "bravo", "energia": 0.3, "dormindo": False}


def test_pergunta_sem_estado_nao_manda_o_campo(ponte, tmp_path):
    c = cliente(ponte, tmp_path)
    c.perguntar("oi")
    esperar(c)
    assert "estado" not in ponte.corpos[0]


def test_resposta_com_acao_e_evento_de_acao(ponte, tmp_path, monkeypatch):
    c = cliente(ponte, tmp_path)
    monkeypatch.setattr(c, "_pedido", lambda *a, **k: {"resposta": "Oba!", "acao": "bolinha"})
    c.perguntar("brinca?")
    assert esperar(c, n=2) == [("resposta", "Oba!"), ("acao", "bolinha")]
    monkeypatch.undo()
    c.consultar()
    ponte.eventos.append({"id": 1, "tipo": "acao", "acao": "dormir"})
    c.consultar()
    assert c.coletar() == [("acao", "dormir")]


# ---------------- no app ----------------

def test_app_obedece_de_bom_humor(ponte, tmp_path, monkeypatch):
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        chamado = []
        monkeypatch.setattr(app, "menu_sleep", lambda: chamado.append("dormir"))
        monkeypatch.setattr(obediencia, "decidir", lambda *a, **k: (True, None))
        app.hermes._chegou.put(("acao", "dormir"))
        app.receber_hermes()
        assert app.palco.ativo("estrela", time.monotonic()) and chamado == []      # estrela antes de obedecer
        deixar_rolar(app)
        assert chamado == ["dormir"] and not app.mischief.things
    finally:
        _fechar(app)


def test_app_recusa_com_post_it(ponte, tmp_path, monkeypatch):
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        chamado = []
        monkeypatch.setattr(app, "menu_pedir_trabalho", lambda: chamado.append("trabalhar"))
        monkeypatch.setattr(obediencia, "decidir", lambda *a, **k: (False, "Não quero!"))
        app.hermes._chegou.put(("acao", "trabalhar"))
        app.receber_hermes()
        assert app.palco.ativo("bufo", time.monotonic())
        deixar_rolar(app)
        assert chamado == [] and [t.text for t in app.mischief.things] == ["Não quero!"]
    finally:
        _fechar(app)


def test_app_respeita_as_permissoes(ponte, tmp_path, monkeypatch):
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        monkeypatch.setitem(app.perms, "travessuras", False)
        chamado = []
        monkeypatch.setattr(app, "menu_mischief", lambda: chamado.append("travessura"))
        app.pedido_do_hermes("travessura")
        assert chamado == [] and "Configurações" in app.mischief.things[0].text
    finally:
        _fechar(app)


def test_estado_para_hermes(ponte, tmp_path):
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        estado = app.estado_para_hermes()
        assert set(estado) == {"emocao", "energia", "dormindo"}
        assert estado["emocao"] == app.emotion.current and 0 <= estado["energia"] <= 1
    finally:
        _fechar(app)


# ---------------- lado de fora: cidade e horários ----------------

class PontePerfil(PonteFalsa):
    """A ponte de mentira, com /api/perfil."""

    def __init__(self, status=200):
        super().__init__()
        self.status_perfil = status
        handler = self.servidor.RequestHandlerClass
        original = handler.do_POST
        fake = self

        def do_post(h):
            if h.path != "/api/perfil":
                return original(h)
            corpo = json.loads(h.rfile.read(int(h.headers["Content-Length"])))
            fake.corpos.append(corpo)
            if fake.status_perfil != 200:
                return h._json(fake.status_perfil, {"detail": "não"})
            h._json(200, {**corpo, "nome": "Franca, São Paulo", "fuso": "America/Sao_Paulo"})

        handler.do_POST = do_post


@pytest.mark.parametrize("status, esperado", [
    (200, ("info", "Agora eu olho o céu de Franca, São Paulo! Aviso entre 08:00 e 18:00.")),
    (404, ("info", "Não achei essa cidade. Tenta 'Cidade, UF' ou 'Cidade, País'.")),
    (422, ("info", "Horário estranho… use HH:MM, a entrada antes da saída.")),
])
def test_configurar_cidade(tmp_path, status, esperado):
    p = PontePerfil(status)
    try:
        c = cliente(p, tmp_path)
        c.configurar_perfil(" Franca, SP ", "08:00", "18:00")
        assert esperar(c) == [esperado]
        assert p.corpos[0] == {"cidade": "Franca, SP", "entrada": "08:00", "saida": "18:00"}
        assert (c.perfil is not None) == (status == 200)
    finally:
        p.fechar()


def test_cidade_vazia_nao_sai(ponte, tmp_path):
    c = cliente(ponte, tmp_path)
    c.configurar_perfil("  ", "08:00", "18:00")
    assert esperar(c, segundos=0.3) == [] and ponte.corpos == []


# ---------------- diário do dia ----------------

import datetime as dt  # noqa: E402

from pestinha.mind.diario import DiarioDoDia  # noqa: E402


def amostra(d, dt_s=1.0, emocao="feliz", **kw):
    estado = dict(dormindo=False, carinho=False, castigo=False, ultima_fuga=None, protesto=0)
    estado.update(kw)
    d.observar(dt_s, emocao, **estado)


def test_diario_soma_minutos_e_conta_viradas(tmp_path):
    d = DiarioDoDia(tmp_path / "d.json", hoje=lambda: dt.date(2026, 11, 4))
    for _ in range(120):
        amostra(d, emocao="bravo")                       # 2 min bravo
    amostra(d, carinho=True)
    amostra(d, carinho=True)                             # carinho contínuo conta uma vez
    amostra(d)
    amostra(d, carinho=True)                             # outro carinho
    amostra(d, dormindo=True, emocao="dormindo")
    amostra(d, castigo=True)
    amostra(d, ultima_fuga=100.0)
    amostra(d, ultima_fuga=100.0)
    amostra(d, ultima_fuga=None)                         # fuga desfeita não desconta
    amostra(d, protesto=2)
    amostra(d, protesto=3)                               # mesma manifestação subindo de estágio
    amostra(d, dt_s=3600)                                # computador dormiu: não vira uma hora de emoção
    d.contar("cutucadas")
    d.contar("inventada")
    r = d.resumo()
    assert r["data"] == "2026-11-04"
    assert r["emocoes"]["bravo"] == 2.0 and r["emocoes"]["feliz"] < 0.5
    assert r["contagens"] == {"carinhos": 2, "cochilos": 1, "castigos": 1, "fugas": 1,
                              "protestos": 1, "cutucadas": 1}


def test_diario_persiste_e_vira_o_dia(tmp_path):
    hoje = [dt.date(2026, 11, 4)]
    arquivo = tmp_path / "d.json"
    d = DiarioDoDia(arquivo, hoje=lambda: hoje[0])
    d.contar("cutucadas", 3)
    d.salvar()
    assert DiarioDoDia(arquivo, hoje=lambda: hoje[0]).resumo()["contagens"] == {"cutucadas": 3}
    hoje[0] = dt.date(2026, 11, 5)
    assert DiarioDoDia(arquivo, hoje=lambda: hoje[0]).resumo()["contagens"] == {}   # arquivo de ontem
    d.contar("carinhos")                                  # o mesmo objeto vira o dia sozinho
    assert d.resumo() == {"data": "2026-11-05", "emocoes": {}, "contagens": {"carinhos": 1}}


def test_formatar_data():
    assert hermes.formatar_data("2026-11-04") == "04/11/2026"
    assert hermes.formatar_data("ontem") == "ontem"


class PonteDiario(PonteFalsa):
    def __init__(self, paginas):
        super().__init__()
        self.paginas = paginas
        handler = self.servidor.RequestHandlerClass
        get_original, post_original = handler.do_GET, handler.do_POST
        fake = self

        def do_get(h):
            if h.path.startswith("/api/diario"):
                return h._json(200, {"paginas": fake.paginas})
            return get_original(h)

        def do_post(h):
            if h.path == "/api/dia":
                fake.corpos.append(json.loads(h.rfile.read(int(h.headers["Content-Length"]))))
                return h._json(200, {"ok": True})
            return post_original(h)

        handler.do_GET, handler.do_POST = do_get, do_post


def test_cliente_envia_o_dia_e_le_o_diario(tmp_path):
    p = PonteDiario([{"data": "2026-11-04", "texto": "Hoje fugi do castigo."},
                     {"data": "2026-11-03", "texto": "Dia calmo."}])
    try:
        c = cliente(p, tmp_path)
        c.enviar_dia({"data": "2026-11-04", "emocoes": {}, "contagens": {"cutucadas": 2}}, esperar=True)
        assert p.corpos == [{"data": "2026-11-04", "emocoes": {}, "contagens": {"cutucadas": 2}}]
        c.ler_diario()
        assert esperar(c) == [("diario", "04/11/2026\nHoje fugi do castigo.\n\n03/11/2026\nDia calmo.")]
        p.paginas = []
        c.ler_diario()
        assert esperar(c)[0][0] == "info"
    finally:
        p.fechar()


def test_app_alimenta_o_diario_e_mostra_as_paginas(tmp_path, monkeypatch):
    p = PonteDiario([])
    app = _app(tmp_path, com_hermes=True, url=p.url)
    try:
        assert app.diario is not None
        enviados = []
        monkeypatch.setattr(app.hermes, "enviar_dia", lambda resumo, esperar=False: enviados.append(resumo))
        app.on_poke()
        app.pedido_do_hermes("voar")                     # ação desconhecida: o instinto ignora (recusa)
        app.anotar_diario(forcar_envio=True)
        assert enviados and enviados[-1]["contagens"]["cutucadas"] == 1
        assert enviados[-1]["contagens"]["recusou"] == 1
        assert app.paths.diario_hoje.exists()
        app.hermes._chegou.put(("diario", "04/11/2026\nHoje fugi do castigo."))
        app.receber_hermes()
        assert app._caixa_diario.text() == "04/11/2026\nHoje fugi do castigo."
        app._caixa_diario.close()
    finally:
        _fechar(app)
        p.fechar()


def test_sem_hermes_sem_diario(tmp_path):
    app = _app(tmp_path, com_hermes=False)
    try:
        assert app.diario is None
        app.on_poke()                                    # não quebra sem diário
        app.contar_no_diario("cutucadas")
    finally:
        _fechar(app)


# ---------------- conversa mais fácil: balão, atalho, responder post-it ----------------

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402


def test_balao_envia_com_enter_e_fecha(tmp_path):
    from pestinha.ui.balao import BalaoDeConversa
    _app_qt = _app(tmp_path, com_hermes=False)
    try:
        b = BalaoDeConversa("Uptime")
        recebidos = []
        b.enviado.connect(lambda t, r: recebidos.append((t, r)))
        b.abrir(10, 10, (0, 0, 800, 600), respondendo="Leva o guarda-chuva hoje, viu? Vai chover muito à tarde em Franca e eu não quero ver você molhada!")
        assert b.isVisible() and b.citacao.isVisible() and "Respondendo" in b.citacao.text()
        assert b.citacao.text().endswith("…”")                   # citação longa é encurtada
        assert b.x() >= 4 and b.y() >= 4                          # perto da borda: fica dentro da tela
        b.campo.setText("  e amanhã?  ")                        # keyClicks do QTest só aceita ASCII
        QTest.keyClick(b.campo, Qt.Key_Return)
        assert recebidos == [("e amanhã?", "Leva o guarda-chuva hoje, viu? Vai chover muito à tarde em Franca e eu não quero ver você molhada!")]
        assert not b.isVisible()
        b.abrir(400, 300, (0, 0, 800, 600))
        assert b.citacao.text() == "" and b.campo.text() == ""
        QTest.keyClick(b.campo, Qt.Key_Return)                    # vazio: não envia nada
        assert len(recebidos) == 1
        b.abrir(400, 300, (0, 0, 800, 600))
        QTest.keyClick(b.campo, Qt.Key_Escape)
        assert not b.isVisible()
        b.close()
    finally:
        _fechar(_app_qt)


def test_clicar_na_fala_nao_conta_como_travessura_dispensada(ponte, tmp_path):
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        dispensadas, clicadas = [], []
        app.mischief.dismissed.connect(lambda *a: dispensadas.append(a))
        app.mischief.fala_clicada.connect(clicadas.append)
        app.mostrar_fala("Hoje é sexta!")
        nota = app.mischief.things[0]
        QTest.mouseClick(nota, Qt.LeftButton)
        assert clicadas == ["Hoje é sexta!"] and dispensadas == [] and not app.mischief.things
        assert app.balao.isVisible() and app.balao.respondendo == "Hoje é sexta!"
        app.balao.hide()
    finally:
        _fechar(app)


def test_clique_duplo_no_pet_abre_o_balao(ponte, tmp_path):
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        app.pet.conversar.emit()
        assert app.balao.isVisible() and app.balao.respondendo == ""
        app.balao.hide()
        app.paused = True
        app.pet.conversar.emit()                                 # pausado não abre
        assert not app.balao.isVisible()
    finally:
        _fechar(app)


def test_enviar_do_balao_leva_estado_e_post_it(ponte, tmp_path, monkeypatch):
    app = _app(tmp_path, com_hermes=True, url=ponte.url)
    try:
        chamadas = []
        monkeypatch.setattr(app.hermes, "perguntar", lambda *a: chamadas.append(a))
        app.balao.enviado.emit("e amanhã?", "Leva o guarda-chuva!")
        texto, estado, respondendo = chamadas[0]
        assert texto == "e amanhã?" and respondendo == "Leva o guarda-chuva!" and "emocao" in estado
        assert not app.mischief.things and app.palco.ativo("pensando", time.monotonic())   # nuvem, não post-it
        assert app.diario.resumo()["contagens"]["perguntas"] == 1
    finally:
        _fechar(app)


def test_cliente_manda_o_post_it_respondido(ponte, tmp_path):
    c = cliente(ponte, tmp_path)
    c.perguntar("e amanhã?", None, "  Leva o guarda-chuva!  ")
    esperar(c)
    assert ponte.corpos[0] == {"texto": "e amanhã?", "respondendo": "Leva o guarda-chuva!"}


def test_atalho_de_conversa_fora_do_windows_fica_desligado():
    from pestinha import plataforma
    import sys
    if sys.platform != "win32":
        assert plataforma.iniciar_atalho_conversa(lambda: None) is False


def test_atalho_de_conversa_registra_ctrl_alt_p_no_windows(monkeypatch):
    pytest.importorskip("winreg")                                # o módulo do Windows só importa no Windows
    from pestinha.plataforma import windows

    class User32:
        registrado = None

        def RegisterHotKey(self, hwnd, ident, mods, vk):
            User32.registrado = (ident, mods, vk)
            return 1

        def GetMessageW(self, *a):
            return 0

    falso = type("windll", (), {"user32": User32()})
    monkeypatch.setattr(windows.ctypes, "windll", falso, raising=False)
    assert windows.iniciar_atalho_conversa(lambda: None) is True
    ident, mods, vk = User32.registrado
    assert ident == windows.HOTKEY_CONVERSA_ID != windows.HOTKEY_ID
    assert mods == windows.MOD_CONTROL | windows.MOD_ALT | windows.MOD_NOREPEAT and vk == ord("P")
