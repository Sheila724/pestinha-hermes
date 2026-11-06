"""
CONVERSA - memória curta para o Pestinha conversar em vez de responder perguntas soltas.

Guarda as últimas trocas (o que a pessoa disse e o que o pet respondeu), inclusive as falas que o pet
mandou sozinho (avisos de clima, diário), para dar para responder a elas ("e amanhã?").
Trocas mais velhas que ESQUECE_DEPOIS são esquecidas: uma conversa nova começa limpa.

No pet da equipe, cada computador tem a sua conversa (`cliente`); as falas que o pet manda para todos
(avisos, lembretes, diário) ficam com cliente "" e entram na conversa de todo mundo.
"""
import sqlite3
import threading
import time

MAX_TROCAS = 8                   # mensagens (pessoa + pet) mandadas ao Hermes como histórico
ESQUECE_DEPOIS = 30 * 60         # segundos sem conversa até esquecer


class Conversa:
    def __init__(self, caminho, relogio=time.time):
        self._lock = threading.Lock()
        self._relogio = relogio
        self._db = sqlite3.connect(str(caminho), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS conversa ("
                         " id INTEGER PRIMARY KEY AUTOINCREMENT, criado REAL NOT NULL,"
                         " papel TEXT NOT NULL, texto TEXT NOT NULL)")
        colunas = [linha[1] for linha in self._db.execute("PRAGMA table_info(conversa)")]
        if "cliente" not in colunas:                        # banco de antes do pet da equipe
            self._db.execute("ALTER TABLE conversa ADD COLUMN cliente TEXT NOT NULL DEFAULT ''")
        self._db.commit()

    def anotar(self, papel, texto, cliente=""):
        """papel: 'user' (a pessoa) ou 'assistant' (o pet). `cliente` "" é fala para todos."""
        if papel not in ("user", "assistant") or not str(texto).strip():
            return
        with self._lock:
            self._db.execute("INSERT INTO conversa (criado, papel, texto, cliente) VALUES (?, ?, ?, ?)",
                             (self._relogio(), papel, str(texto).strip(), cliente))
            self._db.execute("DELETE FROM conversa WHERE id NOT IN "
                             "(SELECT id FROM conversa ORDER BY id DESC LIMIT 400)")
            self._db.commit()

    def recente(self, cliente=""):
        """
        As últimas trocas ainda frescas deste computador (e as falas para todos), no formato de mensagens
        do Hermes, mais antiga primeiro.
        """
        limite = self._relogio() - ESQUECE_DEPOIS
        with self._lock:
            linhas = self._db.execute(
                "SELECT papel, texto FROM conversa WHERE criado >= ? AND cliente IN (?, '') "
                "ORDER BY id DESC LIMIT ?", (limite, cliente, MAX_TROCAS)).fetchall()
        return [{"role": p, "content": t} for p, t in reversed(linhas)]

    def esquecer(self, cliente=""):
        """Conversa nova para este computador (sem cliente: apaga tudo)."""
        with self._lock:
            if cliente:
                self._db.execute("DELETE FROM conversa WHERE cliente = ?", (cliente,))
            else:
                self._db.execute("DELETE FROM conversa")
            self._db.commit()
