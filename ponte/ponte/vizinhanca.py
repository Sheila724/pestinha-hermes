"""
VIZINHANÇA - os pets de pessoas diferentes se visitando.

Todas as pontes da VPS (a sua, a de outra pessoa, a da equipe) rodam com o mesmo usuário e usam o mesmo
arquivo SQLite (PONTE_VIZINHANCA, padrão ~/.config/pestinha/vizinhanca.db). Nada novo fica exposto na
internet: uma ponte só lê e escreve nesse arquivo.

  moradores   quem está em casa agora: cada pet que consultou a fila há pouco (casa, computador, nome,
              personagem e se recebe visitas)
  visitas     indo -> chegou -> fim -> contada   (ou sumiu, se ninguém abriu a porta)

Como uma visita anda:
  1. Você pede (menu "Visitar alguém..." ou "vai visitar a Talita" no balão): POST /api/visitar.
     A ponte de quem visita pede ao Hermes dela um cumprimento e uma despedida, e anota a visita "indo".
     O seu pet sai de casa.
  2. O pet de quem recebe consulta a fila: a ponte dele vê a visita "indo" e entrega um evento "visita"
     só para aquele computador. O visitante aparece na tela dele, brinca e vai embora.
  3. Quem recebeu avisa o fim (POST /api/visita/fim, com a emoção do pet dele): "fim".
  4. O seu pet consulta a fila: a sua ponte vê "fim" e entrega "voltou", com o que ele achou da visita.
     Se ninguém abriu a porta (o outro fechou o pet), ele volta sozinho dizendo isso.

Só passam nome, personagem e as falas. Nada da tela de ninguém.
"""
import hashlib
import sqlite3
import threading
import time
import unicodedata

ONLINE_S = 30                 # consultou a fila há menos que isso: está em casa (o pet consulta a cada 5 s)
DURACAO_S = 75                # quanto tempo o visitante fica brincando na tela do outro
ESPERA_PORTA_S = 60           # ninguém abriu a porta nesse tempo: volta para casa
ESPERA_FIM_S = DURACAO_S + 120
MAX_FALA = 120

CUMPRIMENTOS = ("Oi! Vim brincar um pouquinho.", "Toc toc! Cheguei de visita.", "Oi, vizinho! Passei para dar um alô.")
DESPEDIDAS = ("Tchau! Volto outro dia.", "Bom, deixa eu voltar pra casa. Tchau!", "Foi bom, hein! Até a próxima.")
VOLTOU = {
    "feliz": "Voltei! O pet {dono} me recebeu todo feliz.",
    "contente": "Voltei! Fui bem recebido na casa {dono}.",
    "curioso": "Voltei! O pet {dono} ficou me olhando curioso o tempo todo.",
    "bravo": "Voltei… o pet {dono} tava bravinho, mas eu fiz a minha parte.",
    "triste": "Voltei. O pet {dono} tava meio tristinho; acho que alegrei um pouco.",
    "dormindo": "Voltei! O pet {dono} tava dormindo, então fiquei quietinho.",
}
VOLTOU_PADRAO = "Voltei da casa {dono}! Foi divertido."
NINGUEM_ATENDEU = "Bati na porta {dono}, mas ninguém atendeu. Voltei."


def id_da_casa(banco):
    """Id curto e fixo de uma ponte (pelo caminho do banco dela)."""
    return hashlib.sha256(str(banco).encode()).hexdigest()[:12]


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def da(nome):
    """'da Talita' ou 'da equipe do suporte' (o pet fala de quem é a casa)."""
    return f"da {nome}" if nome else "do vizinho"


