"""Cores estáveis por candidato, compartilhadas pelo mapa e pelo gráfico."""

from eleicoes.normalizacao import chave_texto

PALETA = [
    "#0E6B4F",
    "#C2410C",
    "#A16207",
    "#7C3AED",
    "#0E7490",
    "#3F6212",
    "#9F1239",
    "#0369A1",
]

COR_LUIZ_INACIO = "#DC2626"
COR_FLAVIO_BOLSONARO = "#1D4ED8"
COR_EMPATE = "#6B7280"
COR_SEM_VENCEDOR = "#9CA3AF"


def cor_fixa(nome: str) -> str | None:
    """Vermelho para Luiz Inácio e azul para Flávio Bolsonaro, em qualquer grafia."""
    chave = chave_texto(nome)
    if "LUIZ INACIO" in chave:
        return COR_LUIZ_INACIO
    if "FLAVIO" in chave and "BOLSONARO" in chave:
        return COR_FLAVIO_BOLSONARO
    return None


def mapa_cores(vencedores: list[str], outros: list[str] | None = None) -> dict[str, str]:
    """Atribui cores. Quem vence algum bairro recebe as primeiras cores da paleta."""
    ordem: list[str] = []
    for nome in list(vencedores) + list(outros or []):
        if not nome or nome in ordem or str(nome).startswith("Empate") or nome.startswith("Sem "):
            continue
        ordem.append(nome)
    cores: dict[str, str] = {}
    indice_paleta = 0
    for nome in ordem:
        fixa = cor_fixa(nome)
        if fixa:
            cores[nome] = fixa
            continue
        cores[nome] = PALETA[indice_paleta % len(PALETA)]
        indice_paleta += 1
    cores["Empate"] = COR_EMPATE
    return cores


def cor_de(nome: str, cores: dict[str, str]) -> str:
    if not nome or nome.startswith("Empate"):
        return COR_EMPATE
    if nome.startswith("Sem "):
        return COR_SEM_VENCEDOR
    fixa = cor_fixa(nome)
    if fixa:
        return fixa
    return cores.get(nome, PALETA[0])
