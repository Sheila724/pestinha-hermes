"""
PALCO - janela transparente que acompanha o pet e mostra o que acontece EM VOLTA dele.

Não pega clique nem foco (os cliques passam direto para o que está embaixo) e só aparece enquanto
algum efeito está rodando. Coordenadas dos efeitos: origem no centro do corpo do pet.

Efeitos:
  pensando      balão de pensamento de HQ: bolinhas subindo, nuvem balançando, três pontinhos
                pulando; se demora (pesquisando na internet), uma lupa dá voltas na nuvem; some num "puf"
  exclamacao    um "!" que pula em cima da cabeça com estalinhos: "ouvi!"
  guarda_chuva  uma nuvenzinha chove em cima dele, ele abre o guarda-chuva e a chuva respinga nele
  estrela       estrela que gira e explode em brilhos (obedeceu)
  bufo          nuvens de bufo saindo do lado (recusou)
  confete       chuva de confete colorido (sexta-feira, véspera de feriado)
  calor         um solzinho com raios girando e o ar tremulando de calor
  frio          flocos de neve caindo devagar em volta
  brilho        brilhinhos perto do olho e um coraçãozinho subindo (tchau)
"""

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..body.animacao import acelerar, balanco, com_volta, elastico, lerp, limitar, progresso, suave
from ..body.pet import overlay_flags, set_no_activate

LARGURA, ALTURA = 560, 500
CX, CY = LARGURA / 2, 320            # onde fica o centro do pet dentro do palco
CONTORNO = QColor("#26262b")

# nome -> (duração padrão em s ou None = até mandar encerrar, duração da saída em s)
TEMPOS = {
    "pensando": (None, 0.4),
    "exclamacao": (1.3, 0.25),
    "guarda_chuva": (12.0, 0.6),
    "estrela": (1.4, 0.3),
    "bufo": (1.2, 0.2),
    "confete": (5.0, 1.0),
    "calor": (20.0, 0.6),
    "frio": (20.0, 0.8),
    "brilho": (1.4, 0.3),
}
LUPA_DEPOIS_S = 8.0


class Efeito:
    def __init__(self, nome, inicio, duracao, saida, semente):
        self.nome = nome
        self.inicio = inicio
        self.fim = None if duracao is None else inicio + duracao   # quando começa a sair
        self.saida_s = saida
        self.rng = random.Random(semente)
        self.particulas = []

    def saida(self, agora):
        return 0.0 if self.fim is None or agora < self.fim else progresso(agora, self.fim, self.saida_s)

    def acabou(self, agora):
        return self.fim is not None and agora >= self.fim + self.saida_s

    def encerrar(self, agora):
        if self.fim is None or self.fim > agora:
            self.fim = agora


