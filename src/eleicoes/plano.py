"""PDF de rua: mapa e lista dos locais em que o Flávio teve mais votos que o Lula."""

from __future__ import annotations

import math
import time
import unicodedata
import urllib.request
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Rectangle
import pandas as pd
from PIL import Image as PilImage
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from eleicoes.config import BANCO, PASTA_PROCESSADO
from eleicoes.normalizacao import titulo_pt
from eleicoes.relatorio import (
    AZUL,
    HEADER,
    VERMELHO,
    _estilo,
    _fonte,
    _fmt_int,
    _inteiro,
    carregar,
)

SAIDA = PASTA_PROCESSADO / "plano_panfletagem_tres_rios.pdf"
SAIDA_MAPA = PASTA_PROCESSADO / "mapa_tres_rios.pdf"
PASTA_TILES = PASTA_PROCESSADO / "tiles"
AGENTE = "eleicoes-tres-rios/1.0 (mapa local de campanha em Três Rios)"


@dataclass
class Escola:
    bairro: str
    nome: str
    endereco: str
    latitude: float
    longitude: float
    lula: int
    flavio: int
    ordem: int = 0

    @property
    def diferenca(self) -> int:
        return self.flavio - self.lula


def _endereco_legivel(texto: str) -> str:
    partes = " ".join(str(texto).split()).split(" ")
    if not partes or partes == [""]:
        return ""
    numero = partes.pop() if partes[-1].isdigit() else ""
    nome = titulo_pt(" ".join(partes)).rstrip(" .,;")
    if numero and nome.upper().endswith(" N"):
        nome = nome[:-2].rstrip(" .,;")
        return f"{nome}, nº {numero}"
    if numero:
        return f"{nome}, {numero}"
    return nome


def _mais_comum(valores: pd.Series) -> str:
    limpos = [str(valor).strip() for valor in valores if str(valor).strip() and str(valor).strip().lower() != "nan"]
    if not limpos:
        return ""
    return Counter(limpos).most_common(1)[0][0]


def listar_escolas(votos: pd.DataFrame, locais: pd.DataFrame) -> list[Escola]:
    mapa = {"13": "lula", "22": "flavio"}
    trabalho = votos.copy()
    trabalho["balde"] = [
        mapa.get(str(numero)) if tipo == "nominal" else None
        for tipo, numero in zip(trabalho["tipo"], trabalho["nr_votavel"])
    ]
    trabalho = trabalho.loc[trabalho["balde"].notna()]
    somas = (
        trabalho.groupby(["zona", "secao", "balde"], as_index=False)["qt_votos"]
        .sum()
        .pivot(index=["zona", "secao"], columns="balde", values="qt_votos")
        .reset_index()
    )
    for coluna in ("lula", "flavio"):
        if coluna not in somas.columns:
            somas[coluna] = 0
    base = locais.merge(somas, on=["zona", "secao"], how="left")
    base["lula"] = base["lula"].map(_inteiro)
    base["flavio"] = base["flavio"].map(_inteiro)
    base = base.loc[base["latitude"].notna() & base["longitude"].notna()].copy()

    escolas: list[Escola] = []
    for (bairro, nome), grupo in base.groupby(["bairro", "local_votacao"], sort=False):
        lula = int(grupo["lula"].sum())
        flavio = int(grupo["flavio"].sum())
        if lula == 0 and flavio == 0:
            continue
        escolas.append(
            Escola(
                bairro=str(bairro),
                nome=str(nome),
                endereco=_endereco_legivel(_mais_comum(grupo["endereco"])),
                latitude=float(grupo["latitude"].mean()),
                longitude=float(grupo["longitude"].mean()),
                lula=lula,
                flavio=flavio,
            )
        )
    prioridades = [escola for escola in escolas if escola.flavio > escola.lula]
    prioridades.sort(key=lambda escola: (-escola.diferenca, -escola.flavio, escola.bairro, escola.nome))
    for indice, escola in enumerate(prioridades, start=1):
        escola.ordem = indice
    return escolas



