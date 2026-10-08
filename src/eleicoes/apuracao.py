"""Apuração por bairro e por local de votação.

A margem é a diferença entre o primeiro e o segundo colocado, em pontos
percentuais dos votos válidos:

    margem = (votos do 1º − votos do 2º) / votos válidos × 100

Votos válidos = nominais + legenda. Branco, nulo e anulado ficam de fora,
no mesmo critério da totalização oficial. O vencedor sai só dos votos
nominais: voto de legenda não elege um nome.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from eleicoes.config import BAIRRO_DESCONHECIDO, LOCAL_DESCONHECIDO

COLUNAS_BAIRROS = [
    "bairro",
    "votos_validos",
    "votos_nominais",
    "votos_legenda",
    "brancos",
    "nulos",
    "anulados",
    "vencedor",
    "empate",
    "empate_entre",
    "votos_vencedor",
    "percentual_vencedor",
    "segundo",
    "votos_segundo",
    "margem_pp",
    "prioritario",
    "aptos",
    "comparecimento",
    "abstencao",
    "abstencao_pct",
    "secoes",
    "locais",
]

COLUNAS_CANDIDATOS = [
    "bairro",
    "candidato",
    "nr_votavel",
    "tipo",
    "votos",
    "percentual",
    "posicao",
]

COLUNAS_LOCAIS = [
    "bairro",
    "local_votacao",
    "endereco",
    "latitude",
    "longitude",
    "votos_validos",
    "vencedor",
    "empate",
    "percentual_vencedor",
    "margem_pp",
    "comparecimento",
    "votos_computados",
    "secoes",
]


@dataclass
class Visao:
    bairros: pd.DataFrame
    candidatos: pd.DataFrame
    locais: pd.DataFrame
    resumo: dict


def visao_vazia() -> Visao:
    return Visao(
        bairros=pd.DataFrame(columns=COLUNAS_BAIRROS),
        candidatos=pd.DataFrame(columns=COLUNAS_CANDIDATOS),
        locais=pd.DataFrame(columns=COLUNAS_LOCAIS),
        resumo=_resumo_vazio(),
    )


def _resumo_vazio() -> dict:
    return {
        "vencedor": "Sem votos",
        "empate": False,
        "empate_entre": "",
        "percentual_vencedor": None,
        "segundo": "",
        "margem_pp": None,
        "votos_validos": 0,
        "votos_nominais": 0,
        "brancos": 0,
        "nulos": 0,
        "abstencao_pct": None,
        "aptos": None,
        "comparecimento": None,
        "secoes": 0,
    }


def _soma_tipo(grupo: pd.DataFrame, tipo: str) -> int:
    return int(grupo.loc[grupo["tipo"].eq(tipo), "qt_votos"].sum())


def _ranking(grupo: pd.DataFrame, tipo: str) -> pd.DataFrame:
    recorte = grupo.loc[grupo["tipo"].eq(tipo)]
    if recorte.empty:
        return pd.DataFrame(columns=["nr_votavel", "nm_votavel", "qt_votos"])
    ranking = (
        recorte.groupby(["nr_votavel", "nm_votavel"], as_index=False)["qt_votos"]
        .sum()
        .sort_values(["qt_votos", "nm_votavel"], ascending=[False, True])
    )
    return ranking.loc[ranking["qt_votos"].gt(0)].reset_index(drop=True)


def apurar_votos(grupo: pd.DataFrame, limiar: float) -> tuple[dict, list[dict]]:
    """Calcula vencedor, margem e a lista de candidatos de um conjunto de seções."""
    nominais = _ranking(grupo, "nominal")
    legendas = _ranking(grupo, "legenda")
    votos_nominais = _soma_tipo(grupo, "nominal")
    votos_legenda = _soma_tipo(grupo, "legenda")
    brancos = _soma_tipo(grupo, "branco")
    nulos = _soma_tipo(grupo, "nulo")
    anulados = _soma_tipo(grupo, "anulado")
    validos = votos_nominais + votos_legenda

    resultado = {
        "votos_validos": validos,
        "votos_nominais": votos_nominais,
        "votos_legenda": votos_legenda,
        "brancos": brancos,
        "nulos": nulos,
        "anulados": anulados,
        "vencedor": "Sem candidato nominal",
        "empate": False,
        "empate_entre": "",
        "votos_vencedor": 0,
        "percentual_vencedor": None,
        "segundo": "",
        "votos_segundo": 0,
        "margem_pp": None,
        "prioritario": False,
    }

    if not nominais.empty and validos > 0:
        topo = int(nominais.iloc[0]["qt_votos"])
        lideres = nominais.loc[nominais["qt_votos"].eq(topo), "nm_votavel"].tolist()
        resultado["votos_vencedor"] = topo
        resultado["percentual_vencedor"] = topo / validos * 100
        if len(lideres) > 1:
            resultado["empate"] = True
            resultado["vencedor"] = "Empate"
            resultado["empate_entre"] = " e ".join(lideres)
            resultado["votos_segundo"] = topo
            resultado["margem_pp"] = 0.0
            resultado["prioritario"] = True
        else:
            resultado["vencedor"] = lideres[0]
            if len(nominais) > 1:
                segundo = nominais.iloc[1]
                resultado["segundo"] = segundo["nm_votavel"]
                resultado["votos_segundo"] = int(segundo["qt_votos"])
                resultado["margem_pp"] = (topo - int(segundo["qt_votos"])) / validos * 100
                resultado["prioritario"] = resultado["margem_pp"] < limiar

    candidatos: list[dict] = []
    for posicao, linha in enumerate(nominais.itertuples(index=False), start=1):
        candidatos.append(
            {
                "candidato": linha.nm_votavel,
                "nr_votavel": linha.nr_votavel,
                "tipo": "nominal",
                "votos": int(linha.qt_votos),
                "percentual": (linha.qt_votos / validos * 100) if validos else None,
                "posicao": posicao,
            }
        )
    for linha in legendas.itertuples(index=False):
        candidatos.append(
            {
                "candidato": linha.nm_votavel,
                "nr_votavel": linha.nr_votavel,
                "tipo": "legenda",
                "votos": int(linha.qt_votos),
                "percentual": (linha.qt_votos / validos * 100) if validos else None,
                "posicao": None,
            }
        )
    return resultado, candidatos


def _pct_abstencao(aptos: float | None, abstencao: float | None) -> float | None:
    if aptos is None or abstencao is None or pd.isna(aptos) or pd.isna(abstencao) or aptos <= 0:
        return None
    return float(abstencao) / float(aptos) * 100


def _dimensao_secoes(votos: pd.DataFrame, locais: pd.DataFrame) -> pd.DataFrame:
    colunas = ["zona", "secao", "bairro", "local_votacao", "endereco", "latitude", "longitude"]
    partes: list[pd.DataFrame] = []
    if not locais.empty:
        partes.append(locais.loc[:, [coluna for coluna in colunas if coluna in locais.columns]].copy())
    if not votos.empty:
        extras = votos.loc[:, [coluna for coluna in colunas if coluna in votos.columns]].drop_duplicates(["zona", "secao"])
        partes.append(extras)
    if not partes:
        return pd.DataFrame(columns=colunas)
    dim = pd.concat(partes, ignore_index=True)
    for coluna in colunas:
        if coluna not in dim.columns:
            dim[coluna] = pd.NA
    dim["bairro"] = dim["bairro"].fillna(BAIRRO_DESCONHECIDO).replace("", BAIRRO_DESCONHECIDO)
    dim["local_votacao"] = dim["local_votacao"].fillna(LOCAL_DESCONHECIDO).replace("", LOCAL_DESCONHECIDO)
    dim["endereco"] = dim["endereco"].fillna("")
    dim["_chave"] = dim["zona"].astype(str) + "-" + dim["secao"].astype(str)
    dim["_bairro_ok"] = dim["bairro"].ne(BAIRRO_DESCONHECIDO).astype(int)
    dim["_coord_ok"] = dim["latitude"].notna().astype(int)
    dim = dim.sort_values(["_bairro_ok", "_coord_ok"]).drop_duplicates("_chave", keep="last")
    return dim.drop(columns=["_chave", "_bairro_ok", "_coord_ok"])


def _agregar_abstencao(dim: pd.DataFrame, abstencao: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    base = dim.loc[:, ["zona", "secao", *chaves]].drop_duplicates()
    if abstencao.empty:
        for coluna in ("qt_aptos", "qt_comparecimento", "qt_abstencao"):
            base[coluna] = pd.NA
        return base.groupby(chaves, as_index=False)[["qt_aptos", "qt_comparecimento", "qt_abstencao"]].sum(min_count=1)
    cruzado = base.merge(abstencao, on=["zona", "secao"], how="left")
    return cruzado.groupby(chaves, as_index=False)[["qt_aptos", "qt_comparecimento", "qt_abstencao"]].sum(min_count=1)


def construir_visoes(
    votos: pd.DataFrame,
    locais: pd.DataFrame,
    abstencao: pd.DataFrame,
    limiar: float,
    par: tuple[str, str] | None = None,
) -> Visao:
    if votos.empty:
        return visao_vazia()

    dim = _dimensao_secoes(votos, locais)
    tabela = votos.merge(
        dim.loc[:, ["zona", "secao", "bairro", "local_votacao", "endereco", "latitude", "longitude"]],
        on=["zona", "secao"],
        how="left",
    )
    tabela["bairro"] = tabela["bairro"].fillna(BAIRRO_DESCONHECIDO)
    tabela["local_votacao"] = tabela["local_votacao"].fillna(LOCAL_DESCONHECIDO).replace("", LOCAL_DESCONHECIDO)

    abst_bairro = _agregar_abstencao(dim, abstencao, ["bairro"])
    abst_local = _agregar_abstencao(dim, abstencao, ["bairro", "local_votacao"])

    linhas_bairro: list[dict] = []
    linhas_candidato: list[dict] = []
    for bairro, grupo in tabela.groupby("bairro", sort=False):
        apuracao, candidatos = apurar_votos(grupo, limiar)
        apuracao["bairro"] = bairro
        apuracao["secoes"] = int(grupo[["zona", "secao"]].drop_duplicates().shape[0])
        apuracao["locais"] = int(grupo["local_votacao"].nunique())
        faixa = abst_bairro.loc[abst_bairro["bairro"].eq(bairro)]
        if faixa.empty:
            aptos = comparecimento = abst = None
        else:
            aptos = faixa.iloc[0]["qt_aptos"]
            comparecimento = faixa.iloc[0]["qt_comparecimento"]
            abst = faixa.iloc[0]["qt_abstencao"]
        apuracao["aptos"] = None if pd.isna(aptos) else int(aptos)
        apuracao["comparecimento"] = None if pd.isna(comparecimento) else int(comparecimento)
        apuracao["abstencao"] = None if pd.isna(abst) else int(abst)
        apuracao["abstencao_pct"] = _pct_abstencao(aptos, abst)
        linhas_bairro.append(apuracao)
        for candidato in candidatos:
            candidato["bairro"] = bairro
            linhas_candidato.append(candidato)

    bairros = pd.DataFrame(linhas_bairro, columns=COLUNAS_BAIRROS)
    bairros = bairros.sort_values(["votos_validos", "bairro"], ascending=[False, True]).reset_index(drop=True)
    candidatos = pd.DataFrame(linhas_candidato, columns=COLUNAS_CANDIDATOS)
    if not candidatos.empty:
        candidatos = candidatos.sort_values(["bairro", "tipo", "votos"], ascending=[True, True, False]).reset_index(drop=True)

    linhas_local: list[dict] = []
    for (bairro, local), grupo in tabela.groupby(["bairro", "local_votacao"], sort=False):
        apuracao, _ = apurar_votos(grupo, limiar)
        faixa = abst_local.loc[abst_local["bairro"].eq(bairro) & abst_local["local_votacao"].eq(local)]
        comparecimento = None if faixa.empty else faixa.iloc[0]["qt_comparecimento"]
        linhas_local.append(
            {
                "bairro": bairro,
                "local_votacao": local,
                "endereco": next((valor for valor in grupo["endereco"] if isinstance(valor, str) and valor.strip()), ""),
                "latitude": grupo["latitude"].mean(skipna=True),
                "longitude": grupo["longitude"].mean(skipna=True),
                "votos_validos": apuracao["votos_validos"],
                "vencedor": apuracao["vencedor"],
                "empate": apuracao["empate"],
                "percentual_vencedor": apuracao["percentual_vencedor"],
                "margem_pp": apuracao["margem_pp"],
                "comparecimento": None if comparecimento is None or pd.isna(comparecimento) else int(comparecimento),
                "votos_computados": int(grupo["qt_votos"].sum()),
                "secoes": int(grupo[["zona", "secao"]].drop_duplicates().shape[0]),
            }
        )
    locais_mapa = pd.DataFrame(linhas_local, columns=COLUNAS_LOCAIS)

    resumo, _ = apurar_votos(tabela, limiar)
    if abstencao.empty:
        aptos = comparecimento = abst = None
    else:
        aptos = abstencao["qt_aptos"].sum(min_count=1)
        comparecimento = abstencao["qt_comparecimento"].sum(min_count=1)
        abst = abstencao["qt_abstencao"].sum(min_count=1)
    resumo_cidade = {
        "vencedor": resumo["vencedor"],
        "empate": resumo["empate"],
        "empate_entre": resumo["empate_entre"],
        "percentual_vencedor": resumo["percentual_vencedor"],
        "segundo": resumo["segundo"],
        "margem_pp": resumo["margem_pp"],
        "votos_validos": resumo["votos_validos"],
        "votos_nominais": resumo["votos_nominais"],
        "brancos": resumo["brancos"],
        "nulos": resumo["nulos"],
        "abstencao_pct": _pct_abstencao(aptos, abst),
        "aptos": None if aptos is None or pd.isna(aptos) else int(aptos),
        "comparecimento": None if comparecimento is None or pd.isna(comparecimento) else int(comparecimento),
        "secoes": int(tabela[["zona", "secao"]].drop_duplicates().shape[0]),
    }
    _aplicar_disputa(bairros, candidatos, locais_mapa, tabela, resumo_cidade, limiar, par)
    return Visao(bairros=bairros, candidatos=candidatos, locais=locais_mapa, resumo=resumo_cidade)


def _par_disputa(candidatos: pd.DataFrame, par: tuple[str, str] | None) -> tuple[str, str] | None:
    if par and par[0] and par[1] and par[0] != par[1]:
        return par
    if candidatos.empty:
        return None
    nominais = candidatos.loc[candidatos["tipo"].eq("nominal")]
    if nominais.empty:
        return None
    ranking = nominais.groupby("candidato")["votos"].sum().sort_values(ascending=False)
    if len(ranking) < 2:
        return None
    return str(ranking.index[0]), str(ranking.index[1])


def _aplicar_disputa(
    bairros: pd.DataFrame,
    candidatos: pd.DataFrame,
    locais_mapa: pd.DataFrame,
    tabela: pd.DataFrame,
    resumo: dict,
    limiar: float,
    par: tuple[str, str] | None,
) -> None:
    """Compara, em cada bairro, os dois nomes que disputam o turno seguinte.

    O vencedor do 1º turno pode ser um terceiro candidato. Para a rua, o que
    importa é a diferença entre os dois primeiros e se os votos dos demais
    cabem nessa diferença — aí o bairro ainda pode virar.
    """
    vazio = {
        "lider_disputa": "",
        "adversario_disputa": "",
        "votos_lider_disputa": 0,
        "votos_adversario_disputa": 0,
        "margem_disputa_pp": None,
        "votos_outros": 0,
        "pode_virar": False,
        "prioritario_2t": False,
    }
    for coluna, valor in vazio.items():
        bairros[coluna] = valor
        if coluna in {"lider_disputa", "margem_disputa_pp", "votos_outros", "pode_virar", "prioritario_2t"}:
            locais_mapa[coluna] = valor
    resumo.update(
        {
            "disputa_a": "",
            "disputa_b": "",
            "votos_disputa_a": 0,
            "votos_disputa_b": 0,
            "margem_disputa_pp": None,
            "votos_outros": 0,
        }
    )
    escolhido = _par_disputa(candidatos, par)
    if escolhido is None or bairros.empty:
        return
    nome_a, nome_b = escolhido
    resumo["disputa_a"] = nome_a
    resumo["disputa_b"] = nome_b

    nominais = candidatos.loc[candidatos["tipo"].eq("nominal")]
    totais = nominais.groupby(["bairro", "candidato"])["votos"].sum() if not nominais.empty else pd.Series(dtype=int)

    def votos_de(bairro: str, nome: str) -> int:
        chave = (bairro, nome)
        if chave not in totais.index:
            return 0
        return int(totais.loc[chave])

    for indice, bairro in bairros["bairro"].items():
        votos_a = votos_de(bairro, nome_a)
        votos_b = votos_de(bairro, nome_b)
        validos = int(bairros.at[indice, "votos_validos"])
        nominais_bairro = int(bairros.at[indice, "votos_nominais"])
        outros = max(nominais_bairro - votos_a - votos_b, 0)
        if votos_a == votos_b:
            lider, adversario = "Empate", ""
            votos_lider = votos_adversario = votos_a
        elif votos_a > votos_b:
            lider, adversario = nome_a, nome_b
            votos_lider, votos_adversario = votos_a, votos_b
        else:
            lider, adversario = nome_b, nome_a
            votos_lider, votos_adversario = votos_b, votos_a
        margem = ((votos_lider - votos_adversario) / validos * 100) if validos and lider != "Empate" else (0.0 if lider == "Empate" else None)
        pode_virar = outros > 0 and outros >= abs(votos_a - votos_b)
        bairros.at[indice, "lider_disputa"] = lider
        bairros.at[indice, "adversario_disputa"] = adversario
        bairros.at[indice, "votos_lider_disputa"] = votos_lider
        bairros.at[indice, "votos_adversario_disputa"] = votos_adversario
        bairros.at[indice, "margem_disputa_pp"] = margem
        bairros.at[indice, "votos_outros"] = outros
        bairros.at[indice, "pode_virar"] = pode_virar
        bairros.at[indice, "prioritario_2t"] = bool(pode_virar or (margem is not None and margem < limiar))

    resumo["votos_disputa_a"] = int(nominais.loc[nominais["candidato"].eq(nome_a), "votos"].sum()) if not nominais.empty else 0
    resumo["votos_disputa_b"] = int(nominais.loc[nominais["candidato"].eq(nome_b), "votos"].sum()) if not nominais.empty else 0
    resumo["votos_outros"] = max(int(resumo["votos_nominais"]) - resumo["votos_disputa_a"] - resumo["votos_disputa_b"], 0)
    if resumo["votos_validos"]:
        resumo["margem_disputa_pp"] = abs(resumo["votos_disputa_a"] - resumo["votos_disputa_b"]) / resumo["votos_validos"] * 100

    if locais_mapa.empty or tabela.empty:
        return
    nominais_local = tabela.loc[tabela["tipo"].eq("nominal")]
    por_local = (
        nominais_local.groupby(["bairro", "local_votacao", "nm_votavel"])["qt_votos"].sum()
        if not nominais_local.empty
        else pd.Series(dtype=int)
    )
    for indice, linha in locais_mapa.iterrows():
        def pegar(nome: str, bairro=linha["bairro"], local=linha["local_votacao"]) -> int:
            chave = (bairro, local, nome)
            if chave not in por_local.index:
                return 0
            return int(por_local.loc[chave])

        votos_a = pegar(nome_a)
        votos_b = pegar(nome_b)
        validos = int(linha["votos_validos"])
        outros = max(int(nominais_local.loc[
            nominais_local["bairro"].eq(linha["bairro"]) & nominais_local["local_votacao"].eq(linha["local_votacao"]),
            "qt_votos",
        ].sum()) - votos_a - votos_b, 0) if not nominais_local.empty else 0
        if votos_a == votos_b:
            lider = "Empate"
            margem = 0.0
        else:
            lider = nome_a if votos_a > votos_b else nome_b
            margem = (abs(votos_a - votos_b) / validos * 100) if validos else None
        locais_mapa.at[indice, "lider_disputa"] = lider
        locais_mapa.at[indice, "margem_disputa_pp"] = margem
        locais_mapa.at[indice, "votos_outros"] = outros
        locais_mapa.at[indice, "pode_virar"] = outros > 0 and outros >= abs(votos_a - votos_b)
        locais_mapa.at[indice, "prioritario_2t"] = bool(
            locais_mapa.at[indice, "pode_virar"] or (margem is not None and margem < limiar)
        )
