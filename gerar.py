"""Gera os PDFs de uma cidade do Rio de Janeiro.

Uso:
    python gerar.py "Nova Iguacu"
    python gerar.py --listar
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from eleicoes.armazenamento import conectar
from eleicoes.config import PASTA_PROCESSADO, PASTA_RAW
from eleicoes.erros import ErroPipeline
from eleicoes.etl import executar_pipeline
from eleicoes.normalizacao import chave_texto
from eleicoes.plano import gerar as gerar_plano
from eleicoes.plano import gerar_mapa
from eleicoes.relatorio import gerar as gerar_relatorio

BANCO_ESTADO = PASTA_PROCESSADO / "rio.db"


def _listar(conexao) -> list[tuple[str, int]]:
    linhas = conexao.execute(
        "SELECT municipio, COUNT(*) FROM locais GROUP BY municipio ORDER BY municipio"
    ).fetchall()
    return [(str(linha[0]), int(linha[1])) for linha in linhas]


def _resolver(pedido: str, nomes: list[str]) -> str:
    chave = chave_texto(pedido)
    iguais = [nome for nome in nomes if chave_texto(nome) == chave]
    if len(iguais) == 1:
        return iguais[0]
    parciais = [nome for nome in nomes if chave in chave_texto(nome)]
    if len(parciais) == 1:
        return parciais[0]
    if not parciais:
        raise ErroPipeline(
            f'Não encontrei o município "{pedido}" no Rio de Janeiro. '
            "Confira o nome ou rode: python gerar.py --listar"
        )
    lista = ", ".join(parciais[:12])
    raise ErroPipeline(f'Há mais de um município parecido com "{pedido}": {lista}')


def _tem_arquivos_tse() -> bool:
    if not PASTA_RAW.exists():
        return False
    return any(PASTA_RAW.glob("*.csv")) or any(PASTA_RAW.glob("*.zip"))


def _garantir_banco(reprocessar: bool) -> None:
    if BANCO_ESTADO.exists() and not reprocessar:
        return
    if not _tem_arquivos_tse():
        raise ErroPipeline(
            "Não achei os arquivos do TSE em data/raw. "
            "Coloque lá a votação nacional, o eleitorado do RJ e o detalhe da apuração."
        )
    print("Lendo os arquivos do TSE de todo o Rio de Janeiro.")
    print("A primeira vez pode levar vários minutos. Depois, cada cidade sai rápido.")
    executar_pipeline(todo_o_estado=True, ano=2026, cargo="PRESIDENTE")


def _pasta(nome: str) -> Path:
    slug = chave_texto(nome).lower().replace(" ", "-")
    pasta = PASTA_PROCESSADO / "cidades" / slug
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera os PDFs de uma cidade do Rio de Janeiro.")
    parser.add_argument("cidade", nargs="*", help="Nome do município. Ex.: Nova Iguaçu")
    parser.add_argument("--listar", action="store_true", help="Lista as cidades disponíveis.")
    parser.add_argument("--reprocessar", action="store_true", help="Lê os arquivos do TSE de novo.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        _garantir_banco(args.reprocessar)
        conexao = conectar(BANCO_ESTADO)
        try:
            pares = _listar(conexao)
        finally:
            conexao.close()
        nomes = [nome for nome, _ in pares]
        if args.listar or not args.cidade:
            print(f"{len(nomes)} municípios do Rio de Janeiro:")
            for nome, secoes in pares:
                print(f"  {nome} ({secoes} seções)")
            if not args.cidade and not args.listar:
                print()
                print('Para gerar os PDFs: gerar.bat "Nova Iguacu"')
            return 0
        cidade = _resolver(" ".join(args.cidade), nomes)
        pasta = _pasta(cidade)
        print(f"Gerando os PDFs de {cidade}...")
        eleicao = gerar_relatorio(
            pasta / "eleicao_presidencial_2026.pdf",
            BANCO_ESTADO,
            municipio=cidade,
            nome_cidade=cidade,
        )
        print(f"Apuração: {eleicao}")
        roteiro = gerar_plano(
            pasta / "plano_panfletagem.pdf",
            BANCO_ESTADO,
            municipio=cidade,
            cidade=cidade,
        )
        print(f"Roteiro: {roteiro}")
        mapa = gerar_mapa(
            pasta / "mapa.pdf",
            BANCO_ESTADO,
            municipio=cidade,
            cidade=cidade,
        )
        print(f"Mapa: {mapa}")
    except ErroPipeline as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
