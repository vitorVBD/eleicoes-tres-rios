"""Cores estáveis por candidato, compartilhadas pelo mapa e pelo gráfico."""

PALETA = [
    "#0E6B4F",
    "#C2410C",
    "#1D4ED8",
    "#A16207",
    "#7C3AED",
    "#BE123C",
    "#0E7490",
    "#3F6212",
    "#9F1239",
    "#0369A1",
]

COR_EMPATE = "#6B7280"
COR_SEM_VENCEDOR = "#9CA3AF"


def mapa_cores(vencedores: list[str], outros: list[str] | None = None) -> dict[str, str]:
    """Atribui cores. Quem vence algum bairro recebe as primeiras cores da paleta."""
    ordem: list[str] = []
    for nome in list(vencedores) + list(outros or []):
        if not nome or nome in ordem or str(nome).startswith("Empate") or nome.startswith("Sem "):
            continue
        ordem.append(nome)
    cores = {nome: PALETA[indice % len(PALETA)] for indice, nome in enumerate(ordem)}
    cores["Empate"] = COR_EMPATE
    return cores


def cor_de(nome: str, cores: dict[str, str]) -> str:
    if not nome or nome.startswith("Empate"):
        return COR_EMPATE
    if nome.startswith("Sem "):
        return COR_SEM_VENCEDOR
    return cores.get(nome, PALETA[0])