def _recorte_aglomerado(escolas: list[Escola]) -> tuple[float, float, float, float] | None:
    """Caixa da regiao em que as escolas ficam juntas demais no mapa da cidade."""
    if len(escolas) < 6:
        return None
    limite = 0.012
    densas: list[Escola] = []
    for escola in escolas:
        vizinhos = 0
        for outra in escolas:
            if outra is escola:
                continue
            if abs(escola.latitude - outra.latitude) <= limite and abs(escola.longitude - outra.longitude) <= limite:
                vizinhos += 1
        if vizinhos >= 4:
            densas.append(escola)
    if len(densas) < 6:
        return None
    latitudes = [escola.latitude for escola in densas]
    longitudes = [escola.longitude for escola in densas]
    return (
        min(latitudes) - 0.003,
        max(latitudes) + 0.003,
        min(longitudes) - 0.003,
        max(longitudes) + 0.003,
    )


def _dentro(escola: Escola, caixa: tuple[float, float, float, float]) -> bool:
    lat0, lat1, lon0, lon1 = caixa
    return lat0 <= escola.latitude <= lat1 and lon0 <= escola.longitude <= lon1


def _mundo(latitude: float, longitude: float, zoom: int) -> tuple[float, float]:
    tamanho = 2**zoom
    x = (longitude + 180.0) / 360.0 * tamanho
    seno = math.sin(math.radians(latitude))
    seno = min(max(seno, -0.9999), 0.9999)
    y = (0.5 - math.log((1 + seno) / (1 - seno)) / (4 * math.pi)) * tamanho
    return x, y


def _tile(zoom: int, x: int, y: int) -> PilImage.Image:
    PASTA_TILES.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_TILES / f"{zoom}_{x}_{y}.png"
    if not caminho.exists() or caminho.stat().st_size < 100:
        url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
        pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
        try:
            with urllib.request.urlopen(pedido, timeout=25) as resposta:
                caminho.write_bytes(resposta.read())
        except OSError:
            time.sleep(0.4)
            try:
                with urllib.request.urlopen(pedido, timeout=25) as resposta:
                    caminho.write_bytes(resposta.read())
            except OSError:
                return PilImage.new("RGB", (256, 256), "#E5E8E8")
        time.sleep(0.12)
    return PilImage.open(caminho).convert("RGB")


def _escolher_zoom(latitudes: list[float], longitudes: list[float], zooms: tuple[int, ...] = (14, 13, 12), teto: float = 7) -> int:
    for zoom in zooms:
        x0, y0 = _mundo(max(latitudes), min(longitudes), zoom)
        x1, y1 = _mundo(min(latitudes), max(longitudes), zoom)
        if max(abs(x1 - x0), abs(y1 - y0)) <= teto:
            return zoom
    return zooms[-1]


