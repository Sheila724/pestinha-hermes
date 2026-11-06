"""
Desenha os memes do Uptime em pets/uptime/memes/: cartões de status do suporte, um para cada situação.

Desenho feito por código (sem imagem de terceiros). Rode de novo para refazer os arquivos;
para mudar as frases, edite a lista CARTOES e rode outra vez.
"""
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter,  # noqa: E402
                           QPainterPath, QPen)

LARGURA, ALTURA = 480, 300
DESTINO = Path(__file__).resolve().parent.parent / "pets" / "uptime" / "memes"

STATUS = {               # rótulo, cor
    "ok": ("OK", "#39e27a"),
    "atencao": ("ATENÇÃO", "#ffb547"),
    "critico": ("CRÍTICO", "#ff5a5a"),
    "sem_dados": ("SEM DADOS", "#8b949e"),
}

# (pasta da emoção, arquivo, status, frase grande, frase pequena, forma do gráfico)
CARTOES = [
    ("feliz", "fila_zerada", "ok", "FILA ZERADA", "nenhum chamado aberto. por enquanto.", "calmo"),
    ("feliz", "chamado_fechado", "ok", "CHAMADO RESOLVIDO NO 1º CONTATO", "o cliente até agradeceu", "calmo"),
    ("feliz", "elogio", "ok", "CLIENTE MANDOU ELOGIO", "print e emoldura", "calmo"),
    ("contente", "reiniciou", "ok", "REINICIOU E FUNCIONOU", "como sempre", "volta"),
    ("curioso", "erro_novo", "atencao", "ERRO QUE NINGUÉM VIU AINDA", "investigando...", "pico"),
    ("bravo", "sem_print", "critico", "“NÃO FUNCIONA”. SEM PRINT.", "nem mensagem de erro", "pico"),
    ("bravo", "nao_mexi", "critico", "“NÃO MEXI EM NADA”", "mexeu.", "pico"),
    ("bravo", "urgente", "critico", "TUDO URGENTE ÀS 17H58 DE SEXTA", "todos os 12 chamados", "queda"),
    ("triste", "sem_retorno", "sem_dados", "CLIENTE SUMIU", "aguardando retorno há 3 dias", "queda"),
    ("triste", "bloqueado", "atencao", "USUÁRIO BLOQUEADO POR TENTATIVAS", "e eu também", "queda"),
    ("trabalhando", "fila", "atencao", "47 CHAMADOS NA FILA", "um café e a gente resolve", "serra"),
    ("trabalhando", "acesso_remoto", "atencao", "ACESSO REMOTO EM ANDAMENTO", "não mexe no mouse, por favor", "calmo"),
    ("trabalhando", "tutorial", "ok", "ESCREVENDO TUTORIAL", "passo a passo, com print", "serra"),
]


