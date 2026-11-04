"""Cidade e horários escolhidos pela pessoa (pelo menu do pet), e o que já foi avisado hoje. No mesmo SQLite da fila."""
import json
import re
import sqlite3
import threading

HORA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
PADRAO = {"entrada": "08:00", "saida": "18:00"}


def hora_valida(texto):
    m = HORA.match(str(texto).strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


class Perfil:
    def __init__(self, caminho):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(caminho), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS perfil (chave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS avisos_enviados (chave TEXT PRIMARY KEY)")
        self._db.commit()

    def ler(self):
        """O perfil salvo (dict) ou None se ninguém escolheu cidade ainda."""
        with self._lock:
            linha = self._db.execute("SELECT valor FROM perfil WHERE chave = 'atual'").fetchone()
        return json.loads(linha[0]) if linha else None

    def gravar(self, dados):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO perfil (chave, valor) VALUES ('atual', ?)",
                             (json.dumps(dados, ensure_ascii=False),))
            self._db.commit()

    def marcar(self, chave):
        """True na primeira vez que essa chave (ex.: '2026-11-04:saida') é marcada; False se já foi."""
        with self._lock:
            cur = self._db.execute("INSERT OR IGNORE INTO avisos_enviados (chave) VALUES (?)", (chave,))
            self._db.commit()
            return cur.rowcount == 1
