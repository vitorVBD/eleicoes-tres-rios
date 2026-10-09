# Inteligência eleitoral · cidades do Rio de Janeiro

Para gerar os três PDFs de uma cidade (apuração, mapa e roteiro), dê dois cliques em `gerar.bat`. O arquivo vale no Windows e no Linux. Ele prepara o programa na primeira vez, pergunta o nome da cidade e abre a pasta dos PDFs.

No Linux, se o dois cliques abrir o arquivo em vez de rodar, abra o terminal nesta pasta e rode `bash gerar.bat`.

A primeira vez lê os arquivos do TSE de todo o estado e pode levar vários minutos. As cidades seguintes saem rápido. Os PDFs ficam em `data/processed/cidades/`.

O painel abaixo continua o recorte de Três Rios.

# Inteligência eleitoral · Três Rios (RJ)

Painel local para a coordenação olhar, por bairro, quem venceu, por quantos pontos, quantos votos nominais cada candidatura teve e qual foi a abstenção. Os números saem dos arquivos abertos do Tribunal Superior Eleitoral. A aplicação não envia esses dados para lugar nenhum: o processamento acontece na sua máquina.

## O que a tela mostra

- Filtro de **ano**, **cargo** e **turno**.
- Tabela de bairros, ordenável, com vencedor, percentual, margem e abstenção.
- **Bairros prioritários**: margem entre o 1º e o 2º abaixo de 5 pontos percentuais dos votos válidos (o limiar pode ser ajustado na barra lateral).
- Detalhe do bairro, com os votos nominais de cada candidatura.
- Mapa dos **locais de votação** (escolas e colégios). A cor é o candidato mais votado naquele local.
- Exportação do recorte atual em **CSV** e **Excel** para a equipe de rua.

Definições usadas na apuração:

| Medida | Cálculo |
| --- | --- |
| Votos válidos | Nominais + legenda. Branco, nulo e anulado ficam de fora. |
| Vencedor | Candidato com mais votos nominais. Voto de legenda não elege um nome. |
| Margem | `(votos do 1º − votos do 2º) / votos válidos × 100`, em pontos percentuais. |
| Prioritário | Margem menor que o limiar (padrão: 5). Empate entra como prioritário. |
| Abstenção | Abstenções ÷ eleitores aptos das seções do bairro. |

O mapa marca o ponto do local de votação. O TSE não publica, nestes arquivos, o polígono dos bairros.

## Estrutura do projeto

```text
eleicoes-tres-rios/
├── app.py                     # interface Streamlit
├── pipeline.py                # comando do ETL
├── requirements.txt
├── data/
│   ├── raw/                   # CSVs ou ZIPs oficiais do TSE
│   ├── amostras/              # CSVs fictícios gerados por --amostra
│   └── processed/             # tres_rios.db e tres_rios_dados_bairros.json
├── src/eleicoes/
│   ├── leitura.py             # CSV em blocos, Latin-1, separador ";"
│   ├── preparacao.py          # limpeza, bairros, branco/nulo/legenda
│   ├── apuracao.py            # vencedor, margem, abstenção
│   ├── etl.py                 # orquestra o cruzamento
│   ├── armazenamento.py       # SQLite
│   ├── consultas.py           # recortes para a tela
│   ├── amostra.py             # dados fictícios de demonstração
│   ├── mapa.py                # Leaflet via Folium
│   ├── exportacao.py          # CSV e Excel
│   └── ...
└── tests/test_etl.py
```

O cruzamento é feito pela chave `(NR_ZONA, NR_SECAO)`, depois de filtrar `NM_MUNICIPIO` para Três Rios. A interface lê o SQLite e não reabre os arquivos grandes a cada clique. O JSON `data/processed/tres_rios_dados_bairros.json` é o retrato agregado, útil para outras ferramentas.

## 1. Arquivos do TSE

