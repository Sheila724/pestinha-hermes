"""
VIVO - o pet reagindo com o corpo à conversa com o Hermes (mixin do app).

  você digita              ele olha para o balão e inclina a cabeça
  você manda a pergunta    nuvem de pensamento (com lupa se demora); some num "puf" e a resposta sai voando
  chega fala da VPS        "!" em cima da cabeça, e o post-it sai voando de trás dele
  efeitos da ponte         chuva = guarda-chuva · calor = óculos escuros e sol · frio = cachecol e neve ·
                           festa = chapéu e confete · diario = caderninho ·
                           lembrete = acorda (no susto, se dormia) e toca o despertador, depois o post-it
  pedido do Hermes         obedece: estrela e pulinho · recusa: revira os olhos, bufa e diz por quê
  você fecha a conversa    piscadinha e coraçãozinho
  anotou algo no diário    tira o caderninho e rabisca (sempre que anota; várias anotações seguidas
                           viram um rabisco só, a cada RABISCO_INTERVALO_S)

Os atrasos (o "!" antes da fala, o "puf" antes da resposta) ficam numa agenda que roda a cada quadro.
"""

import math
import time

from ..body.figurino import RABISCO_S
from ..log import log
from ..mind import obediencia
from ..world.palco import Palco

ATRASO_FALA_S = 0.55
ATRASO_RESPOSTA_S = 0.3
ATRASO_ACAO_S = 0.6
ATRASO_RECUSA_S = 0.5
ATRASO_LEMBRETE_S = 1.1             # o post-it do lembrete sai com o despertador já tocando
RABISCO_INTERVALO_S = 25.0
RABISCO_ESPERA_S = 1.0
PENSANDO_MAX_S = 170.0
PULO_VY = -560.0
FIGURINO_DO_TEMPO = {"calor": ("oculos_sol", 20.0), "frio": ("cachecol", 20.0), "festa": ("chapeu", 8.0)}
PALCO_DO_TEMPO = {"chuva": ("guarda_chuva", 12.0), "calor": ("calor", 20.0), "frio": ("frio", 20.0),
                  "festa": ("confete", 5.0)}


