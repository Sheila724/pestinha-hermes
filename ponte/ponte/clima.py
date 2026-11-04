"""
Onde fica a cidade e como vai estar o tempo, pelo Open-Meteo (gratuito, sem chave).

- Geocodificação: https://geocoding-api.open-meteo.com/v1/search
- Previsão:       https://api.open-meteo.com/v1/forecast
"""
import unicodedata

import httpx

URL_BUSCA = "https://geocoding-api.open-meteo.com/v1/search"
URL_PREVISAO = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 15.0
CHUVA_PROVAVEL = 50          # % de chance a partir da qual vale avisar

UF = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}


class ClimaErro(Exception):
    """Não deu para achar a cidade ou buscar a previsão."""


def _normal(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def _get(url, params, cliente):
    try:
        r = cliente.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as erro:
        raise ClimaErro(str(erro)) from erro


def geocodificar(cidade, cliente=httpx):
    """
    "Franca, SP" / "Lisboa" / "Porto, Portugal" -> {nome, lat, lon, fuso, pais}.
    O que vem depois da vírgula (sigla do estado, estado ou país) desempata cidades com o mesmo nome.
    """
    partes = [p.strip() for p in str(cidade).split(",") if p.strip()]
    if not partes:
        raise ClimaErro("cidade vazia")
    nome, dica = partes[0], ", ".join(partes[1:])
    dados = _get(URL_BUSCA, {"name": nome, "count": 10, "language": "pt", "format": "json"}, cliente)
    resultados = [r for r in dados.get("results") or [] if "latitude" in r and "timezone" in r]
    if not resultados:
        raise ClimaErro(f"não achei a cidade {nome!r}")
    escolhido = resultados[0]
    if dica:
        procura = _normal(UF.get(dica.upper(), dica))
        for r in resultados:
            onde = " ".join(_normal(r.get(k, "")) for k in ("admin1", "country", "country_code"))
            if procura in onde:
                escolhido = r
                break
        else:
            raise ClimaErro(f"não achei {nome!r} em {dica!r}")
    regiao = escolhido.get("admin1") or escolhido.get("country", "")
    return {
        "nome": f"{escolhido['name']}, {regiao}".rstrip(", "),
        "lat": float(escolhido["latitude"]),
        "lon": float(escolhido["longitude"]),
        "fuso": escolhido["timezone"],
        "pais": escolhido.get("country_code", ""),
    }


def previsao(lugar, cliente=httpx):
    """Previsão de hoje e amanhã: mínimas, máximas, chance de chuva por dia e por hora (no fuso da cidade)."""
    dados = _get(URL_PREVISAO, {
        "latitude": lugar["lat"], "longitude": lugar["lon"], "timezone": lugar["fuso"], "forecast_days": 2,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "hourly": "precipitation_probability",
    }, cliente)
    try:
        diario, horario = dados["daily"], dados["hourly"]
        dias = [{"data": diario["time"][i], "max": diario["temperature_2m_max"][i],
                 "min": diario["temperature_2m_min"][i], "chuva": diario["precipitation_probability_max"][i]}
                for i in range(len(diario["time"]))]
        horas = dict(zip(horario["time"], horario["precipitation_probability"]))
    except (KeyError, IndexError, TypeError) as erro:
        raise ClimaErro(f"previsão em formato inesperado: {erro}") from erro
    return {"dias": dias, "horas": horas}


def chuva_entre(prev, inicio, fim):
    """Maior chance de chuva (%) nas horas de `inicio` a `fim` (datetimes no fuso da cidade), ou 0."""
    chances = [p for t, p in prev["horas"].items()
               if p is not None and inicio.strftime("%Y-%m-%dT%H:00") <= t <= fim.strftime("%Y-%m-%dT%H:00")]
    return max(chances, default=0)
