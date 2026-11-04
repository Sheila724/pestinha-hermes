"""Fila de eventos para o Pestinha, gravada em SQLite (sobrevive a reinícios da ponte).

Cada evento tem um id crescente. O pet pergunta "o que tem depois do id N?" e guarda o
último id que viu; assim ele não perde nem repete mensagens, mesmo ficando um tempo offline.
"""
import json
import sqlite3
import threading
import time

TIPOS = ("falar", "humor")
MAX_POR_CONSULTA = 50
MAX_GUARDADOS = 1000          # os mais antigos são apagados


class Eventos:
    def __init__(self, caminho):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(caminho), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS eventos ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " criado REAL NOT NULL,"
            " tipo TEXT NOT NULL,"
            " dados TEXT NOT NULL)"
        )
        self._db.commit()

    def adicionar(self, tipo, dados):
        if tipo not in TIPOS:
            raise ValueError(f"tipo desconhecido: {tipo}")
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO eventos (criado, tipo, dados) VALUES (?, ?, ?)",
                (time.time(), tipo, json.dumps(dados, ensure_ascii=False)),
            )
            self._db.execute(
                "DELETE FROM eventos WHERE id <= ?", (cur.lastrowid - MAX_GUARDADOS,)
            )
            self._db.commit()
            return cur.lastrowid

    def depois_de(self, desde):
        with self._lock:
            linhas = self._db.execute(
                "SELECT id, criado, tipo, dados FROM eventos WHERE id > ? ORDER BY id LIMIT ?",
                (desde, MAX_POR_CONSULTA),
            ).fetchall()
            ultimo = self._db.execute("SELECT COALESCE(MAX(id), 0) FROM eventos").fetchone()[0]
        eventos = [
            {"id": i, "criado": c, "tipo": t, **json.loads(d)} for i, c, t, d in linhas
        ]
        return eventos, ultimo
