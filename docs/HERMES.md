# Pestinha + Hermes Agent

O Pestinha pode ter um "cérebro" na VPS: o [Hermes Agent](https://hermes-agent.nousresearch.com/),
atrás da ponte (pasta [`ponte/`](../ponte/README.md)).

```text
Pestinha (PC) ── HTTPS, polling a cada 5 s ──► ponte (VPS) ──► Hermes Agent (VPS)
```

## Ligar no computador

Crie `memory/hermes.json` (a pasta `memory/` nunca vai para o Git):

```json
{"url": "https://pestinha.exemplo.com.br", "token": "<PONTE_TOKEN da VPS>"}
```

No PowerShell, um jeito seguro de criar (sem depender da codificação):

```powershell
[IO.File]::WriteAllText("$env:LOCALAPPDATA\Pestinha\hermes.json", '{"url": "https://...", "token": "..."}')
```

(Use `memory\hermes.json` ao lado do `.exe` se essa pasta existir.) Abra o Pestinha de novo e procure
`[hermes] ligado` no log. Sem esse arquivo, o Hermes fica desligado e nada muda; com o arquivo
ilegível ou incompleto, o log diz o motivo.

## O que ele faz

- **Falas da VPS:** o que o cron do Hermes (ou qualquer script na VPS) põe em `/interno/eventos`
  aparece como post-it perto do pet. Pausado ou escondido, as falas esperam até ele voltar.
- **Perguntar:** botão direito no pet → *Perguntar ao Hermes...*. A resposta chega num post-it.
- **Sem travar:** a rede roda em threads próprias (`pestinha/sense/hermes.py`); com a VPS fora do ar
  ele espera cada vez mais entre tentativas (até 60 s) e o pet segue normal.
- **Sem repetir:** o último evento mostrado fica em `memory/hermes_ultimo.txt`. Na primeira conexão,
  o histórico antigo da fila não é despejado na tela.

## Dois cérebros: instinto e razão

O pet tem dois cérebros. A **rede neural local** é o instinto: decide o que ele sente. O **Hermes** é a
razão: conversa e pode pedir coisas ao corpo. Um não manda no outro.

- **Do pet para o Hermes:** cada pergunta leva só a emoção, a energia e se ele está dormindo (nada da sua
  tela). O Hermes responde no tom do momento: emburrado se bravo, manhoso se triste, bocejando se cansado.
- **Do Hermes para o pet:** quando você pede ("vai dormir", "brinca com a bolinha", "apronta uma",
  "vem trabalhar"), o Hermes termina a resposta com `[acao: ...]`. A ponte tira essa marca do texto e
  manda a ação separada. Só existem quatro: `dormir`, `bolinha`, `travessura`, `trabalhar`.
- **Quem decide é o instinto** (`pestinha/mind/obediencia.py`): bravo recusa 80% das vezes, dramático e
  assustado 60%, triste 50%, cansado não brinca nem trabalha e dormindo não ouve. Recusando, ele diz por
  quê num post-it. As permissões das Configurações continuam valendo, e "trabalhar" ainda passa pela
  rede, que também pode recusar.
- Scripts na VPS podem pedir uma ação direto: `POST /interno/eventos` com `{"tipo": "acao", "acao": "bolinha"}`.

## Ainda não

- Eventos `humor` chegam, mas ainda não mexem na emoção do pet (só vão para o log).
