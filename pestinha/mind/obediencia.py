"""
OBEDIÊNCIA - o instinto do pet diante de um pedido que veio do Hermes (a parte racional, na VPS).

O Hermes pode pedir ao corpo: dormir, bolinha, travessura, trabalhar. Quem decide se obedece é o pet,
pelo jeito que ele está agora: bravo quase sempre recusa, triste às vezes, cansado não brinca e
dormindo não ouve. Quando recusa, diz por quê num post-it.

Puro (sem Qt): o app chama `decidir` e executa a ação se vier `obedece=True`.
"""

import random

ACOES = ("dormir", "bolinha", "travessura", "trabalhar")
GASTAM_ENERGIA = ("bolinha", "travessura", "trabalhar")
SEM_ENERGIA_ABAIXO = 0.2

# emoção -> chance de recusar um pedido
RECUSA = {
    "bravo": 0.8,
    "dramatico": 0.6,
    "assustado": 0.6,
    "triste": 0.5,
}

FALAS_RECUSA = {
    "bravo": ("Não quero!", "Pede de novo com carinho.", "Hmpf. Não."),
    "dramatico": ("Ninguém me entende…", "Agora não, tô num momento."),
    "assustado": ("Calma, ainda tô me recuperando!", "Me deixa respirar primeiro."),
    "triste": ("Agora não… tô tristinho.", "Sem vontade…"),
}
FALA_CANSADO = ("Tô sem energia pra isso…", "Bocejo… depois?")
FALA_DORMINDO = ("Zzz…",)
FALA_JA_DORMINDO = ("Já tô dormindo, ué. Zzz…",)


def decidir(acao, emocao, energia, dormindo, sorte=random):
    """
    (obedece, fala) para um pedido do Hermes.
    `fala` é o que aparece no post-it quando ele recusa (None quando obedece).
    """
    if acao not in ACOES:
        return False, None
    if dormindo:
        return False, sorte.choice(FALA_JA_DORMINDO if acao == "dormir" else FALA_DORMINDO)
    if acao in GASTAM_ENERGIA and energia < SEM_ENERGIA_ABAIXO:
        return False, sorte.choice(FALA_CANSADO)
    if sorte.random() < RECUSA.get(emocao, 0.0):
        return False, sorte.choice(FALAS_RECUSA[emocao])
    return True, None
