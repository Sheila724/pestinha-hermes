"""
DIÁRIO - toda noite o Pestinha escreve, em primeira pessoa, como foi o dia dele.

O pet manda ao longo do dia um resumo do que viveu (POST /api/dia): quanto tempo passou em cada emoção e
quantas cutucadas, carinhos, castigos, fugas, travessuras, cochilos e pedidos do Hermes aconteceram.
À noite (DIARIO_HORA, no fuso da cidade escolhida), o Hermes transforma o resumo numa página de diário.
A página fica guardada (GET /api/diario) e um post-it avisa o pet de que tem página nova.

Uso manual (na pasta ponte/, com o ponte.env carregado):
    python -m ponte.diario            escreve a página de hoje, se já for a hora e ainda não tiver escrito
    python -m ponte.diario --agora    escreve a página de hoje já, para testar
"""
import datetime as dt
import json
import sqlite3
import sys
import threading
from zoneinfo import ZoneInfo

from . import acoes, hermes
from . import config as config_mod
from .eventos import Eventos
from .perfil import Perfil

DIARIO_HORA = dt.time(21, 0)
FUSO_PADRAO = "America/Sao_Paulo"
CONTAGENS = {                     # nome no resumo -> como contar para o Hermes
    "cutucadas": "levei {n} cutucada(s)",
    "carinhos": "ganhei {n} carinho(s)",
    "castigos": "fui posto de castigo {n} vez(es)",
    "fugas": "fugi do castigo {n} vez(es)",
    "travessuras": "aprontei {n} travessura(s)",
    "dispensadas": "{n} travessura(s) minha(s) foram dispensadas",
    "cochilos": "tirei {n} cochilo(s)",
    "protestos": "fiz {n} protesto(s) contra o cursor",
    "perguntas": "a Sheila me perguntou {n} coisa(s)",
    "obedeceu": "obedeci {n} pedido(s)",
    "recusou": "recusei {n} pedido(s)",
}
EMOCOES = ("observando", "contente", "feliz", "curioso", "bravo", "triste", "assustado", "dramatico", "dormindo")
MAX_PAGINA = 700


class Diario:
    def __init__(self, caminho):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(caminho), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS diario_dias (data TEXT PRIMARY KEY, resumo TEXT NOT NULL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS diario_paginas (data TEXT PRIMARY KEY, texto TEXT NOT NULL)")
        self._db.commit()

    def guardar_dia(self, data, resumo):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO diario_dias (data, resumo) VALUES (?, ?)",
                             (data, json.dumps(resumo, ensure_ascii=False)))
            self._db.commit()

    def dia(self, data):
        with self._lock:
            linha = self._db.execute("SELECT resumo FROM diario_dias WHERE data = ?", (data,)).fetchone()
        return json.loads(linha[0]) if linha else None

    def tem_pagina(self, data):
        with self._lock:
            return self._db.execute("SELECT 1 FROM diario_paginas WHERE data = ?", (data,)).fetchone() is not None

    def guardar_pagina(self, data, texto):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO diario_paginas (data, texto) VALUES (?, ?)", (data, texto))
            self._db.commit()

    def paginas(self, quantas=7):
        with self._lock:
            linhas = self._db.execute(
                "SELECT data, texto FROM diario_paginas ORDER BY data DESC LIMIT ?", (quantas,)).fetchall()
        return [{"data": d, "texto": t} for d, t in linhas]


def limpar_resumo(bruto):
    """Só o que o diário usa, com números sãos (o resumo vem do computador da pessoa)."""
    emocoes = {e: round(float(m), 1) for e, m in (bruto.get("emocoes") or {}).items()
               if e in EMOCOES and isinstance(m, (int, float)) and 0 <= m <= 24 * 60}
    contagens = {c: int(n) for c, n in (bruto.get("contagens") or {}).items()
                 if c in CONTAGENS and isinstance(n, (int, float)) and 0 <= n <= 10_000}
    return {"emocoes": emocoes, "contagens": contagens}


def fatos(resumo):
    """O dia do pet em frases simples (vira contexto para o Hermes)."""
    lista = []
    emocoes = sorted(((m, e) for e, m in resumo.get("emocoes", {}).items() if m >= 1), reverse=True)
    if emocoes:
        lista.append("passei o dia mais " + ", depois ".join(f"{e} ({round(m)} min)" for m, e in emocoes[:3]))
    for nome, frase in CONTAGENS.items():
        n = resumo.get("contagens", {}).get(nome, 0)
        if n:
            lista.append(frase.format(n=n))
    return lista


def escrever_pagina(cfg, data, resumo, perguntar=hermes.perguntar):
    lista = fatos(resumo)
    pedido = (f"[Página do seu diário de {data}. Exceção à regra do post-it: aqui você pode escrever até "
              "5 frases, em primeira pessoa, como um diário íntimo e dramático de bichinho. "
              f"O que aconteceu hoje: {'; '.join(lista) if lista else 'quase nada, o computador ficou quieto'}.]\n"
              "Escreva a página do diário. Não peça nenhuma ação.")
    try:
        texto, _ = acoes.separar_acao(perguntar(cfg, pedido))
    except hermes.HermesErro:
        texto = ""
    if not texto:
        texto = "Querido diário: hoje " + ("; ".join(lista) if lista else "foi um dia calmo") + "."
    return texto[:MAX_PAGINA]


def verificar(cfg, diario, perfil, eventos, agora_utc=None, forcar=False, perguntar=hermes.perguntar):
    """Escreve a página de hoje se já passou da hora e ainda não escreveu. Devolve a data escrita ou None."""
    lugar = perfil.ler() or {}
    agora = (agora_utc or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(lugar.get("fuso", FUSO_PADRAO)))
    data = agora.date().isoformat()
    resumo = diario.dia(data)
    if resumo is None or diario.tem_pagina(data):
        return None
    if not forcar and agora.time() < DIARIO_HORA:
        return None
    diario.guardar_pagina(data, escrever_pagina(cfg, data, resumo, perguntar))
    eventos.adicionar("falar", {"texto": "Escrevi no meu diário! Botão direito → Ler meu diário."})
    return data


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cfg = config_mod.carregar()
    data = verificar(cfg, Diario(cfg.banco), Perfil(cfg.banco), Eventos(cfg.banco), forcar="--agora" in argv)
    print(f"página do diário escrita ({data})" if data else "nada para escrever agora")


if __name__ == "__main__":
    main()
