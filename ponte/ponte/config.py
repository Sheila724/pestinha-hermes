"""Configuração da ponte, lida das variáveis de ambiente (arquivo ponte.env no systemd)."""
import os
import re
from dataclasses import dataclass
from pathlib import Path

PERSONA_PADRAO = Path(__file__).with_name("persona.md")
JEITOS = Path(__file__).with_name("jeitos")      # personalidades: travesso (padrão), zoeiro...
DONO_PADRAO = "Sheila"
EQUIPE = """- Você é o pet da equipe inteira: várias pessoas falam com você, cada uma do computador dela. A linha
  "[Quem está falando: ...]" diz quem é; chame pelo nome, sem confundir uma pessoa com a outra.
- Avisos, lembretes e o diário são para a equipe toda. Um lembrete pedido por alguém toca para todos."""


@dataclass(frozen=True)
class Config:
    token: str              # o Pestinha manda "Authorization: Bearer <token>"
    hermes_url: str         # API do Hermes (só local)
    hermes_key: str         # API_SERVER_KEY do ~/.hermes/.env
    banco: Path             # SQLite com a fila de eventos
    persona: str            # texto de sistema mandado ao Hermes em cada pergunta
    dono: str               # como o pet chama a pessoa (persona e diário)
    hermes_timeout: float   # o agente pode demorar: ele pensa e usa ferramentas
    equipe: bool = False    # pet de uma equipe: várias pessoas, cada mensagem diz quem fala


def _ler_persona(caminho):
    try:
        return Path(caminho).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def ler_jeito(nome):
    """(tom, exemplos) de ponte/jeitos/<nome>.md: tom antes da linha "---", exemplos depois."""
    if not re.fullmatch(r"[a-z_]{1,30}", nome):
        raise RuntimeError(f"PONTE_JEITO inválido: {nome!r}")
    arquivo = JEITOS / f"{nome}.md"
    if not arquivo.exists():
        existentes = ", ".join(sorted(a.stem for a in JEITOS.glob("*.md")))
        raise RuntimeError(f"PONTE_JEITO={nome}: não existe ponte/jeitos/{nome}.md (tem: {existentes})")
    linhas = [l for l in arquivo.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    texto = "\n".join(linhas)
    tom, _, exemplos = texto.partition("\n---\n")
    return tom.strip(), exemplos.rstrip()


def montar_persona(modelo, dono, jeito="travesso", equipe=False):
    """A persona com a pessoa e a personalidade escolhidas ({dono}, {jeito} e {exemplos} no texto)."""
    tom, exemplos = ler_jeito(jeito)
    if equipe:
        tom = f"{tom}\n{EQUIPE}"
    return modelo.replace("{jeito}", tom).replace("{exemplos}", exemplos).replace("{dono}", dono).strip()


def carregar(env=None):
    env = os.environ if env is None else env
    token = env.get("PONTE_TOKEN", "").strip()
    if len(token) < 32:
        raise RuntimeError("PONTE_TOKEN ausente ou curto demais (gere com: openssl rand -hex 32)")
    dono = " ".join(env.get("PONTE_DONO", DONO_PADRAO).split())[:40] or DONO_PADRAO
    equipe = env.get("PONTE_EQUIPE", "").strip().lower() in ("1", "true", "sim", "yes")
    return Config(
        token=token,
        hermes_url=env.get("HERMES_URL", "http://127.0.0.1:8642").rstrip("/"),
        hermes_key=env.get("HERMES_API_KEY", "").strip(),
        banco=Path(env.get("PONTE_BANCO", "ponte.db")),
        persona=montar_persona(_ler_persona(env.get("PONTE_PERSONA", PERSONA_PADRAO)), dono,
                               env.get("PONTE_JEITO", "travesso").strip() or "travesso", equipe),
        dono=dono,
        hermes_timeout=float(env.get("HERMES_TIMEOUT", "120")),
        equipe=equipe,
    )
