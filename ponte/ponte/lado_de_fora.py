"""
LADO DE FORA - o pet comenta o mundo: clima da cidade escolhida, sexta-feira, véspera de feriado.

Roda de 15 em 15 minutos (deploy/pestinha-lado-de-fora.timer) e, em dia útil, manda dois avisos:
  manha   logo depois da entrada: bom-dia com a previsão do dia
  saida   uns 30 min antes da saída: chuva na volta para casa, feriado amanhã, sexta-feira
Cada aviso sai uma vez por dia. O Hermes escreve a frase no jeito do pet; se ele falhar, vai uma frase pronta.
O mesmo disparo escreve a página do diário à noite (ponte/diario.py).

Uso manual (na pasta ponte/, com o ponte.env carregado):
    python -m ponte.lado_de_fora            confere o horário e manda o que for a hora
    python -m ponte.lado_de_fora --agora    manda o aviso de saída já, para testar
"""
import datetime as dt
import sys
from zoneinfo import ZoneInfo

from . import acoes, calendario, clima, diario, hermes
from . import config as config_mod
from .eventos import Eventos
from .perfil import PADRAO, Perfil

JANELA = dt.timedelta(minutes=20)       # o timer roda a cada 15 min: a janela pega um disparo só
DEPOIS_DA_ENTRADA = dt.timedelta(minutes=5)
ANTES_DA_SAIDA = dt.timedelta(minutes=30)


def _hora(texto):
    h, m = texto.split(":")
    return dt.time(int(h), int(m))


def _graus(valor):
    return f"{round(valor)}°C"


def fatos(momento, lugar, prev, agora):
    """Lista de frases simples com o que vale comentar agora (vira contexto para o Hermes)."""
    hoje = agora.date()
    lista = []
    dias = {d["data"]: d for d in (prev or {}).get("dias", [])}
    dia = dias.get(hoje.isoformat())
    amanha = dias.get((hoje + dt.timedelta(days=1)).isoformat())
    if momento == "manha":
        if dia:
            lista.append(f"hoje em {lugar['nome']}: mínima {_graus(dia['min'])}, máxima {_graus(dia['max'])}")
            if (dia.get("chuva") or 0) >= clima.CHUVA_PROVAVEL:
                lista.append(f"{dia['chuva']}% de chance de chuva hoje")
    else:
        if prev:
            chance = clima.chuva_entre(prev, agora, agora + dt.timedelta(hours=3))
            if chance >= clima.CHUVA_PROVAVEL:
                lista.append(f"{chance}% de chance de chuva nas próximas horas, na volta para casa")
        if amanha and (amanha.get("chuva") or 0) >= clima.CHUVA_PROVAVEL:
            lista.append(f"amanhã também pode chover ({amanha['chuva']}%)")
    lista += calendario.fatos_do_dia(hoje, lugar.get("pais", "BR"))
    return lista


def frase_pronta(momento, lista):
    """Quando o Hermes não responde: uma frase direta com os fatos."""
    inicio = "Bom dia!" if momento == "manha" else "Quase hora de ir embora!"
    return f"{inicio} {lista[0][0].upper()}{lista[0][1:]}." if lista else inicio


def escrever(cfg, momento, lugar, lista, perguntar=hermes.perguntar):
    quando = "início do expediente" if momento == "manha" else "faltam uns 30 minutos para o fim do expediente"
    pedido = (f"[Aviso seu, ninguém perguntou nada. Momento: {quando}. Cidade: {lugar['nome']}. "
              f"Fatos: {'; '.join(lista) if lista else 'nada de especial hoje'}.]\n"
              "Escreva um aviso curto, no seu jeito, comentando o que for mais importante desses fatos. "
              "Não peça nenhuma ação.")
    try:
        texto, _ = acoes.separar_acao(perguntar(cfg, pedido))
        return texto or frase_pronta(momento, lista)
    except hermes.HermesErro:
        return frase_pronta(momento, lista)


def momento_agora(perfil, agora, forcar=False):
    """'manha', 'saida' ou None, pelo horário escolhido na cidade escolhida."""
    if forcar:
        return "saida"
    if not calendario.dia_util(agora.date(), perfil.get("pais", "BR")):
        return None
    base = agora.replace(second=0, microsecond=0)
    entrada = dt.datetime.combine(agora.date(), _hora(perfil.get("entrada", PADRAO["entrada"])), agora.tzinfo)
    saida = dt.datetime.combine(agora.date(), _hora(perfil.get("saida", PADRAO["saida"])), agora.tzinfo)
    for nome, alvo in (("manha", entrada + DEPOIS_DA_ENTRADA), ("saida", saida - ANTES_DA_SAIDA)):
        if alvo <= base < alvo + JANELA:
            return nome
    return None


def verificar(cfg, perfil, eventos, agora_utc=None, forcar=False,
              buscar_previsao=clima.previsao, perguntar=hermes.perguntar):
    """Manda o aviso da hora, se for a hora e ainda não tiver ido hoje. Devolve o id do evento ou None."""
    lugar = perfil.ler()
    if not lugar:
        return None
    agora = (agora_utc or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(lugar["fuso"]))
    momento = momento_agora(lugar, agora, forcar)
    if momento is None or (not forcar and not perfil.marcar(f"{agora.date()}:{momento}")):
        return None
    try:
        prev = buscar_previsao(lugar)
    except clima.ClimaErro:
        prev = None
    texto = escrever(cfg, momento, lugar, fatos(momento, lugar, prev, agora), perguntar)
    return eventos.adicionar("falar", {"texto": texto})


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cfg = config_mod.carregar()
    perfil, eventos = Perfil(cfg.banco), Eventos(cfg.banco)
    novo = verificar(cfg, perfil, eventos, forcar="--agora" in argv)
    print(f"aviso enviado (evento {novo})" if novo else "nada para avisar agora")
    pagina = diario.verificar(cfg, diario.Diario(cfg.banco), perfil, eventos)   # o mesmo timer escreve o diário
    if pagina:
        print(f"página do diário escrita ({pagina})")


if __name__ == "__main__":
    main()
