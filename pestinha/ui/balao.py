"""
BALÃO - campo de conversa que aparece ao lado do pet, no estilo do post-it.

Abre com clique duplo no pet, com o atalho de teclado ou clicando num post-it do Hermes (aí ele mostra
o post-it que você está respondendo). Enter envia; × ou Esc encerram a conversa (o pet se despede).
Se você clicar fora sem escrever nada, ele só fecha.
"""

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QToolButton, QVBoxLayout, QWidget

LARGURA = 280
MAX_TEXTO = 500
CITACAO_MAX = 70


def citar(texto, limite=CITACAO_MAX):
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


class BalaoDeConversa(QWidget):
    """Janelinha sem moldura com um campo de texto; emite `enviado(texto, respondendo)`."""
    enviado = Signal(str, str)
    fechado = Signal()            # você encerrou a conversa (× ou Esc)
    digitando = Signal()          # cada tecla: o pet presta atenção

    def __init__(self, nome):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(LARGURA)
        self.respondendo = ""
        self.citacao = QLabel(self)
        self.citacao.setWordWrap(True)
        self.citacao.setStyleSheet("color: #6b5a12; font-style: italic; font-size: 11px;")
        self.campo = QLineEdit(self)
        self.campo.setMaxLength(MAX_TEXTO)
        self.campo.setPlaceholderText(f"Fala com o {nome}… (Enter envia, Esc fecha)")
        self.campo.setStyleSheet("QLineEdit { background: #fffbe6; border: 1px solid #d9b93c;"
                                 " border-radius: 6px; padding: 6px; font-size: 13px; color: #3a3000; }")
        self.campo.returnPressed.connect(self._enviar)
        self.campo.textEdited.connect(lambda _t: self.digitando.emit())
        self.campo.installEventFilter(self)
        self.botao_fechar = QToolButton(self)
        self.botao_fechar.setText("×")
        self.botao_fechar.setToolTip("encerrar a conversa")
        self.botao_fechar.setCursor(Qt.PointingHandCursor)
        self.botao_fechar.setStyleSheet(
            "QToolButton { border: none; color: #6b5a12; font-size: 18px; font-weight: bold; padding: 0 4px; }"
            "QToolButton:hover { color: #e63946; }")
        self.botao_fechar.clicked.connect(self.encerrar)
        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.addWidget(self.citacao, 1)
        topo.addWidget(self.botao_fechar, 0, Qt.AlignTop | Qt.AlignRight)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 8, 12)
        layout.setSpacing(4)
        layout.addLayout(topo)
        layout.addWidget(self.campo)

    # ---------- o que o app usa ----------

    def abrir(self, x, y, bounds, respondendo=""):
        """Mostra o balão com o canto de baixo perto de (x, y), dentro da tela, e já com o cursor no campo."""
        self.respondendo = str(respondendo or "").strip()
        self.citacao.setText(f"Respondendo: “{citar(self.respondendo)}”" if self.respondendo else "")
        self.citacao.setVisible(True)                   # sem citação fica vazio, só para o × ter o seu canto
        self.campo.clear()
        self.adjustSize()
        left, top, right, bottom = bounds
        nx = min(max(int(x - self.width() / 2), left + 4), right - self.width() - 4)
        ny = min(max(int(y - self.height()), top + 4), bottom - self.height() - 4)
        self.move(nx, ny)
        self.show()
        self.raise_()
        self.activateWindow()
        self.campo.setFocus(Qt.OtherFocusReason)

    def encerrar(self):
        """× ou Esc: fecha e avisa que você não quer continuar a conversa agora."""
        self.hide()
        self.fechado.emit()

    # ---------- por dentro ----------

    def _enviar(self):
        texto = self.campo.text().strip()
        if texto:
            self.enviado.emit(texto, self.respondendo)
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.encerrar()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if obj is self.campo and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.encerrar()
            return True
        if obj is self.campo and event.type() == QEvent.FocusOut and not self.campo.text().strip():
            QTimer.singleShot(150, self._fechar_se_vazio)
        return super().eventFilter(obj, event)

    def _fechar_se_vazio(self):
        if not self.campo.hasFocus() and not self.campo.text().strip():
            self.hide()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor("#d9b93c"))
        p.setBrush(QColor("#ffe680"))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 10, 10)
        p.end()
