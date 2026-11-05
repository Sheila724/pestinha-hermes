# Pestinha + Hermes para outra pessoa

Outra pessoa pode ter o próprio Pestinha com Hermes na **mesma VPS**, sem misturar nada com o seu:

| | Você | Ela |
| --- | --- | --- |
| Perfil do Hermes (memória, sessões, configuração) | padrão, `~/.hermes/` | `pestinha2`, `~/.hermes/profiles/pestinha2/` |
| API do Hermes | `127.0.0.1:8642` | `127.0.0.1:8643` |
| Ponte (token, fila, conversa, lembretes, cidade, diário) | `pestinha-ponte`, porta 8765 | `pestinha-ponte@pestinha2`, porta 8766 |
| Endereço | `pestinha.gapsaa.com.br` | `pestinha2.gapsaa.com.br` |
| Nome e jeito | Sheila, travesso | `PONTE_DONO`, `PONTE_JEITO=zoeiro` |

O Gemini e o Tavily usam as suas chaves: o uso dela entra na sua conta. Como administradora da VPS, você
consegue ver os dados dela que ficam lá (conversas, diário); vale avisar.

Os comandos abaixo são na VPS, como `sheila`, e no mesmo terminal do começo ao fim. Troque `NOME` pelo nome
dela.

## 1. DNS

No Cloudflare, crie um registro **A** `pestinha2` apontando para o IP da VPS (o mesmo do `pestinha`), com a
nuvem **cinza** (DNS only).

## 2. Código atualizado

```bash
cd ~/pestinha-hermes && git pull && systemctl --user restart pestinha-ponte
```

## 3. Hermes dela (perfil novo, memória vazia)

Sem `--clone`: o clone copiaria os seus arquivos de memória.

```bash
hermes profile create pestinha2
P=~/.hermes/profiles/pestinha2
cp ~/.hermes/config.yaml "$P/config.yaml"                 # mesmo modelo e só web + memória na API
cut -d= -f1 ~/.hermes/.env                                 # confira os nomes das chaves do Gemini e do Tavily
grep -E '^(GEMINI|GOOGLE|TAVILY)[A-Z_]*=' ~/.hermes/.env > "$P/.env"
printf 'API_SERVER_ENABLED=true\nAPI_SERVER_HOST=127.0.0.1\nAPI_SERVER_PORT=8643\nAPI_SERVER_KEY=%s\n' \
  "$(openssl rand -hex 32)" >> "$P/.env"
chmod 600 "$P/.env"
cut -d= -f1 "$P/.env"                                      # deve listar as chaves e as 4 linhas API_SERVER_
grep -A3 platform_toolsets "$P/config.yaml"                # api_server: [web, memory]
hermes -p pestinha2 gateway install
systemctl --user status hermes-gateway-pestinha2 --no-pager | sed -n 3p
curl -s http://127.0.0.1:8643/health
```

Se a chave do Gemini tiver outro nome no `cut` do seu `.env`, acrescente a linha dela no `$P/.env` à mão.

## 4. Ponte dela

```bash
CHAVE=$(grep '^API_SERVER_KEY=' ~/.hermes/profiles/pestinha2/.env | cut -d= -f2)
cat > ~/.config/pestinha/pestinha2.env <<EOF
PONTE_PORTA=8766
PONTE_TOKEN=$(openssl rand -hex 32)
HERMES_URL=http://127.0.0.1:8643
HERMES_API_KEY=$CHAVE
PONTE_BANCO=/home/sheila/.config/pestinha/pestinha2.db
PONTE_DONO=NOME
PONTE_JEITO=zoeiro
HERMES_TIMEOUT=120
EOF
chmod 600 ~/.config/pestinha/pestinha2.env
cp ~/pestinha-hermes/deploy/pestinha-ponte@.service ~/pestinha-hermes/deploy/pestinha-lado-de-fora@.service \
   ~/pestinha-hermes/deploy/pestinha-lado-de-fora@.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pestinha-ponte@pestinha2 pestinha-lado-de-fora@pestinha2.timer
curl -s http://127.0.0.1:8766/saude
```

## 5. Caddy

```bash
sudo tee -a /etc/caddy/Caddyfile >/dev/null <<'EOF'

pestinha2.gapsaa.com.br {
	@interno path /interno/*
	respond @interno 404

	reverse_proxy 127.0.0.1:8766
}
EOF
sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
sleep 20; curl -s https://pestinha2.gapsaa.com.br/saude
```

## 6. Teste

```bash
set -a; . ~/.config/pestinha/pestinha2.env; set +a
curl -s https://pestinha2.gapsaa.com.br/api/perguntar -H "Authorization: Bearer $PONTE_TOKEN" \
  -H 'Content-Type: application/json' -d '{"texto": "oi, quem é você?"}'
```

Ele deve responder zoeiro e chamando ela pelo nome. Pergunte também algo sobre você ("quem é a Sheila?"):
ele não deve saber nada.

## 7. O pet dela

1. Mande o executável (o instalador ou o .exe das Actions). Não mande a sua pasta do pet: ela tem a sua
   `memory/`, com o seu `hermes.json`.
2. Pegue o token dela com `grep '^PONTE_TOKEN=' ~/.config/pestinha/pestinha2.env` e mande por um canal
   privado.
3. No computador dela, o `memory/hermes.json` (como em [HERMES.md](HERMES.md)), com o endereço dela:
   `{"url": "https://pestinha2.gapsaa.com.br", "token": "<token dela>"}`
4. Ela escolhe a cidade dela no menu do pet.

## Manutenção

- Atualizar o código: `git pull` e reiniciar as duas pontes
  (`systemctl --user restart pestinha-ponte pestinha-ponte@pestinha2`).
- Trocar o jeito ou o nome: edite `PONTE_JEITO`/`PONTE_DONO` no `.env` dela e reinicie a ponte dela. Os
  jeitos ficam em `ponte/ponte/jeitos/`; um arquivo novo lá vira um jeito novo.
- Cortar o acesso dela: troque o `PONTE_TOKEN` no `.env` dela e reinicie.
- Desfazer tudo: `systemctl --user disable --now pestinha-ponte@pestinha2 pestinha-lado-de-fora@pestinha2.timer`,
  `hermes profile delete pestinha2`, apague o `.env` e o `.db` dela e o bloco do Caddyfile.
