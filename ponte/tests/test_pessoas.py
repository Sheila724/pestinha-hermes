"""Outra pessoa na mesma VPS: nome da dona e jeito do pet escolhidos pelo .env."""
import re

import pytest

from ponte import config, diario
from ponte.config import JEITOS

TOKEN = "t" * 64


def test_padrao_e_a_sheila_travesso():
    cfg = config.carregar({"PONTE_TOKEN": TOKEN})
    assert cfg.dono == "Sheila" and "computador da Sheila" in cfg.persona
    assert "travesso e carinhoso" in cfg.persona


def test_outra_dona_e_zoeiro():
    cfg = config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_DONO": "  Ana   Paula ", "PONTE_JEITO": "zoeiro"})
    assert cfg.dono == "Ana Paula"
    assert "computador da Ana Paula" in cfg.persona and "Sheila" not in cfg.persona
    assert "zoeiro e sarcástico" in cfg.persona and "travesso e carinhoso" not in cfg.persona
    assert "[lembrete:" in cfg.persona and "[acao:" in cfg.persona               # as regras continuam


@pytest.mark.parametrize("jeito", sorted(a.stem for a in JEITOS.glob("*.md")))
def test_todo_jeito_monta_sem_sobras(jeito):
    persona = config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_JEITO": jeito, "PONTE_DONO": "Ana"}).persona
    assert not re.search(r"\{(dono|jeito|exemplos)\}", persona)
    assert "\n---\n" not in persona and not any(l.startswith("# ") for l in persona.splitlines())
    tom, exemplos = config.ler_jeito(jeito)
    assert tom.startswith("- Tom") and "[acao:" in exemplos


@pytest.mark.parametrize("jeito", ["nao_existe", "../persona", "Zoeiro"])
def test_jeito_invalido_avisa(jeito):
    with pytest.raises(RuntimeError, match="PONTE_JEITO"):
        config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_JEITO": jeito})


def test_persona_propria_sem_marcas_continua_valendo(tmp_path):
    arquivo = tmp_path / "minha.md"
    arquivo.write_text("Você é um gato.", encoding="utf-8")
    assert config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_PERSONA": str(arquivo)}).persona == "Você é um gato."


def test_diario_usa_o_nome_da_dona():
    assert "a Ana me perguntou 2 coisa(s)" in diario.fatos({"contagens": {"perguntas": 2}}, "Ana")
    assert "a Sheila me perguntou 1 coisa(s)" in diario.fatos({"contagens": {"perguntas": 1}})
