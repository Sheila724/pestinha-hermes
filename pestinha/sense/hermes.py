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


def formatar_data(iso):
    """'2026-11-04' -> '04/11/2026' (o resto passa como veio)."""
    partes = str(iso).split("-")
    return "/".join(reversed(partes)) if len(partes) == 3 else str(iso)


def carregar_config(caminho, avisar=None):
    """
    {"url", "token"} de memory/hermes.json, ou None se não existe ou está incompleto.
    Aceita o arquivo com BOM (o Set-Content -Encoding utf8 do PowerShell 5.1 grava assim).
    `avisar(texto)` é chamado quando o arquivo existe mas não dá para usar, para não desligar calado.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as erro:
        if avisar:
            avisar(f"[hermes] {caminho.name} ilegível, Hermes desligado: {erro}")
        return None
    url = str(dados.get("url", "")).strip().rstrip("/") if isinstance(dados, dict) else ""
    token = str(dados.get("token", "")).strip() if isinstance(dados, dict) else ""
    if not url.startswith(("https://", "http://")) or not token:
        if avisar:
            avisar(f"[hermes] {caminho.name} precisa de \"url\" (https://...) e \"token\"; Hermes desligado")
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
        self.perfil = None              # cidade e horários escolhidos nesta sessão (para preencher o menu)
        self._ultimo = self._ler_ultimo()

    @classmethod
    def de_arquivo(cls, config_json, arquivo_ultimo, avisar=None, **kw):
        cfg = carregar_config(config_json, avisar)
        return cls(cfg["url"], cfg["token"], arquivo_ultimo, **kw) if cfg else None

    # ---------- o que o app usa ----------

    def iniciar(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._laco, name="hermes", daemon=True)
            self._thread.start()

    def parar(self):
        self._parar.set()

    def coletar(self):
        """
        Tudo o que chegou desde a última chamada, em ordem, como (tipo, texto):
          falar     fala que a VPS mandou sozinha (aviso, diário)     resposta / erro   da sua pergunta
          efeito    animação para a fala seguinte                       acao              pedido ao corpo
          info      confirmação local (cidade salva, conversa nova)     diario            páginas do diário
          humor     (ainda sem efeito)
        """
        itens = []
        while True:
            try:
                itens.append(self._chegou.get_nowait())
            except queue.Empty:
                return itens

    def perguntar(self, texto, estado=None, respondendo=""):
        """
        Manda a pergunta em segundo plano; a resposta chega depois em coletar() como "resposta" ou "erro"
        (e "acao", se o Hermes pediu algo ao corpo). `estado` conta ao Hermes como o pet está agora;
        `respondendo` é o post-it dele que você está respondendo.
        """
        texto = str(texto).strip()[:500]
        if not texto:
            return
        threading.Thread(target=self._perguntar, args=(texto, estado, str(respondendo or "").strip()[:500]),
                         name="hermes-pergunta", daemon=True).start()

    def configurar_perfil(self, cidade, entrada, saida):
        """
        Escolhe a cidade e os horários dos avisos do lado de fora (clima, sexta-feira, feriado).
        Em segundo plano; a confirmação chega em coletar() como "resposta" (ou "erro").
        """
        corpo = {"cidade": str(cidade).strip()[:80], "entrada": str(entrada).strip(), "saida": str(saida).strip()}
        if corpo["cidade"]:
            threading.Thread(target=self._configurar_perfil, args=(corpo,), name="hermes-perfil", daemon=True).start()

    def enviar_dia(self, resumo, esperar=False):
        """Manda o resumo do dia (para o diário). `esperar` segura até 3 s, para dar tempo ao fechar o app."""
        t = threading.Thread(target=self._enviar_dia, args=(resumo,), name="hermes-dia", daemon=True)
        t.start()
        if esperar:
            t.join(timeout=3.0)

    def esquecer_conversa(self):
        """Começa uma conversa nova: a memória curta da ponte some. Confirma com um post-it."""
        threading.Thread(target=self._esquecer, name="hermes-esquecer", daemon=True).start()

    def _esquecer(self):
        try:
            self._pedido("/api/conversa/esquecer", {})
            self._chegou.put(("info", "Pronto, página virada! Sobre o que a gente conversa agora?"))
        except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
            self._chegou.put(("info", "Não consegui falar com a VPS."))

    def ler_diario(self):
        """Busca as últimas páginas do diário; chegam em coletar() como ("diario", texto) ou ("erro", ...)."""
        threading.Thread(target=self._ler_diario, name="hermes-diario", daemon=True).start()

    # ---------- por dentro ----------

    def _enviar_dia(self, resumo):
        try:
            self._pedido("/api/dia", resumo)
        except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
            pass                            # tenta de novo no próximo envio; o resumo é cumulativo

    def _ler_diario(self):
        try:
            paginas = self._pedido("/api/diario?quantas=5")["paginas"]
        except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
            self._chegou.put(("info", "Não consegui buscar meu diário agora."))
            return
        if not paginas:
            self._chegou.put(("info", "Meu diário ainda está em branco. Hoje à noite eu escrevo!"))
            return
        texto = "\n\n".join(f"{formatar_data(p['data'])}\n{p['texto']}" for p in paginas)
        self._chegou.put(("diario", texto))

    def _configurar_perfil(self, corpo):
        try:
            dados = self._pedido("/api/perfil", corpo)
            self.perfil = dados
            self._chegou.put(("info", encurtar(
                f"Agora eu olho o céu de {dados['nome']}! Aviso entre {dados['entrada']} e {dados['saida']}.")))
        except urllib.error.HTTPError as erro:
            self._chegou.put(("info", {404: "Não achei essa cidade. Tenta 'Cidade, UF' ou 'Cidade, País'.",
                                       422: "Horário estranho… use HH:MM, a entrada antes da saída."}
                              .get(erro.code, "A VPS não aceitou a cidade agora.")))
        except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
            self._chegou.put(("info", "Não consegui falar com a VPS."))

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
                    self._efeitos(ev.get("efeitos"))
                    self._chegou.put(("falar", encurtar(ev["texto"])))
                elif ev.get("tipo") == "humor" and ev.get("humor"):
                    self._chegou.put(("humor", str(ev["humor"])))
                elif ev.get("tipo") == "acao" and ev.get("acao"):
                    self._chegou.put(("acao", str(ev["acao"])))
        if primeira_vez or ultimo < self._ultimo:      # 1ª conexão, ou o banco da ponte foi recriado
            novo = ultimo
        else:                                           # vem no máximo 50 por vez: avança só até o último lido
            novo = max([self._ultimo] + [int(ev.get("id", 0)) for ev in eventos])
        if novo != self._ultimo or primeira_vez:
            self._ultimo = novo
            self._gravar_ultimo()
        return True

    def _perguntar(self, texto, estado=None, respondendo=""):
        corpo = {"texto": texto}
        if estado:
            corpo["estado"] = estado
        if respondendo:
            corpo["respondendo"] = respondendo
        try:
            dados = self._pedido("/api/perguntar", corpo, timeout=TIMEOUT_PERGUNTA)
            resposta = dados["resposta"]
            self._efeitos(dados.get("efeitos"))
            self._chegou.put(("resposta", encurtar(resposta)))
            if dados.get("acao"):
                self._chegou.put(("acao", str(dados["acao"])))
        except urllib.error.HTTPError as erro:
            self._chegou.put(("erro", "Meu cérebro não respondeu agora…" if erro.code >= 500
                              else "A VPS não me reconheceu (token?)."))
        except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
            self._chegou.put(("erro", "Não consegui falar com a VPS."))

    def _efeitos(self, nomes):
        """Animações pedidas pela ponte (chuva, calor, frio, festa, diario), antes da fala que elas acompanham."""
        if isinstance(nomes, list):
            for nome in nomes[:4]:
                if isinstance(nome, str) and nome:
                    self._chegou.put(("efeito", nome[:20]))

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
