"""
DIÁRIO - o que o pet viveu hoje, para ele escrever no diário à noite (a página é escrita na VPS, pelo Hermes).

Guarda só números: quantos minutos em cada emoção e quantas cutucadas, carinhos, castigos, fugas,
travessuras, cochilos, protestos e pedidos do Hermes. Nada do que aparece na sua tela.

Duas formas de alimentar:
  observar(...)   amostra periódica do estado: soma o tempo da emoção e conta as viradas
                  (adormeceu, ganhou carinho, entrou no castigo, fugiu, começou a protestar)
  contar(nome)    eventos que o app vê na hora: cutucada, travessura, dispensa, pergunta, pedido

Sem Qt. Grava em memory/diario_hoje.json e zera sozinho quando o dia vira.
"""

import datetime as dt
import json
from pathlib import Path

CONTAGENS = ("cutucadas", "carinhos", "castigos", "fugas", "travessuras", "dispensadas",
             "cochilos", "protestos", "perguntas", "obedeceu", "recusou", "visitas_feitas", "visitas_recebidas")
MAX_PASSO_S = 30.0          # um intervalo maior (pausa, computador dormindo) não vira minutos de emoção


class DiarioDoDia:
    def __init__(self, arquivo, hoje=dt.date.today):
        self._arquivo = Path(arquivo)
        self._hoje = hoje
        self._anterior = {}
        self.anotacoes = 0                      # quantas vezes anotou algo desde que o pet abriu
        self._carregar()

    # ---------- o que o app usa ----------

    def observar(self, dt_s, emocao, *, dormindo, carinho, castigo, ultima_fuga, protesto):
        """Amostra do estado: `dt_s` segundos desde a última, e as viradas viram contagens."""
        self._virar_o_dia()
        if 0 < dt_s <= MAX_PASSO_S and emocao:
            self.emocoes[emocao] = self.emocoes.get(emocao, 0.0) + dt_s / 60.0
        a = self._anterior
        if a:
            if dormindo and not a["dormindo"]:
                self.contar("cochilos")
            if carinho and not a["carinho"]:
                self.contar("carinhos")
            if castigo and not a["castigo"]:
                self.contar("castigos")
            if ultima_fuga is not None and ultima_fuga != a["ultima_fuga"]:
                self.contar("fugas")
            if protesto >= 2 > a["protesto"]:
                self.contar("protestos")
        self._anterior = {"dormindo": dormindo, "carinho": carinho, "castigo": castigo,
                          "ultima_fuga": ultima_fuga, "protesto": protesto}

    def contar(self, nome, n=1):
        if nome in CONTAGENS and n > 0:
            self._virar_o_dia()
            self.contagens[nome] = self.contagens.get(nome, 0) + n
            self.anotacoes += 1                 # o app vê isso subir e o pet rabisca no caderninho

    def resumo(self):
        """O que vai para a ponte: {"data", "emocoes": {nome: minutos}, "contagens": {nome: n}}."""
        self._virar_o_dia()
        return {"data": self.data,
                "emocoes": {e: round(m, 1) for e, m in self.emocoes.items()},
                "contagens": dict(self.contagens)}

    def salvar(self):
        try:
            self._arquivo.parent.mkdir(parents=True, exist_ok=True)
            self._arquivo.write_text(json.dumps(self.resumo(), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass                    # sem disco: só perde o diário de hoje se fechar

    # ---------- por dentro ----------

    def _zerar(self):
        self.data = self._hoje().isoformat()
        self.emocoes = {}
        self.contagens = {}

    def _carregar(self):
        self._zerar()
        try:
            dados = json.loads(self._arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(dados, dict) and dados.get("data") == self.data:
            self.emocoes = {str(e): float(m) for e, m in (dados.get("emocoes") or {}).items()}
            self.contagens = {str(c): int(n) for c, n in (dados.get("contagens") or {}).items() if c in CONTAGENS}

    def _virar_o_dia(self):
        if self._hoje().isoformat() != self.data:
            self._zerar()
