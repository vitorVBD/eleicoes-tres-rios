"""Normalização de texto: município, bairro e nome de candidato."""

import re

import pandas as pd

from eleicoes.config import BAIRRO_DESCONHECIDO, BAIRROS_CONHECIDOS, CHAVES_VAZIAS

PARTICULAS = {"de", "da", "do", "das", "dos", "e", "di", "du"}


def chave_texto_serie(serie: pd.Series) -> pd.Series:
    """Reduz um texto à chave de comparação: sem acento, maiúsculo, espaço único.

    "TRÊS RIOS", "Tres Rios" e "  três   rios " viram "TRES RIOS".
    """
    texto = serie.fillna("").astype(str)
    texto = texto.str.replace(r"\s+", " ", regex=True).str.strip()
    texto = texto.str.upper()
    texto = texto.str.normalize("NFKD").str.encode("ascii", "ignore").str.decode("ascii")
    texto = texto.str.replace(r"[^A-Z0-9]+", " ", regex=True)
    texto = texto.str.replace(r"\s+", " ", regex=True).str.strip()
    return texto


def chave_texto(valor: object) -> str:
    """Versão escalar de ``chave_texto_serie``."""
    if valor is None:
        return ""
    return str(chave_texto_serie(pd.Series([valor])).iloc[0])


def titulo_pt(nome: str) -> str:
    """Converte "ANA RIBEIRO" ou "ana ribeiro" em "Ana Ribeiro", preservando acentos."""
    texto = re.sub(r"\s+", " ", str(nome)).strip()
    if not texto:
        return ""
    partes: list[str] = []
    for indice, parte in enumerate(texto.split(" ")):
        if indice > 0 and parte.lower() in PARTICULAS:
            partes.append(parte.lower())
        else:
            partes.append(parte[:1].upper() + parte[1:].lower() if parte else parte)
    return " ".join(partes)


def formatar_bairros(serie: pd.Series) -> pd.Series:
    """Unifica grafias do mesmo bairro e devolve um nome legível.

    Espaços repetidos e acentos inconsistentes ("BOA UNIAO" / "Boa União")
    caem na mesma chave. Se o bairro for conhecido, usamos o nome canônico;
    caso contrário, aplicamos capitalização ao texto original.
    """
    limpo = serie.fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    chaves = chave_texto_serie(limpo)
    vazio = chaves.isin(CHAVES_VAZIAS) | chaves.eq("")
    conhecido = chaves.map(BAIRROS_CONHECIDOS).fillna("")
    fallback = limpo.map(titulo_pt)
    resultado = conhecido.where(conhecido.ne(""), fallback)
    return resultado.mask(vazio, BAIRRO_DESCONHECIDO)


def formatar_nomes(serie: pd.Series) -> pd.Series:
    """Normaliza o nome que aparece na urna, colapsando espaços duplicados."""
    limpo = serie.fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    return limpo.map(lambda nome: titulo_pt(nome) if nome else "")