class VivoMixin:
    """Reações do corpo à conversa. O app chama `_iniciar_vivo` (com o Hermes ligado) e `tick_vivo` a cada quadro."""

    def _iniciar_vivo(self):
        self.palco = Palco()
        self.agenda = []
        self._perguntas = 0
        self._pensando_desde = 0.0
        self._anotacoes_vistas = self.diario.anotacoes if self.diario else 0
        self._rabisco_pendente = None          # quando rabiscar a anotação que chegou (None: nada pendente)
        self._ultimo_rabisco = -1e9
        self.balao.digitando.connect(self.ouvir_voce)
        self.balao.fechado.connect(self.despedir)

    @property
    def figurino(self):
        return self.pet.figurino

    # ---------- agenda e quadro ----------

    def agendar(self, atraso, acao, agora=None):
        agora = time.monotonic() if agora is None else agora
        self.agenda.append((agora + atraso, acao))

    def rodar_agenda(self, agora):
        """Roda o que já está na hora (pausado ou escondido, espera)."""
        if not getattr(self, "agenda", None) or self._congelado() or self.hidden:
            return
        prontas = [a for a in self.agenda if a[0] <= agora]
        self.agenda = [a for a in self.agenda if a[0] > agora]
        for _quando, acao in sorted(prontas, key=lambda a: a[0]):
            acao()

    def tick_vivo(self, agora):
        if getattr(self, "palco", None) is None:
            return
        self.rodar_agenda(agora)
        self._talvez_rabiscar(agora)
        if self._perguntas and agora - self._pensando_desde > PENSANDO_MAX_S:     # nunca fica pensando para sempre
            self._perguntas = 0
            self.palco.encerrar("pensando", agora)
        body = self.pet.body
        visivel = self.pet.isVisible() and not self.paused and not self.hidden and not self.wiping
        self.palco.tick(agora, body.x, body.y, body.angle, visivel)

    # ---------- o que chega do Hermes ----------

    def receber_hermes(self):
        """Mostra o que chegou do Hermes, com as reações do corpo. Pausado ou escondido, espera na fila."""
        if self._congelado() or self.hidden:
            return
        self.anotar_diario()
        agora = time.monotonic()
        atraso_fala, exclamar = ATRASO_FALA_S, True
        for tipo, texto in self.hermes.coletar():
            if tipo == "efeito":
                self.efeito(texto, agora)
                if texto == "diario":
                    atraso_fala = RABISCO_S - 0.2              # o post-it sai depois que ele guarda o caderno
                elif texto == "lembrete":
                    atraso_fala, exclamar = ATRASO_LEMBRETE_S, False    # o despertador já chama atenção
            elif tipo == "falar":
                if exclamar:
                    self.palco.iniciar("exclamacao", agora)
                self.agendar(atraso_fala, lambda t=texto: self.mostrar_fala(t), agora)
                atraso_fala, exclamar = ATRASO_FALA_S, True    # os efeitos valem só para a fala que acompanham
            elif tipo in ("resposta", "erro"):
                self._fim_da_pergunta(agora)
                self.agendar(ATRASO_RESPOSTA_S, lambda t=texto: self.mostrar_fala(t), agora)
            elif tipo == "info":
                self.mostrar_fala(texto)
            elif tipo == "acao":
                self.pedido_do_hermes(texto)
            elif tipo == "diario":
                self.mostrar_diario(texto)
            elif tipo == "humor":
                log(f"[hermes] humor recebido (ainda sem efeito): {texto}")

    def efeito(self, nome, agora=None):
        """Animação pedida pela ponte (ou pelo app): o pet "veste" o tempo, a festa ou o caderninho."""
        agora = time.monotonic() if agora is None else agora
        if nome == "diario":
            self.figurino.rabiscar(agora)
            self._ultimo_rabisco = agora
            return
        if nome == "lembrete":
            if self.asleep:
                self.sleep.wake(startled=True)         # acorda no susto com o despertador
            self.palco.iniciar("despertador", agora)
            self.pular()
            return
        if nome in FIGURINO_DO_TEMPO:
            peca, dur = FIGURINO_DO_TEMPO[nome]
            self.figurino.vestir(peca, agora, dur)
        if nome in PALCO_DO_TEMPO:
            efeito, dur = PALCO_DO_TEMPO[nome]
            self.palco.iniciar(efeito, agora, dur)

    def mostrar_fala(self, texto):
        """Post-it com a fala, saindo de trás do pet e voando até em cima dele."""
        body = self.pet.body
        self.mischief.mostrar_fala(texto, body.x, body.y - 150, self.bounds(), origem=(body.x, body.y - 10))

    # ---------- conversa ----------

    def abrir_conversa(self, respondendo=""):
        """Abre o balão de conversa em cima do pet (clique duplo, Ctrl+Alt+P, ou clique num post-it dele)."""
        if not self.balao or self._congelado():
            return
        if self.hidden:
            self.toggle_hidden()                 # chamou pelo atalho com ele escondido: ele volta para conversar
        body = self.pet.body
        self.balao.abrir(body.x, body.y - 70, self.bounds(), respondendo)

    def enviar_ao_hermes(self, texto, respondendo=""):
        """O que você escreveu vai para o Hermes; enquanto isso, a nuvem de pensamento."""
        agora = time.monotonic()
        self.hermes.perguntar(texto, self.estado_para_hermes(), respondendo)
        self.contar_no_diario("perguntas")
        if self.palco is not None:
            if not self._perguntas:
                self._pensando_desde = agora
            self._perguntas += 1
            self.palco.iniciar("pensando", agora)

    def _fim_da_pergunta(self, agora):
        self._perguntas = max(0, self._perguntas - 1)
        if not self._perguntas:
            self.palco.encerrar("pensando", agora)

    def ouvir_voce(self):
        """Você está digitando: ele olha para o balão e inclina a cabeça."""
        body = self.pet.body
        b = self.balao
        dx, dy = b.x() + b.width() / 2 - body.x, b.y() + b.height() / 2 - body.y
        d = max(1.0, math.hypot(dx, dy))
        self.figurino.ouvir(time.monotonic(), (dx / d, dy / d))

    def despedir(self):
        """Você fechou a conversa: piscadinha e coraçãozinho."""
        agora = time.monotonic()
        self.figurino.piscar(agora)
        self.palco.iniciar("brilho", agora)

    # ---------- pedidos do Hermes ----------

    def pedido_do_hermes(self, acao):
        """O Hermes pediu algo ao corpo: o instinto decide. Obedece com estrela e pulinho; recusa bufando."""
        perms = self.perms
        if (acao == "bolinha" and not perms["bolinha"]) or (acao == "travessura" and not perms["travessuras"]):
            self.mostrar_fala("Isso está desligado nas Configurações.")
            return
        obedece, fala = obediencia.decidir(acao, self.emotion.current, self.drives.energy, self.asleep)
        log(f"[hermes] pedido '{acao}' com emoção {self.emotion.current}: {'obedeceu' if obedece else 'recusou'}")
        self.contar_no_diario("obedeceu" if obedece else "recusou")
        agora = time.monotonic()
        if not obedece:
            if self.palco is not None and acao in obediencia.ACOES:
                self.palco.iniciar("bufo", agora)
                self.figurino.revirar_olhos(agora)
            if fala:
                self.agendar(ATRASO_RECUSA_S, lambda: self.mostrar_fala(fala), agora)
            return
        executar = {"dormir": self.menu_sleep, "bolinha": self.menu_place_ball,
                    "travessura": self.menu_mischief, "trabalhar": self.menu_pedir_trabalho}.get(acao)
        if executar is None:
            return
        if self.palco is not None:
            self.palco.iniciar("estrela", agora)
            self.pular()
        self.agendar(ATRASO_ACAO_S, executar, agora)

    def pular(self):
        """Pulinho de alegria (só se está no chão, solto, acordado e fora do notebook e do castigo)."""
        body = self.pet.body
        if body.grounded and not body.held and not self.asleep and not self.mesa.sentado and not self.castigo.dentro:
            body.vy = PULO_VY
            body.grounded = False
            body.platform = None

    # ---------- caderninho do diário ----------

    def _talvez_rabiscar(self, agora):
        """Anotou algo no diário: tira o caderninho e rabisca (anotações seguidas viram um rabisco só)."""
        if not self.diario:
            return
        if self.diario.anotacoes > self._anotacoes_vistas:
            self._anotacoes_vistas = self.diario.anotacoes
            if self._rabisco_pendente is None:
                self._rabisco_pendente = agora + RABISCO_ESPERA_S
        if self._rabisco_pendente is None or agora < self._rabisco_pendente:
            return
        if agora - self._ultimo_rabisco < RABISCO_INTERVALO_S:
            self._rabisco_pendente = self._ultimo_rabisco + RABISCO_INTERVALO_S     # anota junto, logo mais
            return
        body = self.pet.body
        ocupado = (self.asleep or body.held or self.mesa.sentado or self.hidden or self._congelado()
                   or self.palco.ativo("pensando", agora) or self.figurino.ativo("caderno", agora))
        if ocupado:
            self._rabisco_pendente = agora + 2.0                                      # espera ele ficar livre
            return
        self._rabisco_pendente = None
        self._ultimo_rabisco = agora
        self.figurino.rabiscar(agora)
