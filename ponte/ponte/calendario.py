"""Feriados nacionais do Brasil (fixos e móveis), calculados aqui mesmo, sem consultar nada."""
import datetime as dt

FIXOS = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (9, 7): "Independência do Brasil",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Dia da Consciência Negra",
    (12, 25): "Natal",
}
DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return dt.date(ano, mes, dia)


def feriados(ano):
    """{data: nome} dos feriados nacionais e do Carnaval (ponto facultativo, mas quase todo mundo para)."""
    p = pascoa(ano)
    datas = {dt.date(ano, m, d): nome for (m, d), nome in FIXOS.items()}
    datas[p - dt.timedelta(days=48)] = "Carnaval"
    datas[p - dt.timedelta(days=47)] = "Carnaval"
    datas[p - dt.timedelta(days=2)] = "Sexta-feira Santa"
    datas[p + dt.timedelta(days=60)] = "Corpus Christi"
    return datas


def feriado(data, pais="BR"):
    """Nome do feriado nesse dia, ou None. Por enquanto só o calendário do Brasil."""
    return feriados(data.year).get(data) if pais == "BR" else None


def dia_util(data, pais="BR"):
    return data.weekday() < 5 and feriado(data, pais) is None


def fatos_do_dia(data, pais="BR"):
    """Coisas que valem comentar hoje: sexta-feira, véspera de feriado, feriado prolongado."""
    fatos = []
    amanha = data + dt.timedelta(days=1)
    nome_amanha = feriado(amanha, pais)
    if nome_amanha:
        fatos.append(f"amanhã é feriado ({nome_amanha})")
        if amanha.weekday() == 4 or (amanha.weekday() == 0 and data.weekday() == 6):
            fatos.append("vai ser feriado prolongado")
    if data.weekday() == 4:
        segunda = data + dt.timedelta(days=3)
        if feriado(segunda, pais):
            fatos.append(f"segunda que vem é feriado ({feriado(segunda, pais)}): fim de semana prolongado")
        else:
            fatos.append("hoje é sexta-feira")
    return fatos
