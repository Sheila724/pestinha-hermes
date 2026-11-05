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
| `GET /api/eventos?desde=N` | sim | Eventos com id maior que `N` (`falar`, `humor` ou `acao`) e o `ultimo` id; antes, os lembretes vencidos viram falas |
| `POST /api/perguntar` `{"texto": "...", "estado": {...}}` | sim | Pergunta ao Hermes; devolve `{"resposta": "..."}` e, se for o caso, `"acao"` (pedido ao corpo) e `"efeitos"` (animações do tempo) |
| `POST /api/conversa/esquecer` | sim | Apaga a memória curta da conversa (as últimas 8 mensagens, que somem sozinhas após 30 min) |
| `GET /api/perfil` / `POST /api/perfil` `{"cidade": "Franca, SP", "entrada": "08:00", "saida": "18:00"}` | sim | Cidade e horários dos avisos do lado de fora |
| `POST /api/dia` `{"data": "2026-11-04", "emocoes": {...}, "contagens": {...}}` | sim | Resumo do dia do pet, para o diário |
| `GET /api/diario?quantas=5` | sim | As últimas páginas do diário |
| `POST /interno/eventos` `{"texto": "..."}`, `{"tipo": "humor", "humor": "feliz"}` ou `{"tipo": "acao", "acao": "dormir"}` | sim | Só da própria VPS: põe algo na fila do pet |

O `/api/perguntar` também aceita `"respondendo": "<texto do post-it>"`, quando a pessoa responde a uma fala do
pet; junto com a memória curta, isso deixa a conversa continuar. O `estado` (opcional) é `{"emocao": "bravo", "energia": 0.3, "dormindo": false}`: vira uma linha de contexto
para o Hermes falar no tom certo. As ações possíveis estão em `ponte/acoes.py`; o Hermes as pede terminando
a resposta com `[acao: nome]`, e quem decide se obedece é o pet.

Falas podem trazer `"efeitos"`: animações que o pet faz junto (`chuva`, `calor`, `frio`, `festa`, `diario`,
`lembrete`). Vêm nos avisos do lado de fora, na página do diário, nos lembretes e nas perguntas sobre o tempo.

**Lembretes** (`ponte/lembretes.py`): o Hermes termina a resposta com `[lembrete: +30 | o que lembrar]`
(`+30`, `+2h`, `16:00`, `06/11 09:00`) ou `[cancelar: N]`. A ponte calcula a hora no fuso da cidade, guarda no
SQLite, acrescenta "Anotado para HH:MM." e, quando vence, põe a fala na fila com o efeito `lembrete`. Os
marcados vão para o Hermes numa linha de contexto, para ele listar e cancelar.

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

## Avisos do lado de fora (clima e calendário)

`python -m ponte.lado_de_fora` confere se é hora de um aviso (manhã ou saída) na cidade escolhida pelo pet e,
se for, põe a fala na fila. Para rodar sozinho de 15 em 15 minutos:

```bash
cp ../deploy/pestinha-lado-de-fora.service ../deploy/pestinha-lado-de-fora.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pestinha-lado-de-fora.timer
systemctl --user list-timers | grep lado
```

O mesmo timer escreve a página do diário às 21h (no fuso da cidade), se o pet mandou o resumo do dia
(`python -m ponte.diario --agora` escreve na hora, para testar).

Para testar sem esperar o horário (manda o aviso de saída na hora):

```bash
set -a; . ~/.config/pestinha/ponte.env; set +a
.venv/bin/python -m ponte.lado_de_fora --agora
```

## Desenvolver

```bash
cd ponte
pip install -r requirements-dev.txt
python -m pytest -q
python -m pyflakes ponte tests
```
