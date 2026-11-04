"""Configuração da ponte, lida das variáveis de ambiente (arquivo ponte.env no systemd)."""
import os
from dataclasses import dataclass
from pathlib import Path

PERSONA_PADRAO = Path(__file__).with_name("persona.md")


@dataclass(frozen=True)
class Config:
    token: str              # o Pestinha manda "Authorization: Bearer <token>"
    hermes_url: str         # API do Hermes (só local)
    hermes_key: str         # API_SERVER_KEY do ~/.hermes/.env
    banco: Path             # SQLite com a fila de eventos
    persona: str            # texto de sistema mandado ao Hermes em cada pergunta
    hermes_timeout: float   # o agente pode demorar: ele pensa e usa ferramentas


def _ler_persona(caminho):
    try:
        return Path(caminho).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def carregar(env=None):
    env = os.environ if env is None else env
    token = env.get("PONTE_TOKEN", "").strip()
    if len(token) < 32:
        raise RuntimeError("PONTE_TOKEN ausente ou curto demais (gere com: openssl rand -hex 32)")
    return Config(
        token=token,
        hermes_url=env.get("HERMES_URL", "http://127.0.0.1:8642").rstrip("/"),
        hermes_key=env.get("HERMES_API_KEY", "").strip(),
        banco=Path(env.get("PONTE_BANCO", "ponte.db")),
        persona=_ler_persona(env.get("PONTE_PERSONA", PERSONA_PADRAO)),
        hermes_timeout=float(env.get("HERMES_TIMEOUT", "120")),
    )