def _imagem_mapa(
    escolas: list[Escola],
    *,
    recorte: tuple[float, float, float, float] | None = None,
    ocultar_numeros: tuple[float, float, float, float] | None = None,
    raio: float = 0.085,
    tamanho_fonte: float = 6,
    zoom_fixo: int | None = None,
    mostrar_nomes: bool = False,
    legenda: bool = True,
    somente: set[int] | None = None,
) -> BytesIO:
    if recorte:
        lat0, lat1, lon0, lon1 = recorte
        latitudes = [lat0, lat1]
        longitudes = [lon0, lon1]
        zoom = zoom_fixo or _escolher_zoom(latitudes, longitudes, zooms=(16, 15, 14), teto=6)
    else:
        latitudes = [escola.latitude for escola in escolas]
        longitudes = [escola.longitude for escola in escolas]
        zoom = zoom_fixo or _escolher_zoom(latitudes, longitudes)
    x0, y_norte = _mundo(max(latitudes), min(longitudes), zoom)
    x1, y_sul = _mundo(min(latitudes), max(longitudes), zoom)
    folga_x = max((x1 - x0) * 0.06, 0.12)
    folga_y = max((y_sul - y_norte) * 0.06, 0.12)
    x0 -= folga_x
    x1 += folga_x
    y_norte -= folga_y
    y_sul += folga_y
    tile_x0, tile_x1 = math.floor(x0), math.floor(x1)
    tile_y0, tile_y1 = math.floor(y_norte), math.floor(y_sul)
    largura = (tile_x1 - tile_x0 + 1) * 256
    altura = (tile_y1 - tile_y0 + 1) * 256
    mosaico = PilImage.new("RGB", (largura, altura), "#F4F6F7")
    for tile_x in range(tile_x0, tile_x1 + 1):
        for tile_y in range(tile_y0, tile_y1 + 1):
            imagem = _tile(zoom, tile_x, tile_y)
            mosaico.paste(imagem, ((tile_x - tile_x0) * 256, (tile_y - tile_y0) * 256))

    figura, eixo = plt.subplots(figsize=(11.6, 7.2), dpi=160)
    eixo.imshow(mosaico, extent=(tile_x0, tile_x1 + 1, tile_y1 + 1, tile_y0), origin="upper", zorder=0)
    eixo.set_xlim(x0, x1)
    eixo.set_ylim(y_sul, y_norte)
    eixo.set_aspect("equal")

    if mostrar_nomes:
        raio = max(x1 - x0, y_sul - y_norte) * 0.014
        tamanho_fonte = 8

    def ponto(escola: Escola) -> tuple[float, float]:
        return _mundo(escola.latitude, escola.longitude, zoom)

    def entra(escola: Escola) -> bool:
        if recorte and not _dentro(escola, recorte):
            return False
        if somente is not None and escola.ordem and escola.ordem not in somente:
            return False
        return True

    if ocultar_numeros:
        lat_a, lat_b, lon_a, lon_b = ocultar_numeros
        x_w, y_n = _mundo(lat_b, lon_a, zoom)
        x_e, y_s = _mundo(lat_a, lon_b, zoom)
        rx0, rx1 = min(x_w, x_e), max(x_w, x_e)
        ry0, ry1 = min(y_n, y_s), max(y_n, y_s)
        eixo.add_patch(
            Rectangle(
                (rx0, ry0),
                rx1 - rx0,
                ry1 - ry0,
                fill=False,
                edgecolor=AZUL,
                linewidth=1.3,
                linestyle="--",
                zorder=6,
            )
        )
        eixo.text(
            rx0,
            ry0,
            "  nesta área, veja o mapa seguinte",
            color=AZUL,
            fontsize=8,
            ha="left",
            va="bottom",
            fontweight="bold",
            zorder=7,
        )

    for escola in escolas:
        if escola.ordem or not entra(escola):
            continue
        x, y = ponto(escola)
        eixo.add_patch(Circle((x, y), raio * 0.62, facecolor=VERMELHO, edgecolor="white", linewidth=0.6, zorder=2))

    prioridades = [escola for escola in escolas if escola.ordem and entra(escola)]
    ocupados: list[tuple[float, float]] = []
    caixas: list[tuple[float, float, float, float]] = []
    separacao = raio * 2.35
    polegada = (x1 - x0) / 11.6

    def cabe(cx: float, cy: float, largura_caixa: float, altura_caixa: float) -> bool:
        if cx < x0 or cx + largura_caixa > x1 or cy - altura_caixa / 2 < y_norte or cy + altura_caixa / 2 > y_sul:
            return False
        for ox, oy, ow, oh in caixas:
            if cx < ox + ow and cx + largura_caixa > ox and cy - altura_caixa / 2 < oy + oh / 2 and cy + altura_caixa / 2 > oy - oh / 2:
                return False
        for ox, oy in ocupados:
            if (cx - ox) ** 2 + (cy - oy) ** 2 < (separacao * 0.9) ** 2:
                return False
            if (cx + largura_caixa - ox) ** 2 + (cy - oy) ** 2 < (separacao * 0.9) ** 2:
                return False
        return True

    for escola in prioridades:
        x, y = ponto(escola)
        if ocultar_numeros and _dentro(escola, ocultar_numeros):
            eixo.add_patch(Circle((x, y), raio * 0.55, facecolor=AZUL, edgecolor="white", linewidth=0.6, zorder=3))
            continue
        nx, ny = x, y
        escolhido = False
        for anel in range(0, 7):
            if anel == 0:
                candidatos = [(x, y)]
            else:
                distancia = separacao * anel * 0.52
                candidatos = [
                    (x + distancia * math.cos(passo), y + distancia * math.sin(passo))
                    for passo in (indice * math.pi / 6 for indice in range(12))
                ]
            for candidato in candidatos:
                if all((candidato[0] - ox) ** 2 + (candidato[1] - oy) ** 2 > separacao**2 for ox, oy in ocupados):
                    nx, ny = candidato
                    escolhido = True
                    break
            if escolhido:
                break
        ocupados.append((nx, ny))
        if (nx, ny) != (x, y):
            eixo.plot([x, nx], [y, ny], color=AZUL, linewidth=0.7, zorder=3)
            eixo.add_patch(Circle((x, y), raio * 0.28, facecolor=AZUL, edgecolor="white", linewidth=0.4, zorder=4))
        eixo.add_patch(Circle((nx, ny), raio, facecolor=AZUL, edgecolor="white", linewidth=0.8, zorder=4))
        eixo.text(
            nx,
            ny,
            str(escola.ordem),
            color="white",
            fontsize=tamanho_fonte,
            ha="center",
            va="center",
            fontweight="bold",
            zorder=5,
        )
        if not mostrar_nomes:
            continue
        rotulo = _nome_curto(escola.nome)
        char = (7.2 / 72) * 0.5 * polegada
        largura_caixa = char * len(rotulo) + 0.06 * polegada
        altura_caixa = (7.2 / 72) * 1.7 * polegada
        lugar = None
        for anel in range(1, 8):
            distancia = raio * (1.35 + anel * 0.85)
            opcoes = []
            for passo in (indice * math.pi / 6 for indice in range(12)):
                cx = nx + distancia * math.cos(passo)
                cy = ny - distancia * math.sin(passo)
                if math.cos(passo) < -0.25:
                    cx -= largura_caixa
                elif abs(math.cos(passo)) <= 0.25:
                    cx -= largura_caixa / 2
                opcoes.append((cx, cy))
            for cx, cy in opcoes:
                if cabe(cx, cy, largura_caixa, altura_caixa):
                    lugar = (cx, cy)
                    break
            if lugar:
                break
        if lugar is None:
            lugar = (nx + raio * 1.4, ny)
        cx, cy = lugar
        caixas.append((cx, cy, largura_caixa, altura_caixa))
        if math.hypot((cx + largura_caixa / 2) - nx, cy - ny) > raio * 2.2:
            eixo.plot([nx, cx], [ny, cy], color="#1A5276", linewidth=0.45, zorder=5)
        eixo.text(
            cx,
            cy,
            rotulo,
            color="#1B2631",
            fontsize=7.2,
            ha="left",
            va="center",
            zorder=6,
            bbox={"boxstyle": "round,pad=0.18", "fc": "white", "ec": "#1A5276", "lw": 0.4, "alpha": 0.94},
        )

    eixo.set_axis_off()
    if legenda:
        eixo.legend(
            handles=[
                Line2D([0], [0], marker="o", color="none", markerfacecolor=AZUL, markeredgecolor="white", markersize=9, label="Azul: Flávio teve mais votos. Comece por aqui."),
                Line2D([0], [0], marker="o", color="none", markerfacecolor=VERMELHO, markeredgecolor="white", markersize=9, label="Vermelho: Lula teve mais votos."),
            ],
            loc="lower left",
            frameon=True,
            fontsize=8,
        )
    figura.tight_layout(pad=0.15)
    buffer = BytesIO()
    figura.savefig(buffer, format="png")
    plt.close(figura)
    buffer.seek(0)
    return buffer