class Palco(QWidget):
    def __init__(self):
        super().__init__(None, overlay_flags() | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(LARGURA, ALTURA)
        self.efeitos = []
        self.angulo = 0.0
        self.agora = 0.0
        self._sementes = 0

    def showEvent(self, event):
        super().showEvent(event)
        set_no_activate(self)

    # ---------- o que o app usa ----------

    def iniciar(self, nome, agora, duracao="padrao"):
        """Começa um efeito (se já está rodando e não acaba sozinho, só continua). Devolve o efeito."""
        padrao, saida = TEMPOS[nome]
        duracao = padrao if duracao == "padrao" else duracao
        for ef in self.efeitos:
            if ef.nome == nome and not ef.acabou(agora) and ef.saida(agora) == 0.0:
                if duracao is None:
                    ef.fim = None
                    return ef
                if ef.fim is not None:
                    ef.fim = max(ef.fim, agora + duracao)
                    return ef
        self._sementes += 1
        ef = Efeito(nome, agora, duracao, saida, self._sementes)
        self.efeitos.append(ef)
        return ef

    def encerrar(self, nome, agora):
        """Manda o efeito sair (com a animação de saída dele)."""
        for ef in self.efeitos:
            if ef.nome == nome:
                ef.encerrar(agora)

    def ativo(self, nome, agora):
        return any(ef.nome == nome and not ef.acabou(agora) and ef.saida(agora) == 0.0 for ef in self.efeitos)

    def limpar(self):
        self.efeitos.clear()
        self.hide()

    def tick(self, agora, x, y, angulo, pet_visivel):
        """Um quadro: acompanha o pet, tira o que acabou e redesenha (some quando não há nada)."""
        self.agora = agora
        self.angulo = angulo
        self.efeitos = [ef for ef in self.efeitos if not ef.acabou(agora)]
        if not self.efeitos or not pet_visivel:
            if self.isVisible():
                self.hide()
            return
        self.move(int(x - CX), int(y - CY))
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(CX, CY)
        for ef in list(self.efeitos):
            p.save()
            DESENHOS[ef.nome](p, ef, self.agora, self.angulo)
            p.restore()
        p.end()


# ======================= desenhos =======================

_NUVENS = {}


def _nuvem(raio_base, bolas):
    """Contorno único de várias bolas juntas (o desenho de nuvem de HQ). Calculado uma vez e guardado."""
    chave = (raio_base, tuple(bolas))
    if chave not in _NUVENS:
        caminho = QPainterPath()
        for dx, dy, r in bolas:
            bola = QPainterPath()
            bola.addEllipse(QPointF(dx, dy), r * raio_base, r * raio_base)
            caminho = caminho.united(bola)
        _NUVENS[chave] = caminho
    return _NUVENS[chave]


BOLAS_PENSAMENTO = [(-52, 10, 28), (-26, -14, 32), (10, -22, 34), (46, -8, 30), (60, 16, 22),
                    (26, 24, 28), (-14, 26, 28), (-56, 22, 20)]


def _pensando(p, ef, agora, _ang):
    t = agora - ef.inicio
    sai = ef.saida(agora)
    alfa = 1.0 - sai
    p.setOpacity(alfa)
    # bolinhas subindo da cabeça até a nuvem, uma de cada vez
    for i, (x, y, r) in enumerate([(44, -60, 6), (60, -86, 9), (80, -114, 12)]):
        s = com_volta(progresso(agora, ef.inicio + i * 0.12, 0.25))
        if s <= 0:
            continue
        flutua = 2.5 * math.sin(agora * 3.0 + i)
        p.setPen(QPen(CONTORNO, 2.5))
        p.setBrush(Qt.white)
        p.drawEllipse(QPointF(x, y + flutua), r * s, r * s)
    s = com_volta(progresso(agora, ef.inicio + 0.36, 0.38))
    if s <= 0:
        return
    centro = QPointF(118, -172 + 5.0 * math.sin(agora * 2.1))
    p.save()
    p.translate(centro)
    escala = s * (1.0 + 0.28 * suave(sai))
    p.scale(escala, escala)
    p.rotate(2.0 * math.sin(agora * 1.4))
    nuvem = _nuvem(1.0, BOLAS_PENSAMENTO)
    p.setPen(QPen(CONTORNO, 3))
    p.setBrush(Qt.white)
    p.drawPath(nuvem)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(210, 220, 235, 120))
    p.drawEllipse(QPointF(-30, -18), 12, 7)               # brilhinho
    for i in range(3):                                     # pontinhos pulando em onda
        pulo = max(0.0, math.sin(agora * 6.5 - i * 0.9))
        p.setBrush(CONTORNO)
        p.drawEllipse(QPointF(-24 + i * 24, 4 - 7 * pulo), 5.5 + 1.5 * pulo, 5.5 + 1.5 * pulo)
    p.restore()
    if t > LUPA_DEPOIS_S:                                   # demorando: está pesquisando
        k = com_volta(progresso(agora, ef.inicio + LUPA_DEPOIS_S, 0.4))
        volta = agora * 1.6
        lx, ly = centro.x() + 74 * math.cos(volta), centro.y() + 46 * math.sin(volta)
        _lupa(p, lx, ly, 13 * k, -35 + 20 * math.sin(agora * 2))
    if sai > 0:                                            # "puf": fumacinhas saindo da nuvem
        p.setOpacity(1.0 - sai)
        p.setPen(QPen(CONTORNO, 2))
        p.setBrush(Qt.white)
        for i in range(8):
            a = i * math.pi / 4 + 0.3
            d = 60 + 70 * suave(sai)
            r = 11 * (1.0 - sai)
            p.drawEllipse(QPointF(centro.x() + d * math.cos(a), centro.y() + 0.7 * d * math.sin(a)), r, r)


