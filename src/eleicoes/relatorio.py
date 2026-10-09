"""PDF no formato do boletim de Paraíba do Sul, com os números de Três Rios.

Páginas:
1. Resumo da cidade e gráfico geral.
2. Resultado por bairro.
3. Lula × Flávio por bairro.
4. Resultado por local de votação.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from eleicoes.config import ANO_ELEICAO, BANCO, CARGO_ELEICAO, PASTA_PROCESSADO

ANO = ANO_ELEICAO
TURNO = 1
CARGO = CARGO_ELEICAO
SAIDA = PASTA_PROCESSADO / "eleicao_presidencial_2026_tres_rios.pdf"

# Mesma ordem e os mesmos cinco nomes em destaque do modelo.
DESTAQUES = (
    ("13", "lula", "Lula", "Lula (13)"),
    ("22", "flavio", "Flávio", "Flávio Bolsonaro (22)"),
    ("14", "renan", "Renan", "Renan Santos (14)"),
    ("55", "caiado", "Caiado", "Ronaldo Caiado (55)"),
    ("70", "cury", "Cury", "Augusto Cury (70)"),
)
COLUNAS = ("lula", "flavio", "renan", "caiado", "cury", "outros", "brancos", "nulos")
APELIDOS = {
    "30": "Zema",
    "80": "Samara",
    "27": "Clariana Barão",
    "16": "Hertz Dias",
    "21": "Edmilson Costa",
    "29": "Rui Costa Pimenta",
    "35": "Wilson Grassi",
    "28": "Leonardo Alves",
}

VERMELHO = "#C0392B"
AZUL = "#1A5276"
LARANJA = "#D35400"
VERDE = "#196F3D"
ROXO = "#6C3483"
CINZA = "#566573"
PRETO = "#1C1C1C"
AZUL_ABST = "#5D6D7E"
HEADER = "#1B2631"

TINTA = {
    "lula": ("#F8D7D3", VERMELHO),
    "flavio": ("#D6E6F5", AZUL),
    "renan": ("#FDE6D0", LARANJA),
    "caiado": ("#D9F2E3", VERDE),
    "cury": ("#EADCF3", ROXO),
    "outros": ("#E6E8EA", CINZA),
    "brancos": ("#FFFFFF", PRETO),
    "nulos": ("#E8E8E8", PRETO),
    "aptos": ("#F4F6F7", HEADER),
    "abst": ("#E4E8EB", AZUL_ABST),
}
COR_BARRA = {
    "Lula": VERMELHO,
    "Flávio": AZUL,
    "Renan": LARANJA,
    "Caiado": VERDE,
    "Cury": ROXO,
    "Outros": "#7F8C8D",
    "Brancos": "#BFC3C7",
    "Nulos": PRETO,
    "Abstenções": "#85929E",
}


@dataclass
class Fatia:
    rotulo: str
    bairro: str
    local: str
    lula: int
    flavio: int
    renan: int
    caiado: int
    cury: int
    outros: int
    brancos: int
    nulos: int
    aptos: int
    comparecimento: int
    abstencao: int
    apuradas: int
    previstas: int

    @property
    def nominais(self) -> int:
        return self.lula + self.flavio + self.renan + self.caiado + self.cury + self.outros


def _fonte() -> str:
    regular = Path(r"C:\Windows\Fonts\arial.ttf")
    negrito = Path(r"C:\Windows\Fonts\arialbd.ttf")
    if "Relatorio" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Relatorio", str(regular)))
        pdfmetrics.registerFont(TTFont("Relatorio-Bold", str(negrito)))
    plt.rcParams["font.family"] = "Arial"
    return "Relatorio"


def _inteiro(valor: object) -> int:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0
    return int(valor)


def _fmt_int(valor: int) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _fmt_pct(parte: int, todo: int) -> str:
    if not todo:
        return "—"
    return f"{100 * parte / todo:.1f}%".replace(".", ",")


def _fmt_secoes(apuradas: int, previstas: int) -> str:
    if apuradas == previstas:
        return str(apuradas)
    return f"{apuradas}/{previstas}"


def _lista_pt(nomes: list[str]) -> str:
    if not nomes:
        return "nenhum"
    if len(nomes) == 1:
        return nomes[0]
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def carregar(conexao: sqlite3.Connection, municipio: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    filtro = " AND municipio = ?" if municipio else ""
    votos = pd.read_sql_query(
        f"""
        SELECT zona, secao, nr_votavel, nm_votavel, qt_votos, tipo
        FROM votos
        WHERE ano = ? AND turno = ? AND cargo = ?{filtro}
        """,
        conexao,
        params=(ANO, TURNO, CARGO, municipio) if municipio else (ANO, TURNO, CARGO),
    )
    locais = pd.read_sql_query(
        f"SELECT zona, secao, bairro, local_votacao FROM locais{' WHERE municipio = ?' if municipio else ''}",
        conexao,
        params=(municipio,) if municipio else None,
    )
    abstencao = pd.read_sql_query(
        f"""
        SELECT zona, secao, qt_aptos, qt_comparecimento, qt_abstencao
        FROM abstencao
        WHERE ano = ? AND turno = ?{filtro}
        """,
        conexao,
        params=(ANO, TURNO, municipio) if municipio else (ANO, TURNO),
    )
    for quadro in (votos, locais, abstencao):
        quadro["zona"] = quadro["zona"].astype(str)
        quadro["secao"] = quadro["secao"].astype(str)
    return votos, locais, abstencao


def montar(
    votos: pd.DataFrame,
    locais: pd.DataFrame,
    abstencao: pd.DataFrame,
    nome_cidade: str = "Três Rios",
) -> tuple[Fatia, list[Fatia], list[Fatia], list[str], list[str]]:
    mapa = {item[0]: item[1] for item in DESTAQUES}
    trabalho = votos.copy()
    trabalho["balde"] = [
        "brancos" if tipo == "branco" else "nulos" if tipo == "nulo" else mapa.get(str(numero), "outros") if tipo == "nominal" else None
        for tipo, numero in zip(trabalho["tipo"], trabalho["nr_votavel"])
    ]
    trabalho = trabalho.loc[trabalho["balde"].notna()]
    somas = (
        trabalho.groupby(["zona", "secao", "balde"], as_index=False)["qt_votos"].sum()
        .pivot(index=["zona", "secao"], columns="balde", values="qt_votos")
        .reset_index()
    )
    for coluna in COLUNAS:
        if coluna not in somas.columns:
            somas[coluna] = 0
    base = locais.merge(somas, on=["zona", "secao"], how="outer")
    base = base.merge(abstencao, on=["zona", "secao"], how="left")
    base["bairro"] = base["bairro"].fillna("Sem bairro")
    base["local_votacao"] = base["local_votacao"].fillna("Sem local")
    for coluna in COLUNAS:
        base[coluna] = base[coluna].map(_inteiro)
    base["qt_aptos"] = base["qt_aptos"].map(_inteiro)
    base["qt_comparecimento"] = base["qt_comparecimento"].map(_inteiro)
    base["qt_abstencao"] = base["qt_abstencao"].map(_inteiro)
    chaves_abst = set(zip(abstencao["zona"], abstencao["secao"]))
    chaves_voto = set(zip(somas["zona"], somas["secao"]))
    base["apurada"] = [((zona, secao) in chaves_abst) or ((zona, secao) in chaves_voto) for zona, secao in zip(base["zona"], base["secao"])]

    def fatia(grupo: pd.DataFrame, rotulo: str, bairro: str = "", local: str = "") -> Fatia:
        return Fatia(
            rotulo=rotulo,
            bairro=bairro,
            local=local,
            lula=int(grupo["lula"].sum()),
            flavio=int(grupo["flavio"].sum()),
            renan=int(grupo["renan"].sum()),
            caiado=int(grupo["caiado"].sum()),
            cury=int(grupo["cury"].sum()),
            outros=int(grupo["outros"].sum()),
            brancos=int(grupo["brancos"].sum()),
            nulos=int(grupo["nulos"].sum()),
            aptos=int(grupo["qt_aptos"].sum()),
            comparecimento=int(grupo["qt_comparecimento"].sum()),
            abstencao=int(grupo["qt_abstencao"].sum()),
            apuradas=int(grupo["apurada"].sum()),
            previstas=int(len(grupo)),
        )

    cidade = fatia(base, nome_cidade)
    bairros = [
        fatia(grupo, str(nome), bairro=str(nome))
        for nome, grupo in sorted(base.groupby("bairro"), key=lambda item: item[0])
    ]
    locais_grupo = [
        fatia(grupo, str(local), bairro=str(bairro), local=str(local))
        for (bairro, local), grupo in sorted(base.groupby(["bairro", "local_votacao"]), key=lambda item: item[0])
    ]
    pendencias = (
        base.loc[~base["apurada"], ["bairro", "local_votacao"]]
        .drop_duplicates()
        .sort_values(["bairro", "local_votacao"])
    )
    faltando = [f"{linha.local_votacao} ({linha.bairro})" for linha in pendencias.itertuples(index=False)]

    outros = trabalho.loc[trabalho["balde"].eq("outros")]
    ranking = (
        outros.groupby(["nr_votavel", "nm_votavel"], as_index=False)["qt_votos"].sum().sort_values("qt_votos", ascending=False)
        if not outros.empty
        else pd.DataFrame(columns=["nr_votavel", "nm_votavel", "qt_votos"])
    )
    apelidos = [APELIDOS.get(str(linha.nr_votavel), str(linha.nm_votavel)) for linha in ranking.itertuples(index=False)]
    return cidade, bairros, locais_grupo, apelidos, faltando


def _conferir(cidade: Fatia, bairros: list[Fatia], locais: list[Fatia]) -> None:
    def soma(fatias: list[Fatia], campo: str) -> int:
        return sum(getattr(item, campo) for item in fatias)

    for campo in ("lula", "flavio", "renan", "caiado", "cury", "outros", "brancos", "nulos", "aptos", "comparecimento", "abstencao"):
        if soma(bairros, campo) != getattr(cidade, campo) or soma(locais, campo) != getattr(cidade, campo):
            raise RuntimeError(f"A soma de {campo} não fecha com o total da cidade.")
    if cidade.nominais + cidade.brancos + cidade.nulos != cidade.comparecimento:
        raise RuntimeError("Comparecimento diferente de nominais + brancos + nulos.")
    if cidade.aptos and cidade.comparecimento + cidade.abstencao != cidade.aptos:
        raise RuntimeError("Aptos diferente de comparecimento + abstenção.")


def _estilo(fonte: str, nome: str, tamanho: float, alinhamento: int, negrito: bool = False, cor: str = "#1C1C1C") -> ParagraphStyle:
    return ParagraphStyle(
        nome,
        fontName="Relatorio-Bold" if negrito else fonte,
        fontSize=tamanho,
        leading=tamanho + 2,
        alignment=alinhamento,
        textColor=HexColor(cor),
    )


def _p(texto: str, estilo: ParagraphStyle) -> Paragraph:
    return Paragraph(str(texto), estilo)


def _grafico_geral(cidade: Fatia) -> BytesIO:
    rotulos = ["Lula", "Flávio", "Renan", "Caiado", "Cury", "Outros", "Brancos", "Nulos", "Abstenções"]
    valores = [
        cidade.lula,
        cidade.flavio,
        cidade.renan,
        cidade.caiado,
        cidade.cury,
        cidade.outros,
        cidade.brancos,
        cidade.nulos,
        cidade.abstencao,
    ]
    figura, eixo = plt.subplots(figsize=(6.4, 3.55), dpi=140)
    barras = eixo.bar(rotulos, valores, color=[COR_BARRA[nome] for nome in rotulos], width=0.72)
    eixo.set_title("Resultado geral", loc="right", fontsize=11, pad=8)
    eixo.tick_params(axis="x", labelsize=8)
    eixo.tick_params(axis="y", labelsize=8)
    eixo.spines["top"].set_visible(False)
    eixo.spines["right"].set_visible(False)
    eixo.set_ylim(0, max(valores) * 1.18)
    for barra, valor in zip(barras, valores):
        eixo.text(barra.get_x() + barra.get_width() / 2, barra.get_height() + max(valores) * 0.02, _fmt_int(valor), ha="center", va="bottom", fontsize=7)
    figura.tight_layout()
    buffer = BytesIO()
    figura.savefig(buffer, format="png")
    plt.close(figura)
    buffer.seek(0)
    return buffer


def _grafico_bairros(bairros: list[Fatia]) -> BytesIO:
    nomes = [item.rotulo for item in bairros]
    figura, eixo = plt.subplots(figsize=(11.2, 4.6), dpi=140)
    posicoes = range(len(nomes))
    largura = 0.38
    eixo.bar([indice - largura / 2 for indice in posicoes], [item.lula for item in bairros], width=largura, color=VERMELHO, label="Lula")
    eixo.bar([indice + largura / 2 for indice in posicoes], [item.flavio for item in bairros], width=largura, color=AZUL, label="Flávio")
    eixo.set_xticks(list(posicoes))
    eixo.set_xticklabels(nomes, rotation=70, ha="right", fontsize=8)
    eixo.set_title("Lula x Flávio por bairro", fontsize=13, pad=10)
    eixo.tick_params(axis="y", labelsize=8)
    eixo.spines["top"].set_visible(False)
    eixo.spines["right"].set_visible(False)
    eixo.legend(frameon=False, fontsize=9)
    figura.tight_layout()
    buffer = BytesIO()
    figura.savefig(buffer, format="png")
    plt.close(figura)
    buffer.seek(0)
    return buffer


def _tabela(dados: list[list], colunas: list[float], comandos: list) -> Table:
    tabela = Table(dados, colWidths=colunas, repeatRows=1)
    tabela.setStyle(TableStyle(comandos))
    return tabela


def _comandos_base(fonte_tamanho: float) -> list:
    return [
        ("FONTNAME", (0, 0), (-1, 0), "Relatorio-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Relatorio"),
        ("FONTSIZE", (0, 0), (-1, -1), fonte_tamanho),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(HEADER)),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.2, HexColor("#D5D8DC")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("BACKGROUND", (0, -1), (-1, -1), HexColor("#E5E8E8")),
        ("FONTNAME", (0, -1), (-1, -1), "Relatorio-Bold"),
    ]


def _pintar_colunas(comandos: list, inicio: int, ultima_linha: int) -> None:
    chaves = ("lula", "flavio", "renan", "caiado", "cury", "outros", "brancos", "nulos", "aptos", "abst")
    for deslocamento, chave in enumerate(chaves):
        coluna = inicio + deslocamento
        tinta, cor = TINTA[chave]
        texto = white if chave in {"lula", "flavio", "renan", "caiado", "cury", "outros", "aptos", "abst"} else HexColor("#1C1C1C")
        if chave == "nulos":
            comandos.append(("BACKGROUND", (coluna, 0), (coluna, 0), HexColor(PRETO)))
            comandos.append(("TEXTCOLOR", (coluna, 0), (coluna, 0), white))
        elif chave == "brancos":
            comandos.append(("BACKGROUND", (coluna, 0), (coluna, 0), white))
            comandos.append(("TEXTCOLOR", (coluna, 0), (coluna, 0), HexColor(PRETO)))
        else:
            comandos.append(("BACKGROUND", (coluna, 0), (coluna, 0), HexColor(cor)))
            comandos.append(("TEXTCOLOR", (coluna, 0), (coluna, 0), texto))
        if ultima_linha > 1:
            comandos.append(("BACKGROUND", (coluna, 1), (coluna, ultima_linha - 1), HexColor(tinta)))


def _numeros(fatia: Fatia, nominais_cidade: int | None = None) -> list[str]:
    del nominais_cidade
    return [
        _fmt_int(fatia.lula),
        _fmt_int(fatia.flavio),
        _fmt_int(fatia.renan),
        _fmt_int(fatia.caiado),
        _fmt_int(fatia.cury),
        _fmt_int(fatia.outros),
        _fmt_int(fatia.brancos),
        _fmt_int(fatia.nulos),
        _fmt_int(fatia.aptos),
        _fmt_int(fatia.abstencao),
        _fmt_pct(fatia.abstencao, fatia.aptos),
    ]


def gerar_pdf(
    destino: Path,
    cidade: Fatia,
    bairros: list[Fatia],
    locais: list[Fatia],
    apelidos: list[str],
    faltando: list[str],
    nome_cidade: str = "Três Rios",
) -> None:
    fonte = _fonte()
    titulo = _estilo(fonte, "titulo", 16, TA_LEFT, negrito=True)
    subtitulo = _estilo(fonte, "sub", 8, TA_LEFT, cor="#34495E")
    secao = _estilo(fonte, "secao", 12, TA_LEFT, negrito=True)
    nota = _estilo(fonte, "nota", 7, TA_LEFT, cor="#34495E")
    celula = _estilo(fonte, "celula", 6.5, TA_LEFT)
    destino.parent.mkdir(parents=True, exist_ok=True)

    def rodape(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Relatorio", 8)
        canvas.setFillColor(HexColor("#34495E"))
        canvas.drawString(16 * mm, 8 * mm, "Fonte: dados abertos do TSE")
        canvas.drawRightString(landscape(A4)[0] - 16 * mm, 8 * mm, f"Página {doc.page}")
        canvas.restoreState()

    documento = SimpleDocTemplate(
        str(destino),
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"Eleição presidencial 2026 – 1º turno – {nome_cidade} (RJ)",
    )
    historia: list = []
    historia.append(_p(f"Eleição presidencial 2026 – 1º turno – {nome_cidade} (RJ)", titulo))
    historia.append(Spacer(1, 2 * mm))
    historia.append(
        _p(
            "Resultado por local de votação e por bairro, a partir dos boletins de urna por seção. "
            f"Total: {_fmt_int(cidade.apuradas)} seções apuradas.",
            subtitulo,
        )
    )
    historia.append(Spacer(1, 3 * mm))

    cabecalho_resumo = ["Item", "Votos", "% dos votos nominais", "% do comparecimento"]
    linhas_resumo: list[tuple[str, int, str, str, str]] = []
    for _, chave, _, rotulo in DESTAQUES:
        votos = getattr(cidade, chave)
        linhas_resumo.append((rotulo, votos, _fmt_pct(votos, cidade.nominais), _fmt_pct(votos, cidade.comparecimento), chave))
    linhas_resumo.append(("Outros candidatos", cidade.outros, _fmt_pct(cidade.outros, cidade.nominais), _fmt_pct(cidade.outros, cidade.comparecimento), "outros"))
    linhas_resumo.append(("Brancos", cidade.brancos, "", _fmt_pct(cidade.brancos, cidade.comparecimento), "brancos"))
    linhas_resumo.append(("Nulos", cidade.nulos, "", _fmt_pct(cidade.nulos, cidade.comparecimento), "nulos"))
    linhas_resumo.append(("Abstenções", cidade.abstencao, "", _fmt_pct(cidade.abstencao, cidade.aptos), "abst"))
    linhas_resumo.append(("Eleitores aptos", cidade.aptos, "", "", "aptos"))
    linhas_resumo.append(("Comparecimento", cidade.comparecimento, "", _fmt_pct(cidade.comparecimento, cidade.aptos), "comp"))
    linhas_resumo.append(("Votos nominais", cidade.nominais, "", "", "nom"))

    dados_resumo = [cabecalho_resumo] + [[item[0], _fmt_int(item[1]), item[2], item[3]] for item in linhas_resumo]
    comandos_resumo = [
        ("FONTNAME", (0, 0), (-1, 0), "Relatorio-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Relatorio"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(HEADER)),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, HexColor("#D5D8DC")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for indice, linha in enumerate(linhas_resumo, start=1):
        chave = linha[4]
        if chave in {"lula", "flavio", "renan", "caiado", "cury", "outros"}:
            comandos_resumo.append(("BACKGROUND", (0, indice), (0, indice), HexColor(TINTA[chave][1])))
            comandos_resumo.append(("TEXTCOLOR", (0, indice), (0, indice), white))
        elif chave == "nulos":
            comandos_resumo.append(("BACKGROUND", (0, indice), (0, indice), HexColor(PRETO)))
            comandos_resumo.append(("TEXTCOLOR", (0, indice), (0, indice), white))
        elif chave == "abst":
            comandos_resumo.append(("BACKGROUND", (0, indice), (0, indice), HexColor(AZUL_ABST)))
            comandos_resumo.append(("TEXTCOLOR", (0, indice), (0, indice), white))
        else:
            comandos_resumo.append(("BACKGROUND", (0, indice), (-1, indice), HexColor("#F4F6F7")))
    resumo = Table(dados_resumo, colWidths=[52 * mm, 24 * mm, 38 * mm, 40 * mm])
    resumo.setStyle(TableStyle(comandos_resumo))
    grafico = Image(_grafico_geral(cidade), width=118 * mm, height=65 * mm)
    historia.append(Table([[resumo, grafico]], colWidths=[158 * mm, 118 * mm]))
    historia.append(Spacer(1, 3 * mm))
    historia.append(
        _p(
            "Legenda: vermelho = Lula · azul = Flávio · preto = nulos · branco = brancos · demais cores = outros candidatos. "
            "Abstenção = aptos - comparecimento; comparecimento = votos nominais + brancos + nulos. "
            f"Outros candidatos: {_lista_pt(apelidos)}.",
            nota,
        )
    )

    historia.append(PageBreak())
    historia.append(_p("Resultado por bairro", secao))
    historia.append(Spacer(1, 2 * mm))
    cabecalho_bairro = ["Bairro", "Seções", "Lula", "Flávio", "Renan", "Caiado", "Cury", "Outros", "Brancos", "Nulos", "Aptos", "Abstenções", "% abst."]
    corpo_bairros = [
        [item.rotulo, _fmt_secoes(item.apuradas, item.previstas), *_numeros(item)]
        for item in bairros
    ]
    corpo_bairros.append(["Total", _fmt_secoes(cidade.apuradas, cidade.previstas), *_numeros(cidade)])
    dados_bairros = [cabecalho_bairro] + corpo_bairros
    comandos_bairros = _comandos_base(7)
    _pintar_colunas(comandos_bairros, 2, len(dados_bairros) - 1)
    larguras_bairro = [38 * mm, 16 * mm] + [18 * mm] * 11
    historia.append(_tabela(dados_bairros, larguras_bairro, comandos_bairros))
    historia.append(Spacer(1, 2 * mm))
    texto_falta = ""
    if faltando:
        texto_falta = " Sem boletim nestes locais: " + _lista_pt(faltando) + "."
    historia.append(
        _p(
            "Seções: apuradas (e previstas, quando diferentes)." + texto_falta,
            nota,
        )
    )

    historia.append(PageBreak())
    historia.append(Image(_grafico_bairros(bairros), width=260 * mm, height=150 * mm))

    historia.append(PageBreak())
    historia.append(_p("Resultado por local de votação", secao))
    historia.append(_p("Seç.: seções apuradas e, quando diferentes, previstas.", nota))
    historia.append(Spacer(1, 2 * mm))
    cabecalho_local = ["Local de votação", "Bairro", "Seç.", "Lula", "Flávio", "Renan", "Caiado", "Cury", "Outros", "Brancos", "Nulos", "Aptos", "Abst.", "% abst."]
    miudo = _estilo(fonte, "miudo", 6, TA_LEFT)
    corpo_locais = [
        [
            _p(item.local, miudo),
            _p(item.bairro, miudo),
            _fmt_secoes(item.apuradas, item.previstas),
            *_numeros(item),
        ]
        for item in locais
    ]
    corpo_locais.append(["TOTAL", "", _fmt_secoes(cidade.apuradas, cidade.previstas), *_numeros(cidade)])
    dados_locais = [cabecalho_local] + corpo_locais
    comandos_locais = _comandos_base(6.5)
    _pintar_colunas(comandos_locais, 3, len(dados_locais) - 1)
    larguras_local = [62 * mm, 28 * mm, 12 * mm] + [14.2 * mm] * 11
    historia.append(_tabela(dados_locais, larguras_local, comandos_locais))

    documento.build(historia, onFirstPage=rodape, onLaterPages=rodape)


def gerar(
    destino: Path | None = None,
    banco: Path | None = None,
    municipio: str | None = None,
    nome_cidade: str = "Três Rios",
) -> Path:
    caminho = destino or SAIDA
    from eleicoes.armazenamento import conectar

    conexao = conectar(banco or BANCO)
    try:
        votos, locais, abstencao = carregar(conexao, municipio)
    finally:
        conexao.close()
    if municipio and locais.empty:
        from eleicoes.erros import ErroPipeline

        raise ErroPipeline(f"Não há locais de votação para {nome_cidade} neste banco.")
    cidade, bairros, locais_fatia, apelidos, faltando = montar(votos, locais, abstencao, nome_cidade)
    _conferir(cidade, bairros, locais_fatia)
    gerar_pdf(caminho, cidade, bairros, locais_fatia, apelidos, faltando, nome_cidade)
    return caminho
