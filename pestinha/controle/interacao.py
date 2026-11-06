"""
INTERAÇÃO - o que você faz com o pet: cutucar, arrastar, arremessar, dispensar travessuras,
os comandos do menu do botão direito e o notebook.

Cada interação vira sinal para a rede (sentidos), homeostase, condicionamento e memória.
Pausado ou desligado, as interações não mexem no estado (ver SessaoMixin._congelado).
Mixin de PestinhaApp: usa os atributos criados em PestinhaApp.__init__.
"""

from ..log import log
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox
from ..body.pet import cursor_pos
from ..ajustes import (
    INSATISFACAO_NOTEBOOK,
    ARREMESSOS_TOLERADOS,
    INSATISFACAO_PROVOCACAO,
    IRRITACAO_ARREMESSO,
    JANELA_ARREMESSOS,
    COOLDOWN_CUTUCADA as POKE_COOLDOWN,
    ESPERA_MEDIDA_CUTUCADA as POKE_PROBE,
    HZ_RESPOSTA_CHEIA as POKE_FULL_HZ,
    RESPOSTA_MINIMA as POKE_MIN_RESPONSE,
)


class InteracaoMixin:
    """Ações do usuário sobre o pet: cutucar, arrastar, arremessar, dispensar travessuras e o menu do botão direito. Vira atributo de PestinhaApp."""
    def on_poke(self):
        """Você cutucou o pet: ele reage e a rede recebe o toque (ignorado na pausa)."""
        if self._congelado():
            return
        now = time.monotonic()
        if now - self.last_poke < POKE_COOLDOWN:
            return
        self.sad.grievance = max(0.0, self.sad.grievance - 0.25)     # cutucar alegra um pouco
        self.last_poke = now
        self.contar_no_diario("cutucadas")
        self.conditioning.outcome(now)
        self.senses.poke()
        self.timeline.note_interaction()
        self.drives.stimulate("poke")
        self.drives.touched("poke")
        self.memory.on_interaction()
        if self.asleep:
            self.sleep.wake(startled=True)
        # a reação NÃO é fixa: mede-se o que a rede fez com a cutucada (ver poke_reflex)
        self.poke_probe = (now + POKE_PROBE, self.brain.motor_activity()["CHEER"])

    def poke_reflex(self, delta_hz):
        """
        Tamanho da reação = aumento real de CHEER causado pela cutucada.
        Com cutucadas repetidas a sinapse de POKE habitua e a resposta encolhe:
        pulo grande, pulo menor, só os olhos, quase nada. Volta depois de minutos.
        """
        self.poke_probe = None
        response = max(0.0, min(1.0, delta_hz / POKE_FULL_HZ))
        if self.protest.stage == 3:
            response *= 0.2                         # em greve: mal responde
        self.last_poke_response = response
        body = self.pet.body
        if response >= POKE_MIN_RESPONSE and body.grounded:
            body.jump(0.0, -(150.0 + 650.0 * response))
        else:
            self.pet_state.blink_until = time.monotonic() + 0.13       # só pisca e olha
            cx, cy = cursor_pos()
            self.behavior.look_at(cx, cy, time.monotonic())
        if self.debugging():
            eff = self.brain.efficacy()["POKE"]
            log(f"[cutucada] resposta da rede {response:.2f} "
                  f"(+{delta_hz:.1f} Hz em CHEER, eficácia POKE {eff:.2f})")

    def on_drag_started(self):
        """Você pegou o pet: ele sente o arraste e a insatisfação baixa um pouco (você está interagindo)."""
        if self._congelado():
            return
        self.sad.grievance = max(0.0, self.sad.grievance - 0.1)
        self.conditioning.outcome(time.monotonic())
        self.senses.set_dragging(True)
        self.timeline.note_interaction()
        self.drives.stimulate("drag")
        self.drives.touched("drag")
        self.memory.on_interaction()
        if self.asleep:
            self.sleep.wake(startled=True)

    def on_thrown(self, speed):
        """
        Você arremessou o pet: a velocidade vira intensidade do arremesso; ele não aprende com isso na pausa.
        Os primeiros arremessos são brincadeira; muitos seguidos (JANELA_ARREMESSOS) irritam e somam insatisfação.
        """
        if self._congelado():
            return
        now = time.monotonic()
        self.conditioning.outcome(now)
        self.senses.thrown(min(1.0, speed / 2000.0))
        self.arremessos = [t for t in self.arremessos if now - t < JANELA_ARREMESSOS] + [now]
        if len(self.arremessos) > ARREMESSOS_TOLERADOS:
            self.senses.irritar(IRRITACAO_ARREMESSO)
            self.provocar(INSATISFACAO_PROVOCACAO)
            if self.debugging():
                log(f"[arremesso] {len(self.arremessos)} seguidos: irritou "
                    f"(insatisfação {self.protest.grievance:.2f})")
        self.timeline.note_interaction()
        self.drives.stimulate("throw")
        self.drives.touched("throw")
        self.in_flight = True

    def provocar(self, quanto):
        """Provocação física (arremesso demais, batida forte): soma insatisfação, se ele não estiver dormindo."""
        if not self.asleep:
            self.protest_ctl.provoke(quanto)

    def on_dismissed(self, thing, elapsed):
        """
        Você fechou uma travessura com um clique: vira frustração (a raiva sobe; várias seguidas, drama) e o tempo
        até você fechar vira aprendizado (fechar rápido é pior). Ele bufa, para você ver que não gostou.
        """
        if self._congelado():
            return                                   # o objeto some, mas não vira aprendizado na pausa
        agora = time.monotonic()
        self.mischief_ctl.on_dismissed(thing, elapsed, self.prof, agora)
        if getattr(self, "palco", None) is not None:
            self.palco.iniciar("bufo", agora)
        self.contar_no_diario("dispensadas")

    def on_fechado(self, thing, elapsed):
        """Você fechou uma travessura pelo ×: ele aprende que você não quis, sem ficar bravo (nem tremer)."""
        if self._congelado():
            return
        self.mischief_ctl.on_fechado(thing, elapsed, self.prof, time.monotonic())
        self.contar_no_diario("dispensadas")

    def arrancar_notebook(self, now):
        """Arrancaram o notebook dele: ele levanta e fica bravo ou triste, conforme o pet."""
        self.mesa.levantar_arrancado(now)
        self.senses.dismissed()                    # a dispensa entra na rede como frustração
        alvo = self.sad_ctl if self.reacao_notebook == "triste" else self.protest_ctl
        alvo.provoke(INSATISFACAO_NOTEBOOK)
        if self.debugging():
            log(f"[notebook] arrancado: reação {self.reacao_notebook}")

    def show_pet_menu(self, pos):
        """Mostra o menu do botão direito no pet; cada item fica desativado se não fizer sentido agora."""
        menu = QMenu()
        perms = self.perms

        def item(text, fn, enabled=True):
            """Cria um item do menu; `enabled=False` deixa o item visível mas sem ação."""
            act = menu.addAction(text)
            act.setEnabled(enabled)
            act.triggered.connect(fn)

        item("Cutucar", self.menu_poke, perms["cutucar"])
        item("Dar carinho", self.menu_caress, perms["carinho"])
        menu.addSeparator()
        item("Jogar a bolinha perto dele", self.menu_place_ball, perms["bolinha"])
        item("Guardar a bolinha", self.menu_store_ball, perms["bolinha"] and not self.ball_stored)
        menu.addSeparator()
        item("Pedir para dormir", self.menu_sleep, not self.asleep)
        item("Pedir para trabalhar", self.menu_pedir_trabalho)
        item("Mostrar o notebook" if self.mesa.escondido else "Esconder o notebook",
             self.menu_alternar_notebook)
        item("Fazer uma travessura agora", self.menu_mischief, perms["travessuras"])
        if getattr(self, "hermes", None):
            item("Conversar  (clique duplo · Ctrl+Alt+P)", self.menu_perguntar_hermes, not self._congelado())
            item("Começar conversa nova", self.hermes.esquecer_conversa)
            item("Minha cidade e horários...", self.menu_cidade_hermes)
            item("Ler meu diário...", self.hermes.ler_diario)
            item("Visitar alguém...", self.menu_visitar, not self._congelado() and not self.fora_de_casa)
        menu.addSeparator()
        item("Cantinho do castigo", lambda: self.castigo.toggle(self.bounds()))
        item("Painel de protesto", lambda: self.floats.toggle("greve"))
        item("Monitor neural", lambda: self.floats.toggle("neural"))
        item("Configurações...", self.open_settings)
        menu.addSeparator()
        item("Esconder (volta pela bandeja)", self.toggle_hidden)
        item("Fechar", self.menu_close)
        menu.exec(pos)

    def menu_perguntar_hermes(self):
        """Menu: abre o balão de conversa (o mesmo do clique duplo e do Ctrl+Alt+P)."""
        self.abrir_conversa()

    def menu_cidade_hermes(self):
        """Menu: cidade e horários de entrada e saída, para ele comentar o clima, a sexta-feira e os feriados."""
        atual = self.hermes.perfil or {}
        cidade, ok = QInputDialog.getText(None, self.nome, "Sua cidade (ex.: Franca, SP ou Lisboa, Portugal):",
                                          text=atual.get("cidade", ""))
        if not ok or not cidade.strip():
            return
        entrada, ok = QInputDialog.getText(None, self.nome, "Que horas você começa? (HH:MM)",
                                           text=atual.get("entrada", "08:00"))
        if not ok:
            return
        saida, ok = QInputDialog.getText(None, self.nome, "E que horas vai embora? (HH:MM)",
                                         text=atual.get("saida", "18:00"))
        if ok:
            self.hermes.configurar_perfil(cidade, entrada, saida)

    def mostrar_diario(self, texto):
        """As últimas páginas do diário (que o Hermes escreveu à noite), numa janelinha."""
        caixa = QMessageBox()
        caixa.setWindowTitle(f"Diário do {self.nome}")
        caixa.setText(texto)
        caixa.setIcon(QMessageBox.Icon.NoIcon)
        caixa.setStandardButtons(QMessageBox.StandardButton.Close)
        caixa.setModal(False)
        caixa.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.pet.figurino.abrir_caderno(time.monotonic())            # segura o caderno aberto enquanto você lê
        caixa.finished.connect(lambda _r: self.pet.figurino.tirar("caderno", time.monotonic()))
        caixa.show()
        self._caixa_diario = caixa              # sem referência, o Python apaga a janela na hora

    def menu_poke(self):
        """Menu: 'Cutucar' (ignora o intervalo mínimo entre cutucadas)."""
        self.last_poke = 0.0
        self.on_poke()

    def menu_caress(self):
        """Menu: 'Fazer carinho' (conta como carinho na rede, se não estiver pausado)."""
        if self._congelado():
            return
        self.pet_state.mark_caress()
        self.drives.touched("caress")
        self.memory.on_interaction()
        self.timeline.note_interaction()

    def menu_place_ball(self):
        """Menu: 'Pôr a bolinha' (coloca a bolinha perto do pet, no chão)."""
        self.ball_stored = False
        self.ball.body.x = self.pet.body.x + 130
        self.ball.body.y = self.bounds()[3] - 40
        self.ball.body.vx = self.ball.body.vy = 0.0
        self.update_visibility()

    def menu_store_ball(self):
        """Menu: 'Guardar a bolinha' (some com a bolinha até você pedir de novo)."""
        self.ball_stored = True
        self.update_visibility()

    def menu_sleep(self):
        """Menu: 'Dormir' (baixa a energia: ele cochila em vez de ficar acordado)."""
        if self._congelado():
            return
        self.drives.energy = min(self.drives.energy, 0.1)

    def menu_mischief(self):
        """Menu: 'Aprontar' (pede uma travessura agora)."""
        self.mischief_ctl.pedir(time.monotonic())

    def menu_alternar_notebook(self):
        """Menu: mostra ou esconde o notebook; sem o notebook, ele não pode sentar nele."""
        self.mesa.alternar_notebook()
        self.pet_state.at_desk = self.mesa.sentado
        if not self.mesa.sentado:
            self.pet_state.desk_top = None

    def menu_pedir_trabalho(self):
        """Menu: 'Pedir para trabalhar' (ele pode aceitar, ou recusar com frustração)."""
        self.mesa.pedir(time.monotonic())
