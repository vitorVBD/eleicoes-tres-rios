"""Gráfico de barras dos votos nominais de um bairro."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from eleicoes.cores import cor_de
from eleicoes.formatacao import fmt_int, fmt_pct


def grafico_nominais(candidatos: pd.DataFrame, cores: dict[str, str], limite: int = 12) -> go.Figure | None:
    nominais = candidatos.loc[candidatos["tipo"].eq("nominal")].sort_values("votos", ascending=False)
    if nominais.empty:
        return None
    visiveis = nominais.head(limite).iloc[::-1]
    figura = go.Figure(
        go.Bar(
            x=visiveis["votos"],
            y=visiveis["candidato"],
            orientation="h",
            marker_color=[cor_de(nome, cores) for nome in visiveis["candidato"]],
            text=[f"{fmt_int(votos)} · {fmt_pct(pct)}" for votos, pct in zip(visiveis["votos"], visiveis["percentual"])],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:,} votos<extra></extra>",
            cliponaxis=False,
        )
    )
    figura.update_layout(
        margin=dict(l=8, r=90, t=8, b=8),
        height=max(280, 46 * len(visiveis)),
        xaxis_title="Votos nominais",
        yaxis_title="",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Source Sans 3, Segoe UI, sans-serif", color="#1B2430", size=13),
        xaxis=dict(gridcolor="#E7E1D6", zeroline=False),
    )
    return figura
