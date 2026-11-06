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
- **Conversar:** clique duplo no pet, Ctrl+Alt+P ou clique duplo num post-it dele (veja abaixo). A resposta chega num post-it.
- **Sem travar:** a rede roda em threads próprias (`pestinha/sense/hermes.py`); com a VPS fora do ar
  ele espera cada vez mais entre tentativas (até 60 s) e o pet segue normal.
- **Sem repetir:** o último evento mostrado fica em `memory/hermes_ultimo.txt`. Na primeira conexão,
  o histórico antigo da fila não é despejado na tela.

## Conversar

Três jeitos de abrir o balão de conversa, que aparece em cima do pet no estilo de um post-it:

- **Clique duplo no pet.**
- **Ctrl+Alt+P** de qualquer lugar (Windows). Se o pet estiver escondido, ele volta para conversar.
- **Clique duplo num post-it dele.** O balão abre mostrando o que ele disse, e a resposta continua a
  partir dali ("e amanhã?" depois de um aviso de chuva). Vale para as falas do Hermes e para as travessuras,
  e não conta como travessura dispensada.

**Enter** envia, **Esc** ou o **×** do balão fecham. Fechar só esconde o balão: a memória curta continua.
O menu do botão direito também tem **Conversar**.

A ponte guarda uma **memória curta** (as últimas 8 mensagens, esquecidas depois de 30 minutos sem
conversa), inclusive as falas que o pet mandou sozinho, como os avisos de clima. Assim dá para conversar
em vez de fazer perguntas soltas. **Começar conversa nova**, no menu, apaga essa memória.

## Lembretes

No balão: **"me lembra daqui a 30 min de ligar para o cliente"**, **"me avisa às 16h da reunião"**,
**"amanhã às 9h"**. Ele confirma com o horário certo ("Anotado para 11:06.") e, na hora, toca o
despertador e mostra o post-it. Também dá para perguntar **"quais lembretes eu tenho?"**, pedir para
**cancelar** um e, quando ele lembrar, responder **"adia 10 min"**.

- O Hermes só entende o pedido e escreve `[lembrete: +30 | ligar para o cliente]`; quem calcula o horário,
  guarda (no SQLite da ponte) e dispara é a ponte (`ponte/ponte/lembretes.py`). O agente não ganhou
  ferramenta nova.
- Com o pet fechado, o lembrete espera e aparece quando ele abrir, dizendo a hora combinada.
- Se o modelo disser que vai lembrar sem marcar, a ponte troca a resposta por um "não entendi para quando".
- Fuso: o da cidade escolhida no menu (sem cidade, horário de Brasília). Até 30 lembretes marcados.

## Visitas

Os pets de pessoas diferentes que usam pontes na mesma VPS (você, outra pessoa, a equipe) podem se visitar.

- **Ir:** botão direito → **Visitar alguém...** (ou "vai visitar a Talita" no balão). Aparece quem está com o pet
  aberto agora; você escolhe, ele deixa um post-it avisando e sai de casa (some da tela).
- **Lá:** o pet dele aparece na tela da outra pessoa, desenhado com o personagem dele, chega pulando,
  cumprimenta (no jeito dele, pelo Hermes dele), brinca um minuto olhando para o pet da casa, se despede com
  uma piscadinha e vai embora. Cutucar a visita: "Ei! Eu sou visita, tá?".
- **Volta:** ele reaparece pulando e conta como foi ("O pet da Talita me recebeu todo feliz"). Se ninguém abrir
  a porta (a outra pessoa fechou o pet), ele volta dizendo isso.
- **Não sai** dormindo, de castigo, sentado no notebook, segurado ou com visita em casa.
- **Receber visitas** nas Configurações (ligado por padrão). Desligado, ninguém vem, e quem tentou fica sabendo.
- Entra no diário dos dois. Só passam o personagem, o nome e as falas; nada da tela de ninguém.

