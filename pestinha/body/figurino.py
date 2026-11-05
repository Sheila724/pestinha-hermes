"""
FIGURINO - o que o pet veste ou segura, e pequenas poses: tudo com entrada e saída animadas.

Peças (desenhadas no próprio corpo, acompanham cada pulo e giro):
  oculos_sol   descem do alto e quicam no rosto; um brilho passa pela lente de vez em quando
  cachecol     enrola da esquerda para a direita; a ponta balança ao vento
  chapeu       chapéu de festa que pula de trás da cabeça; o pompom balança
  caderno      sobe com molinha, abre, a caneta rabisca linha por linha, fecha e cai
               ("rabiscar": uma anotação rápida; "aberto": fica aberto enquanto você lê o diário)

Poses (mudam os olhos e a cabeça por um instante):
  ouvir        olha para o balão de conversa e inclina a cabeça, curioso
  revirar      revira os olhos (quando recusa um pedido)
  piscar       piscadinha de um olho só (tchau)
  e, com o caderno, olha para baixo, para a página

Puro de estado (os horários vêm de fora); o desenho usa só o QPainter que o corpo já abriu.
"""

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen, QPolygonF

from .animacao import acelerar, balanco, com_volta, elastico, lerp, limitar, progresso, quique, suave
from .desenho_rosto import BODY_H, BODY_W

ENTRADA_S = 0.55
SAIDA_S = 0.4
RABISCO_S = 3.4                 # uma anotação no caderninho
REVIRAR_S = 0.9
PISCAR_S = 0.7
OUVIR_FOLGA_S = 1.6             # continua prestando atenção um pouco depois que você para de digitar
PECAS = ("cachecol", "caderno", "oculos_sol", "chapeu")     # ordem de desenho (de trás para a frente)


@dataclass
class Peca:
    inicio: float
    fim: float | None = None    # quando começa a sair (None: até alguém tirar)

    def entrada(self, agora):
        return progresso(agora, self.inicio, ENTRADA_S)

    def saida(self, agora):
        return 0.0 if self.fim is None or agora < self.fim else progresso(agora, self.fim, SAIDA_S)

    def acabou(self, agora):
        return self.fim is not None and agora >= self.fim + SAIDA_S


class Figurino:
    def __init__(self):
        self.pecas = {}
        self.caderno_modo = "rabiscar"
        self.ouvindo_ate = 0.0
        self.ouvindo_desde = 0.0
        self.ouvindo_alvo = (0.0, -0.8)
        self.revirar_desde = -100.0
        self.piscar_ate = 0.0

    # ---------- vestir e tirar ----------

    def vestir(self, nome, agora, duracao=None):
        """Veste a peça por `duracao` segundos (None: até tirar). Se já está vestida, só estende o tempo."""
        peca = self.pecas.get(nome)
        fim = None if duracao is None else agora + duracao
        if peca and not peca.acabou(agora) and peca.saida(agora) == 0.0:
            peca.fim = fim
        else:
            self.pecas[nome] = Peca(agora, fim)

    def tirar(self, nome, agora):
        peca = self.pecas.get(nome)
        if peca and (peca.fim is None or peca.fim > agora):
            peca.fim = agora

    def ativo(self, nome, agora):
        peca = self.pecas.get(nome)
        return peca is not None and not peca.acabou(agora)

    def rabiscar(self, agora):
        """Tira o caderninho, rabisca uma anotação e guarda (não interrompe uma leitura do diário)."""
        if self.ativo("caderno", agora) and self.caderno_modo == "aberto":
            return
        self.caderno_modo = "rabiscar"
        self.pecas["caderno"] = Peca(agora, agora + RABISCO_S)

    def abrir_caderno(self, agora):
        """Segura o caderno aberto (enquanto você lê o diário) até `tirar('caderno')`."""
        self.caderno_modo = "aberto"
        self.vestir("caderno", agora)

    def limpar(self, agora):
        for nome in [n for n, p in self.pecas.items() if p.acabou(agora)]:
            del self.pecas[nome]

    def algo_animando(self, agora):
        return (bool(self.pecas) or agora < self.ouvindo_ate or agora < self.piscar_ate
                or agora - self.revirar_desde < REVIRAR_S)

    # ---------- poses ----------

    def ouvir(self, agora, alvo=(0.0, -0.8)):
        """Você está digitando: ele olha para o balão (`alvo` é a direção do olhar) e inclina a cabeça."""
        if agora >= self.ouvindo_ate:
            self.ouvindo_desde = agora
        self.ouvindo_ate = agora + OUVIR_FOLGA_S
        self.ouvindo_alvo = alvo

    def revirar_olhos(self, agora):
        self.revirar_desde = agora

    def piscar(self, agora):
        self.piscar_ate = agora + PISCAR_S

    def olhar(self, agora, base):
        """Para onde os olhos apontam agora: a pose manda; sem pose, vale o olhar de sempre (`base`)."""
        t = agora - self.revirar_desde
        if 0.0 <= t < REVIRAR_S:
            volta = suave(t / REVIRAR_S) * 2.0 * math.pi
            return (0.95 * math.sin(volta), -0.95 * math.cos(volta))
        if self.ativo("caderno", agora):
            return (0.15 * math.sin(agora * 7.0), 0.95)       # lendo o que escreve, acompanhando a caneta
        if agora < self.ouvindo_ate:
            k = suave(progresso(agora, self.ouvindo_desde, 0.3)) * suave((self.ouvindo_ate - agora) / 0.3)
            return (lerp(base[0], self.ouvindo_alvo[0], k), lerp(base[1], self.ouvindo_alvo[1], k))
        return base

    def inclinacao(self, agora):
        """Graus a mais na cabeça: inclina curioso enquanto ouve."""
        if agora < self.ouvindo_ate:
            k = suave(progresso(agora, self.ouvindo_desde, 0.35)) * suave((self.ouvindo_ate - agora) / 0.35)
            return k * (10.0 + 3.0 * math.sin(agora * 2.4))
        return 0.0

    def piscadinha(self, agora):
        """Qual olho está fechado na piscadinha (1 = o direito) ou None."""
        return 1 if agora < self.piscar_ate else None