A pasta `data/raw` já traz o recorte de 2026 que o programa usa: a votação presidencial do Rio de Janeiro, o eleitorado do estado e o detalhe da apuração de presidente. Os pacotes nacionais completos passam de 100 MB e o GitHub recusa esse tamanho, por isso não entram no repositório.

Portal de origem: [dadosabertos.tse.jus.br](https://dadosabertos.tse.jus.br/). O recorte desta tela é a eleição **presidencial de 2026**.

1. **Votação por seção para presidente** (arquivo nacional; o ZIP do Rio de Janeiro não traz esse cargo)

   [Resultados 2026](https://dadosabertos.tse.jus.br/dataset/resultados-2026)

   Download direto: [votacao_secao_2026_BR.zip](https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_2026_BR.zip)

2. **Eleitorado por local de votação** (traz bairro, escola e coordenadas)

   [Eleitorado 2026](https://dadosabertos.tse.jus.br/dataset/eleitorado-2026)

   Download direto: [eleitorado_local_votacao_2026.zip](https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip)

3. **Detalhe da apuração por seção** (aptos, comparecimento e abstenção)

   O perfil de comparecimento de 2026 não estava publicado. A abstenção sai deste arquivo, filtrado para presidente, para o total da seção não ser repetido em cada cargo.

   Download direto: [detalhe_votacao_secao_2026.zip](https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_secao/detalhe_votacao_secao_2026.zip)

Coloque os `.zip` em `data/raw/`. O pipeline lê em blocos, fica só com Três Rios e, no processamento oficial, só com presidente no ano pedido. Nos ZIPs nacionais, lê apenas o CSV do Rio de Janeiro.

O arquivo do estado inteiro é grande. A primeira leitura pode levar alguns minutos e precisa de alguns gigabytes livres em disco se você descompactar o ZIP. Com o ZIP fechado, o pipeline lê o CSV que está dentro dele.

## 2. Ambiente virtual

Requer Python 3.11 ou mais recente.

```bash
cd eleicoes-tres-rios
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

No Windows, ative com `venv\Scripts\activate`.

## 3. Processar

Demonstração, com votos fictícios, para ver a tela antes de baixar o TSE:

```bash
python pipeline.py --amostra
```

Arquivos oficiais que estão em `data/raw`:

```bash
python pipeline.py --ano 2026 --cargo PRESIDENTE
```

`--ano` e `--cargo` são o padrão. Com `--amostra`, os dois são ignorados.

Outra pasta de entrada ou de saída:

```bash
python pipeline.py --raw /caminho/dos/csvs --saida data/processed
```

O comando grava:

- `data/processed/tres_rios.db`
- `data/processed/tres_rios_dados_bairros.json`

## 4. Abrir o painel

```bash
streamlit run app.py
```

O navegador abre em `http://localhost:8501`. Se o banco ainda não existir, a própria tela oferece **Abrir demonstração** ou **Processar arquivos oficiais**.

O mapa usa um fundo do OpenStreetMap. Sem rede, a lista de bairros e a exportação continuam funcionando; os pontos podem aparecer sem o mapa de ruas.

## Conferência automática

```bash
python -m unittest tests/test_etl.py
```

O teste gera a amostra fictícia, confere o filtro de município, a margem, a abstenção e o fato de a legenda não virar "candidata vencedora".

## Limitações

- A abstenção do TSE às vezes vem fatiada por perfil (sexo, idade, escolaridade). Se o total da seção está repetido em todas as fatias, o pipeline não soma de novo. Se cada fatia é um pedaço do eleitorado, as quantidades são somadas.
- Coordenada fora do Brasil é descartada. Latitude e longitude invertidas são corrigidas quando o par só faz sentido trocado.
- Seção sem bairro herda o bairro das outras seções do mesmo local de votação, desde que esse local aponte para um único bairro.
- Não há login. Use na rede local da coordenação; não publique o `streamlit` na internet aberta.