def _linhas_tabela(escolas: list[Escola], miudo: Paragraph) -> list[list]:
    linhas = [["N.", "Bairro", "Escola", "Endereço", "Votos do Flávio", "Votos do Lula", "Flávio a mais"]]
    for escola in escolas:
        linhas.append(
            [
                str(escola.ordem),
                Paragraph(escola.bairro, miudo),
                Paragraph(escola.nome, miudo),
                Paragraph(escola.endereco, miudo),
                _fmt_int(escola.flavio),
                _fmt_int(escola.lula),
                _fmt_int(escola.diferenca),
            ]
        )
    return linhas


def gerar_pdf(destino: Path, escolas: list[Escola], cidade: str = "Três Rios") -> None:
    fonte = _fonte()
    titulo = _estilo(fonte, "titulo-plano", 16, TA_LEFT, negrito=True)
    secao = _estilo(fonte, "secao-plano", 13, TA_LEFT, negrito=True)
    texto = _estilo(fonte, "texto-plano", 10, TA_LEFT)
    nota = _estilo(fonte, "nota-plano", 8, TA_LEFT, cor="#34495E")
    miudo = _estilo(fonte, "miudo-plano", 7.5, TA_LEFT)
    prioridades = sorted((escola for escola in escolas if escola.ordem), key=lambda escola: escola.ordem)
    outras = [escola for escola in escolas if not escola.ordem]

    def rodape(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Relatorio", 8)
        canvas.setFillColor(HexColor("#34495E"))
        canvas.drawString(14 * mm, 8 * mm, "Fonte: dados abertos do TSE. O ponto é a escola, não a casa do eleitor.")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm, f"Página {doc.page}")
        canvas.restoreState()

    documento = SimpleDocTemplate(
        str(destino),
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"Onde panfletar e conversar em {cidade}",
    )
    historia: list = []
    historia.append(Paragraph(f"Onde panfletar e conversar em {cidade}", titulo))
    historia.append(Spacer(1, 1.5 * mm))
    historia.append(Paragraph("Presidente 2026, 1º turno. Escolas em que o Flávio teve mais votos que o Lula.", nota))
    historia.append(Spacer(1, 3 * mm))
    historia.append(
        Paragraph(
            f"Há {len(prioridades)} escolas azuis. Nelas, o Flávio ficou na frente. "
            f"Há {len(outras)} escolas vermelhas. Nelas, o Lula ficou na frente, e esta rodada não começa por elas.",
            texto,
        )
    )
    historia.append(Spacer(1, 2 * mm))
    historia.append(Paragraph("Como usar este papel", secao))
    historia.append(Spacer(1, 1.5 * mm))
    for frase in (
        "1. Olhe o mapa. Cada número azul é uma escola. O número 1 é o primeiro lugar da lista.",
        "2. No dia da rua, siga a ordem. O endereço de cada escola está na tabela.",
        "3. A panfletagem e a conversa são na escola e nas ruas do bairro em volta.",
        "4. A conta da ordem é simples: votos do Flávio menos votos do Lula. Quem tem a maior diferença vem primeiro.",
    ):
        historia.append(Paragraph(frase, texto))
        historia.append(Spacer(1, 1 * mm))

    historia.append(Spacer(1, 2 * mm))
    historia.append(Paragraph("Comece por estes lugares", secao))
    historia.append(Spacer(1, 1.5 * mm))
    historia.append(_tabela_escolas(prioridades[:8], miudo))

    recorte = _recorte_aglomerado(escolas)
    historia.append(PageBreak())
    historia.append(Paragraph("Mapa das escolas", secao))
    legenda_mapa = "Número azul: ordem da lista. Ponto vermelho: Lula teve mais votos."
    if recorte:
        legenda_mapa += " Onde os números se juntam, o mapa seguinte abre essa parte."
    historia.append(Paragraph(legenda_mapa, nota))
    historia.append(Spacer(1, 2 * mm))
    historia.append(Image(_imagem_mapa(escolas, ocultar_numeros=recorte), width=268 * mm, height=158 * mm))
    if recorte:
        historia.append(PageBreak())
        historia.append(Paragraph("O centro, mais de perto", secao))
        historia.append(Paragraph("Os números são os mesmos da lista. Comece pelo menor.", nota))
        historia.append(Spacer(1, 2 * mm))
        historia.append(Image(_imagem_mapa(escolas, recorte=recorte, raio=0.09, tamanho_fonte=7), width=268 * mm, height=158 * mm))

    historia.append(PageBreak())
    historia.append(Paragraph("Lista completa, na ordem de ir", secao))
    historia.append(Paragraph("O número é o mesmo do mapa. Flávio a mais = votos do Flávio menos votos do Lula.", nota))
    historia.append(Spacer(1, 2 * mm))
    historia.append(_tabela_escolas(prioridades, miudo))

    historia.append(PageBreak())
    historia.append(Paragraph("Roteiro por bairro", secao))
    historia.append(
        Paragraph(
            "Cada equipe fica em um bairro. Dentro do bairro, comece pelo número menor. Esse número é o do mapa.",
            nota,
        )
    )
    historia.append(Spacer(1, 2 * mm))
    bairros = sorted({escola.bairro for escola in prioridades}, key=lambda nome: -sum(item.diferenca for item in prioridades if item.bairro == nome))
    for bairro in bairros:
        do_bairro = [escola for escola in prioridades if escola.bairro == bairro]
        do_bairro.sort(key=lambda escola: escola.ordem)
        diferenca = sum(escola.diferenca for escola in do_bairro)
        bloco = [
            Paragraph(
                f"<b>{bairro}</b> — {_fmt_int(diferenca)} votos a mais para o Flávio nestas escolas.",
                texto,
            ),
            Spacer(1, 1 * mm),
            _tabela_escolas(do_bairro, miudo),
            Spacer(1, 3 * mm),
        ]
        historia.append(KeepTogether(bloco))

    destino.parent.mkdir(parents=True, exist_ok=True)
    documento.build(historia, onFirstPage=rodape, onLaterPages=rodape)


