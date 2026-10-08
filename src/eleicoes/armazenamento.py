"""SQLite local. A interface lê daqui e não reabre os CSVs do TSE a cada clique."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ESQUEMA = """
CREATE TABLE meta (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE locais (
    zona TEXT NOT NULL,
    secao TEXT NOT NULL,
    bairro TEXT NOT NULL,
    local_votacao TEXT,
    endereco TEXT,
    latitude REAL,
    longitude REAL,
    PRIMARY KEY (zona, secao)
);

CREATE TABLE votos (
    ano INTEGER NOT NULL,
    turno INTEGER NOT NULL,
    cargo TEXT NOT NULL,
    zona TEXT NOT NULL,
    secao TEXT NOT NULL,
    nr_votavel TEXT,
    nm_votavel TEXT,
    qt_votos INTEGER NOT NULL,
    tipo TEXT NOT NULL
);

CREATE TABLE abstencao (
    ano INTEGER NOT NULL,
    turno INTEGER NOT NULL,
    zona TEXT NOT NULL,
    secao TEXT NOT NULL,
    qt_aptos INTEGER,
    qt_comparecimento INTEGER,
    qt_abstencao INTEGER,
    PRIMARY KEY (ano, turno, zona, secao)
);

CREATE INDEX idx_votos_recorte ON votos (ano, turno, cargo);
CREATE INDEX idx_abstencao_recorte ON abstencao (ano, turno);
"""


def conectar(caminho: Path) -> sqlite3.Connection:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    return conexao


def criar_banco(caminho: Path) -> sqlite3.Connection:
    if caminho.exists():
        caminho.unlink()
    conexao = conectar(caminho)
    conexao.executescript(ESQUEMA)
    return conexao


def _valor_sql(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.floating,)):
        return float(valor)
    if isinstance(valor, (np.bool_,)):
        return int(valor)
    return valor


def inserir(conexao: sqlite3.Connection, tabela: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    colunas = list(df.columns)
    marcadores = ", ".join("?" for _ in colunas)
    sql = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({marcadores})"
    registros = [tuple(_valor_sql(valor) for valor in linha) for linha in df.itertuples(index=False, name=None)]
    conexao.executemany(sql, registros)


def gravar_meta(conexao: sqlite3.Connection, meta: dict[str, str]) -> None:
    conexao.executemany(
        "INSERT INTO meta (chave, valor) VALUES (?, ?)",
        [(chave, "" if valor is None else str(valor)) for chave, valor in meta.items()],
    )


def ler_meta(conexao: sqlite3.Connection) -> dict[str, str]:
    linhas = conexao.execute("SELECT chave, valor FROM meta").fetchall()
    return {linha["chave"]: linha["valor"] for linha in linhas}