def serie(forma, rng, n=40):
    """Os pontos do gráfico (0..1): calmo, pico no fim, queda até zero, volta do zero, ou serra."""
    base = [0.35 + rng.uniform(-0.06, 0.06) for _ in range(n)]
    if forma == "pico":
        for i in range(n - 8, n):
            base[i] = min(0.95, 0.35 + (i - (n - 8)) * 0.09 + rng.uniform(0, 0.05))
    elif forma == "queda":
        for i in range(n // 2, n):
            base[i] = max(0.02, base[i] - (i - n // 2) * 0.05)
    elif forma == "volta":
        for i in range(n // 3):
            base[i] = 0.03
    elif forma == "serra":
        base = [0.3 + 0.25 * ((i % 8) / 8) + rng.uniform(-0.04, 0.04) for i in range(n)]
    return base


def fonte(tamanho, negrito=True):
    """Fonte sem serifa que exista em qualquer sistema."""
    f = QFont()
    f.setFamilies(["Segoe UI", "Arial", "DejaVu Sans", "Helvetica"])
    f.setPixelSize(tamanho)
    f.setBold(negrito)
    return f


def desenhar(status, grande, pequena, forma, semente):
    """Um cartão de status: título, selo colorido, frase, gráfico e LEDs."""
    rotulo, cor = STATUS[status]
    rng = random.Random(semente)
    img = QImage(LARGURA, ALTURA, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    cartao = QRectF(6, 6, LARGURA - 12, ALTURA - 12)
    fundo = QLinearGradient(cartao.topLeft(), cartao.bottomLeft())
    fundo.setColorAt(0.0, QColor("#1b2026"))
    fundo.setColorAt(1.0, QColor("#11151a"))
    p.setPen(QPen(QColor(cor), 3))
    p.setBrush(fundo)
    p.drawRoundedRect(cartao, 18, 18)

    # cabeçalho: "SUPORTE · fila" e o selo de status
    p.setPen(QColor("#8b949e"))
    p.setFont(fonte(17, negrito=False))
    p.drawText(QRectF(28, 22, 260, 28), Qt.AlignLeft | Qt.AlignVCenter, "SUPORTE · fila")
    p.setFont(fonte(16))
    largura_selo = p.fontMetrics().horizontalAdvance(rotulo) + 34
    selo = QRectF(LARGURA - 28 - largura_selo, 22, largura_selo, 28)
    fundo_selo = QColor(cor)
    fundo_selo.setAlpha(45)
    p.setPen(Qt.NoPen)
    p.setBrush(fundo_selo)
    p.drawRoundedRect(selo, 14, 14)
    p.setBrush(QColor(cor))
    p.drawEllipse(QRectF(selo.left() + 10, selo.center().y() - 4, 8, 8))
    p.setPen(QColor(cor))
    p.drawText(selo.adjusted(22, 0, -8, 0), Qt.AlignCenter, rotulo)

    # frase grande (diminui até caber em duas linhas) e a pequena
    area = QRectF(28, 62, LARGURA - 56, 92)
    tamanho = 40
    while tamanho > 20:
        p.setFont(fonte(tamanho))
        if p.fontMetrics().boundingRect(area.toRect(), Qt.TextWordWrap, grande).height() <= area.height():
            break
        tamanho -= 2
    p.setPen(QColor("#f2f5f7"))
    p.drawText(area, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, grande)
    p.setFont(fonte(19, negrito=False))
    p.setPen(QColor("#b7c0c9"))
    p.drawText(QRectF(28, 156, LARGURA - 56, 28), Qt.AlignLeft | Qt.AlignVCenter, pequena)

    # gráfico
    grafico = QRectF(28, 196, LARGURA - 56, 64)
    p.setPen(QPen(QColor("#2a3138"), 1))
    for k in range(4):
        y = grafico.top() + k * grafico.height() / 3
        p.drawLine(QPointF(grafico.left(), y), QPointF(grafico.right(), y))
    pontos = serie(forma, rng)
    caminho = QPainterPath()
    for i, v in enumerate(pontos):
        ponto = QPointF(grafico.left() + i * grafico.width() / (len(pontos) - 1),
                        grafico.bottom() - v * grafico.height())
        caminho.moveTo(ponto) if i == 0 else caminho.lineTo(ponto)
    area_graf = QPainterPath(caminho)
    area_graf.lineTo(grafico.bottomRight())
    area_graf.lineTo(grafico.bottomLeft())
    area_graf.closeSubpath()
    preenchimento = QLinearGradient(grafico.topLeft(), grafico.bottomLeft())
    c1, c2 = QColor(cor), QColor(cor)
    c1.setAlpha(90)
    c2.setAlpha(0)
    preenchimento.setColorAt(0.0, c1)
    preenchimento.setColorAt(1.0, c2)
    p.setPen(Qt.NoPen)
    p.setBrush(preenchimento)
    p.drawPath(area_graf)
    p.setPen(QPen(QColor(cor), 3))
    p.setBrush(Qt.NoBrush)
    p.drawPath(caminho)

    # luzinhas de status no rodapé
    for k in range(12):
        aceso = rng.random() < (0.8 if status == "ok" else 0.45)
        led = QColor(cor) if aceso else QColor("#26302a")
        p.setPen(Qt.NoPen)
        p.setBrush(led)
        p.drawEllipse(QRectF(30 + k * 16, ALTURA - 30, 7, 7))
    p.end()
    return img


def main():
    """Gera todos os cartões; devolve quantos arquivos escreveu."""
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    escritos = 0
    for semente, (emocao, nome, status, grande, pequena, forma) in enumerate(CARTOES):
        pasta = DESTINO / emocao
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"{nome}.png"
        if not desenhar(status, grande, pequena, forma, semente).save(str(destino)):
            raise SystemExit(f"não consegui gravar {destino}")
        escritos += 1
    print(f"{escritos} memes em {DESTINO}")
    return escritos


if __name__ == "__main__":
    main()
