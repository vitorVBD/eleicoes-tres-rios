"""Consultas do banco já processado. O recorte por cargo e turno acontece aqui."""

from __future__ import annotations

import sqlite3

import pandas as pd

from eleicoes.apuracao import Visao, construir_visoes
from eleicoes.armazenamento import ler_meta
from eleicoes.config import ORDEM_CARGOS


def listar_combinacoes(conexao: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT DISTINCT ano, turno, cargo
        FROM votos
        ORDER BY ano, cargo, turno
        """,
        conexao,
    )


def ordenar_cargos(cargos: list[str]) -> list[str]:
    ordem = {cargo: indice for indice, cargo in enumerate(ORDEM_CARGOS)}
    return sorted(cargos, key=lambda cargo: (ordem.get(cargo, len(ORDEM_CARGOS)), cargo))


def montar_painel(
    conexao: sqlite3.Connection,
    ano: int,
    turno: int,
    cargo: str,
    limiar: float,
) -> Visao:
    votos = pd.read_sql_query(
        """
        SELECT zona, secao, nr_votavel, nm_votavel, qt_votos, tipo
        FROM votos
        WHERE ano = ? AND turno = ? AND cargo = ?
        """,
        conexao,
        params=(ano, turno, cargo),
    )
    locais = pd.read_sql_query(
        """
        SELECT zona, secao, bairro, local_votacao, endereco, latitude, longitude
        FROM locais
        """,
        conexao,
    )
    abstencao = pd.read_sql_query(
        """
        SELECT zona, secao, qt_aptos, qt_comparecimento, qt_abstencao
        FROM abstencao
        WHERE ano = ? AND turno = ?
        """,
        conexao,
        params=(ano, turno),
    )
    meta = ler_meta(conexao)
    par = None
    if meta.get("disputa_a") and meta.get("disputa_b"):
        par = (meta["disputa_a"], meta["disputa_b"])
    return construir_visoes(votos, locais, abstencao, limiar, par=par)