def _tabela_escolas(escolas: list[Escola], miudo) -> Table:
    dados = _linhas_tabela(escolas, miudo)
    tabela = Table(
        dados,
        colWidths=[12 * mm, 32 * mm, 78 * mm, 72 * mm, 28 * mm, 26 * mm, 28 * mm],
        repeatRows=1,
    )
    tabela.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Relatorio-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Relatorio"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor(HEADER)),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("BACKGROUND", (0, 1), (0, -1), HexColor(AZUL)),
                ("TEXTCOLOR", (0, 1), (0, -1), white),
                ("BACKGROUND", (4, 1), (4, -1), HexColor("#D6E6F5")),
                ("BACKGROUND", (5, 1), (5, -1), HexColor("#F8D7D3")),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.2, HexColor("#D5D8DC")),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("FONTNAME", (0, 1), (0, -1), "Relatorio-Bold"),
            ]
        )
    )
    return tabela



def _sem_acento(valor: str) -> str:
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", valor)
        if unicodedata.category(caractere) != "Mn"
    )


def _nome_curto(nome: str) -> str:
    bruto = " ".join(nome.split())
    chave = _sem_acento(bruto).lower()
    prefixos = (
        "escola estadual municipalizada ",
        "escola municipal ",
        "colegio municipal ",
        "colegio estadual ",
        "colegio ",
        "instituto de educacao professor ",
        "instituto de educacao ",
        "unidade saude da familia - ",
        "unidade saude da familia ",
        "centro educacional ",
        "creche municipal ",
        "posto de saude ",
        "jardim de infancia municipal ",
        "universidade federal rural do rio de janeiro - ",
        "igreja batista do ",
        "igreja batista ",
        "igreja ",
    )
    for prefixo in prefixos:
        if chave.startswith(prefixo):
            bruto = bruto[len(prefixo):].strip(" -")
            chave = _sem_acento(bruto).lower()
            break
    if " - " in bruto:
        esquerda = bruto.split(" - ", 1)[0].strip()
        if len(esquerda) >= 4:
            bruto = esquerda
    if len(bruto) > 28:
        bruto = bruto[:27].rstrip() + "."
    return bruto


