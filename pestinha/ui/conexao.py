"""
CONEXÃO - janelinha do menu "Conectar ao Hermes...": endereço da ponte e token.

Testa antes de aceitar (a função de teste vem de fora, para a janela não saber de rede): com erro, a
mensagem aparece em vermelho e a janela continua aberta para corrigir.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QVBoxLayout)


class ConexaoHermesDialog(QDialog):
    """Pergunta endereço e token; `testar(url, token) -> (ok, mensagem)`; aceita só se ok. Lê em `.url`/`.token`."""

    def __init__(self, nome, url_atual, testar, normalizar):
        super().__init__(None)
        self.setWindowTitle(f"{nome}: conectar ao Hermes")
        self.setMinimumWidth(460)
        self._testar, self._normalizar = testar, normalizar
        self.url = self.token = ""
        explica = QLabel("Cole o endereço da ponte e o token que você recebeu.\n"
                         "Depois disso o pet conversa, avisa do tempo, lembra das coisas e escreve o diário.")
        explica.setWordWrap(True)
        self.campo_url = QLineEdit(url_atual)
        self.campo_url.setPlaceholderText("https://pestinha.seudominio.com.br")
        self.campo_token = QLineEdit()
        self.campo_token.setEchoMode(QLineEdit.Password)
        self.campo_token.setPlaceholderText("cole o token aqui")
        mostrar = QCheckBox("mostrar o token")
        mostrar.toggled.connect(lambda v: self.campo_token.setEchoMode(QLineEdit.Normal if v else QLineEdit.Password))
        self.erro = QLabel("")
        self.erro.setWordWrap(True)
        self.erro.setStyleSheet("color: #e05252;")
        form = QFormLayout()
        form.addRow("Endereço:", self.campo_url)
        form.addRow("Token:", self.campo_token)
        form.addRow("", mostrar)
        self.botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.botoes.button(QDialogButtonBox.Ok).setText("Conectar")
        self.botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        self.botoes.accepted.connect(self.conectar)
        self.botoes.rejected.connect(self.reject)
        caixa = QVBoxLayout(self)
        caixa.addWidget(explica)
        caixa.addLayout(form)
        caixa.addWidget(self.erro)
        caixa.addWidget(self.botoes)
        (self.campo_token if url_atual else self.campo_url).setFocus()

    def conectar(self):
        url, token = self._normalizar(self.campo_url.text(), self.campo_token.text())
        self.erro.setText("Testando…")
        self.botoes.setEnabled(False)
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        QGuiApplication.processEvents()
        try:
            ok, mensagem = self._testar(url, token)
        finally:
            QGuiApplication.restoreOverrideCursor()
            self.botoes.setEnabled(True)
        if not ok:
            self.erro.setText(mensagem)
            return
        self.url, self.token = url, token
        self.accept()
