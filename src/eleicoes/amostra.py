"""CSVs pequenos no formato do TSE, só para demonstrar a ferramenta.

Os votos são fictícios. Servem para abrir o painel antes de baixar os
arquivos oficiais e para o teste automático do cruzamento.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ANO = "2024"

# Totais nominais do 1º turno para prefeito. O teste automático confere Centro.
VOTOS_PREFEITO_TURNO_1 = {
    "Centro": {"Ana Ribeiro": 820, "Carlos Mendonça": 790, "Helena Duarte": 210},
    "Vila Isabel": {"Ana Ribeiro": 1500, "Carlos Mendonça": 400, "Helena Duarte": 100},
    "Boa União": {"Ana Ribeiro": 620, "Carlos Mendonça": 640, "Helena Duarte": 80},
    "Cantagalo": {"Ana Ribeiro": 180, "Carlos Mendonça": 220, "Helena Duarte": 460},
    "Moura Brasil": {"Ana Ribeiro": 510, "Carlos Mendonça": 300, "Helena Duarte": 90},
    "Triângulo": {"Ana Ribeiro": 240, "Carlos Mendonça": 770, "Helena Duarte": 60},
    "Monte Castelo": {"Ana Ribeiro": 400, "Carlos Mendonça": 398, "Helena Duarte": 20},
    "Nova Niterói": {"Ana Ribeiro": 680, "Carlos Mendonça": 250, "Helena Duarte": 70},
    "Pilões": {"Ana Ribeiro": 140, "Carlos Mendonça": 160, "Helena Duarte": 50},
    "Bemposta": {"Ana Ribeiro": 200, "Carlos Mendonça": 430, "Helena Duarte": 40},
}

VOTOS_PREFEITO_TURNO_2 = {
    "Centro": {"Ana Ribeiro": 980, "Carlos Mendonça": 950},
    "Vila Isabel": {"Ana Ribeiro": 1700, "Carlos Mendonça": 500},
    "Boa União": {"Ana Ribeiro": 740, "Carlos Mendonça": 760},
    "Cantagalo": {"Ana Ribeiro": 400, "Carlos Mendonça": 520},
    "Moura Brasil": {"Ana Ribeiro": 600, "Carlos Mendonça": 360},
    "Triângulo": {"Ana Ribeiro": 280, "Carlos Mendonça": 860},
    "Monte Castelo": {"Ana Ribeiro": 428, "Carlos Mendonça": 430},
    "Nova Niterói": {"Ana Ribeiro": 800, "Carlos Mendonça": 300},
    "Pilões": {"Ana Ribeiro": 170, "Carlos Mendonça": 190},
    "Bemposta": {"Ana Ribeiro": 230, "Carlos Mendonça": 500},
}

# No Centro a legenda é de propósito maior que qualquer nome: o vencedor
# tem de continuar sendo a pessoa, não o partido.
VOTOS_VEREADOR = {
    "Centro": {
        "Joana Pires": 400,
        "Paulo Nunes": 350,
        "Lúcia Ferreira": 120,
        "Marcos Teixeira": 80,
        "Partido da Árvore": 900,
        "Partido do Rio": 100,
    }
}

NUMEROS = {
    "Ana Ribeiro": "22",
    "Carlos Mendonça": "15",
    "Helena Duarte": "45",
    "Joana Pires": "22111",
    "Paulo Nunes": "15000",
    "Lúcia Ferreira": "45123",
    "Marcos Teixeira": "13013",
    "Partido da Árvore": "22",
    "Partido do Rio": "15",
    "Branco": "95",
    "Nulo": "96",
}

BAIRROS = [
    {"bairro": "Centro", "local": "ESCOLA MUNICIPAL PROFESSOR JOÃO DA SILVA", "endereco": "Rua Marechal Deodoro, 100", "lat": -22.1168, "lon": -43.2088, "secoes": 4, "zona": "153", "aptos": 625, "abstencao": 100},
    {"bairro": "Vila Isabel", "local": "CIEP VILA ISABEL", "endereco": "Rua das Hortênsias, 40", "lat": -22.1089, "lon": -43.2012, "secoes": 3, "zona": "153", "aptos": 700, "abstencao": 84},
    {"bairro": "Boa União", "local": "ESCOLA MUNICIPAL BOA UNIÃO", "endereco": "Rua do Bosque, 220", "lat": -22.1226, "lon": -43.2165, "secoes": 3, "zona": "153", "aptos": 500, "abstencao": 90},
    {"bairro": "Cantagalo", "local": "COLEGIO ESTADUAL CANTAGALO", "endereco": "Avenida Independência, 15", "lat": -22.1284, "lon": -43.1995, "secoes": 2, "zona": "153", "aptos": 450, "abstencao": 72},
    {"bairro": "Moura Brasil", "local": "ESCOLA MUNICIPAL MOURA BRASIL", "endereco": "Rua do Comércio, 88", "lat": -22.1122, "lon": -43.1960, "secoes": 2, "zona": "153", "aptos": 480, "abstencao": 86},
    {"bairro": "Triângulo", "local": "ESCOLA MUNICIPAL TRIANGULO", "endereco": "Rua Sete de Setembro, 310", "lat": -22.1194, "lon": -43.2238, "secoes": 2, "zona": "153", "aptos": 520, "abstencao": 78},
    {"bairro": "Monte Castelo", "local": "ESCOLA MUNICIPAL MONTE CASTELO", "endereco": "Rua das Palmeiras, 12", "lat": -22.1255, "lon": -43.2080, "secoes": 2, "zona": "153", "aptos": 410, "abstencao": 49},
    {"bairro": "Nova Niterói", "local": "ESCOLA MUNICIPAL NOVA NITEROI", "endereco": "Rua Projetada, 70", "lat": -22.1035, "lon": -43.2148, "secoes": 2, "zona": "153", "aptos": 460, "abstencao": 69},
    {"bairro": "Pilões", "local": "ESCOLA MUNICIPAL PILOES", "endereco": "Estrada dos Pilões, 500", "lat": -22.1328, "lon": -43.2210, "secoes": 2, "zona": "153", "aptos": 400, "abstencao": 128},
    {"bairro": "Bemposta", "local": "ESCOLA MUNICIPAL BEMPOSTA", "endereco": "Rua Principal, 25", "lat": -22.1210, "lon": -43.1885, "secoes": 2, "zona": "154", "aptos": 380, "abstencao": 57},
]


def _distribuir(total: int, partes: int) -> list[int]:
    base, resto = divmod(int(total), partes)
    return [base + (1 if indice < resto else 0) for indice in range(partes)]


def _montar_secoes() -> dict[str, list[dict]]:
    proxima = {}
    por_bairro: dict[str, list[dict]] = {}
    for item in BAIRROS:
        zona = item["zona"]
        proxima.setdefault(zona, 1)
        secoes = []
        for _ in range(item["secoes"]):
            secoes.append(
                {
                    "zona": zona,
                    "secao": str(proxima[zona]),
                    "bairro": item["bairro"],
                    "local": item["local"],
                    "endereco": item["endereco"],
                    "lat": item["lat"],
                    "lon": item["lon"],
                    "aptos": item["aptos"],
                    "abstencao": item["abstencao"],
                }
            )
            proxima[zona] += 1
        por_bairro[item["bairro"]] = secoes
    return por_bairro


def _linhas_voto(por_bairro: dict[str, list[dict]], cargo: str, turno: int, totais: dict[str, dict[str, int]]) -> list[dict]:
    linhas = []
    for bairro, candidatos in totais.items():
        secoes = por_bairro[bairro]
        pacote = dict(candidatos)
        pacote["Branco"] = 25
        pacote["Nulo"] = 15
        for nome, total in pacote.items():
            for secao, quantidade in zip(secoes, _distribuir(total, len(secoes))):
                if quantidade == 0:
                    continue
                linhas.append(
                    {
                        "ANO_ELEICAO": ANO,
                        "NR_TURNO": str(turno),
                        "SG_UF": "RJ",
                        "NM_MUNICIPIO": "TRÊS RIOS",
                        "NR_ZONA": secao["zona"],
                        "NR_SECAO": secao["secao"],
                        "DS_CARGO": cargo,
                        "NR_VOTAVEL": NUMEROS[nome],
                        "NM_VOTAVEL": nome.upper(),
                        "QT_VOTOS": str(quantidade),
                    }
                )
    return linhas


def gerar_amostra(pasta: Path) -> dict[str, Path]:
    """Grava três CSVs Latin-1 com separador ';' e devolve os caminhos."""
    pasta.mkdir(parents=True, exist_ok=True)
    por_bairro = _montar_secoes()

    locais = []
    abstencao = []
    for secoes in por_bairro.values():
        for indice, secao in enumerate(secoes):
            bairro = secao["bairro"]
            if bairro == "Vila Isabel" and indice == 0:
                bairro = "  vila   isabel "
            elif bairro == "Boa União" and indice == 0:
                bairro = "BOA UNIAO"
            lat = f"{secao['lat']:.4f}"
            lon = f"{secao['lon']:.4f}"
            if secao["bairro"] == "Centro" and indice == 0:
                lat = lat.replace(".", ",")
                lon = lon.replace(".", ",")
            locais.append(
                {
                    "ANO_ELEICAO": ANO,
                    "SG_UF": "RJ",
                    "NM_MUNICIPIO": "TRÊS RIOS",
                    "NR_ZONA": secao["zona"],
                    "NR_SECAO": secao["secao"],
                    "NM_LOCAL_VOTACAO": secao["local"],
                    "DS_ENDERECO": secao["endereco"],
                    "NM_BAIRRO": bairro,
                    "NR_LATITUDE": lat,
                    "NR_LONGITUDE": lon,
                }
            )
            for turno in (1, 2):
                abstencao.append(
                    {
                        "ANO_ELEICAO": ANO,
                        "NR_TURNO": str(turno),
                        "SG_UF": "RJ",
                        "NM_MUNICIPIO": "TRÊS RIOS",
                        "NR_ZONA": secao["zona"],
                        "NR_SECAO": secao["secao"],
                        "QT_APTOS": str(secao["aptos"]),
                        "QT_COMPARECIMENTO": str(secao["aptos"] - secao["abstencao"]),
                        "QT_ABSTENCAO": str(secao["abstencao"]),
                    }
                )

    # Linha de outro município: o pipeline precisa descartá-la.
    locais.append(
        {
            "ANO_ELEICAO": ANO,
            "SG_UF": "RJ",
            "NM_MUNICIPIO": "PARAÍBA DO SUL",
            "NR_ZONA": "99",
            "NR_SECAO": "1",
            "NM_LOCAL_VOTACAO": "ESCOLA DE OUTRO MUNICIPIO",
            "DS_ENDERECO": "Rua Distante, 1",
            "NM_BAIRRO": "Centro",
            "NR_LATITUDE": "-22.1600",
            "NR_LONGITUDE": "-43.2900",
        }
    )

    votos = []
    votos += _linhas_voto(por_bairro, "Prefeito", 1, VOTOS_PREFEITO_TURNO_1)
    votos += _linhas_voto(por_bairro, "Prefeito", 2, VOTOS_PREFEITO_TURNO_2)
    vereador = {bairro: _vereador_padrao() for bairro in por_bairro}
    vereador["Centro"] = VOTOS_VEREADOR["Centro"]
    votos += _linhas_voto(por_bairro, "Vereador", 1, vereador)

    primeira = por_bairro["Centro"][0]
    votos.append(
        {
            "ANO_ELEICAO": ANO,
            "NR_TURNO": "1",
            "SG_UF": "RJ",
            "NM_MUNICIPIO": "Tres Rios",
            "NR_ZONA": primeira["zona"],
            "NR_SECAO": primeira["secao"],
            "DS_CARGO": "Prefeito",
            "NR_VOTAVEL": "22",
            "NM_VOTAVEL": "ANA  RIBEIRO",
            "QT_VOTOS": "",
        }
    )
    votos.append(
        {
            "ANO_ELEICAO": ANO,
            "NR_TURNO": "1",
            "SG_UF": "RJ",
            "NM_MUNICIPIO": "PARAÍBA DO SUL",
            "NR_ZONA": "99",
            "NR_SECAO": "1",
            "DS_CARGO": "Prefeito",
            "NR_VOTAVEL": "99",
            "NM_VOTAVEL": "ZÉ FORASTEIRO",
            "QT_VOTOS": "50000",
        }
    )

    caminhos = {
        "votos": pasta / "votacao_secao_2024_RJ.csv",
        "locais": pasta / "eleitorado_local_votacao_2024.csv",
        "abstencao": pasta / "perfil_comparecimento_abstencao_2024.csv",
    }
    _gravar(pd.DataFrame(votos), caminhos["votos"])
    _gravar(pd.DataFrame(locais), caminhos["locais"])
    _gravar(pd.DataFrame(abstencao), caminhos["abstencao"])
    return caminhos


def _vereador_padrao() -> dict[str, int]:
    return {
        "Joana Pires": 90,
        "Paulo Nunes": 70,
        "Lúcia Ferreira": 40,
        "Marcos Teixeira": 25,
        "Partido da Árvore": 30,
        "Partido do Rio": 20,
    }


def _gravar(df: pd.DataFrame, caminho: Path) -> None:
    df.to_csv(caminho, sep=";", index=False, encoding="latin1")
