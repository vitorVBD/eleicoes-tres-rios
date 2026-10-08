"""Orquestração do ETL: CSV do TSE → SQLite + JSON de bairros."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from eleicoes.apuracao import Visao
from eleicoes.armazenamento import criar_banco, gravar_meta, inserir
from eleicoes.config import (
    JSON_BAIRROS,
    LIMIAR_PRIORITARIO,
    MUNICIPIO,
    PASTA_AMOSTRAS,
    PASTA_PROCESSADO,
    PASTA_RAW,
    UF,
)
from eleicoes.consultas import listar_combinacoes, montar_painel
from eleicoes.erros import ErroPipeline
from eleicoes.leitura import descobrir_arquivos, ler_filtrado
from eleicoes.preparacao import preparar_abstencao, preparar_locais, preparar_votos

logger = logging.getLogger(__name__)

COLUNAS_VOTOS = [
    "ANO_ELEICAO",
    "AA_ELEICAO",
    "NR_TURNO",
    "SG_UF",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "DS_CARGO",
    "NR_VOTAVEL",
    "NR_CANDIDATO",
    "NR_PARTIDO",
    "NM_VOTAVEL",
    "NM_URNA_CANDIDATO",
    "NM_CANDIDATO",
    "QT_VOTOS",
    "DS_TIPO_VOTAVEL",
    "NM_TIPO_VOTAVEL",
]
COLUNAS_LOCAIS = [
    "ANO_ELEICAO",
    "AA_ELEICAO",
    "SG_UF",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "NM_LOCAL_VOTACAO",
    "DS_ENDERECO",
    "NM_BAIRRO",
    "NR_LATITUDE",
    "NR_LONGITUDE",
    "DS_LATITUDE",
    "DS_LONGITUDE",
]
COLUNAS_ABSTENCAO = [
    "ANO_ELEICAO",
    "AA_ELEICAO",
    "NR_TURNO",
    "SG_UF",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "QT_APTOS",
    "QT_COMPARECIMENTO",
    "QT_ABSTENCAO",
    "QT_ABSTENCOES",
]


def _validar_votavel(bloco: pd.DataFrame, caminho: Path) -> None:
    opcoes = ["NR_VOTAVEL", "NM_VOTAVEL", "NM_URNA_CANDIDATO", "NM_CANDIDATO", "NR_CANDIDATO"]
    if not any(coluna in bloco.columns for coluna in opcoes):
        raise ErroPipeline(
            f"O arquivo {caminho.name} não traz NR_VOTAVEL nem NM_VOTAVEL. "
            "Use a votação por seção eleitoral, não o boletim de urna nem o detalhe da apuração."
        )


def _registros(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records", force_ascii=False))


def _gravar_atomico(destino: Path, gravar) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    try:
        gravar(temporario)
        temporario.replace(destino)
    except Exception:
        temporario.unlink(missing_ok=True)
        raise


def _montar_json(conexao, meta: dict, limiar: float) -> dict:
    recortes = []
    combinacoes = listar_combinacoes(conexao)
    for linha in combinacoes.itertuples(index=False):
        visao: Visao = montar_painel(conexao, int(linha.ano), int(linha.turno), linha.cargo, limiar)
        recortes.append(
            {
                "ano": int(linha.ano),
                "turno": int(linha.turno),
                "cargo": linha.cargo,
                "resumo_municipio": visao.resumo,
                "bairros": _registros(visao.bairros),
                "candidatos": _registros(visao.candidatos),
                "locais": _registros(visao.locais),
            }
        )
    return {
        "municipio": MUNICIPIO,
        "uf": UF,
        "gerado_em": meta["gerado_em"],
        "origem": meta["origem"],
        "limiar_prioritario_pp": limiar,
        "arquivos": meta["arquivos"].split(" | ") if meta.get("arquivos") else [],
        "avisos": [aviso for aviso in meta.get("avisos", "").split("\n") if aviso],
        "definicoes": {
            "votos_validos": "Nominais mais votos de legenda. Não incluem branco, nulo nem anulado.",
            "vencedor": "Candidato com mais votos nominais no bairro. Legenda não elege um nome.",
            "margem_pp": "Diferença entre o 1º e o 2º colocado, em pontos percentuais dos votos válidos.",
            "prioritario": f"Margem menor que {limiar:g} pontos percentuais.",
            "abstencao_pct": "Abstenções divididas pelos eleitores aptos das seções do bairro.",
        },
        "recortes": recortes,
    }


def executar_pipeline(
    origem: Path | None = None,
    destino: Path | None = None,
    usar_amostra: bool = False,
    limiar: float = LIMIAR_PRIORITARIO,
    ano: int | None = None,
    cargo: str | None = None,
) -> Path:
    """Processa os arquivos e devolve o caminho do SQLite gerado.

    ``ano`` e ``cargo`` limitam o que fica no banco. A demonstração ignora
    esses filtros para continuar exercitando prefeito e vereador.
    """
    pasta_saida = destino or PASTA_PROCESSADO
    banco = pasta_saida / "tres_rios.db"
    json_saida = pasta_saida / JSON_BAIRROS.name
    avisos: list[str] = []
    if usar_amostra:
        ano = None
        cargo = None
    cargo = cargo.strip().upper() if cargo else None
    cargos = {cargo} if cargo else None

    if usar_amostra:
        from eleicoes.amostra import gerar_amostra

        pasta_origem = PASTA_AMOSTRAS if origem is None else origem
        gerar_amostra(pasta_origem)
        tipo_origem = "demonstracao"
    else:
        pasta_origem = origem or PASTA_RAW
        tipo_origem = "oficial"

    arquivos = descobrir_arquivos(pasta_origem)
    if cargo == "PRESIDENTE":
        nacionais = [caminho for caminho in arquivos["votos"] if "_BR" in caminho.stem.upper()]
        if nacionais:
            arquivos["votos"] = nacionais
    logger.info("Votação: %s", ", ".join(caminho.name for caminho in arquivos["votos"]))
    logger.info("Locais: %s", ", ".join(caminho.name for caminho in arquivos["locais"]))
    if arquivos["abstencao"]:
        logger.info("Abstenção: %s", ", ".join(caminho.name for caminho in arquivos["abstencao"]))

    ranking_uf: dict[str, int] = {}
    votos_brutos, stats_votos = ler_filtrado(
        arquivos["votos"],
        ["NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "DS_CARGO", "QT_VOTOS"],
        COLUNAS_VOTOS,
        validar=_validar_votavel,
        ano=ano,
        cargos=cargos,
        ranking_uf=ranking_uf if cargo else None,
        sigla="BR" if cargo == "PRESIDENTE" else None,
    )
    if votos_brutos.empty:
        recorte = f" de {cargo}" if cargo else ""
        periodo = f" em {ano}" if ano else ""
        dica = ""
        if cargo == "PRESIDENTE":
            dica = (
                " O presidente não vem no ZIP da UF: baixe votacao_secao_2026_BR.zip "
                "(arquivo nacional, só desse cargo)."
            )
        raise ErroPipeline(
            f"Nenhuma linha de Três Rios{recorte}{periodo} na votação. "
            "Confira se o município está como TRÊS RIOS."
            + dica
        )

    locais_brutos, stats_locais = ler_filtrado(
        arquivos["locais"],
        ["NM_MUNICIPIO", "NR_ZONA", "NR_SECAO"],
        COLUNAS_LOCAIS,
    )
    if locais_brutos.empty:
        raise ErroPipeline(
            "Nenhuma linha de Três Rios no arquivo de locais de votação. "
            "Sem esse cruzamento não há bairro."
        )

    if arquivos["abstencao"]:
        abstencao_bruta, stats_abst = ler_filtrado(
            arquivos["abstencao"],
            ["NM_MUNICIPIO", "NR_ZONA", "NR_SECAO"],
            COLUNAS_ABSTENCAO,
            ano=ano,
        )
    elif arquivos["detalhe"]:
        logger.info("Abstenção pelo detalhe da apuração: %s", ", ".join(c.name for c in arquivos["detalhe"]))
        abstencao_bruta, stats_abst = ler_filtrado(
            arquivos["detalhe"],
            ["NM_MUNICIPIO", "NR_ZONA", "NR_SECAO"],
            COLUNAS_ABSTENCAO + ["DS_CARGO"],
            ano=ano,
            cargos=cargos,
            sigla="BR" if cargo == "PRESIDENTE" else None,
        )
        avisos.append(
            "Abstenção lida do detalhe da apuração por seção. "
            "O perfil de comparecimento de 2026 ainda não estava publicado."
        )
    else:
        abstencao_bruta, stats_abst = pd.DataFrame(), {"lidas": 0, "mantidas": 0}
        avisos.append(
            "Arquivo de comparecimento e abstenção não encontrado. "
            "A taxa de abstenção ficará em branco até você incluí-lo e processar de novo."
        )

    votos = preparar_votos(votos_brutos, avisos)
    locais = preparar_locais(locais_brutos, avisos)
    abstencao = preparar_abstencao(abstencao_bruta, avisos)

    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")
    nomes = [
        caminho.name
        for grupo in ("votos", "locais", "abstencao", "detalhe")
        for caminho in arquivos[grupo]
    ]
    finalistas = sorted(ranking_uf.items(), key=lambda item: (-item[1], item[0]))
    meta = {
        "municipio": MUNICIPIO,
        "uf": UF,
        "origem": tipo_origem,
        "gerado_em": agora,
        "arquivos": " | ".join(nomes),
        "avisos": "\n".join(avisos),
        "linhas_votos_lidas": str(stats_votos["lidas"]),
        "linhas_votos_tres_rios": str(stats_votos["mantidas"]),
        "linhas_locais_lidas": str(stats_locais["lidas"]),
        "linhas_locais_tres_rios": str(stats_locais["mantidas"]),
        "linhas_abstencao_lidas": str(stats_abst["lidas"]),
        "linhas_abstencao_tres_rios": str(stats_abst["mantidas"]),
        "bairros": str(locais["bairro"].nunique()),
        "limiar_prioritario_pp": str(limiar),
        "ano_filtro": "" if ano is None else str(ano),
        "cargo_filtro": cargo or "",
        "disputa_a": finalistas[0][0] if len(finalistas) >= 2 else "",
        "disputa_b": finalistas[1][0] if len(finalistas) >= 2 else "",
        "disputa_abrangencia": "Brasil" if any("_BR" in caminho.stem.upper() for caminho in arquivos["votos"]) else "Rio de Janeiro",
    }

    def gravar_banco(temporario: Path) -> None:
        conexao = criar_banco(temporario)
        try:
            inserir(conexao, "locais", locais)
            inserir(conexao, "votos", votos)
            inserir(conexao, "abstencao", abstencao)
            gravar_meta(conexao, meta)
            conexao.commit()
        finally:
            conexao.close()

    _gravar_atomico(banco, gravar_banco)

    def gravar_json(temporario: Path) -> None:
        conexao = sqlite3_connect(banco)
        try:
            payload = _montar_json(conexao, meta, limiar)
        finally:
            conexao.close()
        temporario.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    _gravar_atomico(json_saida, gravar_json)
    logger.info("SQLite: %s", banco)
    logger.info("JSON: %s", json_saida)
    return banco


def sqlite3_connect(caminho: Path):
    from eleicoes.armazenamento import conectar

    return conectar(caminho)
