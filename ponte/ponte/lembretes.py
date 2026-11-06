"""
LEMBRETES - "me lembra daqui a 30 min de ligar para o cliente".

O Hermes entende o pedido e termina a resposta com uma linha `[lembrete: QUANDO | o que lembrar]`.
A ponte tira essa linha, calcula o horário certo (o modelo erra conta de hora; aqui não) e guarda no
SQLite. O horário confirmado é a ponte quem escreve no post-it, para nunca prometer uma hora errada.

QUANDO aceita:
    +30  +30min  +2h  +1h30      a partir de agora
    16:00  16h  16h30            hoje (se já passou, amanhã)
    06/11 09:00                  outro dia (se já passou este ano, ano que vem)
    2026-11-06 09:00

Quem dispara é a própria ponte, quando o pet consulta a fila (a cada 5 s): o lembrete vira uma fala com o
efeito "lembrete" (o pet acorda e toca o despertador). Com o pet fechado, o lembrete espera e aparece
quando ele abrir, dizendo a hora em que era para lembrar.
"""
import datetime as dt
import random
import re
import sqlite3
import threading
import time
from zoneinfo import ZoneInfo

MAX_PENDENTES = 30
MAX_TEXTO = 120
MAX_DIAS = 366
MIN_S = 30                              # "daqui a 0 min" vira daqui a 30 s
ATRASADO_S = 5 * 60                     # passou disso, o post-it diz a hora em que era para lembrar

_TAG = re.compile(r"\[\s*lembrete\s*:\s*([^|\]\n]{1,40})\|\s*([^\]\n]{1,300})\]", re.IGNORECASE)
_CANCELAR = re.compile(r"\[\s*cancelar(?:\s+lembrete)?\s*:\s*#?\s*(\d{1,9})\s*\]", re.IGNORECASE)
_RELATIVO = re.compile(r"^\+\s*(?:(\d{1,4})\s*h(?:oras?)?\s*)?(?:(\d{1,5})\s*(?:m|min|minutos?)?)?$", re.IGNORECASE)
_HORA = re.compile(r"^([01]?\d|2[0-3])\s*(?::|h)\s*([0-5]\d)?$", re.IGNORECASE)
_DIA_HORA = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\s+(.+)$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ t](.+)$", re.IGNORECASE)

# Pediu lembrete? ("me lembra", "me avisa", "me cutuca", "despertador") com algo de tempo junto.
PEDIU = re.compile(r"\b(me\s+(lembr|avis|cutuc)\w*|despertador|alarme)", re.IGNORECASE)
PERGUNTA_CONDICIONAL = re.compile(r"\bme\s+avis\w*\s+(se|quando|caso)\b", re.IGNORECASE)   # "me avisa se chover"
TEM_TEMPO = re.compile(r"\d|hora|min|amanh|daqui|depois|meio[\s-]dia|meia[\s-]noite|tarde|manh|noite",
                       re.IGNORECASE)

FALAS = ("Ei, psiu! Hora de: {texto}", "Trim-trim! Você pediu para eu lembrar: {texto}",
         "Lembrete do Pestinha: {texto}", "Acorda pra vida! {texto}")
FALAS_ATRASADO = ("Era para te lembrar às {hora}: {texto}", "Atrasei, mas não esqueci! Às {hora} era: {texto}")


def _hora_min(texto):
    m = _HORA.match(texto.strip())
    return (int(m.group(1)), int(m.group(2) or 0)) if m else None


def interpretar(quando, agora):
    """
    Datetime (no fuso de `agora`, que deve ser consciente de fuso) para o QUANDO do Hermes, ou None.
    Só aceita futuro até MAX_DIAS.
    """
    q = " ".join(str(quando).split()).lower()
    alvo = None
    m = _RELATIVO.match(q)
    if q.startswith("+") and m and (m.group(1) or m.group(2)):
        alvo = agora + dt.timedelta(hours=int(m.group(1) or 0), minutes=int(m.group(2) or 0))
        alvo = max(alvo, agora + dt.timedelta(seconds=MIN_S))
    elif _hora_min(q):
        h, mi = _hora_min(q)
        alvo = agora.replace(hour=h, minute=mi, second=0, microsecond=0)
        if alvo <= agora:
            alvo += dt.timedelta(days=1)
    else:
        d = _DIA_HORA.match(q)
        iso = _ISO.match(q)
        try:
            if d and _hora_min(d.group(4)):
                h, mi = _hora_min(d.group(4))
                ano = int(d.group(3) or agora.year)
                alvo = agora.replace(year=ano, month=int(d.group(2)), day=int(d.group(1)),
                                     hour=h, minute=mi, second=0, microsecond=0)
                if alvo <= agora and not d.group(3):
                    alvo = alvo.replace(year=ano + 1)
            elif iso and _hora_min(iso.group(4)):
                h, mi = _hora_min(iso.group(4))
                alvo = agora.replace(year=int(iso.group(1)), month=int(iso.group(2)), day=int(iso.group(3)),
                                     hour=h, minute=mi, second=0, microsecond=0)
        except ValueError:                       # 31/02 e companhia
            return None
    if alvo is None or alvo <= agora or alvo - agora > dt.timedelta(days=MAX_DIAS):
        return None
    return alvo


