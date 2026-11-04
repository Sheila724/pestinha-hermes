"""
MUNDO - o que o pet sabe do lado de fora em cada conversa: data, hora, previsão e feriados.

Sem isso, perguntar "vai chover hoje?" fazia o pet dizer que não consegue ver pela janela: o clima só
era consultado nos avisos agendados. A previsão fica em cache por alguns minutos para não consultar o
Open-Meteo a cada mensagem.
"""
import datetime as dt
import threading
import time
from zoneinfo import ZoneInfo

from . import calendario, clima

CACHE_S = 30 * 60
FUSO_PADRAO = "America/Sao_Paulo"
DIAS = calendario.DIAS


class Mundo:
    def __init__(self, perfil, buscar_previsao=clima.previsao, relogio=time.time):
        self._perfil = perfil
        self._buscar = buscar_previsao
        self._relogio = relogio
        self._lock = threading.Lock()
        self._cache = (None, 0.0, None)          # (chave do lugar, quando buscou, previsão)

    def _previsao(self, lugar):
        chave = (lugar.get("lat"), lugar.get("lon"))
        with self._lock:
            c_chave, c_quando, c_prev = self._cache
            if c_chave == chave and self._relogio() - c_quando < CACHE_S:
                return c_prev
        try:
            prev = self._buscar(lugar)
        except clima.ClimaErro:
            prev = None
        with self._lock:
            self._cache = (chave, self._relogio(), prev)
        return prev

    def contexto(self, agora_utc=None):
        """Uma linha "[Lado de fora agora: ...]" para o Hermes responder sobre tempo, data e feriados."""
        lugar = self._perfil.ler() or {}
        agora = (agora_utc or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(lugar.get("fuso", FUSO_PADRAO)))
        hoje, amanha = agora.date(), agora.date() + dt.timedelta(days=1)
        partes = [f"{DIAS[hoje.weekday()]}, {hoje:%d/%m}, {agora:%H:%M}"]
        if lugar.get("nome"):
            partes[0] += f" em {lugar['nome']}"
            prev = self._previsao(lugar)
            dias = {d["data"]: d for d in (prev or {}).get("dias", [])}
            for rotulo, data in (("hoje", hoje), ("amanhã", amanha)):
                d = dias.get(data.isoformat())
                if d:
                    partes.append(f"{rotulo} {round(d['min'])} a {round(d['max'])}°C, chance de chuva {d.get('chuva') or 0}%")
            if prev:
                chance = clima.chuva_entre(prev, agora, agora + dt.timedelta(hours=3))
                partes.append(f"chance de chuva nas próximas 3 horas {chance}%")
            else:
                partes.append("previsão do tempo indisponível agora")
        pais = lugar.get("pais", "BR")
        for rotulo, data in (("hoje", hoje), ("amanhã", amanha)):
            nome = calendario.feriado(data, pais)
            if nome:
                partes.append(f"{rotulo} é feriado ({nome})")
        return "[Lado de fora agora: " + "; ".join(partes) + "]"