def _lupa(p, x, y, raio, angulo):
    if raio <= 0.5:
        return
    p.save()
    p.translate(x, y)
    p.rotate(angulo)
    p.setPen(QPen(QColor("#5a3b1c"), raio * 0.45, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(raio * 0.8, raio * 0.8), QPointF(raio * 2.1, raio * 2.1))
    p.setPen(QPen(CONTORNO, 2.5))
    p.setBrush(QColor(170, 215, 255, 150))
    p.drawEllipse(QPointF(0, 0), raio, raio)
    p.setPen(QPen(QColor(255, 255, 255, 200), 2))
    p.drawArc(QRectF(-raio * 0.6, -raio * 0.6, raio * 1.2, raio * 1.2), 100 * 16, 70 * 16)
    p.restore()


def _exclamacao(p, ef, agora, _ang):
    t = agora - ef.inicio
    p.setOpacity(1.0 - ef.saida(agora))
    s = elastico(limitar(t / 0.6))
    p.translate(0, -104 - 14 * com_volta(limitar(t / 0.3)))
    for i, a in enumerate((-55, -90, -125)):               # estalinhos em volta
        k = limitar(t / 0.35)
        if k < 1:
            p.save()
            p.rotate(a + 90)
            p.setOpacity((1.0 - k) * (1.0 - ef.saida(agora)))
            p.setPen(QPen(QColor("#ffb703"), 4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(0, -38 - 22 * k), QPointF(0, -50 - 30 * k))
            p.restore()
    p.rotate(16 * balanco(t, 3.0, 3.5))
    p.scale(1.45 * s, 1.45 * s)
    p.setPen(QPen(CONTORNO, 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor("#ffd23f"))
    barra = QPainterPath()
    barra.addRoundedRect(QRectF(-8, -30, 16, 36), 7, 7)
    p.drawPath(barra)
    p.drawEllipse(QPointF(0, 18), 8, 8)


def _guarda_chuva(p, ef, agora, ang):
    t = agora - ef.inicio
    sai = ef.saida(agora)
    abre = com_volta(limitar((t - 0.5) / 0.45)) * (1.0 - suave(limitar(sai * 1.6)))
    # nuvenzinha de chuva lá em cima
    nuvem_s = com_volta(limitar(t / 0.4)) * (1.0 - suave(sai))
    ncx, ncy = -8 + 10 * math.sin(agora * 0.7), -246
    if not ef.particulas:
        ef.particulas = [(ef.rng.uniform(-110, 110), ef.rng.uniform(0, 1), ef.rng.uniform(560, 760)) for _ in range(42)]
    chovendo = limitar((t - 0.25) / 0.4) * (1.0 - sai)
    if chovendo > 0:
        topo, chao = ncy + 22, 52
        p.setOpacity(0.9 * chovendo)
        for x0, fase, vel in ef.particulas:
            x = ncx + x0
            queda = chao - topo
            y = topo + ((fase * queda + t * vel) % queda)
            borda = _borda_guarda_chuva(x, abre)
            if borda is not None and y > borda:          # bateu no guarda-chuva: respingo
                if y - borda < 22:
                    _respingo(p, x, borda, (y - borda) / 22)
                continue
            if abs(x) < 62 and y > -48:                    # não chove em cima do corpo
                continue
            if chao - y < 16:
                _respingo(p, x, chao, (y - (chao - 16)) / 16)
                continue
            p.setPen(QPen(QColor(90, 160, 255, 210), 2.2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x, y), QPointF(x - 1.5, y - 11))
    p.setOpacity(1.0)
    if nuvem_s > 0:
        p.save()
        p.translate(ncx, ncy)
        p.scale(nuvem_s, nuvem_s)
        nuvem = _nuvem(1.0, [(-60, 6, 24), (-30, -10, 30), (6, -16, 32), (40, -4, 28), (66, 8, 20),
                             (30, 16, 24), (-8, 16, 26), (-46, 18, 20)])
        p.setPen(QPen(QColor("#4a5160"), 3))
        p.setBrush(QColor("#8a93a6"))
        p.drawPath(nuvem)
        p.restore()
    if abre <= 0.02:
        return
    p.save()
    p.rotate(ang * 0.6 + 4 * math.sin(agora * 1.8))
    # cabo saindo do lado do corpo
    p.setPen(QPen(QColor("#5a3b1c"), 4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(20, -108), QPointF(20, 26))
    gancho = QPainterPath(QPointF(20, 26))
    gancho.quadTo(QPointF(20, 40), QPointF(10, 40))
    gancho.quadTo(QPointF(2, 40), QPointF(2, 32))
    p.drawPath(gancho)
    p.translate(20, -108)
    p.scale(max(0.08, abre), 1.0)
    _copa(p)
    p.restore()


LARGURA_COPA = 172


def _borda_guarda_chuva(x, abre):
    """Altura da copa do guarda-chuva no x dado (coordenadas do pet), ou None se fora dela."""
    meia = LARGURA_COPA / 2 * max(0.08, abre)
    dx = x - 20
    if abre < 0.3 or abs(dx) > meia:
        return None
    return -108 - 62 * math.sqrt(max(0.0, 1.0 - (dx / meia) ** 2)) + 6


def _copa(p):
    """Copa do guarda-chuva: cúpula com a barra recortada em ondas, gomos vermelho e branco e varetas."""
    meia, alto, gomos = LARGURA_COPA / 2, 62.0, 6
    pontas = [-meia + i * (2 * meia / gomos) for i in range(gomos + 1)]
    copa = QPainterPath(QPointF(-meia, 0))
    copa.cubicTo(QPointF(-meia, -alto * 1.25), QPointF(meia, -alto * 1.25), QPointF(meia, 0))
    for i in range(gomos, 0, -1):                          # ondinhas da barra, de volta para a esquerda
        a, b = pontas[i], pontas[i - 1]
        copa.quadTo(QPointF((a + b) / 2, -14), QPointF(b, 0))
    p.save()
    p.setClipPath(copa)
    p.setPen(Qt.NoPen)
    for i in range(gomos):
        p.setBrush(QColor("#e63946") if i % 2 == 0 else QColor("#fff3e6"))
        p.drawPolygon(QPolygonF([QPointF(0, -alto - 10), QPointF(pontas[i], 2), QPointF(pontas[i + 1], 2)]))
    p.setBrush(QColor(255, 255, 255, 60))
    p.drawEllipse(QPointF(-meia * 0.35, -alto * 0.55), meia * 0.32, alto * 0.2)       # brilho
    p.restore()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor("#8c1d24"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(copa)
    p.setPen(QPen(QColor("#8c1d24"), 1.2))
    for x in pontas[1:-1]:
        p.drawLine(QPointF(0, -alto * 0.93), QPointF(x, 0))
    p.setPen(QPen(QColor("#5a3b1c"), 3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(0, -alto * 0.93), QPointF(0, -alto - 12))


def _respingo(p, x, y, k):
    k = limitar(k)
    p.setPen(QPen(QColor(120, 180, 255, int(220 * (1 - k))), 1.8, Qt.SolidLine, Qt.RoundCap))
    for lado in (-1, 1):
        p.drawLine(QPointF(x + lado * 3 * k, y - 2 - 6 * k), QPointF(x + lado * (4 + 6 * k), y - 6 - 8 * k))


def _estrela_poligono(r_fora, r_dentro, pontas=5):
    pontos = []
    for i in range(pontas * 2):
        r = r_fora if i % 2 == 0 else r_dentro
        a = -math.pi / 2 + i * math.pi / pontas
        pontos.append(QPointF(r * math.cos(a), r * math.sin(a)))
    return QPolygonF(pontos)


def _estrela(p, ef, agora, _ang):
    t = agora - ef.inicio
    sai = ef.saida(agora)
    p.translate(0, -112)
    # brilhos voando para fora
    for i in range(10):
        a = i * 2 * math.pi / 10 + 0.2
        d = 26 + 96 * suave(limitar(t / 0.9))
        alfa = 1.0 - limitar((t - 0.3) / 0.8)
        if alfa <= 0:
            continue
        p.save()
        p.setOpacity(alfa)
        p.translate(d * math.cos(a), d * math.sin(a))
        p.rotate(t * 200)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffe066") if i % 2 else QColor("#7ee8fa"))
        p.drawPolygon(_estrela_poligono(7, 2.5, 4))
        p.restore()
    s = com_volta(limitar(t / 0.4), 2.6) * (1.0 - acelerar(sai))
    p.setOpacity(1.0 - sai)
    p.rotate(-180 * (1.0 - limitar(t / 0.5)) + 15 * math.sin(agora * 3))
    p.scale(s, s)
    p.setPen(QPen(QColor("#b9770e"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor("#ffcf33"))
    p.drawPolygon(_estrela_poligono(30, 13))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawEllipse(QPointF(-8, -8), 5, 4)


def _bufo(p, ef, agora, _ang):
    t = agora - ef.inicio
    p.setOpacity(1.0 - ef.saida(agora))
    for lado in (-1, 1):
        for i in range(3):
            e = limitar((t - i * 0.14) / 0.8)
            if e <= 0 or e >= 1:
                continue
            x = lado * (62 + 80 * suave(e))
            y = -10 - 40 * suave(e) + (i - 1) * 16 * suave(e)
            r = (9 + 17 * suave(e)) * (1.0 - 0.25 * e)
            p.setOpacity((1.0 - e) * (1.0 - ef.saida(agora)))
            p.setPen(QPen(QColor("#8d8d93"), 2))
            p.setBrush(QColor("#e4e4e8"))
            p.drawEllipse(QPointF(x, y), r, r * 0.8)
    if t < 0.9:                                            # rabisquinho de bravo em cima da cabeça
        k = com_volta(limitar(t / 0.25))
        p.setOpacity(1.0 - limitar((t - 0.6) / 0.3))
        p.translate(40, -70)
        p.scale(k, k)
        p.setPen(QPen(QColor("#e63946"), 3.5, Qt.SolidLine, Qt.RoundCap))
        for a in (0, 90):
            p.save()
            p.rotate(a + 45)
            p.drawLine(QPointF(-9, -3), QPointF(-3, -3))
            p.drawLine(QPointF(3, -3), QPointF(9, -3))
            p.drawLine(QPointF(-9, 3), QPointF(-3, 3))
            p.drawLine(QPointF(3, 3), QPointF(9, 3))
            p.restore()


CORES_CONFETE = ["#ff595e", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93", "#ff8fb1", "#4cc9f0"]


def _confete(p, ef, agora, _ang):
    t = agora - ef.inicio
    if not ef.particulas:
        r = ef.rng
        ef.particulas = [(r.uniform(-230, 230), r.uniform(-330, -230), r.uniform(-60, 60), r.uniform(90, 170),
                          r.uniform(0, 6.28), r.uniform(-400, 400), r.choice(CORES_CONFETE), r.uniform(0, 0.8))
                         for _ in range(70)]
    p.setOpacity(1.0 - ef.saida(agora))
    p.setPen(Qt.NoPen)
    for x0, y0, vx, vy, fase, giro, cor, atraso in ef.particulas:
        tt = t - atraso
        if tt < 0:
            continue
        y = y0 + vy * tt + 14 * tt * tt
        if y > 160:
            continue
        x = x0 + vx * tt * 0.4 + 18 * math.sin(tt * 3 + fase)
        p.save()
        p.translate(x, y)
        p.rotate(fase * 57 + giro * tt)
        p.scale(1.0, 0.35 + 0.65 * abs(math.cos(tt * 5 + fase)))      # "virando" no ar
        p.setBrush(QColor(cor))
        p.drawRect(QRectF(-5, -3, 10, 6))
        p.restore()


def _calor(p, ef, agora, _ang):
    t = agora - ef.inicio
    sai = ef.saida(agora)
    s = com_volta(limitar(t / 0.5)) * (1.0 - acelerar(sai))
    p.setOpacity(1.0 - sai)
    p.save()
    p.translate(-96, -168 + 4 * math.sin(agora * 1.5))
    p.scale(s, s)
    p.rotate(agora * 25)
    p.setPen(QPen(QColor("#ff9f1c"), 4, Qt.SolidLine, Qt.RoundCap))
    for i in range(10):
        p.save()
        p.rotate(i * 36)
        comp = 8 + 4 * math.sin(agora * 4 + i)
        p.drawLine(QPointF(0, -30), QPointF(0, -30 - comp))
        p.restore()
    p.setPen(QPen(QColor("#e07a00"), 2.5))
    p.setBrush(QColor("#ffd23f"))
    p.drawEllipse(QPointF(0, 0), 24, 24)
    p.restore()
    # ar tremulando em cima da cabeça
    p.setPen(QPen(QColor(255, 170, 60, 150), 2.4, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    for i in range(3):
        fase = (agora * 0.6 + i / 3) % 1.0
        y0 = -56 - 70 * fase
        p.setOpacity((1.0 - sai) * math.sin(fase * math.pi))
        onda = QPainterPath(QPointF(-30 + i * 30, y0))
        for k in range(1, 9):
            onda.lineTo(QPointF(-30 + i * 30 + 4 * math.sin(k * 1.2 + agora * 6), y0 - k * 3))
        p.drawPath(onda)


def _frio(p, ef, agora, _ang):
    t = agora - ef.inicio
    sai = ef.saida(agora)
    if not ef.particulas:
        r = ef.rng
        ef.particulas = [(r.uniform(-170, 170), r.uniform(0, 1), r.uniform(28, 46), r.uniform(4, 8), r.uniform(0, 6.28))
                         for _ in range(22)]
    entra = limitar(t / 0.8)
    for x0, fase, vel, tam, giro in ef.particulas:
        queda = 330
        y = -260 + ((fase * queda + t * vel) % queda)
        x = x0 + 16 * math.sin(t * 0.9 + giro)
        if abs(x) < 62 and -48 < y < 48:
            continue
        borda = 1.0 - limitar((y - 40) / 30)
        p.setOpacity(entra * (1.0 - sai) * borda)
        _floco(p, x, y, tam, giro + t * 0.8)


def _floco(p, x, y, tam, giro):
    p.save()
    p.translate(x, y)
    p.rotate(math.degrees(giro))
    for cor, largura in ((QColor(90, 140, 200, 150), 3.4), (QColor(240, 248, 255), 1.8)):
        _bracos(p, tam, cor, largura)
    p.restore()


def _bracos(p, tam, cor, largura):
    p.setPen(QPen(cor, largura, Qt.SolidLine, Qt.RoundCap))
    for i in range(3):
        p.save()
        p.rotate(i * 60)
        p.drawLine(QPointF(-tam, 0), QPointF(tam, 0))
        for lado in (-1, 1):
            p.drawLine(QPointF(lado * tam * 0.55, 0), QPointF(lado * tam * 0.8, -tam * 0.25))
            p.drawLine(QPointF(lado * tam * 0.55, 0), QPointF(lado * tam * 0.8, tam * 0.25))
        p.restore()


def _brilho(p, ef, agora, _ang):
    t = agora - ef.inicio
    p.setOpacity(1.0 - ef.saida(agora))
    for i, (x, y, r) in enumerate([(44, -26, 9), (58, -6, 6), (34, -44, 5)]):
        k = com_volta(limitar((t - i * 0.12) / 0.3)) * (1.0 - limitar((t - 0.7 - i * 0.1) / 0.4))
        if k <= 0:
            continue
        p.save()
        p.translate(x, y)
        p.rotate(t * 120)
        p.scale(k, k)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#fff3b0"))
        p.drawPolygon(_estrela_poligono(r, r * 0.35, 4))
        p.restore()
    k = limitar((t - 0.15) / 1.1)
    if 0 < k < 1:
        p.save()
        p.setOpacity((1.0 - k) * (1.0 - ef.saida(agora)))
        p.translate(lerp(30, 46, k) + 6 * math.sin(t * 6), lerp(-70, -150, suave(k)))
        p.scale(0.6 + 0.5 * com_volta(limitar(k * 3)), 0.6 + 0.5 * com_volta(limitar(k * 3)))
        coracao = QPainterPath(QPointF(0, 8))
        coracao.cubicTo(QPointF(-14, -2), QPointF(-8, -14), QPointF(0, -6))
        coracao.cubicTo(QPointF(8, -14), QPointF(14, -2), QPointF(0, 8))
        p.setPen(QPen(QColor("#b5174a"), 2))
        p.setBrush(QColor("#ff5d8f"))
        p.drawPath(coracao)
        p.restore()


DESENHOS = {
    "pensando": _pensando, "exclamacao": _exclamacao, "guarda_chuva": _guarda_chuva, "estrela": _estrela,
    "bufo": _bufo, "confete": _confete, "calor": _calor, "frio": _frio, "brilho": _brilho,
}
