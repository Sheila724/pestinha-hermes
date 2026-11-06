"""
Uptime, o analista de suporte: Thunderbird, e-mail e navegador como trabalho, recadinhos por programa, rack e memes.

- Thunderbird reconhecido (categoria EMAIL);
- campo "trabalho" no pets/<pet>.json: navegador e e-mail contam como trabalho para aquele pet;
- recadinhos por programa (recadinhos_email.txt, recadinhos_navegador.txt) e o comentário ao abrir o programa;
- campo "computador": "rack" troca o notebook por um rack de servidores desenhado.
"""
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from pestinha import config  # noqa: E402
from pestinha.core.protesto import DEFAULT_SIGNS, load_signs  # noqa: E402
from pestinha.paths import Paths  # noqa: E402
from pestinha.sense import senses  # noqa: E402
from pestinha.settings_store import SettingsStore  # noqa: E402

PATHS = Paths(root=ROOT)
PERMS = dict(config.DEFAULT_PERMISSIONS, ativo=True, travessuras=True, bilhetes=True)


def qt():
    return QApplication.instance() or QApplication([])


# ---------------- programas ----------------

def test_thunderbird_e_email_em_qualquer_sistema():
    for nome in ("thunderbird.exe", "Thunderbird", "thunderbird", "betterbird.exe"):
        assert senses.detect_activity(nome, 0.0, 300.0) == "EMAIL"
    assert senses.detect_activity("chrome.exe", 0.0, 300.0) == "BROWSING"


def test_email_pode_vir_do_programas_json():
    senses.definir_programas({"EMAIL": ["MeuEmail.EXE"]})
    try:
        assert senses.detect_activity("meuemail.exe", 0.0, 300.0) == "EMAIL"
    finally:
        senses.definir_programas({})


def test_trabalho_do_pet_vira_canal_work():
    s = senses.ComputerSenses()
    for _ in range(40):
        s.last -= 0.5
        out = s.update("BROWSING", 0.0, {})
    assert out["WEB"] > 0.9 and out["WORK"] < 0.1           # padrão: navegador é curiosidade

    s = senses.ComputerSenses()
    s.trabalho = senses.ATIVIDADES_TRABALHO | {"BROWSING", "EMAIL"}
    for atividade in ("BROWSING", "EMAIL"):
        for _ in range(40):
            s.last -= 0.5
            out = s.update(atividade, 0.0, {})
        assert out["WORK"] > 0.9 and out["WEB"] < 0.1 and out["SOCIAL"] < 0.1


# ---------------- definição do pet ----------------

def test_uptime_carrega_trabalho_computador_e_aparencia():
    pet = config.load_pet(PATHS, "uptime")
    assert pet["nome"] == "Uptime"
    assert pet["trabalho"] == ["EMAIL", "BROWSING"]
    assert pet["computador"] == "rack"
    assert len(pet["temperamento"]) == 8 and pet["aparencia"]["olho"] == "#39e27a"


def test_campos_novos_com_tipo_errado_ficam_no_padrao(tmp_path):
    paths = Paths(root=tmp_path)
    paths.pets.mkdir()
    paths.definicao("x").write_text('{"trabalho": "EMAIL", "computador": "torradeira"}', encoding="utf-8")
    pet = config.load_pet(paths, "x")
    assert pet["trabalho"] == [] and pet["computador"] == "notebook"
    paths.definicao("x").write_text('{"trabalho": [" email ", ""]}', encoding="utf-8")
    assert config.load_pet(paths, "x")["trabalho"] == ["EMAIL"]


def test_bryan_e_jorge_continuam_iguais():
    for pet_id in ("bryan", "jorge"):
        pet = config.load_pet(PATHS, pet_id)
        assert pet["trabalho"] == [] and pet["computador"] == "notebook"


# ---------------- conteúdo ----------------

def test_uptime_tem_todas_as_secoes_e_recadinhos():
    c = PATHS.conteudo("uptime")
    with open(c.signs, encoding="utf-8") as f:
        secoes = set(re.findall(r"^\[(\w+)\]", f.read(), re.M))
    assert secoes == set(DEFAULT_SIGNS)
    assert all(load_signs(c.signs)[s] for s in DEFAULT_SIGNS)
    for arquivo in (c.notes, c.notes_sad, c.notes_atividade("EMAIL"), c.notes_atividade("BROWSING")):
        assert arquivo.parent == PATHS.pets / "uptime"
        assert config.Notes(arquivo).pick()
    assert c.notes_atividade("AWAY") is None and c.notes_atividade("IDLE") is None


