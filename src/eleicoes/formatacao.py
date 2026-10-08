"""Formatação de números no padrão brasileiro, para a tela e os rótulos do mapa."""

import math


def _ausente(valor: object) -> bool:
    if valor is None:
        return True
    if isinstance(valor, str):
        return valor.strip() == ""
    try:
        return math.isnan(float(valor))
    except (TypeError, ValueError):
        return False


def fmt_int(valor: object) -> str:
    if _ausente(valor):
        return "—"
    return f"{int(round(float(valor))):,}".replace(",", ".")


def fmt_pct(valor: object) -> str:
    if _ausente(valor):
        return "—"
    return f"{float(valor):.1f}%".replace(".", ",")


def fmt_pp(valor: object) -> str:
    """Margem em pontos percentuais, por exemplo ``1,6 p.p.``."""
    if _ausente(valor):
        return "—"
    numero = f"{float(valor):.1f}".replace(".", ",")
    return f"{numero} p.p."


def fmt_turno(turno: int) -> str:
    return f"{int(turno)}º turno"
