"""
Animações: curvas de movimento, figurino no corpo, palco em volta, post-its arrastáveis com × e voo,
fechar sem frustração e as reações do pet à conversa com o Hermes.
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pestinha.body import animacao as an  # noqa: E402
from pestinha.body.figurino import RABISCO_S, Figurino  # noqa: E402
from pestinha.world import palco as palco_mod  # noqa: E402
from pestinha.world.palco import Palco  # noqa: E402

QT = QApplication.instance() or QApplication([])


# ---------------- curvas ----------------

@pytest.mark.parametrize("curva", [an.suave, an.com_volta, an.elastico, an.quique, an.acelerar])
def test_curvas_comecam_em_zero_e_terminam_em_um(curva):
    assert abs(curva(0.0)) < 1e-9 and abs(curva(1.0) - 1.0) < 1e-9
    assert curva(-3) == curva(0.0) and curva(7) == curva(1.0)          # fora do intervalo fica preso


def test_com_volta_passa_do_ponto():
    assert max(an.com_volta(t / 100) for t in range(101)) > 1.05


def test_balanco_vai_parando():
    assert abs(an.balanco(3.0)) < abs(an.balanco(0.1)) and an.balanco(-1) == 0.0


def test_bezier_e_progresso():
    assert an.bezier((0, 0), (5, -10), (10, 0), 0.5) == (5.0, -5.0)
    assert an.progresso(5, 4, 2) == 0.5 and an.progresso(1, 4, 2) == 0.0 and an.progresso(9, 4, 0) == 1.0


# ---------------- figurino ----------------

def test_vestir_estender_e_tirar():
    f = Figurino()
    f.vestir("cachecol", 100.0, 5.0)
    assert f.ativo("cachecol", 104.0)
    f.vestir("cachecol", 104.0, 5.0)                                  # vestido: só estende
    assert f.pecas["cachecol"].inicio == 100.0 and f.ativo("cachecol", 108.0)
    f.tirar("cachecol", 108.0)
    assert f.ativo("cachecol", 108.2) and not f.ativo("cachecol", 109.0)  # sai animando, depois some
    f.limpar(109.0)
    assert "cachecol" not in f.pecas


def test_caderno_rabisca_e_nao_atrapalha_a_leitura():
    f = Figurino()
    f.rabiscar(10.0)
    assert f.caderno_modo == "rabiscar" and f.ativo("caderno", 10.0 + RABISCO_S - 0.1)
    assert not f.ativo("caderno", 10.0 + RABISCO_S + 1.0)
    f.abrir_caderno(20.0)
    f.rabiscar(21.0)                                                   # lendo o diário: não troca de modo
    assert f.caderno_modo == "aberto" and f.ativo("caderno", 500.0)
    f.tirar("caderno", 500.0)
    assert not f.ativo("caderno", 501.0)


def test_poses_mudam_olhar_cabeca_e_olho():
    f = Figurino()
    base = (0.2, 0.0)
    assert f.olhar(0.0, base) == base and f.inclinacao(0.0) == 0.0 and f.piscadinha(0.0) is None
    f.ouvir(10.0, (0.0, -1.0))
    assert f.olhar(10.5, base)[1] < -0.5 and abs(f.inclinacao(10.5)) > 5
    f.revirar_olhos(20.0)
    a, b = f.olhar(20.2, base), f.olhar(20.6, base)
    assert a != b and abs(f.olhar(25.0, base)[0] - base[0]) < 1e-9
    f.piscar(30.0)
    assert f.piscadinha(30.3) == 1 and f.piscadinha(31.0) is None
    f.rabiscar(40.0)
    assert f.olhar(40.5, base)[1] > 0.9                                # olha para a página


def _pixels_diferentes(a, b):
    return sum(1 for y in range(0, a.height(), 3) for x in range(0, a.width(), 3) if a.pixel(x, y) != b.pixel(x, y))


@pytest.mark.parametrize("peca", ["oculos_sol", "cachecol", "chapeu", "caderno"])
def test_cada_peca_aparece_no_desenho(peca, monkeypatch):
    import pestinha.body.pet as petmod
    from pestinha.body.pet import PetWindow
    from pestinha.body.pet_state import PetState
    relogio = [1000.0]
    monkeypatch.setattr(petmod.time, "monotonic", lambda: relogio[0])
    pet = PetWindow(300, 300, PetState())

    def foto():
        img = QImage(pet.width(), pet.height(), QImage.Format_ARGB32)
        img.fill(QColor("#cfd8e3"))
        pet.render(img)
        return img

    sem = foto()
    pet.figurino.vestir(peca, 1000.0, 10.0) if peca != "caderno" else pet.figurino.rabiscar(1000.0)
    relogio[0] = 1001.5
    assert _pixels_diferentes(sem, foto()) > 30
    pet.close()


# ---------------- palco ----------------

def test_palco_inicia_encerra_e_some():
    p = Palco()
    p.iniciar("exclamacao", 10.0)
    p.tick(10.1, 500, 500, 0.0, True)
    assert p.isVisible() and p.ativo("exclamacao", 10.1)
    p.tick(20.0, 500, 500, 0.0, True)
    assert not p.efeitos and not p.isVisible()
    p.iniciar("pensando", 30.0)                                        # dura até mandar parar
    assert p.ativo("pensando", 1000.0)
    p.encerrar("pensando", 1000.0)
    assert not p.ativo("pensando", 1000.1) and p.efeitos              # saindo com o "puf"
    p.tick(1001.0, 0, 0, 0.0, True)
    assert not p.efeitos
    p.close()


def test_palco_esconde_com_o_pet_e_nao_duplica():
    p = Palco()
    p.iniciar("guarda_chuva", 0.0)
    p.iniciar("guarda_chuva", 5.0)                                     # rodando: estende em vez de duplicar
    assert len(p.efeitos) == 1 and p.efeitos[0].fim == 17.0
    p.tick(6.0, 100, 100, 0.0, pet_visivel=False)
    assert not p.isVisible()
    p.close()


def test_palco_nao_pega_clique():
    p = Palco()
    assert p.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert p.windowFlags() & Qt.WindowTransparentForInput
    p.close()


@pytest.mark.parametrize("nome", sorted(palco_mod.TEMPOS))
def test_todo_efeito_desenha_sem_erro_em_varios_momentos(nome):
    p = Palco()
    ef = p.iniciar(nome, 100.0)
    if ef.fim is None:
        ef.fim = 100.0 + 9.0
    for t in (0.0, 0.05, 0.3, 0.8, 2.0, 8.5, ef.fim - 100.0 + 0.1):
        p.agora = 100.0 + t
        img = QImage(p.width(), p.height(), QImage.Format_ARGB32)
        img.fill(0)
        p.render(img)
    p.close()


# ---------------- post-its: arrastar, × e voo ----------------

def _nota(texto="oi"):
    from pestinha.world.objetos import NoteThing
    n = NoteThing(texto)
    n.place(400, 300)
    n.show()
    return n


BARRA = QPointF(60, 12).toPoint()                                     # na barra de cima, longe do ×


def _esperar_clique():
    QTest.qWait(QApplication.doubleClickInterval() + 80)


def test_arrasta_pela_barra_como_janela():
    n = _nota()
    cliques = []
    n.clicked.connect(cliques.append)
    x0, y0 = n.x, n.y
    QTest.mousePress(n, Qt.LeftButton, Qt.NoModifier, BARRA)
    destino = BARRA + QPointF(60, 40).toPoint()
    QTest.mouseMove(n, destino)
    QTest.mouseRelease(n, Qt.LeftButton, Qt.NoModifier, destino)
    assert (n.x, n.y) != (x0, y0) and n.arrastado and cliques == []
    QTest.mouseClick(n, Qt.LeftButton, Qt.NoModifier, BARRA)               # clicar na barra: nada
    assert cliques == []
    n.close()


def test_pelo_corpo_nao_arrasta_nem_fecha():
    n = _nota()
    cliques = []
    n.clicked.connect(cliques.append)
    x0 = n.x
    centro = n.rect().center()
    QTest.mousePress(n, Qt.LeftButton, Qt.NoModifier, centro)
    QTest.mouseMove(n, centro + QPointF(60, 0).toPoint())
    QTest.mouseRelease(n, Qt.LeftButton, Qt.NoModifier, centro + QPointF(60, 0).toPoint())
    assert n.x == x0 and cliques == []                                    # escorregou: não vale como clique
    n.close()


def test_clique_no_corpo_e_x():
    n = _nota()
    cliques, fechados = [], []
    n.clicked.connect(cliques.append)
    n.fechar.connect(fechados.append)
    QTest.mouseClick(n, Qt.LeftButton, Qt.NoModifier, n.rect().center())
    assert cliques == [n] and fechados == []                              # sem clique duplo: vale na hora
    QTest.mouseClick(n, Qt.LeftButton, Qt.NoModifier, n.retangulo_x().center().toPoint())
    assert fechados == [n] and len(cliques) == 1
    n.close()


def test_clique_duplo_responde_e_nao_vira_clique():
    n = _nota()
    n.aceita_duplo = True
    cliques, respostas = [], []
    n.clicked.connect(cliques.append)
    n.responder.connect(respostas.append)
    centro = n.rect().center()
    QTest.mouseClick(n, Qt.LeftButton, Qt.NoModifier, centro)
    assert cliques == []                                                  # espera para ver se vem o 2º
    QTest.mouseDClick(n, Qt.LeftButton, Qt.NoModifier, centro)
    QTest.mouseRelease(n, Qt.LeftButton, Qt.NoModifier, centro)
    _esperar_clique()
    assert respostas == [n] and cliques == []
    QTest.mouseClick(n, Qt.LeftButton, Qt.NoModifier, centro)
    _esperar_clique()
    assert cliques == [n]                                                 # clique sozinho vale depois da espera
    n.close()


def test_post_it_voa_do_pet_e_balanca_ao_pousar():
    n = _nota()
    n.voar_de(100, 600, agora=50.0)
    assert (n.x, n.y) == (100, 600)
    n.animar(50.3)
    meio = (n.x, n.y)
    n.animar(50.0 + 0.66)
    assert meio != (100, 600) and (round(n.x), round(n.y)) == (400, 300) and n.voo is None
    assert n.pousou_em is not None
    n.animar(n.pousou_em + 2.0)
    assert n.tilt == n.tilt_base and n.pousou_em is None
    n.close()


def test_objeto_carregado_pelo_pet_nao_e_arrastado():
    n = _nota()
    n.carried = True
    x0 = n.x
    QTest.mousePress(n, Qt.LeftButton, Qt.NoModifier, BARRA)
    QTest.mouseMove(n, BARRA + QPointF(80, 0).toPoint())
    QTest.mouseRelease(n, Qt.LeftButton, Qt.NoModifier, BARRA)
    assert n.x == x0
    n.close()


# ---------------- app: fechar sem frustração e reações ----------------

def _app(tmp_path, com_hermes=True):
    from pestinha import config
    from pestinha.app import PestinhaApp
    from pestinha.paths import Paths
    from pestinha.settings_store import SettingsStore
    QT.setQuitOnLastWindowClosed(False)
    paths = Paths(root=tmp_path)
    if com_hermes:
        paths.hermes.parent.mkdir(parents=True, exist_ok=True)
        paths.hermes.write_text(json.dumps({"url": "http://127.0.0.1:9", "token": "t"}), encoding="utf-8")
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


def _travessura(app):
    from pestinha.world.objetos import NoteThing
    nota = NoteThing("travessura")
    app.mischief._ligar_travessura(nota)
    app.mischief._add(nota)
    return nota


def test_fechar_travessura_pelo_x_ensina_sem_frustrar(tmp_path, monkeypatch):
    app = _app(tmp_path, com_hermes=False)
    try:
        pulsos, aprendeu = [], []
        monkeypatch.setattr(app.senses, "dismissed", lambda *a, **k: pulsos.append(1))
        monkeypatch.setattr(app.mischief_ctl.memory, "on_dismiss", lambda *a: aprendeu.append(a))
        nota = _travessura(app)
        QTest.mouseClick(nota, Qt.LeftButton, Qt.NoModifier, nota.retangulo_x().center().toPoint())
        assert nota not in app.mischief.things
        assert pulsos == [] and len(aprendeu) == 1                     # aprende, mas não fica bravo
        assert app.mischief_ctl.penalty_until > time.monotonic()        # e dá um tempo antes da próxima
    finally:
        _fechar(app)


def test_fechar_travessura_com_clique_deixa_bravo(tmp_path, monkeypatch):
    app = _app(tmp_path)
    try:
        pulsos = []
        monkeypatch.setattr(app.senses, "dismissed", lambda *a, **k: pulsos.append(1))
        nota = _travessura(app)
        assert nota.aceita_duplo                                        # com o Hermes, espera o clique duplo
        QTest.mouseClick(nota, Qt.LeftButton, Qt.NoModifier, nota.rect().center())
        _esperar_clique()
        assert nota not in app.mischief.things and pulsos == [1]        # frustração: a raiva sobe
        assert app.palco.ativo("bufo", time.monotonic())               # e ele bufa
    finally:
        _fechar(app)


def test_clique_duplo_na_travessura_responde_sem_raiva(tmp_path, monkeypatch):
    app = _app(tmp_path)
    try:
        pulsos = []
        monkeypatch.setattr(app.senses, "dismissed", lambda *a, **k: pulsos.append(1))
        nota = _travessura(app)
        centro = nota.rect().center()
        QTest.mouseDClick(nota, Qt.LeftButton, Qt.NoModifier, centro)
        QTest.mouseRelease(nota, Qt.LeftButton, Qt.NoModifier, centro)
        _esperar_clique()
        assert nota not in app.mischief.things and pulsos == []
        assert app.balao.isVisible() and app.balao.respondendo == "travessura"
        app.balao.hide()
    finally:
        _fechar(app)


def test_sem_hermes_clique_fecha_na_hora(tmp_path, monkeypatch):
    app = _app(tmp_path, com_hermes=False)
    try:
        pulsos = []
        monkeypatch.setattr(app.senses, "dismissed", lambda *a, **k: pulsos.append(1))
        nota = _travessura(app)
        assert not nota.aceita_duplo
        QTest.mouseClick(nota, Qt.LeftButton, Qt.NoModifier, nota.rect().center())
        assert nota not in app.mischief.things and pulsos == [1]
    finally:
        _fechar(app)


def test_sem_hermes_sem_palco(tmp_path):
    app = _app(tmp_path, com_hermes=False)
    try:
        assert app.palco is None
        app.tick_vivo(time.monotonic())                                 # não quebra
    finally:
        _fechar(app)


def test_pergunta_mostra_nuvem_ate_a_resposta(tmp_path, monkeypatch):
    app = _app(tmp_path)
    try:
        monkeypatch.setattr(app.hermes, "perguntar", lambda *a: None)
        agora = time.monotonic()
        app.enviar_ao_hermes("uma")
        app.enviar_ao_hermes("duas")
        assert app.palco.ativo("pensando", agora)
        app.hermes._chegou.put(("resposta", "primeira"))
        app.receber_hermes()
        assert app.palco.ativo("pensando", time.monotonic())            # ainda falta uma resposta
        app.hermes._chegou.put(("erro", "ops"))
        app.receber_hermes()
        assert not app.palco.ativo("pensando", time.monotonic())        # "puf"
        app.rodar_agenda(time.monotonic() + 1)
        assert [t.text for t in app.mischief.things] == ["primeira", "ops"]
    finally:
        _fechar(app)


def test_pensando_tem_limite(tmp_path, monkeypatch):
    from pestinha.controle import vivo
    app = _app(tmp_path)
    try:
        monkeypatch.setattr(app.hermes, "perguntar", lambda *a: None)
        app.enviar_ao_hermes("oi")
        app.tick_vivo(time.monotonic() + vivo.PENSANDO_MAX_S + 1)
        assert app._perguntas == 0 and not app.palco.ativo("pensando", time.monotonic() + vivo.PENSANDO_MAX_S + 1)
    finally:
        _fechar(app)


@pytest.mark.parametrize("nome, peca, efeito", [
    ("chuva", None, "guarda_chuva"), ("calor", "oculos_sol", "calor"),
    ("frio", "cachecol", "frio"), ("festa", "chapeu", "confete"), ("diario", "caderno", None),
])
def test_efeitos_do_tempo_e_do_diario(tmp_path, nome, peca, efeito):
    app = _app(tmp_path)
    try:
        agora = time.monotonic()
        app.efeito(nome, agora)
        if peca:
            assert app.figurino.ativo(peca, agora + 0.5)
        if efeito:
            assert app.palco.ativo(efeito, agora + 0.5)
        app.efeito("inventado", agora)                                  # desconhecido: ignora
    finally:
        _fechar(app)


def test_fala_do_diario_espera_o_rabisco(tmp_path):
    app = _app(tmp_path)
    try:
        app.hermes._chegou.put(("efeito", "diario"))
        app.hermes._chegou.put(("falar", "Escrevi no meu diário!"))
        app.receber_hermes()
        agora = time.monotonic()
        assert app.figurino.ativo("caderno", agora)
        app.rodar_agenda(agora + 1.0)
        assert not app.mischief.things                                  # ainda rabiscando
        app.rodar_agenda(agora + RABISCO_S + 0.5)
        assert [t.text for t in app.mischief.things] == ["Escrevi no meu diário!"]
    finally:
        _fechar(app)


def test_rabisca_quando_anota_e_junta_anotacoes_seguidas(tmp_path, monkeypatch):
    from pestinha.controle import vivo
    app = _app(tmp_path)
    try:
        monkeypatch.setattr(type(app), "asleep", property(lambda self: False), raising=False)
        t0 = time.monotonic() + 100
        app.contar_no_diario("cutucadas")
        app._talvez_rabiscar(t0)
        assert not app.figurino.ativo("caderno", t0)                    # espera um instante
        app._talvez_rabiscar(t0 + vivo.RABISCO_ESPERA_S + 0.1)
        assert app.figurino.ativo("caderno", t0 + vivo.RABISCO_ESPERA_S + 0.2)
        rabiscou_em = app._ultimo_rabisco
        app.contar_no_diario("carinhos")
        app.contar_no_diario("cutucadas")
        app._talvez_rabiscar(rabiscou_em + 5)
        assert app._ultimo_rabisco == rabiscou_em                       # cedo demais: fica pendente
        app._talvez_rabiscar(rabiscou_em + vivo.RABISCO_INTERVALO_S + 0.1)
        assert app._ultimo_rabisco > rabiscou_em and app._rabisco_pendente is None
    finally:
        _fechar(app)


def test_ouvir_e_despedir(tmp_path):
    app = _app(tmp_path)
    try:
        app.abrir_conversa()
        app.balao.digitando.emit()
        agora = time.monotonic()
        assert abs(app.figurino.inclinacao(agora + 0.5)) > 1
        app.balao.encerrar()
        assert app.figurino.piscadinha(time.monotonic()) == 1
        assert app.palco.ativo("brilho", time.monotonic())
    finally:
        _fechar(app)


def test_obedecer_pula(tmp_path, monkeypatch):
    from pestinha.mind import obediencia
    app = _app(tmp_path)
    try:
        body = app.pet.body
        body.grounded, body.held, body.vy = True, False, 0.0
        monkeypatch.setattr(obediencia, "decidir", lambda *a, **k: (True, None))
        monkeypatch.setattr(app, "menu_place_ball", lambda: None)
        app.pedido_do_hermes("bolinha")
        assert body.vy < 0 and not body.grounded
    finally:
        _fechar(app)


def test_ler_diario_segura_o_caderno_aberto(tmp_path):
    app = _app(tmp_path)
    try:
        app.mostrar_diario("04/11/2026\nHoje fugi do castigo.")
        agora = time.monotonic()
        assert app.figurino.ativo("caderno", agora + 60) and app.figurino.caderno_modo == "aberto"
        app._caixa_diario.close()
        assert not app.figurino.ativo("caderno", time.monotonic() + 1)
    finally:
        _fechar(app)


def test_cliente_entrega_efeitos_antes_da_fala(tmp_path):
    from pestinha.sense import hermes
    c = hermes.ClienteHermes("http://127.0.0.1:9", "t", tmp_path / "u.txt")
    c._efeitos(["chuva", "", 3, "festa"])
    c._efeitos("nao-e-lista")
    assert c.coletar() == [("efeito", "chuva"), ("efeito", "festa")]


def test_cartaz_de_protesto_nao_tem_x():
    from pestinha.world.cartazes import SignThing
    c = SignThing("Abaixo o castigo!", "march", 1.0)
    c.place(300, 300)
    c.show()
    cliques, fechados = [], []
    c.clicked.connect(cliques.append)
    c.fechar.connect(fechados.append)
    canto = QPointF(c.width() - 10, 10).toPoint()                       # onde ficaria o ×
    QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, canto)
    assert cliques == [c] and fechados == [] and "×" not in c.toolTip()
    c.close()
