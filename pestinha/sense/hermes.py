"""
Ouvido do Pestinha para o Hermes Agent, que mora numa VPS atrás da ponte (pasta ponte/ do repositório).

Sem Qt: a rede roda em threads próprias e o app só recolhe o que chegou com `coletar()`, num relógio
do Qt. Assim uma VPS lenta ou fora do ar nunca trava o pet.

Configuração em memory/hermes.json (fica fora do Git):
    {"url": "https://pestinha.exemplo.com.br", "token": "<PONTE_TOKEN>"}
Sem esse arquivo, o Hermes fica desligado e o pet funciona como sempre.
"""
import json
import queue
import threading
import urllib.error
import urllib.request
from pathlib import Path

INTERVALO = 5.0             # segundos entre consultas, com tudo bem
INTERVALO_MAX = 60.0        # com a VPS fora do ar, espera dobra até aqui
TIMEOUT_EVENTOS = 15.0
TIMEOUT_PERGUNTA = 150.0    # o agente pensa e usa ferramentas antes de responder
MAX_TEXTO = 180             # cabe no post-it grande (NOTE_SIZE_FALA)


def encurtar(texto, limite=MAX_TEXTO):
    """Texto de uma linha só, cortado com reticências se não couber no post-it."""
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def carregar_config(caminho):
    """{"url", "token"} de memory/hermes.json, ou None se não existe ou está incompleto."""
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    url = str(dados.get("url", "")).strip().rstrip("/")
    token = str(dados.get("token", "")).strip()
    if not url.startswith(("https://", "http://")) or not token:
        return None
    return {"url": url, "token": token}


class ClienteHermes:
    """Consulta a fila de eventos da ponte e faz perguntas, sempre fora da thread do Qt."""

    def __init__(self, url, token, arquivo_ultimo, intervalo=INTERVALO):
        self.url = url.rstrip("/")
        self._token = token
        self._arquivo_ultimo = Path(arquivo_ultimo)
        self._intervalo = intervalo
        self._chegou = queue.Queue()
        self._parar = threading.Event()
        self._thread = None
        self.online = None              # None: ainda não sabe; True/False depois da primeira consulta
        self._ultimo = self._ler_ultimo()

    @classmethod
    def de_arquivo(cls, config_json, arquivo_ultimo, **kw):
        cfg = carregar_config(config_json)
        return cls(cfg["url"], cfg["token"], arquivo_ultimo, **kw) if cfg else None

    # ---------- o que o app usa ----------

    def iniciar(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._laco, name="hermes", daemon=True)
            self._thread.start()

    def parar(self):
        self._parar.set()

    def coletar(self):
        """Tudo o que chegou desde a última chamada: lista de ("falar"|"humor"|"resposta"|"erro", texto)."""
        itens = []
        while True:
            try:
                itens.append(self._chegou.get_nowait())
            except queue.Empty:
                return itens

    def perguntar(self, texto):
        """Manda a pergunta em segundo plano; a resposta chega depois em coletar() como "resposta" ou "erro"."""
        texto = str(texto).strip()[:500]
        if not texto:
            return
        threading.Thread(target=self._perguntar, args=(texto,), name="hermes-pergunta", daemon=True).start()

    # ---------- por dentro ----------

    def _pedido(self, caminho, corpo=None, timeout=TIMEOUT_EVENTOS):
        dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
        req = urllib.request.Request(self.url + caminho, data=dados, method="POST" if dados else "GET")
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("User-Agent", "Pestinha")
        if dados:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def consultar(self):
        """Uma consulta à fila. Devolve True se a ponte respondeu."""
        try:
            dados = self._pedido(f"/api/eventos?desde={self._ultimo}")
            eventos, ultimo = dados["eventos"], int(dados["ultimo"])
        except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
            self.online = False
            return False
        self.online = True
        primeira_vez = self._ultimo == 0 and not self._arquivo_ultimo.exists()
        if not primeira_vez:                # na primeira conexão não despeja o histórico antigo na tela
            for ev in eventos:
                if ev.get("tipo") == "falar" and ev.get("texto"):
                    self._chegou.put(("falar", encurtar(ev["texto"])))
                elif ev.get("tipo") == "humor" and ev.get("humor"):
                    self._chegou.put(("humor", str(ev["humor"])))
        if primeira_vez or ultimo < self._ultimo:      # 1ª conexão, ou o banco da ponte foi recriado
            novo = ultimo
        else:                                           # vem no máximo 50 por vez: avança só até o último lido
            novo = max([self._ultimo] + [int(ev.get("id", 0)) for ev in eventos])
        if novo != self._ultimo or primeira_vez:
            self._ultimo = novo
            self._gravar_ultimo()
        return True

    def _perguntar(self, texto):
        try:
            resposta = self._pedido("/api/perguntar", {"texto": texto}, timeout=TIMEOUT_PERGUNTA)["resposta"]
            self._chegou.put(("resposta", encurtar(resposta)))
        except urllib.error.HTTPError as erro:
            self._chegou.put(("erro", "Meu cérebro não respondeu agora…" if erro.code >= 500
                              else "A VPS não me reconheceu (token?)."))
        except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
            self._chegou.put(("erro", "Não consegui falar com a VPS."))

    def _laco(self):
        espera = self._intervalo
        while not self._parar.is_set():
            espera = self._intervalo if self.consultar() else min(espera * 2, INTERVALO_MAX)
            self._parar.wait(espera)

    def _ler_ultimo(self):
        try:
            return max(0, int(self._arquivo_ultimo.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            return 0

    def _gravar_ultimo(self):
        try:
            self._arquivo_ultimo.parent.mkdir(parents=True, exist_ok=True)
            self._arquivo_ultimo.write_text(str(self._ultimo), encoding="utf-8")
        except OSError:
            pass                            # sem permissão: só repete eventos se reiniciar
