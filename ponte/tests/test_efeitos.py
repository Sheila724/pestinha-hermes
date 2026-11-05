"""Animações que a ponte pede ao pet: tempo do dia, festa de sexta/véspera de feriado e o caderninho do diário."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from ponte import config, diario, hermes, lado_de_fora
from ponte.app import criar_app
from ponte.clima import efeitos_do_dia
from ponte.eventos import Eventos
from ponte.mundo import Mundo
from ponte.perfil import Perfil

TOKEN = "t" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SP = ZoneInfo("America/Sao_Paulo")
FRANCA = {"nome": "Franca, São Paulo", "lat": -20.54, "lon": -47.4, "fuso": "America/Sao_Paulo", "pais": "BR",
          "cidade": "Franca, SP", "entrada": "08:00", "saida": "18:00"}


def prev_para(dia, maxima=31.4, minima=18.6, chuva=80, horas=None):
    return {"dias": [{"data": dia.isoformat(), "max": maxima, "min": minima, "chuva": chuva}],
            "horas": horas or {}}


@pytest.fixture
def cfg(tmp_path):
    return config.carregar({"PONTE_TOKEN": TOKEN, "PONTE_BANCO": str(tmp_path / "p.db")})


@pytest.mark.parametrize("dia, chance, esperado", [
    ({"max": 31.4, "min": 18.6, "chuva": 80}, None, ["chuva", "calor"]),
    ({"max": 22.0, "min": 9.0, "chuva": 10}, None, ["frio"]),
    ({"max": 25.0, "min": 15.0, "chuva": 80}, 0, []),                  # chuva hoje, mas não nas próximas horas
    ({"max": 25.0, "min": 15.0, "chuva": 0}, 90, ["chuva"]),
    (None, 90, []),
])
def test_efeitos_do_dia(dia, chance, esperado):
    assert efeitos_do_dia(dia, chance) == esperado


def test_aviso_de_manha_veste_o_tempo_do_dia():
    agora = dt.datetime(2026, 11, 4, 8, 5, tzinfo=SP)                   # quarta
    assert lado_de_fora.efeitos("manha", prev_para(agora.date()), agora) == ["chuva", "calor"]


def test_aviso_de_saida_chuva_na_volta_e_festa_na_sexta():
    sexta = dt.datetime(2026, 11, 6, 17, 30, tzinfo=SP)
    horas = {"2026-11-06T18:00": 85}
    assert lado_de_fora.efeitos("saida", prev_para(sexta.date(), horas=horas), sexta) == ["chuva", "festa"]
    quarta = dt.datetime(2026, 11, 4, 17, 30, tzinfo=SP)
    assert lado_de_fora.efeitos("saida", prev_para(quarta.date(), chuva=0), quarta) == []
    assert lado_de_fora.efeitos("saida", None, sexta) == ["festa"]          # sem previsão, a festa continua


def test_evento_do_aviso_leva_os_efeitos(cfg):
    perfil, eventos = Perfil(cfg.banco), Eventos(cfg.banco)
    perfil.gravar(FRANCA)
    agora = dt.datetime(2026, 11, 6, 17, 31, tzinfo=SP).astimezone(dt.timezone.utc)
    assert lado_de_fora.verificar(cfg, perfil, eventos, agora,
                                  buscar_previsao=lambda l: prev_para(dt.date(2026, 11, 6)),
                                  perguntar=lambda c, t: "Sextou!")
    assert eventos.depois_de(0)[0][-1]["efeitos"] == ["festa"]


def test_pagina_do_diario_pede_o_caderninho(cfg):
    d, p, e = diario.Diario(cfg.banco), Perfil(cfg.banco), Eventos(cfg.banco)
    d.guardar_dia("2026-11-04", {"emocoes": {"feliz": 10.0}, "contagens": {"cutucadas": 3}})
    quando = dt.datetime(2026, 11, 4, 21, 5, tzinfo=SP).astimezone(dt.timezone.utc)
    assert diario.verificar(cfg, d, p, e, quando, perguntar=lambda c, t: "Querido diário…")
    assert e.depois_de(0)[0][-1]["efeitos"] == ["diario"]


def test_mundo_efeitos_sem_cidade_ou_previsao(cfg):
    perfil = Perfil(cfg.banco)
    assert Mundo(perfil, lambda l: prev_para(dt.date.today())).efeitos() == []
    perfil.gravar(FRANCA)
    assert Mundo(perfil, lambda l: None).efeitos() == []


def test_perguntar_do_tempo_devolve_efeitos(cfg, monkeypatch):
    perfil = Perfil(cfg.banco)
    perfil.gravar(FRANCA)
    hoje = dt.datetime.now(SP).date()
    monkeypatch.setattr(hermes, "perguntar", lambda c, texto, historico=None: "Vai chover sim!")
    c = TestClient(criar_app(cfg, buscar_previsao=lambda l: prev_para(hoje, chuva=10, maxima=33)))
    r = c.post("/api/perguntar", headers=AUTH, json={"texto": "vai fazer calor hoje?"}).json()
    assert r["resposta"] == "Vai chover sim!" and r["efeitos"] == ["calor"]
    r = c.post("/api/perguntar", headers=AUTH, json={"texto": "me conta uma piada"}).json()
    assert "efeitos" not in r
