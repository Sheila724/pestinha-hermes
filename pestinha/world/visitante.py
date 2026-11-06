"""
VISITANTE - o pet de outra pessoa passeando na sua tela.

Ele é desenhado com os arquivos do personagem dele (todo executável tem os mesmos pets), chega pulando de
um canto da tela, para ao lado do seu pet, cumprimenta, brinca uns pulinhos olhando para ele, se despede
com uma piscadinha e vai embora pelo mesmo lado. Não aprende nada nem guarda nada: é só a visita.

    tick(agora, casa_x, casa_y) -> eventos: "cumprimentar", "despedir", "acabou"
"""
import math

from ..body.animacao import limitar, suave
from ..body.pet import PetWindow
from ..body.pet_state import PetState

CHEGADA_S = 2.6
SAIDA_S = 2.6
DESPEDIDA_ANTES_S = 3.2          # a despedida aparece esse tanto antes de ele começar a ir embora
PULINHO_A_CADA_S = 5.5
DISTANCIA = 135                   # do seu pet
FORA = 90                         # quanto além da borda ele começa e termina


class Visitante:
    def __init__(self, dados, aparencia, casa_x, chao_y, bounds, agora, janela=None):
        self.dados = dados
        self.duracao = max(20.0, min(180.0, float(dados.get("duracao", 75))))
        self.inicio = agora
        esquerda, _topo, direita, _baixo = bounds
        vem_da_esquerda = casa_x > (esquerda + direita) / 2       # vem pelo lado com mais espaço
        lado = -1 if vem_da_esquerda else 1
        self.x0 = esquerda - FORA if vem_da_esquerda else direita + FORA
        self.alvo = max(esquerda + 70, min(direita - 70, casa_x + lado * DISTANCIA))
        self.chao = chao_y
        self.janela = janela or PetWindow(self.x0, chao_y, PetState())
        self.janela.aparencia = aparencia
        self.janela.state.emotion = "feliz"
        self.janela.body.x, self.janela.body.y = self.x0, chao_y
        self.janela.setToolTip(f"Visita: o pet {dados.get('nome', '')}")
        self.janela.show()
        self._ditos = set()
        self.terminou = False

    @property
    def x(self):
        return self.janela.body.x

    @property
    def y(self):
        return self.janela.body.y

    def _posicao(self, t):
        """(x, y) no tempo `t` da visita: pulando para chegar, quicando parado, pulando para ir embora."""
        sair_em = self.duracao - SAIDA_S
        if t < CHEGADA_S:
            p = t / CHEGADA_S
            return self.x0 + (self.alvo - self.x0) * suave(p), self.chao - abs(math.sin(p * math.pi * 4)) * 26
        if t >= sair_em:
            p = limitar((t - sair_em) / SAIDA_S)
            return self.alvo + (self.x0 - self.alvo) * suave(p), self.chao - abs(math.sin(p * math.pi * 4)) * 26
        parado = t - CHEGADA_S
        fase = parado % PULINHO_A_CADA_S
        pulo = math.sin(fase / 0.45 * math.pi) * 30 if fase < 0.45 else 0.0
        return self.alvo, self.chao - pulo - 2.5 * math.sin(parado * 2.4)

    def tick(self, agora, casa_x, casa_y):
        """Move e anima o visitante; devolve os momentos que chegaram agora."""
        if self.terminou:
            return []
        t = agora - self.inicio
        x, y = self._posicao(t)
        self.janela.body.x, self.janela.body.y = x, y
        dx = casa_x - x
        self.janela.state.gaze = (max(-1.0, min(1.0, dx / 120.0)), max(-0.6, min(0.6, (casa_y - y) / 160.0)))
        self.janela.animate(agora)
        eventos = []
        for nome, quando in (("cumprimentar", CHEGADA_S + 0.2),
                             ("despedir", self.duracao - SAIDA_S - DESPEDIDA_ANTES_S),
                             ("acabou", self.duracao)):
            if t >= quando and nome not in self._ditos:
                self._ditos.add(nome)
                eventos.append(nome)
                if nome == "despedir":
                    self.janela.figurino.piscar(agora)
        if "acabou" in eventos:
            self.fechar()
        return eventos

    def fechar(self):
        self.terminou = True
        self.janela.close()