As pontes conversam por um arquivo SQLite compartilhado (`PONTE_VIZINHANCA`, padrão: `vizinhanca.db` na mesma
pasta do `PONTE_BANCO`), sem nada novo exposto na internet. Se os bancos das pontes estiverem em pastas
diferentes, ponha o mesmo `PONTE_VIZINHANCA` no `.env` de todas.

## Animações

O pet reage com o corpo ao que acontece na conversa (`pestinha/controle/vivo.py`). As peças que ele veste
são desenhadas no próprio pet (`pestinha/body/figurino.py`); o que flutua em volta dele fica num "palco",
uma janela transparente que segue o pet e deixa o clique passar (`pestinha/world/palco.py`).

| Quando | O que ele faz |
| --- | --- |
| Você digita no balão | Olha para o balão e inclina a cabeça |
| Você manda a pergunta | Nuvem de pensamento estilo HQ (com lupa se demora); some num "puf" quando a resposta chega |
| Chega fala da VPS | "!" em cima da cabeça, e o post-it sai voando de trás dele |
| Chuva (aviso ou pergunta do tempo) | Nuvem de chuva e guarda-chuva |
| Calor (máxima ≥ 30 °C) | Óculos escuros e sol |
| Frio (mínima ≤ 12 °C) | Cachecol e neve |
| Sexta ou véspera de feriado (aviso de saída) | Chapéu de festa e confete |
| Anotou algo no diário | Tira o caderninho e rabisca (anotações seguidas viram um rabisco só, no máximo um a cada 25 s) |
| Página nova do diário / lendo o diário | Rabisca antes do post-it / fica com o caderninho aberto enquanto você lê |
| Hora de um lembrete | Acorda (no susto, se dormia), pula e toca o despertador; depois o post-it |
| Obedece ao Hermes | Estrela e pulinho |
| Recusa | Revira os olhos e bufa |
| Você fecha a conversa | Piscadinha e coraçãozinho |

A ponte manda as animações do tempo junto do aviso ou da resposta (`"efeitos": ["chuva", "festa"]`).
Para ver na hora, na VPS: `.venv/bin/python -m ponte.lado_de_fora --agora`.

**Post-its, memes e fotos** funcionam como uma janela:

| Mouse | Travessura dele | Fala do Hermes |
| --- | --- | --- |
| Arrastar pela **barra de cima** | Leva para onde você quiser | Igual |
| **Clique duplo** | Responde a ela (com o Hermes ligado) | Responde a ela |
| **Um clique** | Fecha, e a **raiva sobe** (ele bufa; várias seguidas, faz drama) | Fecha, sem raiva |
| **×** | Fecha numa boa: ele só espera um pouco antes da próxima | Fecha |

Com o Hermes ligado, um clique espera o tempo de um clique duplo antes de fechar. Os cartazes de protesto
não têm barra nem ×: arrancar o cartaz continua sendo "repressão".

## Pesquisar na internet

Para coisas atuais (notícias, resultados, preços, horários), o Hermes pode pesquisar na web com as
ferramentas `web_search` e `web_extract`. É configuração do Hermes, na VPS:

```bash
hermes config set TAVILY_API_KEY tvly-...      # chave grátis em tavily.com (1.000 créditos/mês)
hermes config set web.backend tavily
hermes doctor                                   # web_search e web_extract devem aparecer prontos
systemctl --user restart hermes-gateway
```

A persona pede para pesquisar só quando precisa de algo atual e responder só o principal, no post-it.
Uma pergunta que pesquisa demora mais (o pet espera até 150 s) e gasta mais tokens.

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

Além dos avisos, **toda conversa** leva uma linha com o dia, a hora, a previsão de hoje e de amanhã (e das
próximas 3 horas) e os feriados (`ponte/mundo.py`, previsão em cache por 30 minutos). Então dá para
perguntar "vai chover hoje?" ou "amanhã é feriado?" a qualquer hora.

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
