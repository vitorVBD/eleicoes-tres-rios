"""Leitura resiliente dos CSVs do TSE.

Os arquivos oficiais usam separador ``;`` e, em geral, encoding Latin-1.
Arquivos regravados em UTF-8 também são aceitos. A leitura é em blocos
para que o arquivo estadual (centenas de MB ou mais) não precise caber
inteiro na memória: de cada bloco só permanecem as linhas de Três Rios.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path

import pandas as pd

from eleicoes.config import BLOCO_LEITURA, MUNICIPIO, MUNICIPIO_CHAVE, UF
from eleicoes.erros import ErroPipeline
from eleicoes.normalizacao import chave_texto, chave_texto_serie

logger = logging.getLogger(__name__)


def listar_entradas(pasta: Path) -> list[Path]:
    if not pasta.exists():
        raise ErroPipeline(f"A pasta de entrada não existe: {pasta}")
    arquivos = [
        caminho
        for caminho in pasta.rglob("*")
        if caminho.is_file()
        and caminho.suffix.lower() in {".csv", ".zip"}
        and not caminho.name.startswith(".")
        and not caminho.name.startswith("~$")
        and "__MACOSX" not in caminho.parts
    ]
    return sorted(arquivos)


def classificar_arquivo(caminho: Path) -> str | None:
    """Identifica o papel do arquivo pelo nome, ignorando acentos e ``_``.

    O detalhe da apuração é outro layout (colunas largas) e fica de fora
    de propósito: o cruzamento pedido usa a votação longa por seção.
    """
    nome = chave_texto(caminho.name)
    if "LEIA" in nome or "MANUAL" in nome:
        return None
    # O detalhe da apuração não traz o voto de cada candidato. Serve para aptos,
    # comparecimento e abstenção quando o perfil de comparecimento ainda não saiu.
    if "DETALHE" in nome and "SECAO" in nome:
        return "detalhe"
    if "DETALHE" in nome:
        return None
    if "VOTACAO" in nome and "SECAO" in nome:
        return "votos"
    if "LOCAL" in nome and "VOTACAO" in nome:
        return "locais"
    if "COMPARECIMENTO" in nome or "ABSTENCAO" in nome:
        return "abstencao"
    return None


def descobrir_arquivos(pasta: Path) -> dict[str, list[Path]]:
    grupos: dict[str, list[Path]] = {"votos": [], "locais": [], "abstencao": [], "detalhe": []}
    ignorados: list[str] = []
    for caminho in listar_entradas(pasta):
        papel = classificar_arquivo(caminho)
        if papel is None:
            ignorados.append(caminho.name)
            continue
        grupos[papel].append(caminho)
    if ignorados:
        logger.info("Arquivos ignorados (não fazem parte do cruzamento): %s", ", ".join(ignorados))
    if not grupos["votos"]:
        raise ErroPipeline(
            "Não encontrei a votação por seção. Coloque em data/raw o arquivo "
            "votacao_secao_ANO_RJ.csv (ou o .zip com esse nome)."
        )
    if not grupos["locais"]:
        raise ErroPipeline(
            "Não encontrei o eleitorado por local de votação. Coloque em data/raw o arquivo "
            "eleitorado_local_votacao_ANO.csv (ou o .zip). Sem ele não há bairro nem mapa."
        )
    return grupos


def detectar_formato(amostra: bytes) -> tuple[str, str]:
    """Escolhe encoding e separador a partir do começo do arquivo.

    Latin-1 é o padrão do TSE. Se a amostra for UTF-8 válida, inclusive com
    BOM, usamos UTF-8 para não corromper acentos de um arquivo regravado.
    O separador é ``;`` quando ele aparece pelo menos tanto quanto a vírgula,
    que é o caso dos arquivos oficiais.
    """
    if amostra.startswith(b"\xef\xbb\xbf"):
        texto = amostra.decode("utf-8-sig", errors="replace")
        return "utf-8-sig", _separador(texto)
    try:
        texto = amostra.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        texto = amostra.decode("latin1")
        encoding = "latin1"
    return encoding, _separador(texto)


def _separador(texto: str) -> str:
    linha = next((linha for linha in texto.splitlines() if linha.strip()), "")
    if linha.count(";") >= linha.count(","):
        return ";"
    return ","


def _membros_por_sigla(membros: list[str], sigla: str) -> list[str]:
    """Em ZIP com um CSV por abrangência, fica só a sigla pedida.

    ``BR`` é o arquivo de presidente. ``BRASIL`` não entra nessa sigla:
    o padrão exige ``_BR.`` ou ``_BR_``, não o prefixo de outro nome.
    ``RJ`` é o arquivo dos cargos estaduais e do eleitorado.
    """
    padrao = re.compile(rf"(^|_){re.escape(sigla)}(\.|_)", re.IGNORECASE)
    escolhidos = [nome for nome in membros if padrao.search(Path(nome).name)]
    if escolhidos and len(escolhidos) < len(membros):
        logger.info(
            "ZIP com vários CSVs: lendo só %s (%s).",
            sigla,
            ", ".join(Path(nome).name for nome in escolhidos),
        )
        return escolhidos
    return escolhidos or membros


def _ano_do_nome(caminho: Path) -> int | None:
    achado = re.search(r"(20\d{2})", caminho.name)
    return int(achado.group(1)) if achado else None


def iter_blocos(caminho: Path, tamanho: int = BLOCO_LEITURA, sigla: str | None = None):
    """Gera DataFrames do CSV, seja ele solto ou o CSV dentro de um ZIP."""
    if caminho.suffix.lower() == ".zip":
        yield from _iter_zip(caminho, tamanho, sigla)
        return
    yield from _iter_csv(caminho, tamanho, _amostra_arquivo(caminho))


def _amostra_arquivo(caminho: Path) -> bytes:
    try:
        with caminho.open("rb") as arquivo:
            return arquivo.read(8192)
    except OSError as exc:
        raise ErroPipeline(f"Não consegui abrir {caminho.name}: {exc}") from exc


def _iter_zip(caminho: Path, tamanho: int, sigla: str | None = None):
    try:
        with zipfile.ZipFile(caminho) as arquivo_zip:
            membros = [
                nome
                for nome in arquivo_zip.namelist()
                if nome.lower().endswith(".csv")
                and not nome.endswith("/")
                and not Path(nome).name.startswith(".")
                and "__MACOSX" not in nome
            ]
    except zipfile.BadZipFile as exc:
        raise ErroPipeline(f"{caminho.name} não é um ZIP válido.") from exc
    if not membros:
        raise ErroPipeline(f"O ZIP {caminho.name} não contém um CSV.")
    membros = _membros_por_sigla(membros, sigla or "RJ")
    for membro in membros:
        logger.info("Lendo %s :: %s", caminho.name, membro)
        with zipfile.ZipFile(caminho) as arquivo_zip:
            with arquivo_zip.open(membro) as bruto:
                amostra = bruto.read(8192)
        # O fluxo do ZIP não é seekable; o motor Python lê em bloco mesmo assim.
        yield from _iter_fluxo_zip(caminho, membro, tamanho, amostra)


def _iter_fluxo_zip(caminho: Path, membro: str, tamanho: int, amostra: bytes):
    encoding, separador = detectar_formato(amostra)
    logger.info("Formato de %s: encoding %s, separador %r", membro, encoding, separador)
    ano = _ano_do_nome(caminho) or _ano_do_nome(Path(membro))
    try:
        with zipfile.ZipFile(caminho) as arquivo_zip:
            with arquivo_zip.open(membro) as bruto:
                texto = io.TextIOWrapper(bruto, encoding=encoding, newline="")
                yield from _consumir_leitor(texto, separador, encoding, tamanho, "python", caminho, ano)
    except UnicodeDecodeError:
        if encoding == "latin1":
            raise
        logger.warning("Falha ao ler %s como %s; tentando latin1.", membro, encoding)
        with zipfile.ZipFile(caminho) as arquivo_zip:
            with arquivo_zip.open(membro) as bruto:
                texto = io.TextIOWrapper(bruto, encoding="latin1", newline="")
                yield from _consumir_leitor(texto, separador, "latin1", tamanho, "python", caminho, ano)


def _iter_csv(caminho: Path, tamanho: int, amostra: bytes):
    encoding, separador = detectar_formato(amostra)
    logger.info("Formato de %s: encoding %s, separador %r", caminho.name, encoding, separador)
    ano = _ano_do_nome(caminho)
    try:
        yield from _consumir_leitor(caminho, separador, encoding, tamanho, None, caminho, ano)
    except UnicodeDecodeError:
        if encoding == "latin1":
            raise
        logger.warning("Falha ao ler %s como %s; tentando latin1.", caminho.name, encoding)
        yield from _consumir_leitor(caminho, separador, "latin1", tamanho, None, caminho, ano)


def _consumir_leitor(origem, separador: str, encoding: str, tamanho: int, motor: str | None, caminho: Path, ano: int | None):
    argumentos: dict = {
        "sep": separador,
        "encoding": encoding,
        "dtype": str,
        "chunksize": tamanho,
        # "NA" e "NULO" não podem virar valor nulo do Pandas: são texto do TSE.
        "keep_default_na": False,
        "na_values": [],
        "on_bad_lines": "warn",
    }
    if motor:
        argumentos["engine"] = motor
    else:
        argumentos["low_memory"] = False
    # Arquivo já decodificado (ZIP): o encoding foi aplicado no TextIOWrapper.
    if not isinstance(origem, (str, Path)):
        argumentos.pop("encoding", None)
    try:
        leitor = pd.read_csv(origem, **argumentos)
    except pd.errors.EmptyDataError as exc:
        raise ErroPipeline(f"{caminho.name} está vazio.") from exc
    except pd.errors.ParserError as exc:
        raise ErroPipeline(
            f"Não consegui interpretar {caminho.name}. Confira se é um CSV do TSE "
            f"(separador ';' e encoding Latin-1) e se o arquivo não está corrompido."
        ) from exc
    try:
        for bloco in leitor:
            bloco.columns = [
                str(coluna).strip().strip('"').strip("'").upper().lstrip("\ufeff") for coluna in bloco.columns
            ]
            bloco["_ano_arquivo"] = ano
            bloco["_arquivo"] = caminho.name
            yield bloco
    except pd.errors.ParserError as exc:
        raise ErroPipeline(
            f"O arquivo {caminho.name} tem linhas com número de colunas inesperado. "
            "Abra o CSV original do TSE, sem reexportar por uma planilha."
        ) from exc


def exigir_colunas(df: pd.DataFrame, obrigatorias: list[str], caminho: Path) -> None:
    faltando = [coluna for coluna in obrigatorias if coluna not in df.columns]
    if faltando:
        encontradas = ", ".join(map(str, list(df.columns[:30])))
        raise ErroPipeline(
            f"O arquivo {caminho.name} não tem as colunas {', '.join(faltando)}. "
            f"Confira se baixou o arquivo certo do TSE. Colunas encontradas: {encontradas}."
        )


def filtrar_recorte(bloco: pd.DataFrame, municipio: str | None) -> pd.DataFrame:
    """Mantém o Rio de Janeiro. Com município, fica só essa cidade.

    A comparação ignora acento, maiúsculas e espaços repetidos.
    ``municipio`` vazio mantém todas as cidades do estado.
    """
    if "SG_UF" in bloco.columns:
        uf = chave_texto_serie(bloco["SG_UF"])
        if uf.ne("").any():
            bloco = bloco.loc[uf.eq(UF)].copy()
    if not municipio or "NM_MUNICIPIO" not in bloco.columns:
        return bloco
    nomes = chave_texto_serie(bloco["NM_MUNICIPIO"])
    return bloco.loc[nomes.eq(chave_texto(municipio))].copy()


def filtrar_tres_rios(bloco: pd.DataFrame) -> pd.DataFrame:
    """Mantém Três Rios/RJ. A comparação ignora acento e espaços."""
    return filtrar_recorte(bloco, MUNICIPIO)


def enxugar(bloco: pd.DataFrame, desejadas: list[str]) -> pd.DataFrame:
    manter = [coluna for coluna in desejadas if coluna in bloco.columns]
    for extra in ("_ano_arquivo", "_arquivo"):
        if extra in bloco.columns and extra not in manter:
            manter.append(extra)
    return bloco.loc[:, manter].copy()


def _filtrar_ano_cargo(bloco: pd.DataFrame, ano: int | None, cargos: set[str] | None) -> pd.DataFrame:
    if cargos and "DS_CARGO" in bloco.columns:
        cargo = bloco["DS_CARGO"].fillna("").astype(str).str.strip().str.upper()
        bloco = bloco.loc[cargo.isin(cargos)]
    if ano is not None:
        coluna = next((nome for nome in ("ANO_ELEICAO", "AA_ELEICAO") if nome in bloco.columns), None)
        if coluna is not None:
            valores = pd.to_numeric(bloco[coluna], errors="coerce")
            bloco = bloco.loc[valores.isna() | valores.eq(ano)]
    return bloco


def _somar_ranking_uf(bloco: pd.DataFrame, cargo: str, ranking: dict[str, int]) -> None:
    """Soma votos nominais do cargo no bloco inteiro, antes de cortar o município.

    No arquivo nacional de presidente, essa soma é a do país: os dois primeiros
    são o par de referência da disputa, e não só quem ficou na frente em Três Rios.
    """
    from eleicoes.normalizacao import formatar_nomes

    if "DS_CARGO" not in bloco.columns or "QT_VOTOS" not in bloco.columns:
        return
    cargos = bloco["DS_CARGO"].fillna("").astype(str).str.strip().str.upper()
    recorte = bloco.loc[cargos.eq(cargo)].copy()
    if recorte.empty or "NM_VOTAVEL" not in recorte.columns:
        return
    numeros = recorte["NR_VOTAVEL"] if "NR_VOTAVEL" in recorte.columns else pd.Series("", index=recorte.index)
    numeros = numeros.fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.replace(r"\D", "", regex=True)
    fora = numeros.isin(["95", "96", "97"])
    recorte = recorte.loc[~fora]
    if recorte.empty:
        return
    quantidades = pd.to_numeric(recorte["QT_VOTOS"], errors="coerce").fillna(0)
    nomes = formatar_nomes(recorte["NM_VOTAVEL"])
    for nome, quantidade in zip(nomes, quantidades):
        if not nome or quantidade <= 0:
            continue
        ranking[nome] = ranking.get(nome, 0) + int(quantidade)


def ler_filtrado(
    caminhos: list[Path],
    obrigatorias: list[str],
    colunas_uteis: list[str],
    validar=None,
    ano: int | None = None,
    cargos: set[str] | None = None,
    ranking_uf: dict[str, int] | None = None,
    sigla: str | None = None,
    municipio: str | None = MUNICIPIO,
) -> tuple[pd.DataFrame, dict]:
    """Concatena os arquivos já reduzidos ao recorte e às colunas usadas no cruzamento.

    ``municipio`` padrão é Três Rios. ``None`` mantém todas as cidades do Rio.
    """
    partes: list[pd.DataFrame] = []
    lidas = 0
    mantidas = 0
    cargo_ranking = next(iter(cargos)) if cargos and len(cargos) == 1 else None
    for caminho in caminhos:
        primeiro = True
        for bloco in iter_blocos(caminho, sigla=sigla):
            if primeiro:
                exigir_colunas(bloco, obrigatorias, caminho)
                if validar is not None:
                    validar(bloco, caminho)
                primeiro = False
            lidas += len(bloco)
            if ranking_uf is not None and cargo_ranking is not None:
                candidato = _filtrar_ano_cargo(bloco, ano, None)
                _somar_ranking_uf(candidato, cargo_ranking, ranking_uf)
            filtrado = _filtrar_ano_cargo(filtrar_recorte(bloco, municipio), ano, cargos)
            mantidas += len(filtrado)
            if not filtrado.empty:
                partes.append(enxugar(filtrado, colunas_uteis))
            logger.info(
                "%s: %s linhas lidas neste bloco, %s no recorte",
                caminho.name,
                f"{len(bloco):,}".replace(",", "."),
                f"{len(filtrado):,}".replace(",", "."),
            )
    if not partes:
        return pd.DataFrame(), {"lidas": lidas, "mantidas": mantidas}
    return pd.concat(partes, ignore_index=True), {"lidas": lidas, "mantidas": mantidas}
