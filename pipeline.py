"""Linha de comando do ETL.

Uso:
    python pipeline.py --amostra
    python pipeline.py --ano 2026 --cargo PRESIDENTE
    python pipeline.py --raw data/raw --saida data/processed
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from eleicoes.armazenamento import conectar, ler_meta
from eleicoes.config import PASTA_PROCESSADO, PASTA_RAW
from eleicoes.consultas import listar_combinacoes, montar_painel, ordenar_cargos
from eleicoes.erros import ErroPipeline
from eleicoes.etl import executar_pipeline
from eleicoes.formatacao import fmt_pct, fmt_pp


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cruza a votação por seção do TSE com o bairro de cada local, só para Três Rios (RJ)."
    )
    parser.add_argument("--raw", type=Path, default=PASTA_RAW, help="Pasta com os CSVs ou ZIPs do TSE.")
    parser.add_argument("--saida", type=Path, default=PASTA_PROCESSADO, help="Pasta do SQLite e do JSON.")
    parser.add_argument(
        "--amostra",
        action="store_true",
        help="Gera dados fictícios e processa a demonstração, sem baixar o TSE.",
    )
    parser.add_argument("--limiar", type=float, default=5.0, help="Margem, em pontos percentuais, que marca bairro prioritário no JSON.")
    parser.add_argument("--ano", type=int, default=2026, help="Ano da eleição. Ignorado com --amostra.")
    parser.add_argument("--cargo", default="PRESIDENTE", help="Cargo a manter. Ignorado com --amostra.")
    return parser.parse_args()


def _imprimir_resumo(banco: Path, limiar: float) -> None:
    conexao = conectar(banco)
    try:
        meta = ler_meta(conexao)
        combinacoes = listar_combinacoes(conexao)
        print(f"Município: {meta.get('municipio', 'TRÊS RIOS')}")
        print(f"Origem: {'demonstração fictícia' if meta.get('origem') == 'demonstracao' else 'arquivos oficiais'}")
        print(f"Gerado em: {meta.get('gerado_em', '')}")
        print(f"Bairros com local de votação: {meta.get('bairros', '')}")
        print(f"Banco: {banco}")
        print(f"JSON: {banco.parent / 'tres_rios_dados_bairros.json'}")
        avisos = [linha for linha in meta.get("avisos", "").split("\n") if linha]
        for aviso in avisos:
            print(f"Aviso: {aviso}")
        if combinacoes.empty:
            return
        cargos = ordenar_cargos(combinacoes["cargo"].unique().tolist())
        cargo = "PRESIDENTE" if "PRESIDENTE" in cargos else ("PREFEITO" if "PREFEITO" in cargos else cargos[0])
        recorte = combinacoes.loc[combinacoes["cargo"].eq(cargo)]
        turno = int(recorte["turno"].min())
        ano = int(recorte["ano"].min())
        visao = montar_painel(conexao, ano, turno, cargo, limiar)
        print()
        print(f"Recorte de conferência: {cargo.title()} · {turno}º turno · {ano}")
        print(
            f"Cidade: {visao.resumo['vencedor']} · {fmt_pct(visao.resumo['percentual_vencedor'])}"
            f" · margem {fmt_pp(visao.resumo['margem_pp'])}"
        )
        if visao.resumo.get("disputa_a") and visao.resumo.get("disputa_b"):
            print(
                f"Par do 2º turno: {visao.resumo['disputa_a']} e {visao.resumo['disputa_b']}"
                f" · diferença {fmt_pp(visao.resumo.get('margem_disputa_pp'))}"
                f" · votos em aberto {visao.resumo.get('votos_outros', 0)}"
            )
        colunas = ["bairro", "vencedor", "percentual_vencedor", "margem_pp", "votos_validos", "abstencao_pct", "prioritario"]
        if "lider_disputa" in visao.bairros.columns:
            colunas += ["lider_disputa", "margem_disputa_pp", "votos_outros", "pode_virar", "prioritario_2t"]
        tabela = visao.bairros.loc[:, colunas].copy()
        for coluna in ("prioritario", "pode_virar", "prioritario_2t"):
            if coluna in tabela.columns:
                tabela[coluna] = tabela[coluna].map(lambda valor: "sim" if valor else "não")
        print(tabela.to_string(index=False, float_format=lambda valor: f"{valor:.1f}"))
    finally:
        conexao.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _argumentos()
    try:
        banco = executar_pipeline(
            origem=None if args.amostra else args.raw,
            destino=args.saida,
            usar_amostra=args.amostra,
            limiar=args.limiar,
            ano=None if args.amostra else args.ano,
            cargo=None if args.amostra else args.cargo,
        )
    except ErroPipeline as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logging.exception("Falha inesperada")
        print(f"Falha inesperada: {exc}", file=sys.stderr)
        return 2
    _imprimir_resumo(banco, args.limiar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
