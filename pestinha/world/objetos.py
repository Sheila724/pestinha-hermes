"""
OBJETOS - os post-its, memes e fotos que o pet traz, como janelas na tela.

Só desenho e mouse. Quem decide criar, largar e remover fica em mischief.py.

Mouse (como uma janela do navegador):
  barra de cima   arrastar leva o objeto para onde você quiser (ele fica onde você soltar)
  ×               botão no canto da barra: fecha numa boa (sinal `fechar`)
  clique          no corpo do objeto (sinal `clicked`): numa travessura, fecha e ele fica bravo
  clique duplo    (sinal `responder`, se `aceita_duplo`): abre a conversa respondendo ao objeto
Com `aceita_duplo`, o clique simples espera o tempo de um clique duplo antes de valer.
Os objetos podem chegar voando (`voar_de`) e balançam um pouco quando pousam.
"""

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from ..body.animacao import balanco, bezier, com_volta, limitar
from ..body.pet import overlay_flags, set_no_activate
from ..ajustes import DISTANCIA_INICIO_ARRASTE as ARRASTE_PX, GRAVIDADE as GRAVITY

TAMANHO_X = 20                   # botão de fechar no canto
BARRA_PX = 30                    # faixa de cima por onde se arrasta (como a barra de uma janela)
FAIXA_PX = 18                    # a faixa amarela mais escura do post-it, que mostra onde fica a barra
VOO_S = 0.65

NOTE_SIZE = (180, 150)
NOTE_SIZE_FALA = (250, 200)      # falas do Hermes: frases maiores que os recadinhos


