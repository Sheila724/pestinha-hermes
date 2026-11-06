"""
VISITAS - o seu pet indo à casa de outra pessoa, e o pet de outra pessoa vindo à sua (mixin do app).

  Visitar alguém...     menu do botão direito (ou "vai visitar a Talita" no balão): a ponte diz quem está
                        em casa, você escolhe, ele deixa um post-it avisando e sai de casa (some da tela)
  voltou                a ponte avisa quando a visita acabou: ele volta pulando e conta como foi
  visita                o pet de alguém aparece aqui (world/visitante.py), cumprimenta, brinca e vai embora
  Receber visitas       nas Configurações; desligado, ninguém vem (a ponte avisa quem tentou)

Sair de casa: não sai dormindo, de castigo, sentado no notebook, segurado ou com visita em casa. Se a ponte
não avisar a volta (VPS fora do ar), ele volta sozinho depois de VOLTA_SOZINHO_S.
"""

import time

from PySide6.QtWidgets import QInputDialog

from .. import config
from ..body.desenho_rosto import aparencia_de
from ..world.visitante import Visitante

VOLTA_SOZINHO_S = 6 * 60
SAIR_DEPOIS_S = 0.8               # o post-it aparece, ele pula, e só então some


def da(nome):
    return f"da {nome}" if nome else "do vizinho"


class VisitasMixin:
    def _iniciar_visitas(self):
        self.fora_de_casa = None          # nome de quem ele foi visitar
        self._fora_desde = 0.0
        self.visitante = None

    # ---------- sair de casa ----------

    def motivo_para_nao_sair(self):
        """Por que ele não pode sair agora (texto do post-it), ou None."""
        if self.fora_de_casa:
            return "Eu já estou na rua!"
        if self.visitante is not None:
            return "Agora não, tô com visita aqui!"
        if self.asleep:
            return "Zzz… agora não, tô dormindo."
        if self.castigo.dentro:
            return "Tô de castigo, não posso sair."
        if self.mesa.sentado:
            return "Agora não, tô trabalhando."
        if self.pet.body.held:
            return "Me solta primeiro!"
        return None

    def menu_visitar(self):
        """Menu: pergunta à ponte quem está em casa (a escolha vem em `escolher_vizinho`)."""
        if not self.hermes:
            return
        motivo = self.motivo_para_nao_sair()
        if motivo:
            self.mostrar_fala(motivo)
            return
        self.hermes.vizinhos()

    def escolher_vizinho(self, lista):
        """Mostra quem está em casa e manda o pet para lá."""
        if not lista:
            self.mostrar_fala("Não tem ninguém em casa agora. Tá todo mundo com o pet fechado.")
            return
        nomes = [v["nome"] + ("" if v.get("recebe", True) else "  (não está recebendo visitas)") for v in lista]
        escolha, ok = QInputDialog.getItem(None, f"{self.nome}: visitar", "Quem você quer que eu visite?",
                                           nomes, 0, False)
        if ok and escolha in nomes:
            motivo = self.motivo_para_nao_sair()          # pode ter mudado enquanto a janela estava aberta
            if motivo:
                self.mostrar_fala(motivo)
            else:
                self.hermes.visitar(lista[nomes.index(escolha)]["id"])

    def sair_de_casa(self, dados, agora=None):
        """A ponte confirmou a visita: avisa num post-it, dá um pulinho e some da tela."""
        agora = time.monotonic() if agora is None else agora
        nome = dados.get("nome", "")
        self.mostrar_fala(dados.get("fala") or f"Fui visitar o pet {da(nome)}! Volto já.")
        if self.palco is not None:
            self.palco.iniciar("brilho", agora)
        if self.asleep:
            self.sleep.wake(startled=False)
        if self.mesa.sentado:
            self.mesa.levantar_arrancado(agora)
        self.pular()
        self.contar_no_diario("visitas_feitas")
        self.agendar(SAIR_DEPOIS_S, lambda: self._sumir(nome), agora)

    def _sumir(self, nome):
        self.fora_de_casa = nome or "vizinho"
        self._fora_desde = time.monotonic()
        self.behavior.drop_carried()
        self.update_visibility()

    def voltar_para_casa(self, texto, agora=None):
        """A visita acabou: ele aparece de novo, pula e conta como foi."""
        agora = time.monotonic() if agora is None else agora
        if not self.fora_de_casa:
            self.mostrar_fala(texto)                     # chegou depois de reabrir o pet: só conta
            return
        self.fora_de_casa = None
        self.update_visibility()
        if self.palco is not None:
            self.palco.iniciar("exclamacao", agora)
        self.pular()
        self.agendar(0.6, lambda: self.mostrar_fala(texto), agora)

    # ---------- receber visita ----------

    def receber_visita(self, dados, agora=None):
        """O pet de alguém chegou: aparece num canto, vem até o seu e cumprimenta."""
        agora = time.monotonic() if agora is None else agora
        if not self.perms.get("visitas", True) or self.fora_de_casa or self.visitante is not None:
            self.hermes.fim_da_visita(dados["visita"], "")
            return
        pet_id = dados.get("pet", "")
        if pet_id not in config.list_pets(self.paths):
            pet_id = config.PET_PADRAO                   # personagem que este executável não tem
        aparencia = aparencia_de(config.load_pet(self.paths, pet_id).get("aparencia"))
        body = self.pet.body
        self.visitante = Visitante(dados, aparencia, body.x, body.y, self.bounds(), agora)
        self.visitante.janela.poked.connect(self._cutucaram_a_visita)
        if self.palco is not None:
            self.palco.iniciar("exclamacao", agora)
        self.contar_no_diario("visitas_recebidas")

    def _cutucaram_a_visita(self):
        v = self.visitante
        if v is not None:
            self.mischief.mostrar_fala("Ei! Eu sou visita, tá?", v.x, v.y - 150, self.bounds(), origem=(v.x, v.y - 10))

    def tick_visitas(self, agora):
        """A cada quadro: anda com o visitante e traz o pet de volta se a ponte sumiu."""
        if self.fora_de_casa and agora - self._fora_desde > VOLTA_SOZINHO_S:
            self.voltar_para_casa("Voltei! Me perdi no caminho, mas cheguei.", agora)
        v = self.visitante
        if v is None:
            return
        body = self.pet.body
        for momento in v.tick(agora, body.x, body.y):
            if momento in ("cumprimentar", "despedir"):
                fala = v.dados["cumprimento" if momento == "cumprimentar" else "despedida"]
                self.mischief.mostrar_fala(fala, v.x, v.y - 150, self.bounds(), origem=(v.x, v.y - 10))
                if momento == "cumprimentar" and self.palco is not None:
                    self.palco.iniciar("brilho", agora)
                    self.pular()
            elif momento == "acabou":
                self.hermes.fim_da_visita(v.dados["visita"], self.pet_state.emotion)
                self.visitante = None

    def fechar_visitas(self):
        if self.visitante is not None:
            self.visitante.fechar()
            self.visitante = None
