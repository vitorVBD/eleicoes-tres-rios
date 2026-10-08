"""Painel local de votos por bairro em Três Rios (RJ)."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from eleicoes.armazenamento import conectar, ler_meta
from eleicoes.config import ANO_ELEICAO, BANCO, CARGO_ELEICAO, LIMIAR_PRIORITARIO, PASTA_RAW
from eleicoes.consultas import montar_painel, ordenar_cargos
from eleicoes.cores import mapa_cores
from eleicoes.erros import ErroPipeline
from eleicoes.etl import executar_pipeline
from eleicoes.exportacao import gerar_csv, gerar_excel
from eleicoes.formatacao import fmt_int, fmt_pct, fmt_pp, fmt_turno
from eleicoes.graficos import grafico_nominais
from eleicoes.mapa import criar_mapa
from eleicoes.normalizacao import chave_texto, titulo_pt

CSS = """
<style>
.block-container { padding-top: 1.4rem; max-width: 1180px; }
h1 { letter-spacing: -0.03em; font-weight: 700; }
[data-testid="stMetric"] {
    background: #fffdf8;
    border: 1px solid #e4ddd0;
    border-radius: 14px;
    padding: 0.7rem 0.9rem 0.4rem;
}
.banner {
    background: #143d34;
    color: #f6f3ec;
    border-radius: 16px;
    padding: 0.95rem 1.15rem;
    margin: 0.2rem 0 0.8rem;
}
.banner strong { color: #ffffff; }
.aviso-demo {
    background: #fff4e5;
    border: 1px solid #f0d3a6;
    color: #7c4a12;
    border-radius: 12px;
    padding: 0.7rem 0.9rem;
    margin-bottom: 0.8rem;
}
.legenda-cor { display: inline-flex; align-items: center; gap: 0.4rem; margin-right: 0.9rem; font-size: 0.92rem; }
.bolinha { width: 0.75rem; height: 0.75rem; border-radius: 99px; display: inline-block; }
</style>
"""


def main() -> None:
    st.set_page_config(
        page_title="Três Rios · Votos por bairro",
        page_icon="🗳️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("Presidente 2026 · Três Rios")
    st.caption("Leitura do 1º turno para orientar o 2º turno e entender a cidade")

    if not BANCO.exists():
        _tela_sem_dados()
        return

    try:
        meta, combinacoes = _carregar_catalogo(_assinatura_banco(), str(BANCO))
    except Exception as exc:
        st.error(f"Não consegui ler o banco processado: {exc}")
        _tela_sem_dados()
        return

    if combinacoes.empty:
        st.warning("O banco não tem votos. Processe os arquivos de novo.")
        _tela_sem_dados()
        return

    if meta.get("origem") == "demonstracao":
        st.markdown(
            "<div class='aviso-demo'><b>Demonstração.</b> Estes votos são fictícios, "
            "para você conhecer a tela. Não são o resultado oficial.</div>",
            unsafe_allow_html=True,
        )

    ano, turno, cargo, limiar, ordem, somente_prioritarios = _barra_lateral(meta, combinacoes)
    visao = _carregar_visao(ano, turno, cargo, limiar, _assinatura_banco(), str(BANCO))
    disputa = _em_disputa(visao.bairros)
    _kpis(visao, disputa)
    _banner_cidade(visao.resumo, turno, meta)
    _exportar(visao, meta, ano, turno, cargo, limiar)

    aba_bairros, aba_mapa, aba_leitura = st.tabs(["Bairros", "Mapa", "Como ler os números"])
    with aba_bairros:
        _aba_bairros(visao, ordem, somente_prioritarios, limiar, f"{ano}-{turno}-{cargo}", disputa)
    with aba_mapa:
        _aba_mapa(visao, disputa)
    with aba_leitura:
        _aba_leitura(limiar, disputa)


def _assinatura_banco() -> str:
    stat = BANCO.stat()
    return f"{stat.st_mtime:.0f}-{stat.st_size}"


@st.cache_data(show_spinner=False)
def _carregar_catalogo(assinatura: str, banco: str):
    del assinatura
    conexao = conectar(Path(banco))
    try:
        meta = ler_meta(conexao)
        combinacoes = pd.read_sql_query(
            "SELECT DISTINCT ano, turno, cargo FROM votos",
            conexao,
        )
    finally:
        conexao.close()
    return meta, combinacoes


@st.cache_data(show_spinner=False)
def _carregar_visao(ano: int, turno: int, cargo: str, limiar: float, assinatura: str, banco: str):
    del assinatura
    conexao = conectar(Path(banco))
    try:
        return montar_painel(conexao, ano, turno, cargo, limiar)
    finally:
        conexao.close()


def _tela_sem_dados() -> None:
    st.subheader("Ainda não há dados processados")
    st.markdown(
        "Baixe a votação por seção de 2026 do Rio de Janeiro, o eleitorado por local "
        "e o detalhe da apuração para a pasta `data/raw`, depois processe. "
        "A demonstração mostra a tela com votos fictícios."
    )
    arquivos = sorted(caminho.name for caminho in PASTA_RAW.glob("*") if caminho.name != ".gitkeep" and caminho.is_file())
    if arquivos:
        st.caption("Arquivos encontrados em data/raw: " + ", ".join(arquivos))
    else:
        st.caption("A pasta data/raw está vazia.")
    coluna_demo, coluna_oficial = st.columns(2)
    with coluna_demo:
        if st.button("Abrir demonstração", type="primary", width="stretch"):
            _processar(amostra=True)
    with coluna_oficial:
        if st.button("Processar arquivos oficiais", width="stretch"):
            _processar(amostra=False)


def _processar(amostra: bool) -> None:
    try:
        with st.spinner("Cruzando seções, bairros e votos de Três Rios. Arquivos do estado inteiro podem levar alguns minutos."):
            executar_pipeline(
                usar_amostra=amostra,
                ano=None if amostra else ANO_ELEICAO,
                cargo=None if amostra else CARGO_ELEICAO,
            )
        st.cache_data.clear()
        st.rerun()
    except ErroPipeline as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Falha inesperada ao processar: {exc}")


def _barra_lateral(meta: dict, combinacoes: pd.DataFrame):
    st.sidebar.header("Filtros")
    anos = sorted(combinacoes["ano"].astype(int).unique().tolist())
    ano = st.sidebar.selectbox("Ano", anos, index=len(anos) - 1)
    cargos_ano = ordenar_cargos(combinacoes.loc[combinacoes["ano"].eq(ano), "cargo"].unique().tolist())
    cargo = st.sidebar.selectbox("Cargo", cargos_ano, format_func=titulo_pt)
    turnos = sorted(
        combinacoes.loc[combinacoes["ano"].eq(ano) & combinacoes["cargo"].eq(cargo), "turno"].astype(int).unique().tolist()
    )
    turno = st.sidebar.selectbox("Turno", turnos, format_func=fmt_turno)
    limiar = st.sidebar.slider(
        "Disputa acirrada abaixo de",
        min_value=0.5,
        max_value=20.0,
        value=float(LIMIAR_PRIORITARIO),
        step=0.5,
        format="%.1f p.p.",
        help="No presidente, marca o bairro em que a diferença entre os dois nomes do 2º turno fica abaixo deste valor.",
    )
    ordem = st.sidebar.selectbox(
        "Ordenar bairros por",
        ["Votos válidos", "Disputa mais apertada", "Maior abstenção", "Nome"],
    )
    somente = st.sidebar.checkbox("Mostrar só bairros prioritários")

    st.sidebar.divider()
    st.sidebar.caption(f"Dados de {meta.get('gerado_em', '—')}")
    if meta.get("origem") == "demonstracao" and st.sidebar.button("Atualizar demonstração", width="stretch"):
        _processar(amostra=True)
    if st.sidebar.button("Reprocessar data/raw", width="stretch"):
        _processar(amostra=False)
    with st.sidebar.expander("Fontes e avisos"):
        st.write(meta.get("arquivos", "Nenhum arquivo registrado."))
        avisos = [linha for linha in meta.get("avisos", "").split("\n") if linha]
        if avisos:
            for aviso in avisos:
                st.write("• " + aviso)
        else:
            st.write("Nenhum aviso no processamento.")
    return int(ano), int(turno), cargo, float(limiar), ordem, somente


def _em_disputa(bairros: pd.DataFrame) -> bool:
    if "lider_disputa" not in bairros.columns or bairros.empty:
        return False
    return bairros["lider_disputa"].fillna("").astype(str).str.len().gt(0).any()


def _kpis(visao, disputa: bool) -> None:
    bairros = visao.bairros
    coluna = "prioritario_2t" if disputa else "prioritario"
    prioritarios = int(bairros[coluna].sum()) if not bairros.empty else 0
    validos = int(bairros["votos_validos"].sum()) if not bairros.empty else 0
    abertos = int(visao.resumo.get("votos_outros") or 0) if disputa else 0
    coluna1, coluna2, coluna3, coluna4 = st.columns(4)
    coluna1.metric("Bairros", fmt_int(len(bairros)), help="Bairros com voto neste cargo e turno.")
    coluna2.metric("Votos válidos", fmt_int(validos), help="Nominais mais legenda. Sem branco e sem nulo.")
    if disputa:
        coluna3.metric(
            "Votos em aberto",
            fmt_int(abertos),
            help="Votos nominais de quem não está no par do 2º turno. É o que ainda pode mudar o bairro.",
        )
    else:
        coluna3.metric(
            "Abstenção na cidade",
            fmt_pct(visao.resumo.get("abstencao_pct")),
            help="Abstenções divididas pelos eleitores aptos.",
        )
    coluna4.metric(
        "Bairros para o 2º turno" if disputa else "Bairros prioritários",
        fmt_int(prioritarios),
        help="Diferença apertada entre os dois nomes, ou votos dos demais suficientes para cobrir essa diferença.",
    )


def _banner_cidade(resumo: dict, turno: int, meta: dict) -> None:
    if resumo.get("empate"):
        texto = f"Empate na cidade entre <strong>{resumo.get('empate_entre') or 'os primeiros colocados'}</strong>."
    elif str(resumo.get("vencedor", "")).startswith("Sem"):
        texto = "Não há votos nominais neste recorte."
    else:
        margem = ""
        if resumo.get("segundo"):
            margem = f" Margem de <strong>{fmt_pp(resumo.get('margem_pp'))}</strong> sobre {resumo['segundo']}."
        texto = (
            f"No {fmt_turno(turno)}, <strong>{resumo['vencedor']}</strong> lidera Três Rios com "
            f"<strong>{fmt_pct(resumo.get('percentual_vencedor'))}</strong> dos votos válidos.{margem}"
        )
    nome_a = resumo.get("disputa_a") or ""
    nome_b = resumo.get("disputa_b") or ""
    if nome_a and nome_b:
        origem = meta.get("disputa_abrangencia") or "na cidade"
        origem = f"no {origem}" if origem in {"Brasil", "Rio de Janeiro"} else "na cidade"
        texto += (
            f" O par de referência do 2º turno, os dois mais votados {origem}, é "
            f"<strong>{nome_a}</strong> ({fmt_int(resumo.get('votos_disputa_a'))}) e "
            f"<strong>{nome_b}</strong> ({fmt_int(resumo.get('votos_disputa_b'))}), "
            f"com <strong>{fmt_pp(resumo.get('margem_disputa_pp'))}</strong> de diferença na cidade "
            f"e <strong>{fmt_int(resumo.get('votos_outros'))}</strong> votos nominais de outros candidatos em aberto."
        )
        if int(turno) == 1:
            texto += " O arquivo do TSE ainda não traz o 2º turno; esta tela lê o 1º."
    st.markdown(f"<div class='banner'>{texto}</div>", unsafe_allow_html=True)


def _exportar(visao, meta: dict, ano: int, turno: int, cargo: str, limiar: float) -> None:
    nome = f"tres-rios_{chave_texto(cargo).lower().replace(' ', '-')}_{ano}_turno-{turno}"
    csv = gerar_csv(visao.bairros)
    excel = gerar_excel(visao.bairros, visao.candidatos, visao.locais, meta, ano, turno, cargo, limiar)
    coluna_csv, coluna_excel, coluna_nota = st.columns([1, 1, 2])
    coluna_csv.download_button(
        "Baixar CSV",
        data=csv,
        file_name=f"{nome}.csv",
        mime="text/csv",
        width="stretch",
        key=f"csv-{nome}-{limiar}",
    )
    coluna_excel.download_button(
        "Baixar Excel",
        data=excel,
        file_name=f"{nome}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
        key=f"xlsx-{nome}-{limiar}",
    )
    coluna_nota.caption("O arquivo segue o cargo, o turno e o limiar de disputa que estão selecionados.")


def _aba_bairros(visao, ordem: str, somente_prioritarios: bool, limiar: float, recorte: str, disputa: bool) -> None:
    base = visao.bairros.copy()
    if base.empty:
        st.info("Não há votos neste cargo e turno.")
        return
    if somente_prioritarios:
        coluna = "prioritario_2t" if disputa else "prioritario"
        base = base.loc[base[coluna]].copy()
    if base.empty:
        st.info(f"Nenhum bairro ficou abaixo de {limiar:g} pontos percentuais neste recorte.")
        return

    base = _ordenar(base, ordem, disputa).reset_index(drop=True)
    _cards_prioritarios(visao.bairros, limiar, disputa)

    opcoes = base["bairro"].tolist()
    if st.session_state.get("bairro") not in opcoes:
        st.session_state["bairro"] = opcoes[0]
        st.session_state["bairro_tabela"] = opcoes[0]

    st.subheader("Todos os bairros")
    st.caption("Clique no cabeçalho para reordenar. Clique numa linha para ver os candidatos.")
    evento = st.dataframe(
        _tabela(base),
        width="stretch",
        hide_index=True,
        height=460,
        on_select="rerun",
        selection_mode="single-row",
        key=f"tabela-{recorte}-{ordem}-{somente_prioritarios}-{limiar}",
        column_config={
            "% do vencedor": st.column_config.NumberColumn(format="%.1f"),
            "Margem (p.p.)": st.column_config.NumberColumn(format="%.1f"),
            "Margem da disputa (p.p.)": st.column_config.NumberColumn(format="%.1f"),
            "Votos na frente": st.column_config.NumberColumn(format="localized"),
            "Votos do adversário": st.column_config.NumberColumn(format="localized"),
            "Votos em aberto": st.column_config.NumberColumn(format="localized"),
            "Votos válidos": st.column_config.NumberColumn(format="localized"),
            "Abstenção (%)": st.column_config.NumberColumn(format="%.1f"),
        },
    )
    if evento.selection.rows:
        escolhido = base.iloc[evento.selection.rows[0]]["bairro"]
        if escolhido != st.session_state.get("bairro_tabela"):
            st.session_state["bairro_tabela"] = escolhido
            st.session_state["bairro"] = escolhido

    st.selectbox("Detalhar bairro", opcoes, key="bairro")
    linha = base.loc[base["bairro"].eq(st.session_state["bairro"])].iloc[0]
    _detalhe_bairro(linha, visao.candidatos, visao.bairros, disputa)


def _ordenar(df: pd.DataFrame, ordem: str, disputa: bool = False) -> pd.DataFrame:
    if ordem == "Disputa mais apertada":
        coluna = "margem_disputa_pp" if disputa and "margem_disputa_pp" in df.columns else "margem_pp"
        return df.sort_values([coluna, "bairro"], ascending=[True, True], na_position="last")
    if ordem == "Maior abstenção":
        return df.sort_values(["abstencao_pct", "bairro"], ascending=[False, True], na_position="last")
    if ordem == "Nome":
        return df.sort_values("bairro")
    return df.sort_values(["votos_validos", "bairro"], ascending=[False, True])


def _tabela(df: pd.DataFrame) -> pd.DataFrame:
    if "lider_disputa" in df.columns and df["lider_disputa"].fillna("").astype(str).str.len().gt(0).any():
        return pd.DataFrame(
            {
                "Bairro": df["bairro"],
                "Na frente": df["lider_disputa"],
                "Votos na frente": df["votos_lider_disputa"],
                "Adversário": df["adversario_disputa"].replace("", "—"),
                "Votos do adversário": df["votos_adversario_disputa"],
                "Margem da disputa (p.p.)": df["margem_disputa_pp"],
                "Votos em aberto": df["votos_outros"],
                "Pode virar": df["pode_virar"].map(lambda valor: "Sim" if valor else "Não"),
                "Votos válidos": df["votos_validos"],
                "Abstenção (%)": df["abstencao_pct"],
                "Mais votado no 1º turno": df.apply(
                    lambda linha: f"Empate entre {linha['empate_entre']}" if linha["empate"] else linha["vencedor"],
                    axis=1,
                ),
            }
        )
    return pd.DataFrame(
        {
            "Bairro": df["bairro"],
            "Vencedor": df.apply(lambda linha: f"Empate entre {linha['empate_entre']}" if linha["empate"] else linha["vencedor"], axis=1),
            "% do vencedor": df["percentual_vencedor"],
            "2º colocado": df["segundo"].replace("", "—"),
            "Margem (p.p.)": df["margem_pp"],
            "Votos válidos": df["votos_validos"],
            "Abstenção (%)": df["abstencao_pct"],
            "Prioritário": df["prioritario"].map(lambda valor: "Sim" if valor else "Não"),
        }
    )


def _cards_prioritarios(bairros: pd.DataFrame, limiar: float, disputa: bool) -> None:
    if disputa:
        prioritarios = bairros.loc[bairros["prioritario_2t"]].sort_values(["margem_disputa_pp", "bairro"], na_position="last")
        st.subheader("Onde o 2º turno se decide")
        st.caption(
            f"Margem abaixo de {limiar:g} pontos entre os dois nomes, "
            "ou votos dos demais candidatos suficientes para cobrir a diferença."
        )
    else:
        prioritarios = bairros.loc[bairros["prioritario"]].sort_values("margem_pp")
        st.subheader("Bairros prioritários")
        st.caption(f"Onde a margem entre o 1º e o 2º ficou abaixo de {limiar:g} pontos percentuais.")
    if prioritarios.empty:
        st.success("Nenhum bairro neste limiar. A disputa não ficou acirrada no recorte atual.")
        return
    colunas = st.columns(min(4, len(prioritarios)))
    for indice, linha in enumerate(prioritarios.head(8).itertuples(index=False)):
        with colunas[indice % len(colunas)]:
            with st.container(border=True):
                st.markdown(f"**{linha.bairro}**")
                if disputa:
                    st.markdown(str(linha.lider_disputa))
                    st.caption(f"margem {fmt_pp(linha.margem_disputa_pp)} · {fmt_int(linha.votos_outros)} votos em aberto")
                    if linha.pode_virar:
                        st.caption("Os votos dos demais cabem na diferença.")
                else:
                    vencedor = f"Empate entre {linha.empate_entre}" if linha.empate else linha.vencedor
                    st.markdown(vencedor)
                    st.caption(f"{fmt_pct(linha.percentual_vencedor)} · margem {fmt_pp(linha.margem_pp)}")
                    if linha.segundo:
                        st.caption(f"2º {linha.segundo}")


def _detalhe_bairro(linha: pd.Series, candidatos: pd.DataFrame, bairros: pd.DataFrame, disputa: bool) -> None:
    st.subheader(linha["bairro"])
    vencedor = f"Empate entre {linha['empate_entre']}" if linha["empate"] else linha["vencedor"]
    c1, c2, c3, c4 = st.columns(4)
    if disputa and linha.get("lider_disputa"):
        c1.metric("Na frente no 2º turno", linha["lider_disputa"])
        c2.metric("Margem da disputa", fmt_pp(linha["margem_disputa_pp"]))
        c3.metric("Votos em aberto", fmt_int(linha["votos_outros"]))
        c4.metric("Pode virar", "Sim" if linha["pode_virar"] else "Não")
        st.caption(
            f"No 1º turno, o mais votado neste bairro foi {vencedor} "
            f"({fmt_pct(linha['percentual_vencedor'])}, margem {fmt_pp(linha['margem_pp'])}). "
            f"Abstenção: {fmt_pct(linha['abstencao_pct'])}."
        )
    else:
        c1.metric("Vencedor", vencedor)
        c2.metric("Percentual", fmt_pct(linha["percentual_vencedor"]))
        c3.metric("Margem", fmt_pp(linha["margem_pp"]), help="Diferença para o 2º colocado, em pontos percentuais dos votos válidos.")
        c4.metric("Abstenção", fmt_pct(linha["abstencao_pct"]))

    do_bairro = candidatos.loc[candidatos["bairro"].eq(linha["bairro"])].copy()
    nominais = do_bairro.loc[do_bairro["tipo"].eq("nominal")]
    cores = mapa_cores(bairros["vencedor"].tolist(), nominais["candidato"].tolist())
    figura = grafico_nominais(do_bairro, cores)
    if figura is not None:
        st.plotly_chart(figura, width="stretch", config={"displayModeBar": False})
        if len(nominais) > 12:
            st.caption(f"O gráfico mostra os 12 mais votados. A tabela abaixo traz os {len(nominais)} candidatos nominais.")
    else:
        st.info("Este bairro não tem voto nominal no recorte.")

    if not nominais.empty:
        tabela = pd.DataFrame(
            {
                "Candidato": nominais["candidato"],
                "Número": nominais["nr_votavel"],
                "Votos": nominais["votos"],
                "% dos válidos": nominais["percentual"],
            }
        )
        st.dataframe(
            tabela,
            width="stretch",
            hide_index=True,
            column_config={
                "Votos": st.column_config.NumberColumn(format="localized"),
                "% dos válidos": st.column_config.NumberColumn(format="%.1f"),
            },
        )
    a1, a2, a3 = st.columns(3)
    a1.metric("Votos de legenda", fmt_int(linha["votos_legenda"]))
    a2.metric("Brancos", fmt_int(linha["brancos"]))
    a3.metric("Nulos", fmt_int(linha["nulos"]))


def _aba_mapa(visao, disputa: bool) -> None:
    st.subheader("Locais de votação")
    if disputa:
        st.caption(
            "Cada ponto é uma escola. A cor é quem está na frente, naquele local, entre os dois nomes do 2º turno. "
            "O mapa de fundo precisa de internet."
        )
    else:
        st.caption(
            "Cada ponto é uma escola ou colégio. A cor é quem teve mais votos nominais naquele local. "
            "O mapa de fundo precisa de internet."
        )
    pontos = visao.locais
    if pontos.empty or pontos["latitude"].notna().sum() == 0:
        st.info(
            "Nenhum local ficou com latitude e longitude válidas. "
            "Confira as colunas NR_LATITUDE e NR_LONGITUDE no arquivo de locais de votação."
        )
        return
    nomes = pontos["lider_disputa"] if disputa and "lider_disputa" in pontos.columns else pontos["vencedor"]
    cores = mapa_cores(nomes.tolist())
    mapa = criar_mapa(pontos, cores)
    if mapa is None:
        st.info("Não foi possível montar o mapa com as coordenadas disponíveis.")
        return
    st_folium(mapa, height=560, use_container_width=True, returned_objects=[], key="mapa-locais")
    legenda = []
    for nome in nomes.drop_duplicates():
        chave = "Empate" if str(nome).startswith("Empate") else nome
        cor = cores.get(chave, "#6B7280")
        legenda.append(f"<span class='legenda-cor'><span class='bolinha' style='background:{cor}'></span>{nome}</span>")
    st.markdown("".join(legenda), unsafe_allow_html=True)


def _aba_leitura(limiar: float, disputa: bool) -> None:
    trecho_disputa = ""
    if disputa:
        trecho_disputa = f"""
**Par do 2º turno** são os dois mais votados para presidente no Brasil, somados a partir do arquivo nacional do TSE.
Se um terceiro nome ganhou o bairro no 1º turno, a coluna "Na frente" continua comparando só os dois do par.

**Margem da disputa** é a diferença entre esses dois nomes, em pontos percentuais dos votos válidos do bairro.

**Votos em aberto** são os votos nominais de quem não está nesse par.

**Pode virar** significa que esses votos em aberto são suficientes para, no mínimo, empatar a diferença do bairro.

**Bairro para o 2º turno** é aquele com margem da disputa abaixo de **{limiar:g} pontos percentuais**, ou que ainda pode virar.
"""
    st.markdown(
        f"""
**Votos válidos** são os nominais mais os de legenda. Branco, nulo e anulado não entram.

**Mais votado no 1º turno** é a pessoa com mais votos nominais no bairro. Voto de legenda conta como válido,
mas não elege um nome.
{trecho_disputa}
**Abstenção** é o número de abstenções dividido pelos eleitores aptos das seções daquele bairro.
Em 2026 ela sai do detalhe da apuração por seção, filtrado para presidente.

**O mapa** marca o local de votação (a escola), não o desenho do bairro.
O TSE não publica o contorno dos bairros neste conjunto de arquivos.

Os totais saem dos dados abertos do Tribunal Superior Eleitoral.
Confira sempre a totalização oficial antes de uma decisão de campanha.
        """
    )


main()