def test_frases_do_uptime_cabem_num_post_it():
    c = PATHS.conteudo("uptime")
    for arquivo in (c.notes, c.notes_sad, c.notes_atividade("EMAIL"), c.notes_atividade("BROWSING")):
        notas = config.Notes(arquivo)
        notas.has_lines()
        longas = [linha for linha in notas.lines if len(linha) > 60]
        assert not longas, (arquivo.name, longas)


# ---------------- recadinhos por programa ----------------

def motor():
    qt()
    from pestinha.world.mischief import MischiefEngine
    return MischiefEngine(PATHS.conteudo("uptime"))


def test_recadinho_do_programa_aberto():
    engine = motor()
    email = set(engine.notas_de("EMAIL").lines)
    assert engine.notas_de("GAMING") is None              # o Uptime não tem recadinhos de jogo
    tipo, thing = engine.plan_contexto("EMAIL")
    assert tipo == "deliver" and thing.text in email
    thing.deleteLater()


def test_trabalhando_sem_meme_de_trabalho_ainda_cola_post_it_do_programa():
    engine = motor()
    assert engine.available("contente", PERMS, working=True, activity="EMAIL") == ["meme_trabalho", "bilhete", "nada"]
    assert engine.available("contente", PERMS, working=True, activity="PROGRAMMING") == ["meme_trabalho", "nada"]
    sem_meme = dict(PERMS, memes=False)
    assert engine.available("contente", sem_meme, working=True, activity="EMAIL") == ["bilhete", "nada"]
    assert engine.available("contente", sem_meme, working=True, activity="PROGRAMMING") == []
    assert engine.available("contente", dict(sem_meme, bilhetes=False), working=True, activity="EMAIL") == []


def test_post_it_comum_puxa_frases_do_programa(monkeypatch):
    import pestinha.world.mischief as mod
    engine = motor()
    monkeypatch.setattr(mod.random, "random", lambda: 0.0)          # sempre o do programa
    _tipo, thing = engine.plan("bilhete", "contente", activity="BROWSING")
    assert thing.text in set(engine.notas_de("BROWSING").lines)
    thing.deleteLater()
    monkeypatch.setattr(mod.random, "random", lambda: 0.99)         # sempre o comum
    _tipo, thing = engine.plan("bilhete", "contente", activity="BROWSING")
    assert thing.text in set(engine.notes.lines)
    thing.deleteLater()


def controlador():
    from pestinha.mind.mischief_ctl import MischiefController
    engine = motor()
    behavior = SimpleNamespace(mission=None, start_mission=Mock())
    memory = SimpleNamespace(context=lambda a, e: f"{a}|{e}", start=Mock())
    ctl = MischiefController(engine, memory, Mock(), Mock(), behavior, Mock(), lambda: False)
    return ctl, behavior, memory


CORPO = SimpleNamespace(held=False, grounded=True)
REGRAS = dict(emotion="contente", perms=PERMS, prof=config.PROFILES["normal"], fullscreen=False,
              asleep=False, protest_stage=0)


def test_abrir_o_email_traz_um_comentario_e_respeita_o_intervalo():
    ctl, behavior, memory = controlador()
    ctl.avisar_chegada(100.0, "EMAIL", 1200.0)
    assert ctl.comentar(101.0, (0, 0, 1920, 1080), (0, 0), CORPO, activity="EMAIL", **REGRAS) == "bilhete"
    behavior.start_mission.assert_called_once()
    assert memory.start.call_args[0][:2] == ("EMAIL|contente", "bilhete")
    behavior.start_mission.call_args[0][0][1].deleteLater()

    ctl.avisar_chegada(200.0, "EMAIL", 1200.0)                       # voltou logo: não repete
    assert ctl.comentario is None
    ctl.avisar_chegada(101.0 + 1200.0, "EMAIL", 1200.0)              # 20 min depois: pode
    assert ctl.comentario is not None


