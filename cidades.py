"""Página para baixar os PDFs de uma cidade do Rio de Janeiro.

No Streamlit Community Cloud, o Main file path é este arquivo: cidades.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

import streamlit as st

from eleicoes.erros import ErroPipeline
from gerar import BANCO_ESTADO, gerar_pdfs, listar_cidades

st.set_page_config(
    page_title="PDFs das cidades",
    page_icon="🗳️",
    layout="centered",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 640px; }
    h1 { letter-spacing: -0.03em; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def _cidades() -> list[str]:
    return listar_cidades()


@st.cache_data(show_spinner=False)
def _pdfs(cidade: str) -> list[tuple[str, str, bytes]]:
    return gerar_pdfs(cidade)


def main() -> None:
    st.title("PDFs da eleição")
    st.caption("Presidente 2026, primeiro turno. Cidades do Rio de Janeiro.")

    if not BANCO_ESTADO.exists():
        st.error("Os dados da eleição ainda não estão nesta pasta. Peça o arquivo rio.db para quem montou o site.")
        return

    cidades = _cidades()
    if not cidades:
        st.error("Não há cidades nos dados da eleição.")
        return

    cidade = st.selectbox("Cidade", cidades, index=None, placeholder="Escolha a cidade")
    gerar = st.button("Gerar os PDFs", type="primary", disabled=cidade is None, use_container_width=True)

    if gerar and cidade:
        st.session_state["cidade_pronta"] = cidade

    pronta = st.session_state.get("cidade_pronta")
    if not pronta:
        st.info("Escolha a cidade e toque em Gerar os PDFs. A primeira vez pode levar alguns minutos.")
        return

    try:
        with st.spinner(f"Gerando os PDFs de {pronta}. Pode levar alguns minutos."):
            arquivos = _pdfs(pronta)
    except ErroPipeline as exc:
        st.error(str(exc))
        return

    st.success(f"Os PDFs de {pronta} estão prontos. Toque em cada botão para baixar.")
    for rotulo, nome, conteudo in arquivos:
        st.download_button(
            f"Baixar {rotulo.lower()}",
            data=conteudo,
            file_name=nome,
            mime="application/pdf",
            use_container_width=True,
            key=f"baixar-{pronta}-{nome}",
        )


main()
