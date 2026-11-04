"""
Ponte entre o Pestinha (no computador) e o Hermes Agent (na VPS).

Rotas:
  GET  /saude              sem token; para monitoramento
  GET  /api/eventos        o pet pergunta "tem algo novo depois do id N?" (polling)
  POST /api/perguntar      você clica no pet, digita, e o Hermes responde
  POST /interno/eventos    só da própria VPS (cron do Hermes, scripts): põe uma fala, humor ou ação na fila

Tudo em /api e /interno exige "Authorization: Bearer <PONTE_TOKEN>".
A ponte escuta só em 127.0.0.1; quem a expõe na internet (com HTTPS) é o Caddy.
"""
import hmac
import logging

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from . import config as config_mod
from . import acoes, hermes
from .eventos import Eventos

log = logging.getLogger("ponte")
LOCAIS = {"127.0.0.1", "::1", "testclient"}


class EstadoPet(BaseModel):
    emocao: str = Field(default="", max_length=20)
    energia: float | None = Field(default=None, ge=0, le=1)
    dormindo: bool = False


class Pergunta(BaseModel):
    texto: str = Field(min_length=1, max_length=500)
    estado: EstadoPet | None = None


class NovoEvento(BaseModel):
    tipo: str = "falar"
    texto: str = Field(default="", max_length=500)
    humor: str = Field(default="", max_length=30)
    acao: str = Field(default="", max_length=20)


def criar_app(cfg=None):
    cfg = cfg or config_mod.carregar()
    eventos = Eventos(cfg.banco)
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
    def listar(desde: int = Query(default=0, ge=0)):
        lista, ultimo = eventos.depois_de(desde)
        return {"eventos": lista, "ultimo": ultimo}

    @app.post("/api/perguntar", dependencies=[Depends(autorizado)])
    def perguntar(p: Pergunta):
        contexto = acoes.descrever_estado(p.estado.model_dump() if p.estado else None)
        try:
            bruta = hermes.perguntar(cfg, f"{contexto}\n{p.texto}" if contexto else p.texto)
        except hermes.HermesErro as erro:
            log.warning("Hermes falhou: %s", erro)
            raise HTTPException(status_code=502, detail="o Hermes não respondeu agora")
        texto, acao = acoes.separar_acao(bruta)
        resposta = {"resposta": texto or "…"}
        if acao:
            resposta["acao"] = acao
        return resposta

    @app.post("/interno/eventos", dependencies=[Depends(so_local), Depends(autorizado)])
    def adicionar(e: NovoEvento):
        if e.tipo == "falar":
            if not e.texto.strip():
                raise HTTPException(status_code=422, detail="texto vazio")
            dados = {"texto": e.texto.strip()}
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