def separar(resposta):
    """(texto sem as linhas de lembrete, [(quando, o que)], [ids para cancelar])."""
    pedidos = [(q.strip(), " ".join(t.split())[:MAX_TEXTO]) for q, t in _TAG.findall(resposta)]
    cancelar = [int(i) for i in _CANCELAR.findall(resposta)]
    texto = _CANCELAR.sub(" ", _TAG.sub(" ", resposta))
    return texto, [(q, t) for q, t in pedidos if t], cancelar


def pediu_lembrete(texto):
    """Parece pedido de lembrete com hora ("me lembra às 16h", "me avisa daqui a 30 min")."""
    return bool(PEDIU.search(texto) and TEM_TEMPO.search(texto) and not PERGUNTA_CONDICIONAL.search(texto))


def descrever_horario(alvo, agora):
    """'11:06', 'amanhã às 09:00' ou '06/11 às 09:00'."""
    if alvo.date() == agora.date():
        return alvo.strftime("%H:%M")
    if alvo.date() == agora.date() + dt.timedelta(days=1):
        return f"amanhã às {alvo:%H:%M}"
    return f"{alvo:%d/%m} às {alvo:%H:%M}"


class Lembretes:
    def __init__(self, caminho, relogio=time.time):
        self._lock = threading.Lock()
        self._relogio = relogio
        self._db = sqlite3.connect(str(caminho), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS lembretes ("
                         " id INTEGER PRIMARY KEY AUTOINCREMENT, quando REAL NOT NULL,"
                         " texto TEXT NOT NULL, criado REAL NOT NULL)")
        if "quem" not in [c[1] for c in self._db.execute("PRAGMA table_info(lembretes)")]:
            self._db.execute("ALTER TABLE lembretes ADD COLUMN quem TEXT NOT NULL DEFAULT ''")
        self._db.commit()

    def criar(self, alvo, texto, quem=""):
        """Guarda e devolve o id, ou None se já tem lembretes demais."""
        with self._lock:
            n = self._db.execute("SELECT COUNT(*) FROM lembretes").fetchone()[0]
            if n >= MAX_PENDENTES:
                return None
            cur = self._db.execute("INSERT INTO lembretes (quando, texto, criado, quem) VALUES (?, ?, ?, ?)",
                                   (alvo.timestamp(), str(texto)[:MAX_TEXTO], self._relogio(), quem))
            self._db.commit()
            return cur.lastrowid

    def cancelar(self, id_):
        with self._lock:
            cur = self._db.execute("DELETE FROM lembretes WHERE id = ?", (id_,))
            self._db.commit()
            return cur.rowcount == 1

    def pendentes(self):
        """[{"id", "quando" (epoch), "texto", "quem"}], o mais próximo primeiro."""
        with self._lock:
            linhas = self._db.execute("SELECT id, quando, texto, quem FROM lembretes ORDER BY quando, id").fetchall()
        return [{"id": i, "quando": q, "texto": t, "quem": w} for i, q, t, w in linhas]

    def vencidos(self):
        """Tira da tabela e devolve os que já passaram da hora (cada um sai uma vez só)."""
        agora = self._relogio()
        with self._lock:
            linhas = self._db.execute("SELECT id, quando, texto, quem FROM lembretes WHERE quando <= ? "
                                      "ORDER BY quando, id", (agora,)).fetchall()
            if linhas:
                self._db.executemany("DELETE FROM lembretes WHERE id = ?", [(i,) for i, *_ in linhas])
                self._db.commit()
        return [{"id": i, "quando": q, "texto": t, "quem": w} for i, q, t, w in linhas]

    def contexto(self, fuso):
        """Linha "[Lembretes marcados: #3 hoje 11:06 ligar...]" para o Hermes, ou "" sem nenhum."""
        lista = self.pendentes()
        if not lista:
            return ""
        z = ZoneInfo(fuso)
        agora = dt.datetime.fromtimestamp(self._relogio(), z)
        partes = [f"#{r['id']} {descrever_horario(dt.datetime.fromtimestamp(r['quando'], z), agora)} {r['texto']}"
                  + (f" (pedido por {r['quem']})" if r.get("quem") else "") for r in lista[:10]]
        return "[Lembretes marcados: " + "; ".join(partes) + "]"


def fala_do_lembrete(lembrete, fuso, agora_epoch, sorteio=random.choice):
    """O texto do post-it na hora do lembrete (com a hora combinada se ele chegou atrasado)."""
    if agora_epoch - lembrete["quando"] > ATRASADO_S:
        hora = dt.datetime.fromtimestamp(lembrete["quando"], ZoneInfo(fuso)).strftime("%H:%M")
        fala = sorteio(FALAS_ATRASADO).format(hora=hora, texto=lembrete["texto"])
    else:
        fala = sorteio(FALAS).format(texto=lembrete["texto"])
    return f"{fala} (pedido por {lembrete['quem']})" if lembrete.get("quem") else fala