def _latlon(x: float, y: float, zoom: int) -> tuple[float, float]:
    tamanho = 2**zoom
    longitude = x / tamanho * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * y / tamanho
    latitude = math.degrees(math.atan(math.sinh(n)))
    return latitude, longitude


@dataclass
class Folha:
    titulo: str
    zoom: int
    recorte: tuple[float, float, float, float]
    foco: set[int]


def _titulo_folha(grupo: list[Escola]) -> str:
    contagem = Counter(escola.bairro for escola in grupo)
    nomes = [nome for nome, _ in sorted(contagem.items(), key=lambda item: (-item[1], item[0]))]
    return ", ".join(nomes[:3])


def _recorte_grupo(grupo: list[Escola], zoom: int) -> tuple[float, float, float, float]:
    xs = [_mundo(escola.latitude, escola.longitude, zoom)[0] for escola in grupo]
    ys = [_mundo(escola.latitude, escola.longitude, zoom)[1] for escola in grupo]
    margem = 0.7
    meia_x = max((max(xs) - min(xs) + 2 * margem) / 2, 1.85)
    meia_y = max((max(ys) - min(ys) + 2 * margem) / 2, 1.35)
    centro_x = (min(xs) + max(xs)) / 2
    centro_y = (min(ys) + max(ys)) / 2
    lat_norte, lon_oeste = _latlon(centro_x - meia_x, centro_y - meia_y, zoom)
    lat_sul, lon_leste = _latlon(centro_x + meia_x, centro_y + meia_y, zoom)
    return (min(lat_sul, lat_norte), max(lat_sul, lat_norte), min(lon_oeste, lon_leste), max(lon_oeste, lon_leste))