class Vizinhanca:
    def __init__(self, caminho, relogio=time.time):
        self._lock = threading.Lock()
        self._relogio = relogio
        self._db = sqlite3.connect(str(caminho), check_same_thread=False, timeout=10)
        self._db.execute("CREATE TABLE IF NOT EXISTS moradores ("
                         " casa TEXT NOT NULL, cliente TEXT NOT NULL, nome TEXT NOT NULL, pet TEXT NOT NULL,"
                         " recebe INTEGER NOT NULL, visto REAL NOT NULL, PRIMARY KEY (casa, cliente))")
        self._db.execute("CREATE TABLE IF NOT EXISTS visitas ("
                         " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                         " de_casa TEXT NOT NULL, de_cliente TEXT NOT NULL, de_nome TEXT NOT NULL, pet TEXT NOT NULL,"
                         " para_casa TEXT NOT NULL, para_cliente TEXT NOT NULL, para_nome TEXT NOT NULL,"
                         " cumprimento TEXT NOT NULL, despedida TEXT NOT NULL,"
                         " estado TEXT NOT NULL, criado REAL NOT NULL, mudou REAL NOT NULL, reacao TEXT NOT NULL DEFAULT '')")
        self._db.commit()

    # ---------- quem está em casa ----------

    def registrar(self, casa, cliente, nome, pet, recebe):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO moradores (casa, cliente, nome, pet, recebe, visto)"
                             " VALUES (?, ?, ?, ?, ?, ?)", (casa, cliente, nome, pet, 1 if recebe else 0, self._relogio()))
            self._db.commit()

    def em_casa(self, menos=None):
        """Quem consultou a fila há pouco: [{"id", "casa", "cliente", "nome", "pet", "recebe"}], sem `menos`."""
        limite = self._relogio() - ONLINE_S
        with self._lock:
            linhas = self._db.execute("SELECT casa, cliente, nome, pet, recebe FROM moradores WHERE visto >= ?"
                                      " ORDER BY nome", (limite,)).fetchall()
        return [{"id": f"{c}:{k}", "casa": c, "cliente": k, "nome": n, "pet": p, "recebe": bool(r)}
                for c, k, n, p, r in linhas if (c, k) != menos]

    def achar(self, texto, menos=None):
        """O vizinho cujo nome aparece no texto ("vai visitar a Talita"), ou None."""
        alvo = _sem_acento(texto)
        for v in sorted(self.em_casa(menos), key=lambda v: -len(v["nome"])):
            primeiro = _sem_acento(v["nome"]).split(" (")[0]
            if primeiro and primeiro in alvo:
                return v
        return None

    # ---------- visitas ----------

    def ocupado(self, casa, cliente):
        """Já está visitando alguém ou recebendo visita."""
        recente = self._relogio() - ESPERA_FIM_S                     # visita perdida não prende ninguém
        with self._lock:
            return self._db.execute(
                "SELECT 1 FROM visitas WHERE estado IN ('indo', 'chegou') AND mudou >= ? AND"
                " ((de_casa = ? AND de_cliente = ?) OR (para_casa = ? AND para_cliente = ?))",
                (recente, casa, cliente, casa, cliente)).fetchone() is not None

    def comecar(self, de, para, pet, cumprimento, despedida):
        """`de` e `para`: (casa, cliente, nome). Devolve o id da visita."""
        agora = self._relogio()
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO visitas (de_casa, de_cliente, de_nome, pet, para_casa, para_cliente, para_nome,"
                " cumprimento, despedida, estado, criado, mudou) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'indo', ?, ?)",
                (*de, pet, *para, cumprimento[:MAX_FALA], despedida[:MAX_FALA], agora, agora))
            self._db.commit()
            return cur.lastrowid

    def chegadas(self, casa, cliente):
        """Visitas chegando nesta casa e computador: passam a "chegou" e saem uma vez só."""
        with self._lock:
            linhas = self._db.execute(
                "SELECT id, de_nome, pet, cumprimento, despedida FROM visitas"
                " WHERE estado = 'indo' AND para_casa = ? AND para_cliente = ?", (casa, cliente)).fetchall()
            for (id_, *_resto) in linhas:
                self._db.execute("UPDATE visitas SET estado = 'chegou', mudou = ? WHERE id = ?", (self._relogio(), id_))
            self._db.commit()
        return [{"visita": i, "nome": n, "pet": p, "cumprimento": c, "despedida": d, "duracao": DURACAO_S}
                for i, n, p, c, d in linhas]

    def terminar(self, id_, casa, cliente, reacao):
        """Quem recebeu avisa o fim (só vale para uma visita que chegou nele)."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE visitas SET estado = 'fim', reacao = ?, mudou = ? WHERE id = ? AND estado = 'chegou'"
                " AND para_casa = ? AND para_cliente = ?", (str(reacao)[:20], self._relogio(), id_, casa, cliente))
            self._db.commit()
            return cur.rowcount == 1

    def retornos(self, casa, cliente):
        """
        O que contar a quem foi visitar: visitas que acabaram, que ninguém atendeu ou que se perderam
        (o outro fechou o pet no meio). Cada uma sai uma vez só, como texto de post-it.
        """
        agora = self._relogio()
        falas = []
        with self._lock:
            linhas = self._db.execute(
                "SELECT id, para_nome, estado, criado, mudou, reacao FROM visitas"
                " WHERE de_casa = ? AND de_cliente = ? AND estado IN ('indo', 'chegou', 'fim')",
                (casa, cliente)).fetchall()
            for id_, para_nome, estado, criado, mudou, reacao in linhas:
                if estado == "fim":
                    fala = VOLTOU.get(reacao, VOLTOU_PADRAO).format(dono=da(para_nome))
                elif estado == "indo" and agora - criado > ESPERA_PORTA_S:
                    fala = NINGUEM_ATENDEU.format(dono=da(para_nome))
                elif estado == "chegou" and agora - mudou > ESPERA_FIM_S:
                    fala = VOLTOU_PADRAO.format(dono=da(para_nome))
                else:
                    continue
                self._db.execute("UPDATE visitas SET estado = 'contada', mudou = ? WHERE id = ?", (agora, id_))
                falas.append(fala)
            self._db.execute("DELETE FROM visitas WHERE estado = 'contada' AND mudou < ?", (agora - 7 * 86400,))
            self._db.commit()
        return falas
