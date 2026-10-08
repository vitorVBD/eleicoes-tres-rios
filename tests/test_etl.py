"""Testes do cruzamento de votos, bairros e abstenção."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from eleicoes.apuracao import construir_visoes
from eleicoes.armazenamento import conectar
from eleicoes.consultas import montar_painel
from eleicoes.etl import executar_pipeline
from eleicoes.normalizacao import chave_texto_serie
from eleicoes.preparacao import preparar_abstencao, preparar_locais


class TestNormalizacao(unittest.TestCase):
    def test_municipio_ignora_acento_e_espaco(self):
        chaves = chave_texto_serie(pd.Series(["TRÊS RIOS", " Tres   Rios ", "PARAÍBA DO SUL"]))
        self.assertEqual(chaves.tolist(), ["TRES RIOS", "TRES RIOS", "PARAIBA DO SUL"])


class TestPreparacao(unittest.TestCase):
    def test_herda_bairro_e_desinverte_coordenada(self):
        bruto = pd.DataFrame(
            [
                {
                    "NM_MUNICIPIO": "TRÊS RIOS",
                    "NR_ZONA": "001",
                    "NR_SECAO": "1.0",
                    "NM_LOCAL_VOTACAO": "ESCOLA A",
                    "NM_BAIRRO": "Centro",
                    "NR_LATITUDE": "-43,2088",
                    "NR_LONGITUDE": "-22.1168",
                    "DS_ENDERECO": "Rua 1",
                },
                {
                    "NM_MUNICIPIO": "TRÊS RIOS",
                    "NR_ZONA": "1",
                    "NR_SECAO": "2",
                    "NM_LOCAL_VOTACAO": "ESCOLA A",
                    "NM_BAIRRO": "   ",
                    "NR_LATITUDE": "",
                    "NR_LONGITUDE": "",
                    "DS_ENDERECO": "",
                },
            ]
        )
        avisos: list[str] = []
        locais = preparar_locais(bruto, avisos)
        self.assertEqual(sorted(locais["bairro"].tolist()), ["Centro", "Centro"])
        self.assertEqual(sorted(locais["zona"].tolist()), ["1", "1"])
        centro = locais.loc[locais["secao"].eq("1")].iloc[0]
        self.assertAlmostEqual(centro["latitude"], -22.1168, places=3)
        self.assertAlmostEqual(centro["longitude"], -43.2088, places=3)
        self.assertTrue(any("invertidas" in aviso for aviso in avisos))

    def test_abstencao_repetida_nao_soma_e_particao_soma(self):
        linhas = []
        for _ in range(3):
            linhas.append(
                {
                    "ANO_ELEICAO": "2024",
                    "NR_TURNO": "1",
                    "NR_ZONA": "1",
                    "NR_SECAO": "1",
                    "QT_APTOS": "400",
                    "QT_COMPARECIMENTO": "300",
                    "QT_ABSTENCAO": "100",
                }
            )
        linhas.extend(
            [
                {
                    "ANO_ELEICAO": "2024",
                    "NR_TURNO": "1",
                    "NR_ZONA": "1",
                    "NR_SECAO": "2",
                    "QT_APTOS": "100",
                    "QT_COMPARECIMENTO": "80",
                    "QT_ABSTENCAO": "20",
                },
                {
                    "ANO_ELEICAO": "2024",
                    "NR_TURNO": "1",
                    "NR_ZONA": "1",
                    "NR_SECAO": "2",
                    "QT_APTOS": "150",
                    "QT_COMPARECIMENTO": "100",
                    "QT_ABSTENCAO": "50",
                },
            ]
        )
        avisos: list[str] = []
        tabela = preparar_abstencao(pd.DataFrame(linhas), avisos).set_index("secao")
        self.assertEqual(int(tabela.loc["1", "qt_aptos"]), 400)
        self.assertEqual(int(tabela.loc["2", "qt_aptos"]), 250)
        self.assertTrue(any("repetido" in aviso for aviso in avisos))


class TestApuracao(unittest.TestCase):
    def test_margem_de_cinco_pontos_nao_e_prioritaria_e_legenda_nao_vence(self):
        votos = pd.DataFrame(
            [
                {"zona": "1", "secao": "1", "nr_votavel": "22", "nm_votavel": "Ana Ribeiro", "qt_votos": 525, "tipo": "nominal"},
                {"zona": "1", "secao": "1", "nr_votavel": "15", "nm_votavel": "Carlos Mendonça", "qt_votos": 475, "tipo": "nominal"},
                {"zona": "1", "secao": "1", "nr_votavel": "95", "nm_votavel": "Branco", "qt_votos": 40, "tipo": "branco"},
                {"zona": "1", "secao": "1", "nr_votavel": "13", "nm_votavel": "Partido Exemplo", "qt_votos": 0, "tipo": "legenda"},
            ]
        )
        locais = pd.DataFrame(
            [
                {
                    "zona": "1",
                    "secao": "1",
                    "bairro": "Centro",
                    "local_votacao": "Escola A",
                    "endereco": "Rua 1",
                    "latitude": -22.11,
                    "longitude": -43.20,
                }
            ]
        )
        vazio = pd.DataFrame(columns=["zona", "secao", "qt_aptos", "qt_comparecimento", "qt_abstencao"])
        visao = construir_visoes(votos, locais, vazio, 5.0)
        linha = visao.bairros.iloc[0]
        self.assertEqual(linha["vencedor"], "Ana Ribeiro")
        self.assertEqual(int(linha["votos_validos"]), 1000)
        self.assertAlmostEqual(linha["margem_pp"], 5.0, places=2)
        self.assertFalse(bool(linha["prioritario"]))
        self.assertIsNone(linha["abstencao_pct"])

        votos.loc[votos["nm_votavel"].eq("Ana Ribeiro"), "qt_votos"] = 524
        votos.loc[votos["nm_votavel"].eq("Carlos Mendonça"), "qt_votos"] = 476
        visao = construir_visoes(votos, locais, vazio, 5.0)
        self.assertTrue(bool(visao.bairros.iloc[0]["prioritario"]))

        votos_legenda = pd.DataFrame(
            [
                {"zona": "1", "secao": "1", "nr_votavel": "22111", "nm_votavel": "Joana Pires", "qt_votos": 10, "tipo": "nominal"},
                {"zona": "1", "secao": "1", "nr_votavel": "22", "nm_votavel": "Partido da Árvore", "qt_votos": 500, "tipo": "legenda"},
            ]
        )
        visao = construir_visoes(votos_legenda, locais, vazio, 5.0)
        self.assertEqual(visao.bairros.iloc[0]["vencedor"], "Joana Pires")
        self.assertEqual(int(visao.bairros.iloc[0]["votos_legenda"]), 500)


class TestPipeline(unittest.TestCase):
    def test_amostra_tres_rios(self):
        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "amostra"
            saida = Path(pasta) / "out"
            executar_pipeline(origem=origem, destino=saida, usar_amostra=True, limiar=5)
            self.assertTrue((saida / "tres_rios_dados_bairros.json").exists())
            conexao = conectar(saida / "tres_rios.db")
            try:
                painel = montar_painel(conexao, 2024, 1, "PREFEITO", 5)
                vereador = montar_painel(conexao, 2024, 1, "VEREADOR", 5)
            finally:
                conexao.close()

        bairros = painel.bairros.set_index("bairro")
        self.assertEqual(len(bairros), 10)
        self.assertNotIn("Paraíba do Sul", bairros.index)
        self.assertIn("Boa União", bairros.index)
        self.assertIn("Vila Isabel", bairros.index)

        centro = bairros.loc["Centro"]
        self.assertEqual(centro["vencedor"], "Ana Ribeiro")
        self.assertEqual(int(centro["votos_validos"]), 1820)
        self.assertEqual(int(centro["brancos"]), 25)
        self.assertEqual(int(centro["nulos"]), 15)
        self.assertTrue(bool(centro["prioritario"]))
        self.assertAlmostEqual(centro["abstencao_pct"], 16.0, places=2)
        self.assertAlmostEqual(centro["margem_pp"], 30 / 1820 * 100, places=2)

        self.assertEqual(bairros.loc["Boa União", "vencedor"], "Carlos Mendonça")
        self.assertTrue(bool(bairros.loc["Monte Castelo", "prioritario"]))
        self.assertFalse(bool(bairros.loc["Pilões", "prioritario"]))
        self.assertNotIn("Zé Forasteiro", set(painel.candidatos["candidato"]))

        local = painel.locais.loc[painel.locais["bairro"].eq("Centro")].iloc[0]
        self.assertAlmostEqual(local["latitude"], -22.1168, places=3)
        self.assertAlmostEqual(local["longitude"], -43.2088, places=3)

        centro_vereador = vereador.bairros.set_index("bairro").loc["Centro"]
        self.assertEqual(centro_vereador["vencedor"], "Joana Pires")
        self.assertGreater(int(centro_vereador["votos_legenda"]), int(centro_vereador["votos_vencedor"]))


if __name__ == "__main__":
    unittest.main()
