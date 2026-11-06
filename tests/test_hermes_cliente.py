"""O pet se identifica para a ponte: id aleatório do computador e usuário (usados no pet da equipe)."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pestinha.paths import Paths  # noqa: E402
from pestinha.sense import hermes  # noqa: E402


def test_id_do_computador_e_fixo_e_aleatorio(tmp_path):
    arquivo = tmp_path / "memory" / "hermes_cliente.txt"
    primeiro = hermes.id_do_computador(arquivo)
    assert len(primeiro) == 32 and hermes.id_do_computador(arquivo) == primeiro
    assert hermes.id_do_computador(tmp_path / "outro.txt") != primeiro
    arquivo.write_text("lixo", encoding="utf-8")
    assert len(hermes.id_do_computador(arquivo)) == 32 and arquivo.read_text(encoding="utf-8") != "lixo"


def test_caminho_do_id_fica_na_memory(tmp_path):
    paths = Paths(root=tmp_path)
    assert paths.hermes_cliente.parent == paths.hermes_ultimo.parent


def test_pedidos_levam_o_id_e_o_usuario(tmp_path, monkeypatch):
    vistos = []

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def abrir(req, timeout=None):
        vistos.append({k.lower(): v for k, v in req.header_items()})
        return Resposta(json.dumps({"eventos": [], "ultimo": 0}).encode())

    monkeypatch.setattr(hermes, "usuario", lambda: "sheila.alves")
    monkeypatch.setattr(hermes.urllib.request, "urlopen", abrir)
    c = hermes.ClienteHermes("https://x.exemplo", "t" * 64, tmp_path / "memory" / "hermes_ultimo.txt")
    assert c.consultar()
    cab = vistos[0]
    assert len(cab["x-pestinha-cliente"]) == 32 and cab["x-pestinha-quem"] == "sheila.alves"
    assert (tmp_path / "memory" / "hermes_cliente.txt").read_text(encoding="utf-8") == cab["x-pestinha-cliente"]
