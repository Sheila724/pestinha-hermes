# Ponte do Pestinha

Serviço pequeno (FastAPI) que roda na VPS entre o Pestinha, no computador, e o
[Hermes Agent](https://hermes-agent.nousresearch.com/), na mesma VPS.

```text
Pestinha (PC) ──HTTPS──► Caddy ──► ponte (127.0.0.1:8765) ──► Hermes API (127.0.0.1:8642)
                                        ▲
                     cron do Hermes ────┘ POST /interno/eventos
```

O pet é quem abre as conexões (polling), então funciona atrás de firewall corporativo sem
VPN: só precisa de saída HTTPS.

## Rotas

| Rota | Token | Para quê |
|---|:-:|---|
| `GET /saude` | não | Monitoramento |
| `GET /api/eventos?desde=N` | sim | Eventos com id maior que `N` (`falar` ou `humor`) e o `ultimo` id |
| `POST /api/perguntar` `{"texto": "..."}` | sim | Pergunta ao Hermes; devolve `{"resposta": "..."}` |
| `POST /interno/eventos` `{"texto": "..."}` ou `{"tipo": "humor", "humor": "feliz"}` | sim | Só da própria VPS: põe algo na fila do pet |

Token: `Authorization: Bearer <PONTE_TOKEN>`. O Hermes nunca fica exposto; a persona
(`ponte/persona.md`) mantém as respostas curtas, do tamanho de um post-it.

## Instalar na VPS

```bash
cd ~ && git clone git@github.com:Sheila724/pestinha-hermes.git   # ou https://
cd ~/pestinha-hermes/ponte
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

mkdir -p ~/.config/pestinha ~/.config/systemd/user
cp ../deploy/ponte.env.example ~/.config/pestinha/ponte.env
chmod 600 ~/.config/pestinha/ponte.env
# preencha PONTE_TOKEN (openssl rand -hex 32) e HERMES_API_KEY (API_SERVER_KEY do ~/.hermes/.env)

cp ../deploy/pestinha-ponte.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pestinha-ponte
curl -s http://127.0.0.1:8765/saude
```

## Desenvolver

```bash
cd ponte
pip install -r requirements-dev.txt
python -m pytest -q
python -m pyflakes ponte tests
```
