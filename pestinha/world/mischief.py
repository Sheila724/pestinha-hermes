"""
MISCHIEF - memes, fotos e bilhetes que o pet espalha pela tela.

Regras fixas (não dependem do cérebro):
    - só com permissão, fora de tela cheia e abaixo do limite de objetos
    - um clique em qualquer lugar do objeto fecha ele (sempre)
    - nada nasce em cima do cursor
O cérebro só decide QUANDO e com que emoção; aqui se decide a FORMA.
"""

import math
import random
import time

from PySide6.QtCore import QObject, Signal

from .. import config
from .objetos import NOTE_SIZE_FALA, ImageThing, NoteThing
from ..ajustes import TAMANHO_MEME as MEME_MAX, TAMANHO_MEME_CANTO as CORNER_MAX

CORNER_MARGIN = 18
CHANCE_CONTEXTO = 0.6     # num post-it comum, chance de usar o recadinho do programa aberto (e-mail, navegador...)


class MischiefEngine(QObject):
    """Guarda os objetos na tela e decide a próxima travessura."""

    dismissed = Signal(object, float)     # (objeto, segundos que ficou na tela)

    def __init__(self, conteudo):
        """Guarda os objetos na tela (memes, bilhetes, fotos) e o conteúdo do pet para sorteá-los."""
        super().__init__()
        self.things = []
        self.paths = conteudo                                 # ConteudoPaths: só o conteúdo deste pet e o comum
        self.notes = config.Notes(conteudo.notes)
        self.notes_sad = config.Notes(conteudo.notes_sad)       # bilhetes de quando ele está triste
        self._notas_contexto = {}                               # atividade -> Notes (recadinhos_<nome>.txt)

    def notas_de(self, atividade):
        """Recadinhos próprios do programa aberto (e-mail, navegador...), ou None se não houver."""
        caminho = self.paths.notes_atividade(atividade)
        if caminho is None:
            return None
        notas = self._notas_contexto.get(atividade)
        if notas is None:
            notas = self._notas_contexto[atividade] = config.Notes(caminho)
        return notas if notas.has_lines() else None

    # ---------------- agenda ----------------

    def allowed(self, perms, prof, fullscreen):
        """Diz se uma travessura pode acontecer agora (permissões, tela cheia e limite de objetos)."""
        if not perms["ativo"] or not perms["travessuras"]:
            return False
        if fullscreen and not perms["tela_cheia"]:
            return False
        if not (perms["memes"] or perms["fotos"] or perms["bilhetes"]):
            return False
        return len(self.things) < prof["max_objects"]

    def available(self, emotion, perms, working=False, activity=None):
        """Ações que as regras permitem agora (a memória escolhe entre elas)."""
        if emotion == "dormindo":
            return []                                   # dormindo, nem pensar
        if emotion == "triste":                         # triste só cola bilhetes tristes
            return ["bilhete_triste", "nada"] if perms["bilhetes"] and self.notes_sad.has_lines() else []
        contexto = perms["bilhetes"] and self.notas_de(activity) is not None
        if working:                                     # trabalhando sem estar sentado: meme ou recadinho do programa
            trabalho = perms["memes"] and bool(config.list_images(self.paths.memes_trabalho))
            options = (["meme_trabalho"] if trabalho else []) + (["bilhete"] if contexto else [])
            return options + ["nada"] if options else []
        memes = perms["memes"] and config.meme_for(self.paths.memes, emotion) is not None
        notes = perms["bilhetes"] and bool(self.notes.lines or self.notes.pick() or contexto)
        if emotion == "bravo":
            options = ((["meme_canto", "meme"] if memes else []) + (["bilhete_canto"] if notes else []))
            return options + ["nada"] if options else []
        photos = perms["fotos"] and config.random_photo(self.paths.fotos) is not None
        options = (["meme"] if memes else []) + (["foto"] if photos else []) + (["bilhete"] if notes else [])
        return options + ["atravessar", "nada"] if options else []

    def plan(self, action, emotion, activity=None):
        """
        Transforma a ação escolhida em algo concreto:
            ("corner", thing)    coisinha de revolta num canto
            ("deliver", thing)   arrasta um meme/foto/bilhete pela tela
            ("cross", None)      atravessa a tela e não faz nada
            None                 nada
        """
        if action in ("meme_canto", "bilhete_canto"):
            thing = self._make(action.split("_")[0], emotion, small=True, activity=activity)
            return ("corner", thing) if thing else None
        if action in ("meme", "meme_trabalho", "foto", "bilhete", "bilhete_triste"):
            thing = self._make(action, emotion, small=False, activity=activity)
            return ("deliver", thing) if thing else None
        if action == "atravessar":
            return ("cross", None)
        return None

    def plan_contexto(self, activity):
        """Post-it do programa que você acabou de abrir (e-mail, navegador...): ("deliver", thing) ou None."""
        notas = self.notas_de(activity)
        text = notas.pick() if notas else None
        if not text:
            return None
        thing = NoteThing(text)
        thing.clicked.connect(self._on_click)
        return ("deliver", thing)

    def _make(self, kind, emotion, small, activity=None):
        """Monta o objeto da travessura: imagem, bilhete ou foto, conforme o tipo e a emoção."""
        if kind == "meme":
            path = config.meme_for(self.paths.memes, emotion)
            thing = ImageThing(path, CORNER_MAX if small else MEME_MAX) if path else None
        elif kind == "meme_trabalho":
            options = config.list_images(self.paths.memes_trabalho)
            thing = ImageThing(random.choice(options), MEME_MAX) if options else None
        elif kind == "foto":
            path = config.random_photo(self.paths.fotos)
            thing = ImageThing(path, MEME_MAX) if path else None
        else:
            if kind == "bilhete_triste":
                notes = self.notes_sad
            else:
                contexto = self.notas_de(activity) if not small else None     # o de revolta é sempre o comum
                usar = contexto is not None and (not self.notes.has_lines() or random.random() < CHANCE_CONTEXTO)
                notes = contexto if usar else self.notes
            text = notes.pick()
            thing = NoteThing(text, small=small) if text else None
        if thing is not None and not getattr(thing, "valida", True):
            thing.deleteLater()                      # imagem ilegível: nada de objeto invisível na tela
            return None
        if thing is not None:
            thing.clicked.connect(self._on_click)
        return thing

    # ---------------- colocação ----------------

    def show_in_corner(self, thing, bounds, cursor):
        """Põe o objeto num canto da tela (travessura 'de revolta')."""
        left, top, right, bottom = bounds
        hw, hh = thing.width() / 2, thing.height() / 2
        corners = [
            (left + hw + CORNER_MARGIN, top + hh + CORNER_MARGIN),
            (right - hw - CORNER_MARGIN, top + hh + CORNER_MARGIN),
            (left + hw + CORNER_MARGIN, bottom - hh - CORNER_MARGIN),
            (right - hw - CORNER_MARGIN, bottom - hh - CORNER_MARGIN),
        ]
        free = [
            c for c in corners
            if all(math.hypot(c[0] - t.x, c[1] - t.y) > 80 for t in self.things)
            and math.hypot(c[0] - cursor[0], c[1] - cursor[1]) > 250
        ]
        if not free:
            thing.deleteLater()
            return False
        thing.place(*random.choice(free))
        self._add(thing)
        return True

    def mostrar_fala(self, texto, x, y, bounds):
        """Post-it com uma fala (do Hermes) colado perto de (x, y), dentro da tela. Some ao clicar."""
        thing = NoteThing(texto, size=NOTE_SIZE_FALA if len(texto) > 60 else None)
        thing.clicked.connect(self._on_click)
        left, top, right, bottom = bounds
        hw, hh = thing.width() / 2, thing.height() / 2
        thing.place(min(max(x, left + hw), right - hw), min(max(y, top + hh), bottom - hh))
        thing.resting = True            # fica colado onde apareceu, como um post-it largado
        self._add(thing)
        return thing

    def attach(self, thing, x, y):
        """Você pegou o objeto: ele segue o mouse até você soltar."""
        thing.carried = True
        thing.resting = False
        thing.place(x, y)
        self._add(thing)

    def release(self, thing):
        """Você soltou o objeto: ele volta a cair."""
        thing.carried = False
        thing.vy = 0.0
        # post-it cola onde foi largado; meme e foto caem como objetos
        thing.resting = isinstance(thing, NoteThing)

    def follow(self, thing, anchor_x, anchor_y, dt):
        """Objeto arrastado segue o pet com atraso (mola), parecendo ter peso."""
        k = 1.0 - math.exp(-dt / 0.12)
        thing.place(thing.x + (anchor_x - thing.x) * k, thing.y + (anchor_y - thing.y) * k)

    def _add(self, thing):
        """Põe um objeto na lista e o mostra."""
        self.things.append(thing)
        thing.show()

    # ---------------- ciclo ----------------

    def tick(self, dt, floor):
        """Um passo de física: os objetos caem até o chão."""
        for thing in self.things:
            thing.fall(dt, floor)

    def set_visible(self, visible):
        """Mostra ou esconde todos os objetos de uma vez."""
        for thing in self.things:
            thing.setVisible(visible)

    def _on_click(self, thing):
        """Clicaram no objeto: ele some e o tempo até o clique é registrado."""
        elapsed = time.monotonic() - thing.born
        self._remove(thing)
        self.dismissed.emit(thing, elapsed)

    def _remove(self, thing):
        """Tira um objeto da tela e da lista."""
        if thing in self.things:
            self.things.remove(thing)
        thing.close()
        thing.deleteLater()

    def clear(self):
        """Tira todos os objetos da tela."""
        for thing in list(self.things):
            self._remove(thing)
