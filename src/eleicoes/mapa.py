"""Mapa dos locais de votação. A cor é o candidato mais votado naquele local."""

from __future__ import annotations

import math

import folium
import pandas as pd

from eleicoes.config import CENTRO_MAPA
from eleicoes.cores import cor_de
from eleicoes.formatacao import fmt_int, fmt_pct, fmt_pp


def criar_mapa(locais: pd.DataFrame, cores: dict[str, str]) -> folium.Map | None:
    if locais.empty or locais["latitude"].notna().sum() == 0:
        return None

    pontos = locais.loc[locais["latitude"].notna() & locais["longitude"].notna()].copy()
    lat_min = float(pontos["latitude"].min())
    lat_max = float(pontos["latitude"].max())
    lon_min = float(pontos["longitude"].min())
    lon_max = float(pontos["longitude"].max())
    centro = (float(pontos["latitude"].mean()), float(pontos["longitude"].mean()))
    # OpenStreetMap não exige chave. O fundo claro do CartoDB passou a pedir API key.
    mapa = folium.Map(location=centro or CENTRO_MAPA, zoom_start=13, tiles="OpenStreetMap", control_scale=True)

    maior = max(int(pontos["votos_validos"].max() or 0), 1)
    grupos: dict[str, folium.FeatureGroup] = {}
    for linha in pontos.itertuples(index=False):
        lider = _texto(getattr(linha, "lider_disputa", ""))
        if lider:
            chave = lider
            nome_a = _texto(getattr(linha, "candidato_a", ""))
            nome_b = _texto(getattr(linha, "candidato_b", ""))
            votos = ""
            if nome_a:
                votos += f"{nome_a}: {fmt_int(getattr(linha, 'votos_a', None))}<br>"
            if nome_b:
                votos += f"{nome_b}: {fmt_int(getattr(linha, 'votos_b', None))}<br>"
            cabecalho = (
                f"Na frente: {lider}<br>"
                f"{votos}"
                f"Margem da disputa: {fmt_pp(getattr(linha, 'margem_disputa_pp', None))}<br>"
                f"Votos de outros candidatos: {fmt_int(getattr(linha, 'votos_outros', None))}<br>"
            )
        else:
            chave = "Empate" if linha.empate else linha.vencedor
            cabecalho = (
                f"{'Empate' if linha.empate else linha.vencedor}<br>"
                f"{fmt_pct(linha.percentual_vencedor)} dos votos válidos<br>"
            )
        if chave not in grupos:
            grupos[chave] = folium.FeatureGroup(name=chave, show=True)
        cor = cor_de(chave, cores)
        tem_comparecimento = _positivo(linha.comparecimento)
        votantes = linha.comparecimento if tem_comparecimento else linha.votos_computados
        rotulo_votantes = "Votantes" if tem_comparecimento else "Votos no local"
        html = (
            f"<b>{linha.bairro}</b><br>"
            f"{linha.local_votacao}<br>"
            f"{cabecalho}"
            f"{rotulo_votantes}: {fmt_int(votantes)}"
        )
        folium.CircleMarker(
            location=[linha.latitude, linha.longitude],
            radius=_raio(int(linha.votos_validos), maior),
            color=cor,
            weight=1,
            fill=True,
            fill_color=cor,
            fill_opacity=0.88,
            tooltip=folium.Tooltip(html, sticky=True),
            popup=folium.Popup(html, max_width=280),
        ).add_to(grupos[chave])

    for grupo in grupos.values():
        grupo.add_to(mapa)
    folium.LayerControl(collapsed=True).add_to(mapa)

    mapa.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]], padding=(24, 24), max_zoom=15)
    return mapa


def _texto(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and math.isnan(valor):
        return ""
    texto = str(valor).strip()
    if texto in {"", "nan", "<NA>", "None"}:
        return ""
    return texto


def _positivo(valor) -> bool:
    if valor is None:
        return False
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return False
    return not math.isnan(numero) and numero > 0


def _raio(votos: int, maior: int) -> float:
    if maior <= 0:
        return 8
    return 7 + 11 * math.sqrt(max(votos, 0) / maior)