def _agrupar(escolas: list[Escola], max_x: float, max_y: float, max_n: int) -> list[list[Escola]]:
    grupos = [[escola] for escola in escolas]

    def caixa(grupo: list[Escola]) -> tuple[float, float]:
        xs = [_mundo(escola.latitude, escola.longitude, 16)[0] for escola in grupo]
        ys = [_mundo(escola.latitude, escola.longitude, 16)[1] for escola in grupo]
        return max(xs) - min(xs), max(ys) - min(ys)

    def centro(grupo: list[Escola]) -> tuple[float, float]:
        xs = [_mundo(escola.latitude, escola.longitude, 16)[0] for escola in grupo]
        ys = [_mundo(escola.latitude, escola.longitude, 16)[1] for escola in grupo]
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    mudou = True
    while mudou:
        mudou = False
        melhor: tuple[int, int] | None = None
        melhor_distancia = 1e9
        for i in range(len(grupos)):
            for j in range(i + 1, len(grupos)):
                junto = grupos[i] + grupos[j]
                if len(junto) > max_n:
                    continue
                dx, dy = caixa(junto)
                if dx > max_x or dy > max_y:
                    continue
                ax, ay = centro(grupos[i])
                bx, by = centro(grupos[j])
                distancia = math.hypot(ax - bx, ay - by)
                if distancia < melhor_distancia:
                    melhor_distancia = distancia
                    melhor = (i, j)
        if melhor:
            i, j = melhor
            grupos[i] = grupos[i] + grupos[j]
            del grupos[j]
            mudou = True
    return grupos


def _folhas_mapa(escolas: list[Escola]) -> list[Folha]:
    azuis = [escola for escola in escolas if escola.ordem]
    # Cada folha cabe numa página A4 com nome de rua legível: no máximo
    # ~4,6 x 3,2 tiles no zoom 16, e no máximo 12 escolas.
    grupos = _agrupar(azuis, 4.6, 3.2, 12)
    folhas: list[Folha] = []
    for grupo in grupos:
        if not grupo:
            continue
        dx, dy = 0.0, 0.0
        if len(grupo) > 1:
            xs = [_mundo(escola.latitude, escola.longitude, 16)[0] for escola in grupo]
            ys = [_mundo(escola.latitude, escola.longitude, 16)[1] for escola in grupo]
            dx, dy = max(xs) - min(xs), max(ys) - min(ys)
        zoom = 17 if len(grupo) >= 6 and dx <= 2.3 and dy <= 1.6 else 16
        folhas.append(
            Folha(
                titulo=_titulo_folha(grupo),
                zoom=zoom,
                recorte=_recorte_grupo(grupo, zoom),
                foco={escola.ordem for escola in grupo},
            )
        )
    folhas.sort(key=lambda folha: min(folha.foco))
    return folhas


