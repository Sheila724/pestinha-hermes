"""
Ponte entre o Pestinha (no computador) e o Hermes Agent (na VPS).

Rotas:
  GET  /saude              sem token; para monitoramento
  GET  /api/eventos        o pet pergunta "tem algo novo depois do id N?" (polling)
  POST /api/perguntar      você clica no pet, digita, e o Hermes responde (e marca lembretes, se pedir)
  POST /api/conversa/esquecer  começa uma conversa nova (a memória curta some)
  GET  /api/vizinhos       quem está em casa para visitar (pets de outras pessoas nesta VPS)
  POST /api/visitar        o pet sai de casa e vai visitar outro (ponte/vizinhanca.py)
  POST /api/visita/fim     quem recebeu a visita avisa que o visitante foi embora
  GET  /api/perfil         cidade e horários escolhidos (para os avisos do lado de fora)
  POST /api/perfil         escolhe a cidade ("Franca, SP", "Lisboa") e os horários de entrada e saída
  POST /api/dia            o pet manda o resumo do dia dele (emoções e contagens) para o diário
  GET  /api/diario         as últimas páginas do diário que o pet escreveu
  POST /interno/eventos    só da própria VPS (cron do Hermes, scripts): põe uma fala, humor ou ação na fila

Os lembretes vencidos viram falas na hora em que o pet consulta a fila (ponte/lembretes.py).

Tudo em /api e /interno exige "Authorization: Bearer <PONTE_TOKEN>".
A ponte escuta só em 127.0.0.1; quem a expõe na internet (com HTTPS) é o Caddy.
"""
import datetime as dt
import hmac
import logging
import random
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from . import config as config_mod
from . import acoes, clima, hermes
from . import lembretes as lemb
from . import vizinhanca as viz
from .conversa import Conversa
from .diario import Diario, limpar_resumo
from .eventos import Eventos
from .mundo import FUSO_PADRAO, Mundo
from .perfil import PADRAO, Perfil, hora_valida

log = logging.getLogger("ponte")
VISITAR = re.compile(r"\bvisit", re.IGNORECASE)
PET_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
SAIU_DE_CASA = ("Fui!", "Já volto!", "Partiu visita!")
SOBRE_O_TEMPO = re.compile(r"chuv|chov|tempo|clima|calor|frio|sol\b|guarda.chuva|temperatura|graus|nublad|garoa",
                           re.IGNORECASE)
LOCAIS = {"127.0.0.1", "::1", "testclient"}
ID_COMPUTADOR = re.compile(r"[0-9a-f]{32}")


def nome_de_usuario(bruto):
    """'sheila.alves' -> 'Sheila', 'talita_souza' -> 'Talita' (o usuário do Windows de quem pergunta)."""
    usuario = str(bruto or "").strip().split("\\")[-1]                 # "DOMINIO\\joao" -> "joao"
    primeiro = re.split(r"[._\-\s@]+", usuario)
    nome = next((p for p in primeiro if p.isalpha()), "")
    return nome[:20].capitalize()


NAO_ENTENDI_LEMBRETE = ("Não entendi para quando é o lembrete. Fala tipo “me lembra às 16h de ligar” "
                        "ou “daqui a 30 min”.")


class EstadoPet(BaseModel):
    emocao: str = Field(default="", max_length=20)
    energia: float | None = Field(default=None, ge=0, le=1)
    dormindo: bool = False


class Pergunta(BaseModel):
    texto: str = Field(min_length=1, max_length=500)
    estado: EstadoPet | None = None
    respondendo: str = Field(default="", max_length=500)   # o post-it do pet que a pessoa está respondendo


class NovoPerfil(BaseModel):
    cidade: str = Field(min_length=2, max_length=80)
    entrada: str = Field(default=PADRAO["entrada"], max_length=5)
    saida: str = Field(default=PADRAO["saida"], max_length=5)


class ResumoDia(BaseModel):
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    emocoes: dict = Field(default_factory=dict)
    contagens: dict = Field(default_factory=dict)


class Visitar(BaseModel):
    para: str = Field(min_length=3, max_length=80)          # "casa:computador", de GET /api/vizinhos


class FimDaVisita(BaseModel):
    id: int = Field(ge=1)
    emocao: str = Field(default="", max_length=20)


class NovoEvento(BaseModel):
    tipo: str = "falar"
    texto: str = Field(default="", max_length=500)
    humor: str = Field(default="", max_length=30)
    acao: str = Field(default="", max_length=20)


