"""
O que o Hermes pode pedir ao corpo do pet, e o que o pet conta ao Hermes sobre como está.

O Hermes pede uma ação terminando a resposta com uma linha `[acao: nome]`. A ponte tira essa linha
do texto e manda o nome separado. Quem decide se obedece é o pet (pestinha/mind/obediencia.py).
"""
import re

ACOES = ("dormir", "bolinha", "travessura", "trabalhar")
EMOCOES = ("observando", "contente", "feliz", "curioso", "bravo", "triste",
           "assustado", "dramatico", "dormindo")

_TAG = re.compile(r"\[\s*a[cç][aã]o\s*:\s*([a-zà-ú]+)\s*\]", re.IGNORECASE)
_COLCHETES = re.compile(r"\[[^\]]{0,60}\]")          # outras marcas que o modelo inventa: "[Petição atendida]"
_LIXO_NO_FIM = re.compile(r"[\s{}|\\/<>\[\]_~^`*#=,;:-]+$")   # restos de formatação: "… }|", "ótimo,"


def limpar(texto):
    """Texto de post-it: sem marcas entre colchetes, sem markdown e sem lixo de formatação no fim."""
    texto = _COLCHETES.sub(" ", texto).replace("**", "").replace("__", "")
    texto = " ".join(texto.split())
    return _LIXO_NO_FIM.sub("", texto).strip()


def separar_acao(resposta):
    """("texto limpo", "acao" ou None). Só vale a última tag e só se for uma ação conhecida."""
    achadas = _TAG.findall(resposta)
    texto = limpar(_TAG.sub(" ", resposta))
    acao = achadas[-1].lower() if achadas else None
    return texto, (acao if acao in ACOES else None)


def descrever_estado(estado):
    """Uma linha para o Hermes saber como o pet está agora, ou "" se não veio nada útil."""
    if not estado:
        return ""
    partes = []
    if estado.get("emocao") in EMOCOES:
        partes.append(f"emoção {estado['emocao']}")
    energia = estado.get("energia")
    if isinstance(energia, (int, float)) and 0 <= energia <= 1:
        partes.append(f"energia {round(energia * 100)}%")
    if estado.get("dormindo") is True:
        partes.append("está dormindo")
    return f"[Como o pet está agora: {', '.join(partes)}]" if partes else ""