def gerar_mapa_pdf(destino: Path, escolas: list[Escola], cidade: str = "Três Rios") -> None:
    fonte = _fonte()
    titulo = _estilo(fonte, "titulo-mapa", 13, TA_LEFT, negrito=True)
    nota = _estilo(fonte, "nota-mapa", 8, TA_LEFT, cor="#34495E")
    folhas = _folhas_mapa(escolas)

    def rodape(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Relatorio", 8)
        canvas.setFillColor(HexColor("#34495E"))
        canvas.drawString(8 * mm, 5.5 * mm, "Fonte: dados abertos do TSE. O ponto é a escola.")
        canvas.drawRightString(landscape(A4)[0] - 8 * mm, 5.5 * mm, f"Página {doc.page}")
        canvas.restoreState()

    documento = SimpleDocTemplate(
        str(destino),
        pagesize=landscape(A4),
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=7 * mm,
        bottomMargin=10 * mm,
        title=f"Mapa de {cidade}",
    )
    historia: list = []
    for indice, folha in enumerate(folhas):
        if indice:
            historia.append(PageBreak())
        historia.append(Paragraph(folha.titulo, titulo))
        historia.append(
            Paragraph(
                f"{cidade}. Número azul: comece pelo menor. Azul, o Flávio ficou na frente. Vermelho, o Lula ficou na frente.",
                nota,
            )
        )
        historia.append(Spacer(1, 1.2 * mm))
        historia.append(
            Image(
                _imagem_mapa(
                    escolas,
                    recorte=folha.recorte,
                    zoom_fixo=folha.zoom,
                    mostrar_nomes=True,
                    legenda=False,
                    somente=folha.foco,
                ),
                width=281 * mm,
                height=172 * mm,
            )
        )
    destino.parent.mkdir(parents=True, exist_ok=True)
    documento.build(historia, onFirstPage=rodape, onLaterPages=rodape)


def _locais_da_cidade(conexao, municipio: str | None) -> pd.DataFrame:
    locais = pd.read_sql_query(
        "SELECT zona, secao, bairro, local_votacao, endereco, latitude, longitude FROM locais"
        + (" WHERE municipio = ?" if municipio else ""),
        conexao,
        params=(municipio,) if municipio else None,
    )
    locais["zona"] = locais["zona"].astype(str)
    locais["secao"] = locais["secao"].astype(str)
    return locais


def gerar_mapa(
    destino: Path | None = None,
    banco: Path | None = None,
    municipio: str | None = None,
    cidade: str = "Três Rios",
) -> Path:
    from eleicoes.armazenamento import conectar

    caminho = destino or SAIDA_MAPA
    conexao = conectar(banco or BANCO)
    try:
        votos, _locais, _abstencao = carregar(conexao, municipio)
        locais = _locais_da_cidade(conexao, municipio)
    finally:
        conexao.close()
    escolas = listar_escolas(votos, locais)
    gerar_mapa_pdf(caminho, escolas, cidade)
    return caminho


def gerar(
    destino: Path | None = None,
    banco: Path | None = None,
    municipio: str | None = None,
    cidade: str = "Três Rios",
) -> Path:
    from eleicoes.armazenamento import conectar

    caminho = destino or SAIDA
    conexao = conectar(banco or BANCO)
    try:
        votos, _locais, _abstencao = carregar(conexao, municipio)
        locais = _locais_da_cidade(conexao, municipio)
    finally:
        conexao.close()
    escolas = listar_escolas(votos, locais)
    gerar_pdf(caminho, escolas, cidade)
    return caminho
