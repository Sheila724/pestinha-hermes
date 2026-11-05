"""
ANIMAÇÃO - curvas de movimento para o figurino e os efeitos: entrar com "molinha", quicar, tremular.

Funções puras de tempo (sem Qt): recebem um progresso de 0 a 1 (ou segundos) e devolvem quanto
mover, escalar ou girar. É o que dá a cara de bichinho virtual: nada aparece "do nada", tudo entra
passando um pouco do ponto e voltando, quica ao cair e balança antes de parar.
"""

import math


def limitar(x, a=0.0, b=1.0):
    """Prende `x` entre `a` e `b`."""
    return a if x < a else b if x > b else x


def progresso(agora, inicio, duracao):
    """Quanto de uma etapa já passou, de 0 a 1 (0 antes de começar, 1 depois de acabar)."""
    if duracao <= 0:
        return 1.0
    return limitar((agora - inicio) / duracao)


def lerp(a, b, t):
    """Ponto entre `a` e `b`, na fração `t`."""
    return a + (b - a) * t


def suave(t):
    """Começa e termina devagar (smoothstep)."""
    t = limitar(t)
    return t * t * (3.0 - 2.0 * t)


def acelerar(t):
    """Começa devagar e vai embora rápido (para saídas)."""
    t = limitar(t)
    return t * t * t


def com_volta(t, forca=1.70158):
    """Chega passando um pouco do ponto e volta (ease-out-back): o 'pop' de quem aparece."""
    t = limitar(t) - 1.0
    return 1.0 + (forca + 1.0) * t * t * t + forca * t * t


def elastico(t):
    """Chega como uma mola esticada, balançando até parar (ease-out-elastic)."""
    t = limitar(t)
    if t in (0.0, 1.0):
        return t
    return 2.0 ** (-10.0 * t) * math.sin((t * 10.0 - 0.75) * (2.0 * math.pi) / 3.0) + 1.0


def quique(t):
    """Cai e quica no chão algumas vezes, cada vez mais baixo (ease-out-bounce)."""
    t = limitar(t)
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


def balanco(segundos, freq=2.0, amortecer=4.0):
    """Balança em volta de zero e vai parando (amplitude 1 no começo). Bom para 'pousou e tremeu'."""
    if segundos < 0:
        return 0.0
    return math.exp(-amortecer * segundos) * math.sin(2.0 * math.pi * freq * segundos)


def bezier(p0, p1, p2, t):
    """Ponto numa curva (Bezier quadrática) de p0 a p2, puxada por p1: o arco de um voo."""
    u = 1.0 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])
