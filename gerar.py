"""Gera os PDFs de uma cidade do Rio de Janeiro.

Uso, para quem já tem o programa preparado:
    python gerar.py "Nova Iguacu"
    python gerar.py --listar

Quem não mexe com computador usa o arquivo gerar.bat, que pergunta a cidade.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
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
            f'Não encontrei o município "{pedido}" no Rio de Janeiro. Confira o nome.'
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


def listar_cidades() -> list[str]:
    if not BANCO_ESTADO.exists():
        return []
    conexao = conectar(BANCO_ESTADO)
    try:
        return [nome for nome, _secoes in _listar(conexao)]
    finally:
        conexao.close()


def _imprimir(pares: list[tuple[str, int]]) -> None:
    print(f"{len(pares)} municípios do Rio de Janeiro:")
    for nome, secoes in pares:
        print(f"  {nome} ({secoes} seções)")


def _abrir_pasta(pasta: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(pasta)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(pasta)], check=False)
        else:
            subprocess.run(["xdg-open", str(pasta)], check=False)
    except OSError:
        return


def _escrever_pdfs(cidade: str) -> list[tuple[str, Path]]:
    pasta = _pasta(cidade)
    return [
        (
            "Apuração",
            gerar_relatorio(
                pasta / "eleicao_presidencial_2026.pdf",
                BANCO_ESTADO,
                municipio=cidade,
                nome_cidade=cidade,
            ),
        ),
        (
            "Roteiro",
            gerar_plano(
                pasta / "plano_panfletagem.pdf",
                BANCO_ESTADO,
                municipio=cidade,
                cidade=cidade,
            ),
        ),
        (
            "Mapa",
            gerar_mapa(
                pasta / "mapa.pdf",
                BANCO_ESTADO,
                municipio=cidade,
                cidade=cidade,
            ),
        ),
    ]


_NOMES_PDF = (
    ("Apuração", "eleicao_presidencial_2026.pdf", "apuracao"),
    ("Roteiro", "plano_panfletagem.pdf", "roteiro"),
    ("Mapa", "mapa.pdf", "mapa"),
)


def _pdf_valido(caminho: Path) -> bool:
    if not caminho.is_file() or caminho.stat().st_size < 100:
        return False
    with caminho.open("rb") as arquivo:
        return arquivo.read(5) == b"%PDF-"


def _caminhos_pdf(cidade: str) -> list[tuple[str, str, Path]]:
    pasta = _pasta(cidade)
    return [
        (rotulo, f"{pasta.name}-{sufixo}.pdf", pasta / nome_interno)
        for rotulo, nome_interno, sufixo in _NOMES_PDF
    ]


def _pdfs_prontos(cidade: str) -> bool:
    return all(_pdf_valido(caminho) for _rotulo, _nome, caminho in _caminhos_pdf(cidade))


def _ler_pdfs(cidade: str) -> list[tuple[str, str, bytes]] | None:
    caminhos = _caminhos_pdf(cidade)
    if not all(_pdf_valido(caminho) for _rotulo, _nome, caminho in caminhos):
        return None
    return [(rotulo, nome, caminho.read_bytes()) for rotulo, nome, caminho in caminhos]


def gerar_pdfs(cidade: str, recriar: bool = False) -> list[tuple[str, str, bytes]]:
    """Devolve os três PDFs. Se já existirem, não monta de novo."""
    if not recriar:
        prontos = _ler_pdfs(cidade)
        if prontos is not None:
            return prontos
    _escrever_pdfs(cidade)
    prontos = _ler_pdfs(cidade)
    if prontos is None:
        raise ErroPipeline(f"Não consegui gravar os PDFs de {cidade}.")
    return prontos


def _gerar_cidade(cidade: str, recriar: bool = False) -> Path:
    pasta = _pasta(cidade)
    if not recriar and _pdfs_prontos(cidade):
        print(f"Os PDFs de {cidade} já estavam prontos.")
    else:
        print(f"Gerando os PDFs de {cidade}...")
        _escrever_pdfs(cidade)
    for rotulo, _nome, caminho in _caminhos_pdf(cidade):
        print(f"{rotulo}: {caminho}")
    print()
    print("Pronto. Os três PDFs estão nesta pasta:")
    print(pasta)
    _abrir_pasta(pasta)
    return pasta


def _perguntar(pares: list[tuple[str, int]], nomes: list[str], recriar: bool = False) -> int:
    print()
    print("Digite o nome da cidade e aperte Enter.")
    print("Exemplo: Nova Iguaçu")
    print("Para ver todas as cidades, digite: lista")
    print("Para sair, aperte Enter sem digitar nada.")
    while True:
        print()
        try:
            pedido = input("Cidade: ").strip()
        except EOFError:
            print()
            return 0
        if not pedido:
            return 0
        if chave_texto(pedido) in {"LISTA", "LISTAR"}:
            _imprimir(pares)
            continue
        try:
            _gerar_cidade(_resolver(pedido, nomes), recriar=recriar)
        except ErroPipeline as exc:
            print(f"Erro: {exc}")
            continue
        print()
        print("Para gerar outra cidade, digite o nome. Para sair, aperte Enter.")


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
        if args.listar:
            _imprimir(pares)
            return 0
        if not args.cidade:
            return _perguntar(pares, nomes, recriar=args.reprocessar)
        _gerar_cidade(_resolver(" ".join(args.cidade), nomes), recriar=args.reprocessar)
    except ErroPipeline as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
