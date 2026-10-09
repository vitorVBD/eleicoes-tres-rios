"""Limpeza das tabelas já filtradas para Três Rios.

Aqui entram os casos que o CSV oficial deixa soltos: voto vazio, bairro em
branco, acento trocado, coordenada com vírgula decimal e abstenção repetida
em várias fatias de perfil da mesma seção.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from eleicoes.config import (
    BAIRRO_DESCONHECIDO,
    CARGOS_PROPORCIONAIS,
    LOCAL_DESCONHECIDO,
)
from eleicoes.normalizacao import chave_texto_serie, formatar_bairros, formatar_nomes

MAPA_VOTOS = {
    "ano": ["ANO_ELEICAO", "AA_ELEICAO"],
    "turno": ["NR_TURNO"],
    "municipio": ["NM_MUNICIPIO"],
    "zona": ["NR_ZONA"],
    "secao": ["NR_SECAO"],
    "cargo": ["DS_CARGO"],
    "nr_votavel": ["NR_VOTAVEL", "NR_CANDIDATO", "NR_PARTIDO"],
    "nm_votavel": ["NM_VOTAVEL", "NM_URNA_CANDIDATO", "NM_CANDIDATO"],
    "qt_votos": ["QT_VOTOS"],
    "tipo_declarado": ["DS_TIPO_VOTAVEL", "NM_TIPO_VOTAVEL"],
}

MAPA_LOCAIS = {
    "ano": ["ANO_ELEICAO", "AA_ELEICAO"],
    "municipio": ["NM_MUNICIPIO"],
    "zona": ["NR_ZONA"],
    "secao": ["NR_SECAO"],
    "local_votacao": ["NM_LOCAL_VOTACAO"],
    "endereco": ["DS_ENDERECO"],
    "bairro": ["NM_BAIRRO"],
    "latitude": ["NR_LATITUDE", "DS_LATITUDE"],
    "longitude": ["NR_LONGITUDE", "DS_LONGITUDE"],
}

MAPA_ABSTENCAO = {
    "ano": ["ANO_ELEICAO", "AA_ELEICAO"],
    "turno": ["NR_TURNO"],
    "municipio": ["NM_MUNICIPIO"],
    "zona": ["NR_ZONA"],
    "secao": ["NR_SECAO"],
    "qt_aptos": ["QT_APTOS"],
    "qt_comparecimento": ["QT_COMPARECIMENTO"],
    "qt_abstencao": ["QT_ABSTENCAO", "QT_ABSTENCOES"],
}


def _renomear(df: pd.DataFrame, mapa: dict[str, list[str]]) -> pd.DataFrame:
    saida = pd.DataFrame(index=df.index)
    for destino, opcoes in mapa.items():
        origem = next((coluna for coluna in opcoes if coluna in df.columns), None)
        saida[destino] = df[origem] if origem is not None else pd.NA
    if "_ano_arquivo" in df.columns:
        saida["_ano_arquivo"] = df["_ano_arquivo"]
    return saida


def _codigo_secao(serie: pd.Series) -> pd.Series:
    """Uniformiza zona e seção: "001" e "1.0" viram "1". Vazio permanece ausente."""
    texto = serie.fillna("").astype(str).str.strip()
    texto = texto.str.replace(r"\.0$", "", regex=True)
    texto = texto.str.replace(r"[^0-9]", "", regex=True)
    vazio = texto.eq("")
    texto = texto.str.lstrip("0")
    texto = texto.mask(texto.eq(""), "0")
    return texto.mask(vazio, pd.NA)


def _numero_votavel(serie: pd.Series) -> pd.Series:
    texto = serie.fillna("").astype(str).str.strip()
    texto = texto.str.replace(r"\.0$", "", regex=True)
    texto = texto.str.replace(r"[^0-9]", "", regex=True)
    texto = texto.str.lstrip("0")
    return texto.mask(texto.eq(""), "")


def para_inteiro_serie(serie: pd.Series) -> pd.Series:
    """Converte quantidade do TSE. Texto vazio ou inválido vira nulo, não zero.

    O zero entra depois, com um aviso, para não confundir "sem informação"
    com um voto realmente zerado na hora de contar o problema.
    """
    texto = serie.fillna("").astype(str).str.strip()
    texto = texto.str.replace(r"\.0$", "", regex=True)
    texto = texto.str.replace(".", "", regex=False)
    texto = texto.str.replace(",", "", regex=False)
    texto = texto.mask(texto.eq(""), pd.NA)
    return pd.to_numeric(texto, errors="coerce")


def para_float_serie(serie: pd.Series) -> pd.Series:
    """Aceita "-22.1168" e também "-22,1168", forma comum quando o CSV passa pelo Excel."""
    texto = serie.fillna("").astype(str).str.strip()
    texto = texto.str.replace(" ", "", regex=False)
    tem_virgula = texto.str.contains(",", regex=False)
    tem_ponto = texto.str.contains(".", regex=False)
    ambos = tem_virgula & tem_ponto
    texto = texto.where(~ambos, texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    ainda_virgula = texto.str.contains(",", regex=False)
    texto = texto.where(~ainda_virgula, texto.str.replace(",", ".", regex=False))
    texto = texto.mask(texto.isin({"", "nan", "None", "NULL", "-", "."}), pd.NA)
    return pd.to_numeric(texto, errors="coerce")


def _preencher_municipio(df: pd.DataFrame) -> pd.DataFrame:
    nomes = formatar_nomes(df["municipio"]) if "municipio" in df.columns else pd.Series("", index=df.index)
    vazio = nomes.fillna("").astype(str).str.strip().eq("")
    df["municipio"] = nomes.mask(vazio, "Não informado")
    return df


def _preencher_ano_turno(df: pd.DataFrame, avisos: list[str], rotulo: str) -> pd.DataFrame:
    ano = pd.to_numeric(df["ano"], errors="coerce")
    if "_ano_arquivo" in df.columns:
        ano = ano.fillna(pd.to_numeric(df["_ano_arquivo"], errors="coerce"))
    if ano.isna().all():
        avisos.append(f"{rotulo}: ano da eleição ausente; os registros ficaram com ano 0.")
        ano = ano.fillna(0)
    else:
        ano = ano.fillna(ano.dropna().mode().iloc[0])
    df["ano"] = ano.astype(int)

    turno = pd.to_numeric(df["turno"], errors="coerce")
    if turno.isna().all():
        avisos.append(f"{rotulo}: turno ausente; foi assumido o 1º turno.")
    df["turno"] = turno.fillna(1).astype(int)
    return df


def classificar_tipos(df: pd.DataFrame) -> pd.Series:
    """Separa nominal, legenda, branco, nulo e anulado.

    Branco e nulo usam os códigos oficiais 95 e 96. No voto proporcional
    (vereador e deputado), número de até dois dígitos é legenda, não candidato.
    No voto majoritário (prefeito, presidente etc.) o número de dois dígitos
    é o próprio candidato e permanece nominal.
    """
    codigo = df["nr_votavel"].fillna("").astype(str)
    nome = chave_texto_serie(df["nm_votavel"])
    cargo = df["cargo"].fillna("").astype(str).str.strip().str.upper()
    declarado = chave_texto_serie(df["tipo_declarado"]) if "tipo_declarado" in df.columns else pd.Series("", index=df.index)

    branco = codigo.eq("95") | nome.isin(["BRANCO", "VOTO BRANCO"]) | declarado.str.contains("BRANCO", na=False)
    nulo = codigo.eq("96") | nome.isin(["NULO", "VOTO NULO"]) | declarado.str.contains("NULO", na=False)
    anulado = (
        codigo.eq("97")
        | nome.isin(["ANULADO", "VOTO ANULADO"])
        | nome.str.startswith("ANULADO")
        | declarado.str.contains("ANULADO", na=False)
    )
    forca_nominal = declarado.str.contains("NOMINAL", na=False)
    legenda_declarada = declarado.str.contains("LEGENDA", na=False)
    legenda_numero = cargo.isin(CARGOS_PROPORCIONAIS) & codigo.ne("") & codigo.str.len().le(2)
    legenda = ~forca_nominal & (legenda_declarada | legenda_numero)

    return pd.Series(
        np.select(
            [branco, nulo, anulado, legenda],
            ["branco", "nulo", "anulado", "legenda"],
            default="nominal",
        ),
        index=df.index,
    )


def preparar_votos(bruto: pd.DataFrame, avisos: list[str]) -> pd.DataFrame:
    if bruto.empty:
        raise ValueError("tabela de votos vazia")
    df = _renomear(bruto, MAPA_VOTOS)
    df["zona"] = _codigo_secao(df["zona"])
    df["secao"] = _codigo_secao(df["secao"])
    sem_chave = df["zona"].isna() | df["secao"].isna()
    if sem_chave.any():
        avisos.append(f"Votos: {int(sem_chave.sum())} linhas sem zona ou seção foram descartadas.")
        df = df.loc[~sem_chave].copy()

    df["cargo"] = df["cargo"].fillna("").astype(str).str.strip().str.upper()
    sem_cargo = df["cargo"].eq("")
    if sem_cargo.any():
        avisos.append(f"Votos: {int(sem_cargo.sum())} linhas sem cargo foram descartadas.")
        df = df.loc[~sem_cargo].copy()

    df = _preencher_ano_turno(df, avisos, "Votos")
    df = _preencher_municipio(df)
    df["nr_votavel"] = _numero_votavel(df["nr_votavel"])
    df["nm_votavel"] = formatar_nomes(df["nm_votavel"])
    sem_nome = df["nm_votavel"].eq("")
    df.loc[sem_nome, "nm_votavel"] = df.loc[sem_nome, "nr_votavel"].map(
        lambda numero: f"Candidato {numero}" if numero else "Não identificado"
    )
    df["tipo"] = classificar_tipos(df)

    quantidades = para_inteiro_serie(df["qt_votos"])
    invalidos = quantidades.isna()
    if invalidos.any():
        avisos.append(
            f"Votos: {int(invalidos.sum())} quantidades vazias ou inválidas foram tratadas como zero."
        )
    negativos = quantidades.fillna(0).lt(0)
    if negativos.any():
        avisos.append(f"Votos: {int(negativos.sum())} quantidades negativas foram tratadas como zero.")
    df["qt_votos"] = quantidades.fillna(0).clip(lower=0).astype(int)

    agrupado = (
        df.groupby(
            ["ano", "turno", "cargo", "municipio", "zona", "secao", "nr_votavel", "nm_votavel", "tipo"],
            as_index=False,
            dropna=False,
        )["qt_votos"]
        .sum()
    )
    return agrupado


def _validar_coordenadas(df: pd.DataFrame, avisos: list[str]) -> pd.DataFrame:
    lat = para_float_serie(df["latitude"])
    lon = para_float_serie(df["longitude"])
    trocado = lat.between(-75, -28) & lon.between(-34, 6)
    lat_final = lat.where(~trocado, lon)
    lon_final = lon.where(~trocado, lat)
    valido = lat_final.between(-34, 6) & lon_final.between(-75, -28)
    informado = lat.notna() | lon.notna()
    invalidos = int((informado & ~valido & ~trocado).sum())
    if int(trocado.sum()):
        avisos.append(
            f"Locais: {int(trocado.sum())} coordenadas estavam com latitude e longitude invertidas e foram corrigidas."
        )
    if invalidos:
        avisos.append(f"Locais: {invalidos} coordenadas fora do Brasil foram descartadas.")
    df["latitude"] = lat_final.where(valido)
    df["longitude"] = lon_final.where(valido)
    return df


def preparar_locais(bruto: pd.DataFrame, avisos: list[str]) -> pd.DataFrame:
    if bruto.empty:
        raise ValueError("tabela de locais vazia")
    df = _renomear(bruto, MAPA_LOCAIS)
    df["zona"] = _codigo_secao(df["zona"])
    df["secao"] = _codigo_secao(df["secao"])
    sem_chave = df["zona"].isna() | df["secao"].isna()
    if sem_chave.any():
        avisos.append(f"Locais: {int(sem_chave.sum())} linhas sem zona ou seção foram descartadas.")
        df = df.loc[~sem_chave].copy()

    df = _preencher_municipio(df)
    df["bairro"] = formatar_bairros(df["bairro"])
    df["local_votacao"] = formatar_nomes(df["local_votacao"]).replace("", LOCAL_DESCONHECIDO)
    df["endereco"] = df["endereco"].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    df = _validar_coordenadas(df, avisos)
    df = _herdar_bairro_do_local(df)
    df["_prioridade_bairro"] = df["bairro"].ne(BAIRRO_DESCONHECIDO).astype(int)
    df["_prioridade_coord"] = df["latitude"].notna().astype(int)
    df = df.sort_values(["_prioridade_bairro", "_prioridade_coord"])
    df = df.drop_duplicates(["municipio", "zona", "secao"], keep="last")
    return df.loc[:, ["municipio", "zona", "secao", "bairro", "local_votacao", "endereco", "latitude", "longitude"]].reset_index(drop=True)


def _herdar_bairro_do_local(df: pd.DataFrame) -> pd.DataFrame:
    """Se uma seção veio sem bairro, copia o bairro das outras seções do mesmo local.

    Só herda quando o local aponta para um único bairro, para não misturar
    escolas homônimas de lugares diferentes.
    """
    conhecidos = df.loc[
        df["bairro"].ne(BAIRRO_DESCONHECIDO) & df["local_votacao"].ne(LOCAL_DESCONHECIDO),
        ["municipio", "local_votacao", "bairro"],
    ].drop_duplicates()
    if conhecidos.empty:
        return df
    contagem = conhecidos.groupby(["municipio", "local_votacao"])["bairro"].nunique()
    unicos = contagem[contagem.eq(1)].reset_index()[["municipio", "local_votacao"]]
    mapa = (
        conhecidos.merge(unicos, on=["municipio", "local_votacao"])
        .drop_duplicates(["municipio", "local_votacao"])
        .rename(columns={"bairro": "_bairro_herdado"})
    )
    if mapa.empty:
        return df
    juntado = df.merge(mapa, on=["municipio", "local_votacao"], how="left")
    faltando = juntado["bairro"].eq(BAIRRO_DESCONHECIDO) & juntado["_bairro_herdado"].notna()
    juntado.loc[faltando, "bairro"] = juntado.loc[faltando, "_bairro_herdado"]
    return juntado.drop(columns="_bairro_herdado")


def preparar_abstencao(bruto: pd.DataFrame | None, avisos: list[str]) -> pd.DataFrame:
    colunas = ["ano", "turno", "municipio", "zona", "secao", "qt_aptos", "qt_comparecimento", "qt_abstencao"]
    if bruto is None or bruto.empty:
        avisos.append(
            "Abstenção indisponível: o arquivo de comparecimento não foi encontrado ou não tem o recorte pedido."
        )
        return pd.DataFrame(columns=colunas)

    df = _renomear(bruto, MAPA_ABSTENCAO)
    df["zona"] = _codigo_secao(df["zona"])
    df["secao"] = _codigo_secao(df["secao"])
    sem_chave = df["zona"].isna() | df["secao"].isna()
    if sem_chave.any():
        avisos.append(f"Abstenção: {int(sem_chave.sum())} linhas sem zona ou seção foram descartadas.")
        df = df.loc[~sem_chave].copy()
    if df.empty:
        avisos.append("Abstenção: nenhuma seção válida depois da limpeza.")
        return pd.DataFrame(columns=colunas)

    df = _preencher_ano_turno(df, avisos, "Abstenção")
    df = _preencher_municipio(df)
    for coluna in ("qt_aptos", "qt_comparecimento", "qt_abstencao"):
        df[coluna] = para_inteiro_serie(df[coluna])

    agrupado = df.groupby(["ano", "turno", "municipio", "zona", "secao"], as_index=False).agg(
        qt_aptos_sum=("qt_aptos", "sum"),
        qt_aptos_max=("qt_aptos", "max"),
        qt_aptos_n=("qt_aptos", "nunique"),
        qt_comparecimento_sum=("qt_comparecimento", "sum"),
        qt_comparecimento_max=("qt_comparecimento", "max"),
        qt_comparecimento_n=("qt_comparecimento", "nunique"),
        qt_abstencao_sum=("qt_abstencao", "sum"),
        qt_abstencao_max=("qt_abstencao", "max"),
        qt_abstencao_n=("qt_abstencao", "nunique"),
        n=("qt_aptos", "size"),
    )
    # O perfil do TSE pode repetir o total da seção em cada fatia (gênero, idade).
    # Se os três números são idênticos em todas as linhas, é repetição: ficamos
    # com um valor. Se variam, cada linha é um pedaço do eleitorado e a soma fecha.
    repetido = (
        agrupado["n"].gt(1)
        & agrupado["qt_aptos_n"].eq(1)
        & agrupado["qt_comparecimento_n"].eq(1)
        & agrupado["qt_abstencao_n"].eq(1)
    )
    if repetido.any():
        avisos.append(
            f"Abstenção: {int(repetido.sum())} seções tinham o mesmo total repetido em várias linhas; "
            "a repetição não foi somada."
        )
    sem_dado = (
        agrupado["qt_aptos_max"].isna()
        & agrupado["qt_comparecimento_max"].isna()
        & agrupado["qt_abstencao_max"].isna()
    )
    if sem_dado.any():
        avisos.append(f"Abstenção: {int(sem_dado.sum())} seções sem quantidades numéricas foram ignoradas.")
        agrupado = agrupado.loc[~sem_dado].copy()
        repetido = repetido.loc[agrupado.index]
    for coluna in ("qt_aptos", "qt_comparecimento", "qt_abstencao"):
        agrupado[coluna] = agrupado[f"{coluna}_sum"].where(~repetido, agrupado[f"{coluna}_max"])

    aptos = agrupado["qt_aptos"]
    comparecimento = agrupado["qt_comparecimento"]
    abstencao = agrupado["qt_abstencao"]
    faltou_abstencao = abstencao.isna() & aptos.notna() & comparecimento.notna()
    abstencao = abstencao.where(~faltou_abstencao, aptos - comparecimento)
    faltou_comparecimento = comparecimento.isna() & aptos.notna() & abstencao.notna()
    comparecimento = comparecimento.where(~faltou_comparecimento, aptos - abstencao)

    agrupado["qt_aptos"] = aptos.fillna(0).clip(lower=0).round().astype(int)
    agrupado["qt_comparecimento"] = comparecimento.fillna(0).clip(lower=0).round().astype(int)
    agrupado["qt_abstencao"] = abstencao.fillna(0).clip(lower=0).round().astype(int)
    return agrupado.loc[:, colunas]
