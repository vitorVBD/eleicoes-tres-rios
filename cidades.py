"""Página para baixar os PDFs de uma cidade do Rio de Janeiro.

No Streamlit Community Cloud, o Main file path deste arquivo é cidades.py.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

import streamlit as st

from eleicoes.erros import ErroPipeline
from gerar import BANCO_ESTADO, gerar_pdfs, listar_cidades

PASTA_IMAGENS = RAIZ / "assets" / "images"
TEMA = (RAIZ / "assets" / "tema.css").read_text(encoding="utf-8")

st.set_page_config(
    page_title="PDFs das cidades",
    page_icon="🗳️",
    layout="centered",
)

st.markdown(f"<style>{TEMA}</style>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _cidades() -> list[str]:
    return listar_cidades()


@st.cache_data(show_spinner=False)
def _pdfs(cidade: str) -> list[tuple[str, str, bytes]]:
    return gerar_pdfs(cidade)


_URI: dict[str, str] = {}


def _imagem(nome: str) -> str:
    if nome not in _URI:
        bruto = (PASTA_IMAGENS / nome).read_bytes()
        tipo = {
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(Path(nome).suffix.lower(), "application/octet-stream")
        _URI[nome] = f"data:{tipo};base64," + base64.b64encode(bruto).decode("ascii")
    return _URI[nome]


def _hero() -> None:
    foto = _imagem("imgi_3_55579039708_1ddd62bfc5_k.jpg")
    logo = _imagem("imgi_1_lula-logo-completo.svg")
    st.markdown(
        f"""
        <header class="hero">
            <img class="hero-foto" src="{foto}" alt="Ato popular com cartazes e bandeiras">
            <div class="hero-velo"></div>
            <img class="hero-logo" src="{logo}" alt="Lula Presidente">
        </header>
        """,
        unsafe_allow_html=True,
    )


def _selos() -> None:
    comite = _imagem("imgi_5_selo-comite-popular.webp")
    censura = _imagem("imgi_6_selo-censura-digital.webp")
    st.markdown(
        f"""
        <section class="parceiros">
            <p>Conheça também</p>
            <div class="selos">
                <a href="https://comitepopular.org.br/" target="_blank" rel="noopener noreferrer">
                    <img src="{comite}" alt="Comitê Popular de Luta">
                </a>
                <a href="https://censuradigital.lula.com.br/" target="_blank" rel="noopener noreferrer">
                    <img src="{censura}" alt="Censura Digital. Denuncie.">
                </a>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    _hero()
    st.title("PDFs da eleição")
    st.markdown('<div class="marca"></div>', unsafe_allow_html=True)
    st.caption("Presidente 2026, primeiro turno. Cidades do Rio de Janeiro.")

    if not BANCO_ESTADO.exists():
        st.error("Os dados da eleição ainda não estão nesta pasta. Peça o arquivo rio.db para quem montou o site.")
        _selos()
        return

    cidades = _cidades()
    if not cidades:
        st.error("Não há cidades nos dados da eleição.")
        _selos()
        return

    cidade = st.selectbox("Cidade", cidades, index=None, placeholder="Escolha a cidade")
    gerar = st.button("Gerar os PDFs", type="primary", disabled=cidade is None, use_container_width=True)

    if gerar and cidade:
        st.session_state["cidade_pronta"] = cidade

    pronta = st.session_state.get("cidade_pronta")
    if not pronta:
        st.info("Escolha a cidade e toque em Gerar os PDFs. A primeira vez pode levar alguns minutos.")
        _selos()
        return

    try:
        with st.spinner(f"Gerando os PDFs de {pronta}. Pode levar alguns minutos."):
            arquivos = _pdfs(pronta)
    except ErroPipeline as exc:
        st.error(str(exc))
        _selos()
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
    _selos()


main()