# ======================= desenho (origem no centro do corpo) =======================

def desenhar(p, fig, agora):
    """Desenha as peças vestidas, cada uma no seu momento da animação."""
    for nome in PECAS:
        peca = fig.pecas.get(nome)
        if peca is None or peca.acabou(agora):
            continue
        p.save()
        DESENHOS[nome](p, peca, agora, fig)
        p.restore()


def _oculos_sol(p, peca, agora, _fig):
    entra, sai = peca.entrada(agora), peca.saida(agora)
    y = lerp(-120.0, 0.0, quique(entra)) - 90.0 * acelerar(sai)
    p.setOpacity(1.0 - sai)
    p.translate(0, y)
    lentes = [QRectF(side * 24 - 22, -27, 44, 52) for side in (-1, 1)]
    for lente in lentes:
        p.setPen(QPen(QColor("#0b0b0b"), 3))
        p.setBrush(QColor(12, 12, 14, 240))
        p.drawRoundedRect(lente, 10, 16)
        # brilho que passa pela lente de vez em quando
        fase = (agora * 0.45) % 1.0
        if fase < 0.35 and entra >= 1.0:
            x = lerp(lente.left() - 14, lente.right() + 14, fase / 0.35)
            caminho = QPainterPath()
            caminho.addRoundedRect(lente, 10, 16)
            p.save()
            p.setClipPath(caminho)
            p.setPen(QPen(QColor(255, 255, 255, 170), 6))
            p.drawLine(QPointF(x, lente.top() - 4), QPointF(x - 16, lente.bottom() + 4))
            p.restore()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawEllipse(QPointF(lente.left() + 10, lente.top() + 8), 4, 3)
    p.setPen(QPen(QColor("#0b0b0b"), 4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(-3, -16), QPointF(3, -16))
    for side in (-1, 1):                                   # hastes indo para as "orelhas"
        p.drawLine(QPointF(side * 46, -18), QPointF(side * 55, -22))


def _cachecol(p, peca, agora, _fig):
    entra, sai = peca.entrada(agora), peca.saida(agora)
    vermelho, listra = QColor("#d8423f"), QColor("#f6e3c8")
    p.setOpacity(1.0 - sai)
    p.translate(0, 40.0 * acelerar(sai))
    largura = BODY_W + 10
    revela = com_volta(entra)                              # enrola da esquerda para a direita
    p.save()
    p.setClipRect(QRectF(-largura / 2 - 6, -BODY_H, (largura + 12) * max(0.02, revela), BODY_H * 3))
    faixa = QRectF(-largura / 2, BODY_H / 2 - 20, largura, 17)
    p.setPen(QPen(vermelho.darker(150), 2))
    p.setBrush(vermelho)
    p.drawRoundedRect(faixa, 8, 8)
    p.setPen(QPen(listra, 3))
    for x in range(-50, 56, 16):
        p.drawLine(QPointF(x, faixa.top() + 3), QPointF(x + 5, faixa.bottom() - 3))
    p.restore()
    if entra < 0.6:
        return
    # a ponta pendurada, balançando ao vento
    vento = 0.6 + 0.4 * math.sin(agora * 1.3)
    pontos_esq, pontos_dir = [], []
    for i in range(7):
        k = i / 6.0
        x = 34 + 7.0 * k + vento * 6.0 * math.sin(agora * 5.0 - k * 3.0) * k
        y = BODY_H / 2 - 8 + 40.0 * k
        pontos_esq.append(QPointF(x - 7, y))
        pontos_dir.append(QPointF(x + 7, y))
    ponta = QPolygonF(pontos_esq + list(reversed(pontos_dir)))
    p.setPen(QPen(vermelho.darker(150), 2))
    p.setBrush(vermelho)
    p.drawPolygon(ponta)
    p.setPen(QPen(listra, 3))
    for i in (2, 4):
        p.drawLine(pontos_esq[i], pontos_dir[i])
    p.setPen(QPen(vermelho.darker(130), 2, Qt.SolidLine, Qt.RoundCap))
    fim = pontos_esq[-1]
    for j in range(5):                                     # franjinha
        x = fim.x() + 2 + j * 3
        p.drawLine(QPointF(x, fim.y()), QPointF(x + math.sin(agora * 6 + j) * 1.5, fim.y() + 7))


def _chapeu(p, peca, agora, _fig):
    entra, sai = peca.entrada(agora), peca.saida(agora)
    p.setOpacity(1.0 - sai)
    sobe = lerp(34.0, 0.0, elastico(entra)) - 80.0 * acelerar(sai)
    p.translate(-20, -BODY_H / 2 + 2 + sobe)
    p.rotate(-16 + 6.0 * balanco(agora - peca.inicio, 1.6, 1.6) - 60.0 * acelerar(sai))
    cone = QPolygonF([QPointF(-17, 0), QPointF(17, 0), QPointF(0, -42)])
    p.setPen(QPen(QColor("#5b2d8c"), 2))
    p.setBrush(QColor("#8e4fd1"))
    p.drawPolygon(cone)
    p.save()
    caminho = QPainterPath()
    caminho.addPolygon(cone)
    p.setClipPath(caminho)
    p.setPen(QPen(QColor("#ffd23f"), 4))
    for y in (-8, -20, -32):
        p.drawLine(QPointF(-20, y + 6), QPointF(20, y - 6))
    p.restore()
    p.setPen(QPen(QColor("#5b2d8c"), 2))
    p.setBrush(QColor("#ff6fa8"))
    pom = 1.0 + 0.25 * balanco(agora - peca.inicio, 3.0, 2.0)
    p.drawEllipse(QPointF(0, -44), 6 * pom, 6 * pom)
    p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
    p.drawLine(QPointF(-14, 0), QPointF(14, 0))


def _caderno(p, peca, agora, fig):
    t = agora - peca.inicio
    sai = peca.saida(agora)
    sobe = com_volta(progresso(agora, peca.inicio, 0.35))
    abre = com_volta(progresso(agora, peca.inicio + 0.25, 0.3)) * (1.0 - suave(limitar(sai * 2.0)))
    cai = acelerar(limitar(sai * 2.0 - 1.0))
    p.setOpacity(1.0 - cai)
    p.translate(0, BODY_H / 2 - 4 + lerp(60.0, 0.0, sobe) + 70.0 * cai)
    p.rotate(-4 + 3.0 * math.sin(agora * 1.7) * (1.0 - cai))
    alto = 42.0
    largura = lerp(30.0, 72.0, limitar(abre))
    capa = QColor("#2f8f83")
    # capa de trás (aparece aberta) e páginas
    p.setPen(QPen(capa.darker(140), 2))
    p.setBrush(capa)
    p.drawRoundedRect(QRectF(-largura / 2 - 3, -alto / 2 - 3, largura + 6, alto + 6), 4, 4)
    if abre > 0.15:
        pagina = QRectF(-largura / 2, -alto / 2, largura, alto)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#fff8e3"))
        p.drawRect(pagina)
        p.setPen(QPen(QColor(120, 160, 210, 110), 1))
        for y in range(-12, 20, 8):                        # pautas
            p.drawLine(QPointF(pagina.left() + 3, y), QPointF(pagina.right() - 3, y))
        p.setPen(QPen(QColor("#c9b88f"), 1.5))
        p.drawLine(QPointF(0, pagina.top()), QPointF(0, pagina.bottom()))           # lombada
        caneta = _rabiscos(p, pagina, t, agora, fig.caderno_modo)
        if caneta is not None and abre > 0.8:
            _lapis(p, caneta, agora, escrevendo=fig.caderno_modo == "rabiscar")
    else:                                                  # fechado: só a capa com o elástico
        p.setPen(QPen(QColor("#f2c14e"), 3))
        p.drawLine(QPointF(largura / 2 - 6, -alto / 2), QPointF(largura / 2 - 6, alto / 2))


def _rabiscos(p, pagina, t, agora, modo):
    """Linhas de rabisco aparecendo na página da direita; devolve onde está a ponta da caneta."""
    esquerda, direita = 4.0, pagina.right() - 5.0
    linhas = [-10.0, -2.0, 6.0, 14.0]
    p.setPen(QPen(QColor("#2b3a67"), 1.6, Qt.SolidLine, Qt.RoundCap))
    if modo == "aberto":
        for i, y in enumerate(linhas[:3]):
            _linha_rabisco(p, esquerda, direita - 6 * i, y, 1.0, i)
        return QPointF(direita - 10, linhas[2] + 1.5 * math.sin(agora * 3.0))
    escrita = (t - 0.6) / 0.62                           # quantas linhas já foram escritas
    if escrita <= 0:
        return QPointF(esquerda, linhas[0])
    ponta = None
    for i, y in enumerate(linhas):
        fracao = limitar(escrita - i)
        if fracao <= 0:
            break
        ponta = _linha_rabisco(p, esquerda, direita - (8 if i == 3 else 0), y, fracao, i)
    return ponta


def _linha_rabisco(p, x0, x1, y, fracao, semente):
    caminho = QPainterPath(QPointF(x0, y))
    passos = max(2, int(14 * fracao))
    x = x0
    for j in range(1, passos + 1):
        x = x0 + (x1 - x0) * fracao * j / passos
        caminho.lineTo(QPointF(x, y + 2.2 * math.sin(j * 1.9 + semente)))
    p.drawPath(caminho)
    return QPointF(x, y + 2.2 * math.sin(passos * 1.9 + semente))


def _lapis(p, ponta, agora, escrevendo):
    p.save()
    tremidinha = 1.6 * math.sin(agora * 32.0) if escrevendo else 0.0
    p.translate(ponta.x(), ponta.y() + tremidinha)
    p.rotate(-38)
    p.setPen(QPen(QColor("#7a5a12"), 1))
    p.setBrush(QColor("#ffcf33"))
    p.drawRect(QRectF(5, -2.5, 22, 5))                     # corpo
    p.setBrush(QColor("#ff8fb1"))
    p.drawRect(QRectF(27, -2.5, 5, 5))                     # borracha
    p.setBrush(QColor("#f1d7a6"))
    p.drawPolygon(QPolygonF([QPointF(5, -2.5), QPointF(5, 2.5), QPointF(0, 0)]))   # ponta de madeira
    p.setBrush(QColor("#2b2b2b"))
    p.drawEllipse(QPointF(0.8, 0), 1.2, 1.2)
    p.restore()


DESENHOS = {"oculos_sol": _oculos_sol, "cachecol": _cachecol, "chapeu": _chapeu, "caderno": _caderno}
