"""Conversa com a API local do Hermes Agent (compatível com OpenAI: /v1/chat/completions)."""
import httpx


class HermesErro(Exception):
    """O Hermes não respondeu ou respondeu algo que não dá para usar."""


def perguntar(cfg, texto):
    mensagens = []
    if cfg.persona:
        mensagens.append({"role": "system", "content": cfg.persona})
    mensagens.append({"role": "user", "content": texto})
    cabecalhos = {"Content-Type": "application/json"}
    if cfg.hermes_key:
        cabecalhos["Authorization"] = f"Bearer {cfg.hermes_key}"
    try:
        r = httpx.post(
            f"{cfg.hermes_url}/v1/chat/completions",
            headers=cabecalhos,
            json={"model": "hermes-agent", "stream": False, "messages": mensagens},
            timeout=cfg.hermes_timeout,
        )
        r.raise_for_status()
        conteudo = r.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as erro:
        raise HermesErro(str(erro)) from erro
    if not isinstance(conteudo, str) or not conteudo.strip():
        raise HermesErro("resposta vazia")
    return conteudo.strip()
