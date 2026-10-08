"""Caminhos, município alvo e regras eleitorais usadas em todo o projeto."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PASTA_RAW = RAIZ / "data" / "raw"
PASTA_PROCESSADO = RAIZ / "data" / "processed"
PASTA_AMOSTRAS = RAIZ / "data" / "amostras"
BANCO = PASTA_PROCESSADO / "tres_rios.db"
JSON_BAIRROS = PASTA_PROCESSADO / "tres_rios_dados_bairros.json"

MUNICIPIO = "TRÊS RIOS"
MUNICIPIO_CHAVE = "TRES RIOS"
UF = "RJ"

# Centro aproximado da cidade, usado quando ainda não há coordenadas válidas.
CENTRO_MAPA = (-22.1166, -43.2088)

# Diferença, em pontos percentuais dos votos válidos, abaixo da qual a disputa
# é tratada como prioritária para a equipe de rua.
LIMIAR_PRIORITARIO = 5.0

# Recorte pedido para a coordenação: só o presidencial de 2026.
ANO_ELEICAO = 2026
CARGO_ELEICAO = "PRESIDENTE"

# No voto proporcional, número de 1 ou 2 dígitos é voto de legenda.
CARGOS_PROPORCIONAIS = {
    "VEREADOR",
    "DEPUTADO FEDERAL",
    "DEPUTADO ESTADUAL",
    "DEPUTADO DISTRITAL",
}

# Ordem em que os cargos aparecem no filtro. Prefeito vem primeiro porque
# o uso principal da ferramenta é a coordenação municipal.
ORDEM_CARGOS = [
    "PRESIDENTE",
    "PREFEITO",
    "VEREADOR",
    "GOVERNADOR",
    "SENADOR",
    "DEPUTADO FEDERAL",
    "DEPUTADO ESTADUAL",
    "DEPUTADO DISTRITAL",
]

BAIRRO_DESCONHECIDO = "Não informado"
LOCAL_DESCONHECIDO = "Local não informado"

# Chaves sem acento. Servem só para exibir um nome estável quando o TSE
# grafa o mesmo bairro de formas diferentes. Bairros fora desta lista
# continuam aparecendo, com o texto original normalizado.
BAIRROS_CONHECIDOS = {
    "CENTRO": "Centro",
    "VILA ISABEL": "Vila Isabel",
    "BOA UNIAO": "Boa União",
    "CANTAGALO": "Cantagalo",
    "MOURA BRASIL": "Moura Brasil",
    "TRIANGULO": "Triângulo",
    "HERMOGENIO SILVA": "Hermogênio Silva",
    "NOVA NITEROI": "Nova Niterói",
    "PILOES": "Pilões",
    "PONTE DAS GARCAS": "Ponte das Garças",
    "PURYS": "Purys",
    "BEMPOSTA": "Bemposta",
    "MONTE CASTELO": "Monte Castelo",
    "CIDADE NOVA": "Cidade Nova",
    "ANDRADE PINTO": "Andrade Pinto",
    "SANTA TEREZINHA": "Santa Terezinha",
    "CAIXA DAGUA": "Caixa D'Água",
    "JARDIM PRIMAVERA": "Jardim Primavera",
    "VILA PARAISO": "Vila Paraíso",
    "PORTAO VERMELHO": "Portão Vermelho",
    "LADEIRA DAS PALMEIRAS": "Ladeira das Palmeiras",
    "BARRAGEM": "Barragem",
}

CHAVES_VAZIAS = {
    "",
    "NAO INFORMADO",
    "NAO INFORMADA",
    "SEM INFORMACAO",
    "NULL",
    "NONE",
    "NAN",
    "N I",
    "SI",
    "S I",
    "NULO",
    "NULO NULO",
    "ND",
    "NA",
}

BLOCO_LEITURA = 100_000