def criar_app(cfg=None, geocodificar=clima.geocodificar, buscar_previsao=clima.previsao, relogio=time.time):
    cfg = cfg or config_mod.carregar()
    eventos = Eventos(cfg.banco)
    perfil = Perfil(cfg.banco)
    diario = Diario(cfg.banco)
    conversa = Conversa(cfg.banco)
    mundo = Mundo(perfil, buscar_previsao)
    lembretes = lemb.Lembretes(cfg.banco, relogio)
    vizinhos = viz.Vizinhanca(cfg.vizinhanca, relogio) if cfg.vizinhanca else None
    casa = viz.id_da_casa(Path(cfg.banco).resolve())

    def fuso():
        return (perfil.ler() or {}).get("fuso") or FUSO_PADRAO

    def disparar_lembretes():
        """Os lembretes que venceram viram falas na fila (com o efeito que acorda o pet e toca o despertador)."""
        vencidos = lembretes.vencidos()
        for r in vencidos:
            fala = lemb.fala_do_lembrete(r, fuso(), relogio())
            eventos.adicionar("falar", {"texto": fala, "efeitos": ["lembrete"]})
            conversa.anotar("assistant", fala)                  # dá para responder: "adia 10 min"

    def quem_e(request):
        """(id do computador, nome de quem fala): o nome só no pet da equipe."""
        cliente = request.headers.get("x-pestinha-cliente", "").strip().lower()
        cliente = cliente if ID_COMPUTADOR.fullmatch(cliente) else ""
        nome = nome_de_usuario(request.headers.get("x-pestinha-quem", "")) if cfg.equipe else ""
        return cliente, nome

    def morador(request):
        """(cliente, nome para os vizinhos, personagem, recebe visitas) de quem fez o pedido."""
        cliente, nome = quem_e(request)
        pet = request.headers.get("x-pestinha-pet", "").strip().lower()
        pet = pet if PET_ID.fullmatch(pet) else "bryan"
        exibido = f"{nome or 'Alguém'} ({cfg.dono})" if cfg.equipe else cfg.dono
        return cliente, exibido, pet, request.headers.get("x-pestinha-visitas", "") == "1"

    def falas_da_visita(para_nome):
        """(cumprimento, despedida) no jeito deste pet, pedidos ao Hermes; sem Hermes, frases prontas."""
        pedido = (f"[Visita] Você está indo agora visitar o pet {viz.da(para_nome)}, na tela dela. Escreva duas "
                  "falas curtas separadas por uma barra vertical: o que você diz ao chegar e o que diz ao ir embora.")
        try:
            partes = [acoes.limpar(x) for x in hermes.perguntar(cfg, pedido, []).split("|")]
        except hermes.HermesErro:
            partes = []
        if len(partes) >= 2 and partes[0] and partes[1]:
            return partes[0], partes[1]
        return random.choice(viz.CUMPRIMENTOS), random.choice(viz.DESPEDIDAS)

    def mexer_na_vizinhanca(request):
        """A cada consulta: registra quem está em casa e põe na fila as chegadas e os retornos de visita."""
        if vizinhos is None:
            return
        cliente, exibido, pet, recebe = morador(request)
        if not cliente:
            return                                   # pet antigo, sem id: não visita nem recebe
        vizinhos.registrar(casa, cliente, exibido, pet, recebe)
        for v in vizinhos.chegadas(casa, cliente):
            eventos.adicionar("visita", {**v, "para": cliente})
        for fala in vizinhos.retornos(casa, cliente):
            eventos.adicionar("voltou", {"texto": fala, "para": cliente})

    def comecar_visita(request, alvo):
        """Começa a visita a `alvo` (um item de em_casa). Devolve o nome ou levanta HTTPException."""
        cliente, exibido, pet, _recebe = morador(request)
        if vizinhos is None or not cliente:
            raise HTTPException(status_code=409, detail="Este pet ainda não sabe visitar ninguém.")
        if not alvo["recebe"]:
            raise HTTPException(status_code=409, detail=f"A casa {viz.da(alvo['nome'])} não está recebendo visitas.")
        if vizinhos.ocupado(casa, cliente):
            raise HTTPException(status_code=409, detail="Eu já estou no meio de uma visita!")
        if vizinhos.ocupado(alvo["casa"], alvo["cliente"]):
            raise HTTPException(status_code=409, detail=f"O pet {viz.da(alvo['nome'])} já está com visita.")
        cumprimento, despedida = falas_da_visita(alvo["nome"])
        vizinhos.comecar((casa, cliente, exibido), (alvo["casa"], alvo["cliente"], alvo["nome"]), pet,
                         cumprimento, despedida)
        return alvo["nome"]

    def marcar_lembretes(pedidos, cancelar, quem=""):
        """Cria e cancela o que o Hermes pediu. Devolve (frase de confirmação, se mexeu em algum)."""
        agora = dt.datetime.fromtimestamp(relogio(), ZoneInfo(fuso()))
        marcados, frases, mexeu = [], [], False
        for quando, oque in pedidos[:3]:
            alvo = lemb.interpretar(quando, agora)
            if alvo is None:
                continue
            mexeu = True
            if lembretes.criar(alvo, oque, quem) is None:
                frases.append("Mas já tenho lembrete demais anotado!")
                break
            marcados.append(lemb.descrever_horario(alvo, agora))
        if marcados:
            frases.insert(0, f"Anotado para {' e '.join(marcados)}.")
        for id_ in cancelar[:5]:
            mexeu = True
            if not lembretes.cancelar(id_):
                frases.append("Esse lembrete eu não achei.")
        return " ".join(frases), mexeu
    app = FastAPI(title="Ponte do Pestinha", docs_url=None, redoc_url=None, openapi_url=None)

    def autorizado(request: Request):
        cabecalho = request.headers.get("authorization", "")
        enviado = cabecalho[7:] if cabecalho.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(enviado.encode(), cfg.token.encode()):
            raise HTTPException(status_code=401, detail="token inválido")

    def so_local(request: Request):
        # Atrás do Caddy toda conexão vem de 127.0.0.1; por isso o Caddyfile bloqueia /interno/*.
        if request.client is None or request.client.host not in LOCAIS:
            raise HTTPException(status_code=403, detail="só da própria VPS")

    @app.get("/saude")
    def saude():
        return {"ok": True}

    @app.get("/api/eventos", dependencies=[Depends(autorizado)])
    def listar(request: Request, desde: int = Query(default=0, ge=0)):
        disparar_lembretes()
        mexer_na_vizinhanca(request)
        lista, ultimo = eventos.depois_de(desde)
        return {"eventos": lista, "ultimo": ultimo}

    @app.post("/api/perguntar", dependencies=[Depends(autorizado)])
    def perguntar(p: Pergunta, request: Request):
        cliente, nome = quem_e(request)
        historico = conversa.recente(cliente)
        linhas = [mundo.contexto(), lembretes.contexto(fuso()),
                  acoes.descrever_estado(p.estado.model_dump() if p.estado else None),
                  f"[Quem está falando: {nome}]" if nome else ""]
        respondendo = p.respondendo.strip()
        lembra = any(m["role"] == "assistant" and m["content"] == respondendo for m in historico)
        if respondendo and not lembra:              # o post-it é antigo ou a memória curta já esqueceu
            linhas.append(f'[Respondendo ao seu post-it: "{respondendo}"]')
        linhas.append(p.texto)
        try:
            bruta = hermes.perguntar(cfg, "\n".join(x for x in linhas if x), historico)
        except hermes.HermesErro as erro:
            log.warning("Hermes falhou: %s", erro)
            raise HTTPException(status_code=502, detail="o Hermes não respondeu agora")
        sem_lembretes, pedidos, cancelar = lemb.separar(bruta)
        texto, acao = acoes.separar_acao(sem_lembretes)
        confirmacao, mexeu = marcar_lembretes(pedidos, cancelar, nome)
        if confirmacao:
            texto = f"{texto} {confirmacao}".strip()
        elif not mexeu and lemb.pediu_lembrete(p.texto) and not texto.rstrip().endswith("?"):
            texto = NAO_ENTENDI_LEMBRETE                    # nunca promete lembrar sem ter marcado
        if respondendo and not lembra:
            conversa.anotar("assistant", respondendo, cliente)
        conversa.anotar("user", p.texto, cliente)
        conversa.anotar("assistant", texto, cliente)
        resposta = {"resposta": texto or "…"}
        if acao:
            resposta["acao"] = acao
        if vizinhos is not None and VISITAR.search(p.texto):     # "vai visitar a Talita"
            cliente_eu = quem_e(request)[0]
            alvo = vizinhos.achar(p.texto, menos=(casa, cliente_eu))
            if alvo is None:
                resposta["resposta"] = f"{resposta['resposta']} Mas não achei ninguém com esse nome em casa agora."
            else:
                try:
                    resposta["visitar"] = {"nome": comecar_visita(request, alvo)}
                except HTTPException as erro:
                    resposta["resposta"] = f"{resposta['resposta']} {erro.detail}"
        if SOBRE_O_TEMPO.search(p.texto):                  # perguntou do tempo: ele "veste" o tempo de hoje
            efeitos = mundo.efeitos()
            if efeitos:
                resposta["efeitos"] = efeitos
        return resposta

    @app.post("/api/conversa/esquecer", dependencies=[Depends(autorizado)])
    def esquecer_conversa(request: Request):
        conversa.esquecer(quem_e(request)[0])
        return {"ok": True}

    @app.get("/api/vizinhos", dependencies=[Depends(autorizado)])
    def listar_vizinhos(request: Request):
        """Quem está em casa agora para visitar (sem você mesmo)."""
        if vizinhos is None:
            return {"vizinhos": []}
        mexer_na_vizinhanca(request)
        eu = (casa, quem_e(request)[0])
        return {"vizinhos": [{"id": v["id"], "nome": v["nome"], "pet": v["pet"], "recebe": v["recebe"]}
                             for v in vizinhos.em_casa(menos=eu)]}

    @app.post("/api/visitar", dependencies=[Depends(autorizado)])
    def visitar(v: Visitar, request: Request):
        eu = (casa, quem_e(request)[0])
        alvo = next((x for x in (vizinhos.em_casa(menos=eu) if vizinhos else []) if x["id"] == v.para), None)
        if alvo is None:
            raise HTTPException(status_code=404, detail="Não tem ninguém em casa lá agora.")
        nome = comecar_visita(request, alvo)
        return {"ok": True, "nome": nome, "fala": f"{random.choice(SAIU_DE_CASA)} Vou visitar o pet {viz.da(nome)}."}

    @app.post("/api/visita/fim", dependencies=[Depends(autorizado)])
    def fim_da_visita(f: FimDaVisita, request: Request):
        if vizinhos is None or not vizinhos.terminar(f.id, casa, quem_e(request)[0], f.emocao):
            raise HTTPException(status_code=404, detail="visita desconhecida")
        return {"ok": True}

    @app.get("/api/perfil", dependencies=[Depends(autorizado)])
    def ver_perfil():
        return perfil.ler() or {}

    @app.post("/api/perfil", dependencies=[Depends(autorizado)])
    def mudar_perfil(p: NovoPerfil):
        entrada, saida = hora_valida(p.entrada), hora_valida(p.saida)
        if not entrada or not saida or entrada >= saida:
            raise HTTPException(status_code=422, detail="horários no formato HH:MM, com a entrada antes da saída")
        try:
            lugar = geocodificar(p.cidade)
        except clima.ClimaErro as erro:
            raise HTTPException(status_code=404, detail=str(erro))
        dados = {**lugar, "cidade": p.cidade.strip(), "entrada": entrada, "saida": saida}
        perfil.gravar(dados)
        return dados

    @app.post("/api/dia", dependencies=[Depends(autorizado)])
    def guardar_dia(r: ResumoDia, request: Request):
        diario.guardar_dia(r.data, limpar_resumo(r.model_dump()), quem_e(request)[0])
        return {"ok": True}

    @app.get("/api/diario", dependencies=[Depends(autorizado)])
    def ler_diario(quantas: int = Query(default=7, ge=1, le=60)):
        return {"paginas": diario.paginas(quantas)}

    @app.post("/interno/eventos", dependencies=[Depends(so_local), Depends(autorizado)])
    def adicionar(e: NovoEvento):
        if e.tipo == "falar":
            if not e.texto.strip():
                raise HTTPException(status_code=422, detail="texto vazio")
            dados = {"texto": e.texto.strip()}
            conversa.anotar("assistant", dados["texto"])       # dá para responder ao que ele disse sozinho
        elif e.tipo == "humor":
            if not e.humor.strip():
                raise HTTPException(status_code=422, detail="humor vazio")
            dados = {"humor": e.humor.strip()}
        elif e.tipo == "acao":
            if e.acao not in acoes.ACOES:
                raise HTTPException(status_code=422, detail=f"acao deve ser uma de: {', '.join(acoes.ACOES)}")
            dados = {"acao": e.acao}
        else:
            raise HTTPException(status_code=422, detail="tipo deve ser falar, humor ou acao")
        return {"id": eventos.adicionar(e.tipo, dados)}

    return app


def app_padrao():
    """Usado pelo uvicorn: uvicorn --factory ponte.app:app_padrao"""
    logging.basicConfig(level=logging.INFO)
    return criar_app()