class Thing(QWidget):
    """Objeto genérico na tela (post-it, meme ou foto): uma janela sem moldura que pode ser clicada, arrastada e cai."""
    clicked = Signal(object)
    fechar = Signal(object)
    responder = Signal(object)
    COM_X = True               # cartazes de protesto não têm × nem barra: o clique neles é a "repressão"
    COM_BARRA = True

    def __init__(self, w, h):
        """Cria a janela do objeto com o tamanho `w` x `h`, transparente e sem foco."""
        super().__init__(None, overlay_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(w, h)
        if self.COM_X:
            self.setToolTip("clique fecha · × fecha numa boa · arraste pela barra de cima")
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
        self._aperto = None        # (pos global, deslocamento até o centro, apertou na barra)
        self._arrastando = False
        self._desistiu = False     # apertou no corpo e arrastou: não vale como clique
        self._no_x = False         # mouse em cima do ×
        self._na_barra = False     # mouse em cima da barra
        self._apertou_x = False
        self._duplo = False        # o soltar que vem depois do clique duplo não conta
        self.aceita_duplo = False  # quem cria liga, quando o clique duplo responde
        self._clique = QTimer(self)
        self._clique.setSingleShot(True)
        self._clique.setInterval(QApplication.doubleClickInterval())
        self._clique.timeout.connect(self._clique_confirmado)

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

    def retangulo_barra(self):
        return QRectF(0, 0, self.width(), BARRA_PX) if self.COM_BARRA else QRectF()

    def _onde(self, pos):
        """"x", "barra" ou "corpo"."""
        if self.retangulo_x().contains(pos):
            return "x"
        return "barra" if self.retangulo_barra().contains(pos) else "corpo"

    def mousePressEvent(self, event):
        """Botão apertado: no × prepara para fechar; na barra pode virar arraste; no corpo, clique."""
        if event.button() != Qt.LeftButton:
            return
        onde = self._onde(event.position())
        if onde == "x":
            self._apertou_x = True
            return
        pos = event.globalPosition()
        self._aperto = (pos, (self.x - pos.x(), self.y - pos.y()), onde == "barra")
        self._arrastando = self._desistiu = False

    def mouseDoubleClickEvent(self, event):
        """Clique duplo: responde (se quem criou aceita); senão vale como mais um clique."""
        if event.button() != Qt.LeftButton:
            return
        if not self.aceita_duplo or self._onde(event.position()) == "x":
            self.mousePressEvent(event)
            return
        self._clique.stop()
        self._duplo = True
        self._aperto = None
        self.responder.emit(self)

    def mouseMoveEvent(self, event):
        """Arrasta pela barra (com o botão apertado) e acende o × e a barra quando o mouse passa por cima."""
        onde = self._onde(event.position())
        no_x, na_barra = onde == "x", onde == "barra"
        if (no_x, na_barra) != (self._no_x, self._na_barra):
            self._no_x, self._na_barra = no_x, na_barra
            if not self._arrastando:
                self.setCursor(Qt.PointingHandCursor if no_x else Qt.OpenHandCursor if na_barra
                               else Qt.ArrowCursor)
            self.update()
        if self._aperto is None:
            return
        pos = event.globalPosition()
        inicio, (dx, dy), pela_barra = self._aperto
        longe = math.hypot(pos.x() - inicio.x(), pos.y() - inicio.y()) >= ARRASTE_PX
        if not pela_barra or self.carried:
            self._desistiu = self._desistiu or longe          # escorregou o mouse no corpo: não fecha
            return
        if not self._arrastando and not longe:
            return
        if not self._arrastando:
            self._arrastando = True
            self.voo = None
            self.setCursor(Qt.ClosedHandCursor)
        self.resting, self.vy, self.arrastado = True, 0.0, True
        self.place(pos.x() + dx, pos.y() + dy)

    def mouseReleaseEvent(self, event):
        """Soltou: no × fecha; arrastando, larga; no corpo, é clique (esperando um possível clique duplo)."""
        if event.button() != Qt.LeftButton:
            return
        if self._apertou_x:
            self._apertou_x = False
            if self.retangulo_x().contains(event.position()):
                self.fechar.emit(self)
            return
        if self._duplo:
            self._duplo = False
            return
        aperto, arrastou, desistiu = self._aperto, self._arrastando, self._desistiu
        self._aperto, self._arrastando, self._desistiu = None, False, False
        if arrastou:
            self.setCursor(Qt.OpenHandCursor)
            self.pousou_em = time.monotonic()                     # balancinho de quem foi largado
            self.update()
        elif aperto is None or aperto[2] or desistiu:
            return                                                # na barra sem arrastar: nada (como numa janela)
        elif self.aceita_duplo:
            self._clique.start()
        else:
            self.clicked.emit(self)

    def _clique_confirmado(self):
        if self.isVisible():
            self.clicked.emit(self)

    def leaveEvent(self, event):
        if self._no_x or self._na_barra:
            self._no_x = self._na_barra = False
            self.update()
        super().leaveEvent(event)

    def desenhar_pegador(self, p, centro_x, centro_y, cor):
        """Três risquinhos no meio da barra: o "pegador" de arrastar."""
        p.setPen(QPen(cor, 1.6, Qt.SolidLine, Qt.RoundCap))
        for k in (-4, 0, 4):
            p.drawLine(QPointF(centro_x - 9, centro_y + k), QPointF(centro_x + 9, centro_y + k))

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
        p.resetTransform()
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 32, 40, 190 if self._na_barra else 120))
        p.drawRoundedRect(QRectF(4, 2, self.width() - 8, BARRA_PX - 6), 7, 7)
        self.desenhar_pegador(p, self.width() / 2, 2 + (BARRA_PX - 6) / 2, QColor(255, 255, 255, 200))
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
        p.setBrush(QColor("#ecc93a") if self._na_barra else QColor("#f5d84f"))
        p.drawRect(QRectF(rect.left(), rect.top(), rect.width(), FAIXA_PX))
        self.desenhar_pegador(p, 0, rect.top() + FAIXA_PX / 2, QColor(120, 95, 20, 170))
        p.setPen(QColor("#3a3320"))
        p.setFont(QFont("Segoe Print", 9 if self.small else 11))
        p.drawText(rect.adjusted(10, FAIXA_PX + 4, -10, -8), Qt.AlignCenter | Qt.TextWordWrap, self.text)
        self.desenhar_x(p)
        p.end()
