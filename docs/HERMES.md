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

## Lado de fora: clima, sexta-feira e feriados

Botão direito no pet → **Minha cidade e horários...**: escolha a cidade (`Franca, SP`, `Lisboa, Portugal`,
`Porto Alegre, RS`) e os horários de entrada e saída. A ponte descobre onde fica a cidade e o fuso dela
(Open-Meteo, gratuito e sem chave), então funciona em qualquer lugar.

Em dia útil, o pet manda dois avisos, no fuso da cidade escolhida:

- **Uns 5 minutos depois da entrada:** bom-dia com a mínima, a máxima e a chance de chuva do dia.
- **Uns 30 minutos antes da saída:** chuva nas próximas horas ("leva o guarda-chuva"), feriado amanhã,
  feriado prolongado, sexta-feira.

Feriados nacionais do Brasil, inclusive os móveis (Carnaval, Sexta-feira Santa, Corpus Christi), são
calculados na própria ponte; em feriado e no fim de semana ele não avisa. O Hermes escreve cada aviso no
jeito do pet; se ele não responder, vai uma frase pronta com o principal.

## Diário do Pestinha

Ao longo do dia, o pet anota **só números** sobre a própria vida (`pestinha/mind/diario.py`): minutos em
cada emoção e quantas cutucadas, carinhos, castigos, fugas, travessuras, dispensas, cochilos, protestos,
perguntas e pedidos obedecidos ou recusados. Nada do que aparece na sua tela. O resumo fica em
`memory/diario_hoje.json` e vai para a ponte a cada 10 minutos e ao fechar o pet.

Às 21h (no fuso da cidade escolhida), o mesmo timer dos avisos pede ao Hermes uma página de diário em
primeira pessoa, dramática, com até 5 frases. No dia seguinte, um post-it avisa que tem página nova, e o
menu **Ler meu diário...** mostra as últimas cinco.

Para testar sem esperar a noite, na VPS:

```bash
cd ~/pestinha-hermes/ponte && set -a; . ~/.config/pestinha/ponte.env; set +a
.venv/bin/python -m ponte.diario --agora
```

## Ainda não

- Eventos `humor` chegam, mas ainda não mexem na emoção do pet (só vão para o log).
