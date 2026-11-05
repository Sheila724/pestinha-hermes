"""
OBJETOS - os post-its, memes e fotos que o pet traz, como janelas na tela.

Só desenho e mouse. Quem decide criar, largar e remover fica em mischief.py.

Mouse:
  arrastar   leva o objeto para onde você quiser (ele fica onde você soltar)
  ×          botão no canto: fecha (sinal `fechar`)
  clique     um toque sem arrastar (sinal `clicked`): num post-it do Hermes, responde a ele
Os objetos podem chegar voando (`voar_de`) e balançam um pouco quando pousam.
"""

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ..body.animacao import balanco, bezier, com_volta, limitar
from ..body.pet import overlay_flags, set_no_activate
from ..ajustes import DISTANCIA_INICIO_ARRASTE as ARRASTE_PX, GRAVIDADE as GRAVITY

TAMANHO_X = 20                   # botão de fechar no canto
VOO_S = 0.65

NOTE_SIZE = (180, 150)
NOTE_SIZE_FALA = (250, 200)      # falas do Hermes: frases maiores que os recadinhos


class Thing(QWidget):
    """Objeto genérico na tela (post-it, meme ou foto): uma janela sem moldura que pode ser clicada, arrastada e cai."""
    clicked = Signal(object)
    fechar = Signal(object)
    COM_X = True               # cartazes de protesto não têm ×: o clique neles é a "repressão"

    def __init__(self, w, h):
        """Cria a janela do objeto com o tamanho `w` x `h`, transparente e sem foco."""
        super().__init__(None, overlay_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(w, h)
        self.setCursor(Qt.OpenHandCursor)
        if self.COM_X:
            self.setToolTip("arraste para mover · × para fechar")
        self.setMouseTracking(True)
        self.born = time.monotonic()
        self.x = self.y = 0.0     # centro
        self.vy = 0.0
        self.carried = False
        self.resting = True
        self.tilt = random.uniform(-6.0, 6.0)
        self.tilt_base = self.tilt
        self.pousou_em = None      # quando pousou (para o balancinho)
        self.voo = None            # (origem, controle, destino, início, giro inicial)
        self.arrastado = False     # você já o tirou do lugar: o pet não mexe mais nele
        self._aperto = None        # (pos global, deslocamento até o centro) no botão apertado
        self._arrastando = False
        self._no_x = False         # mouse em cima do ×
        self._apertou_x = False

    def showEvent(self, event):
        """Ao aparecer, o objeto não rouba o foco do programa que você está usando."""
        super().showEvent(event)
        set_no_activate(self)

    def place(self, x, y):
        """Põe o objeto com o centro em (x, y)."""
        self.x, self.y = x, y
        self.move(int(x - self.width() / 2), int(y - self.height() / 2))

    # ---------- mouse: arrastar, × e clique ----------

    def retangulo_x(self):
        if not self.COM_X:
            return QRectF()
        return QRectF(self.width() - TAMANHO_X - 3, 3, TAMANHO_X, TAMANHO_X)

    def mousePressEvent(self, event):
        """Botão apertado: no × prepara para fechar; no resto, pode virar arraste ou clique."""
        if event.button() != Qt.LeftButton:
            return
        if self.retangulo_x().contains(event.position()):
            self._apertou_x = True
            return
        pos = event.globalPosition()
        self._aperto = (pos, (self.x - pos.x(), self.y - pos.y()))
        self._arrastando = False

    def mouseMoveEvent(self, event):
        """Arrasta (se o botão está apertado) ou acende o × quando o mouse passa por cima."""
        no_x = self.retangulo_x().contains(event.position())
        if no_x != self._no_x:
            self._no_x = no_x
            self.setCursor(Qt.PointingHandCursor if no_x else Qt.OpenHandCursor)
            self.update()
        if self._aperto is None or self.carried:
            return
        pos = event.globalPosition()
        inicio, (dx, dy) = self._aperto
        if not self._arrastando and math.hypot(pos.x() - inicio.x(), pos.y() - inicio.y()) < ARRASTE_PX:
            return
        if not self._arrastando:
            self._arrastando = True
            self.voo = None
            self.setCursor(Qt.ClosedHandCursor)
        self.resting, self.vy, self.arrastado = True, 0.0, True
        self.place(pos.x() + dx, pos.y() + dy)

    def mouseReleaseEvent(self, event):
        """Soltou: no × fecha; se não arrastou, foi um clique."""
        if event.button() != Qt.LeftButton:
            return
        if self._apertou_x:
            self._apertou_x = False
            if self.retangulo_x().contains(event.position()):
                self.fechar.emit(self)
            return
        arrastou, self._aperto, self._arrastando = self._arrastando, None, False
        if arrastou:
            self.setCursor(Qt.OpenHandCursor)
            self.pousou_em = time.monotonic()                     # balancinho de quem foi largado
            self.update()
        else:
            self.clicked.emit(self)

    def leaveEvent(self, event):
        if self._no_x:
            self._no_x = False
            self.update()
        super().leaveEvent(event)

    def desenhar_x(self, p):
        """O botão de fechar no canto: discreto, acende quando o mouse passa por cima."""
        r = self.retangulo_x()
        p.save()
        p.resetTransform()
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.setBrush(QColor(230, 57, 70) if self._no_x else QColor(40, 40, 46, 150))
        p.drawEllipse(r)
        p.setPen(QPen(QColor(255, 255, 255), 2.2, Qt.SolidLine, Qt.RoundCap))
        m = 6.0
        p.drawLine(QPointF(r.left() + m, r.top() + m), QPointF(r.right() - m, r.bottom() - m))
        p.drawLine(QPointF(r.right() - m, r.top() + m), QPointF(r.left() + m, r.bottom() - m))
        p.restore()

    # ---------- voo e pouso ----------

    def voar_de(self, x0, y0, agora=None):
        """Sai de (x0, y0) e voa em arco até onde já foi posto, girando, e balança ao pousar."""
        agora = time.monotonic() if agora is None else agora
        destino = (self.x, self.y)
        controle = ((x0 + destino[0]) / 2, min(y0, destino[1]) - 120)
        self.voo = ((x0, y0), controle, destino, agora, random.choice((-1, 1)) * 200.0)
        self.place(x0, y0)

    def animar(self, agora):
        """Um quadro do voo e do balancinho do pouso."""
        if self.voo is not None:
            origem, controle, destino, inicio, giro = self.voo
            t = limitar((agora - inicio) / VOO_S)
            self.place(*bezier(origem, controle, destino, com_volta(t, 1.2)))
            self.tilt = self.tilt_base + giro * (1.0 - t) ** 2
            if t >= 1.0:
                self.voo = None
                self.pousou_em = agora
            self.update()
            return
        if self.pousou_em is not None:
            k = agora - self.pousou_em
            self.tilt = self.tilt_base + 9.0 * balanco(k, 2.2, 4.5)
            if k > 1.2:
                self.pousou_em, self.tilt = None, self.tilt_base
            self.update()

    def fall(self, dt, floor):
        """Física simples: o objeto cai até `floor` (o chão do pet), se não estiver sendo carregado."""
        if self.carried or self.resting:
            return
        self.vy += GRAVITY * dt
        y = self.y + self.vy * dt
        if y + self.height() / 2 >= floor:
            y = floor - self.height() / 2
            self.vy = -self.vy * 0.25 if self.vy > 300 else 0.0
            self.resting = self.vy == 0.0
        self.place(self.x, y)


class ImageThing(Thing):
    """Objeto com uma imagem (meme ou foto), reduzida para caber no tamanho máximo."""
    def __init__(self, path, max_side):
        """Carrega a imagem; se o arquivo estiver corrompido, `valida` fica falso e ele não aparece."""
        pix = QPixmap(str(path))
        self.valida = not pix.isNull()           # arquivo corrompido ou formato não suportado
        if pix.isNull():
            pix = QPixmap(10, 10)
            pix.fill(Qt.transparent)
        self.pix = pix.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pad = 16
        super().__init__(self.pix.width() + pad, self.pix.height() + pad)

    def paintEvent(self, _event):
        """Desenha a imagem suavizada."""
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self.tilt * 0.5)
        p.drawPixmap(-self.pix.width() // 2, -self.pix.height() // 2, self.pix)
        self.desenhar_x(p)
        p.end()


class NoteThing(Thing):
    """Post-it com uma frase, num papel amarelo."""
    def __init__(self, text, small=False, size=None):
        """Monta o post-it com o texto; `small` é o tamanho de canto (bilhete de revolta), `size` um tamanho próprio."""
        w, h = size or NOTE_SIZE
        if small:
            w, h = int(w * 0.75), int(h * 0.75)
        super().__init__(w + 20, h + 20)
        self.text = text
        self.small = small
        self.note_w, self.note_h = w, h

    def paintEvent(self, _event):
        """Desenha o papel e o texto do post-it."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self.tilt)
        rect = QRectF(-self.note_w / 2, -self.note_h / 2, self.note_w, self.note_h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawRect(rect.translated(3, 4))
        p.setBrush(QColor("#ffe97a"))
        p.drawRect(rect)
        p.setBrush(QColor("#f5d84f"))
        p.drawRect(QRectF(rect.left(), rect.top(), rect.width(), 14))
        p.setPen(QColor("#3a3320"))
        p.setFont(QFont("Segoe Print", 9 if self.small else 11))
        p.drawText(rect.adjusted(10, 18, -10, -8), Qt.AlignCenter | Qt.TextWordWrap, self.text)
        self.desenhar_x(p)
        p.end()