def test_comentario_nao_acontece_fora_de_hora():
    ctl, behavior, _ = controlador()
    ctl.avisar_chegada(0.0, "IDLE", 0.0)                             # sem recadinhos: nem marca
    assert ctl.comentario is None

    ctl.avisar_chegada(0.0, "EMAIL", 0.0)
    assert ctl.comentar(1.0, (0, 0, 1920, 1080), (0, 0), CORPO, activity="BROWSING", **REGRAS) is None
    assert ctl.comentario is None                                    # já saiu do e-mail

    for regra in ({"asleep": True}, {"protest_stage": 3}, {"emotion": "triste"},
                  {"perms": dict(PERMS, bilhetes=False)}):
        ctl.avisar_chegada(0.0, "EMAIL", 0.0)
        assert ctl.comentar(1.0, (0, 0, 1920, 1080), (0, 0), CORPO, activity="EMAIL",
                            **dict(REGRAS, **regra)) is None
    behavior.start_mission.assert_not_called()

    ctl.avisar_chegada(0.0, "EMAIL", 0.0)                            # ocupado: espera, não perde
    ocupado = SimpleNamespace(held=True, grounded=True)
    assert ctl.comentar(1.0, (0, 0, 1920, 1080), (0, 0), ocupado, activity="EMAIL", **REGRAS) is None
    assert ctl.comentario is not None
    ctl.avisar_chegada(0.0, "EMAIL", 0.0)
    assert ctl.comentar(60.0, (0, 0, 1920, 1080), (0, 0), CORPO, activity="EMAIL", **REGRAS) is None


# ---------------- rack ----------------

def test_rack_no_lugar_do_notebook(tmp_path):
    qt()
    from pestinha.world.notebook import RACK_H, RACK_W, Notebook
    app = SimpleNamespace(computador="rack", nome="Uptime", conteudo=PATHS.conteudo("bryan"),
                          paths=SimpleNamespace(panels=tmp_path / "panels.json"))
    rack = Notebook(app)
    assert rack.sprite is None                                      # ignora o notebook.png
    assert (rack.width(), rack.height()) == (RACK_W, RACK_H)
    assert rack.windowTitle() == "Rack do Uptime"
    rack.set_working(True)
    assert rack.pisca.isActive()
    assert not rack.grab().isNull()                                  # desenha sem erro
    rack.set_working(False)
    assert not rack.pisca.isActive()
    rack.close()


def test_app_inteiro_com_o_uptime(tmp_path, monkeypatch):
    import shutil
    paths = Paths(root=tmp_path)
    shutil.copytree(ROOT / "pets", paths.pets)
    shutil.copytree(ROOT / "assets", paths.assets)
    SettingsStore(paths).update(dict(config.DEFAULT_PERMISSIONS, pet="uptime"))
    qt()
    import pestinha.app as app_mod
    monkeypatch.setattr(app_mod, "PanicHotkey", lambda: SimpleNamespace(ok=True, pressed=Mock()))
    app = app_mod.PestinhaApp(SettingsStore(paths), paths)
    for timer in app.findChildren(app_mod.QTimer):
        timer.stop()
    assert app.nome == "Uptime" and app.mesa.caderno.rack
    assert app.atividades_trabalho == {"PROGRAMMING", "DESIGNING", "EMAIL", "BROWSING"}
    app.activity = "EMAIL"
    assert app.trabalhando()
    app.activity = "MUSIC"
    assert not app.trabalhando()
    app.mesa.fechar()


def test_abrir_o_thunderbird_faz_o_uptime_vir_comentar(tmp_path, monkeypatch):
    """Do sensor até o post-it: trocar para o Thunderbird marca o comentário e ele sai no quadro seguinte."""
    import shutil
    paths = Paths(root=tmp_path)
    shutil.copytree(ROOT / "pets", paths.pets)
    shutil.copytree(ROOT / "assets", paths.assets)
    SettingsStore(paths).update(dict(config.DEFAULT_PERMISSIONS, pet="uptime", ativo=True, travessuras=True,
                                     bilhetes=True))
    qt()
    import pestinha.app as app_mod
    monkeypatch.setattr(app_mod, "PanicHotkey", lambda: SimpleNamespace(ok=True, pressed=Mock()))
    app = app_mod.PestinhaApp(SettingsStore(paths), paths)
    for timer in app.findChildren(app_mod.QTimer):
        timer.stop()
    programa = {"nome": "explorer.exe"}
    monkeypatch.setattr(senses, "get_active_app", lambda: programa["nome"])
    monkeypatch.setattr(senses, "get_idle_seconds", lambda: 1.0)
    monkeypatch.setattr(senses, "is_fullscreen", lambda: False)
    monkeypatch.setattr(app, "_congelado", lambda: False)
    app.sense()
    programa["nome"] = "thunderbird.exe"
    app.sense()
    assert app.activity == "EMAIL" and app.mischief_ctl.comentario is not None
    app.pet.body.grounded, app.pet.body.held = True, False
    app.behavior.mission = None
    app.pet_state.emotion = "contente"
    import time
    app.maybe_mischief(time.monotonic(), 0.016, app.bounds(), (0, 0), app.brain.motor_activity())
    assert app.behavior.mission and app.behavior.mission[0] == "deliver"
    assert app.behavior.mission[1].text in set(app.mischief.notas_de("EMAIL").lines)
    app.mischief_ctl.clear()
    app.mesa.fechar()


# ---------------- memes ----------------

def test_uptime_tem_memes_para_cada_humor_e_para_o_trabalho():
    c = PATHS.conteudo("uptime")
    for emocao in ("feliz", "contente", "curioso", "bravo", "triste"):
        meme = config.meme_for(c.memes, emocao)
        assert meme is not None and meme.parent.name == emocao and "uptime" in meme.parts
    assert config.list_images(c.memes_trabalho)


# ---------------- arremessos e o painel de protesto ----------------

def app_para_arremessar(tmp_path, monkeypatch, pet="uptime"):
    import shutil
    paths = Paths(root=tmp_path)
    shutil.copytree(ROOT / "pets", paths.pets)
    shutil.copytree(ROOT / "assets", paths.assets)
    SettingsStore(paths).update(dict(config.DEFAULT_PERMISSIONS, pet=pet))
    qt()
    import pestinha.app as app_mod
    monkeypatch.setattr(app_mod, "PanicHotkey", lambda: SimpleNamespace(ok=True, pressed=Mock()))
    app = app_mod.PestinhaApp(SettingsStore(paths), paths)
    for timer in app.findChildren(app_mod.QTimer):
        timer.stop()
    monkeypatch.setattr(app, "_congelado", lambda: False)
    return app


def test_poucos_arremessos_sao_brincadeira_muitos_irritam(tmp_path, monkeypatch):
    """Antes, arremessar o pet não mexia no painel de protesto: o arremesso só alimentava a brincadeira."""
    import pestinha.controle.interacao as inter
    from pestinha import ajustes
    relogio = [1000.0]
    monkeypatch.setattr(inter.time, "monotonic", lambda: relogio[0])
    app = app_para_arremessar(tmp_path, monkeypatch)
    for _ in range(ajustes.ARREMESSOS_TOLERADOS):
        app.on_thrown(2000.0)
        relogio[0] += 3.0
    assert app.protest.grievance == 0.0 and app.senses.pulse["IMPACT"] == 0.0
    for _ in range(7):
        app.on_thrown(2000.0)
        relogio[0] += 3.0
    assert app.protest.grievance >= 7 * ajustes.INSATISFACAO_PROVOCACAO - 1e-9
    assert app.protest.grievance >= config.PROFILES["normal"]["stage_up"][0]     # dá para reclamar
    assert app.senses.pulse["IMPACT"] > 0.5                                       # a rede sente a irritação
    app.mesa.fechar()


def test_arremessos_espacados_continuam_brincadeira(tmp_path, monkeypatch):
    import pestinha.controle.interacao as inter
    from pestinha import ajustes
    relogio = [1000.0]
    monkeypatch.setattr(inter.time, "monotonic", lambda: relogio[0])
    app = app_para_arremessar(tmp_path, monkeypatch)
    for _ in range(10):
        app.on_thrown(2000.0)
        relogio[0] += ajustes.JANELA_ARREMESSOS / ajustes.ARREMESSOS_TOLERADOS + 1.0
    assert app.protest.grievance == 0.0
    app.mesa.fechar()


def test_dormindo_nao_acumula_insatisfacao(tmp_path, monkeypatch):
    app = app_para_arremessar(tmp_path, monkeypatch)
    import pestinha.app as app_mod
    monkeypatch.setattr(app_mod.PestinhaApp, "asleep", property(lambda self: True))
    app.provocar(0.5)
    assert app.protest.grievance == 0.0
    monkeypatch.setattr(app_mod.PestinhaApp, "asleep", property(lambda self: False))
    app.provocar(0.5)
    assert app.protest.grievance == 0.5
    app.mesa.fechar()
