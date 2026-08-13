# IICA-CSV — Desafio 4

MVP do desafio **Interface Inteligente para Consulta de Arquivos CSV**, do InsurMinds/I2A2. A aplicação recebe um pacote ZIP, carrega um ou mais CSVs em memória e permite perguntas em linguagem natural com respostas fundamentadas nos dados.

O projeto privilegia uma solução pequena e explicável: uma interface Streamlit, um único agente LangChain com ChatGroq e ferramentas determinísticas executadas localmente com pandas. O modelo não recebe os DataFrames completos e não executa código gerado pelo usuário.

## Funcionalidades

- upload de um ZIP diretamente na interface;
- validação do pacote, incluindo proteção contra Zip Slip;
- limites de tamanho expandido, taxa de compressão e dicionários (25 MB);
- descoberta de CSVs em qualquer subdiretório do ZIP;
- leitura controlada de CSVs UTF-8 ou CP1252/Latin-1, com `,` ou `;` e decimal `.` ou `,`;
- carregamento opcional de dicionário de dados JSON ou CSV;
- catálogo em memória com schema, tipos, nulos e metadados de leitura;
- consulta em linguagem natural por um agente LangChain criado com `create_agent`;
- cálculos locais por ferramentas pandas com operações permitidas e resultados limitados;
- respostas em texto e, quando aplicável, tabela e gráfico Plotly;
- histórico restrito à sessão Streamlit;
- mensagens compreensíveis para arquivo inválido, coluna ausente, pergunta fora do escopo e indisponibilidade da Groq.

## Requisitos

- Windows com Python 3.11 ou superior instalado pelo Python Launcher (`py`);
- acesso à internet para a API Groq;
- uma chave `GROQ_API_KEY` válida;
- memória suficiente para manter os CSVs descompactados em uma sessão pandas.

## Quickstart no Windows PowerShell

Execute a partir da raiz do repositório:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python scripts/validate_structure.py
pytest
streamlit run src/iica_csv/ui/app.py
```

No arquivo `.env`, preencha somente a chave local:

```dotenv
GROQ_API_KEY=sua_chave_local
GROQ_MODEL=llama-3.3-70b-versatile
APP_MAX_UPLOAD_MB=500
LOG_LEVEL=INFO
```

O arquivo `.env` é ignorado pelo Git. Se `GROQ_API_KEY` estiver vazia ou ausente, a aplicação orienta a configuração da chave sem mostrar traceback bruto. `APP_MAX_UPLOAD_MB` é aplicado tanto no widget Streamlit quanto na validação do processador ZIP.

## Uso

1. Na seção **Carga**, envie um ZIP com um ou mais CSVs.
2. Confira arquivos encontrados, datasets carregados, dimensões, encoding, separador e estado do dicionário.
3. Se nenhum dicionário for encontrado, a carga continua e a interface informa: “Dicionário de dados não identificado no pacote.”
4. Após pelo menos um CSV válido, use a seção **Consulta** para conversar com o agente.
5. Confira a resposta e, quando retornados pela ferramenta, a tabela ou o gráfico correspondente.

O modelo padrão é `llama-3.3-70b-versatile`, com temperatura zero. É possível trocar o modelo por `GROQ_MODEL`, desde que ele esteja disponível na conta Groq usada na execução.

## Formatos de CSV

O leitor tenta combinações controladas e rejeita interpretações evidentemente inválidas, como um arquivo tabular inteiro lido em uma única coluna. O MVP suporta, no mínimo:

| Propriedade | Valores suportados |
|---|---|
| Encoding | `utf-8-sig`, `utf-8`, `cp1252`, `latin-1` |
| Separador | vírgula (`,`) e ponto e vírgula (`;`) |
| Decimal | ponto (`.`) e vírgula (`,`) |

Conversões numéricas e temporais são conservadoras: uma coluna original não é substituída quando a conversão não é segura. O catálogo registra o encoding e o separador escolhidos, além de linhas, colunas, tipos e nulos.

## Pacote de demonstração 202401

Os dados oficiais do curso são locais e não são distribuídos neste repositório. Coloque `202401_NFs.zip` em `data/raw/` e gere um pacote compatível com o requisito de dicionário:

```powershell
python scripts/build_demo_package.py
```

O comando lê, sem extrair, os CSVs `202401_NFs_Cabecalho.csv` e `202401_NFs_Itens.csv`, acrescenta o dicionário versionado em `data/dictionaries/dicionario_dados_202401.json` e cria:

```text
outputs/entrega/pacote_demo_202401.zip
```

Os caminhos podem ser alterados:

```powershell
python scripts/build_demo_package.py `
  --source data/raw/202401_NFs.zip `
  --output outputs/entrega/pacote_demo_202401.zip `
  --dictionary data/dictionaries/dicionario_dados_202401.json
```

O script nunca extrai nem modifica o arquivo em `data/raw/`. Tanto `data/raw/*` quanto ZIPs e artefatos em `outputs/entrega/` permanecem ignorados pelo Git.

## Arquitetura

```text
Usuário
  → Streamlit
  → validação e leitura segura do ZIP
  → DataManager/catálogo mantido em st.session_state
  → resolução semântica baseada no schema/dicionário
  → agente LangChain + ChatGroq
  → ferramentas determinísticas
  → pandas
  → resultado estruturado e limitado
  → texto, tabela ou gráfico no Streamlit
```

As ferramentas autorizam apenas operações conhecidas, como descrição, agregação, ranking, filtro, valores únicos e agregação temporal. Não são usados `eval`, `exec`, Python gerado pela LLM, SQL arbitrário, shell fornecido pelo usuário, banco de dados ou índice vetorial.

Antes do tool calling, um resolvedor local transforma intenções inequívocas em
um plano sem resultados: dataset, coluna, agrupamento e operação. Assim,
fornecedor/emitente usa a razão social do emitente, destinatário/cliente usa o
nome do destinatário, volume comprado usa `SUM(QUANTIDADE)`, total das notas usa
o valor do cabeçalho e valor de itens usa o total do item somente quando isso é
pedido explicitamente. O retorno da tool é validado contra esse plano antes de
ser exibido.

Quando o pacote não contém dicionário, o fallback aceita apenas nomes de schema
convencionais e inequívocos. Catálogos opacos ou candidatos empatados não são
adivinhados; o fluxo volta ao agente, que deve pedir esclarecimento.

O contrato LangChain de `top_n` aceita `n` como inteiro ou string numérica e o
normaliza localmente. Isso tolera a serialização variável de tool calls do
modelo sem enfraquecer a validação de limites. Falhas finais da Groq são
classificadas por status/tipo (400 de tool, 401, 403, 429, timeout ou conexão),
sem exibir o corpo bruto da resposta externa.

Detalhes e decisões estão em `docs/arquitetura.md` e `docs/decisoes.md`.

## Estrutura principal

```text
src/iica_csv/
  agents/       agente, resolução semântica, prompt e orquestração
  processing/   ZIP, leitura de CSV, configuração e catálogo
  tools/        operações pandas determinísticas
  ui/           aplicação Streamlit
tests/          testes automatizados
scripts/        validação estrutural e pacote demo
data/           somente placeholders e dicionários permitidos
docs/           requisitos, arquitetura, decisões e relatório
workspaces/     contribuições e provas de conceito preservadas
```

O código oficial pertence a `src/iica_csv/`. O notebook `workspaces/leo-vilelela/csv_agent_notebook.ipynb` é preservado como registro da prova de conceito; funcionalidades necessárias à entrega não devem permanecer somente em `workspaces/`.

## Segurança e privacidade

- nunca versione `.env`, chaves, dados oficiais ou pacotes gerados;
- o ZIP é lido sem `extractall` e nomes de entrada são validados contra caminhos absolutos e travessia;
- os DataFrames existem somente na sessão atual;
- a LLM recebe schema, metadados, resultados limitados e pequenas amostras quando indispensáveis, nunca o dataset completo;
- toda afirmação numérica deve resultar de uma ferramenta;
- o agente não executa código ou comandos enviados pelo usuário;
- erros apresentados na interface não expõem credenciais nem traceback bruto.

## Validação

```powershell
python scripts/validate_structure.py
pytest
python -m compileall -q src scripts
```

O dataset `data/raw/202401_NFs.zip` é a referência rápida de desenvolvimento. O pacote maior `data/raw/202505_NFe.zip` valida CP1252, ponto e vírgula, decimal brasileiro e uso de memória. Ambos são ignorados e devem permanecer apenas no ambiente local.

Na validação final local de 11/08/2026, o pacote 202505 carregou 150.976 notas e 549.431 itens em 20,253 s, com pico de working set próximo de 1,1 GiB. Esse valor depende da máquina e evidencia a principal limitação do MVP em pandas/memória; não representa garantia de desempenho em hospedagem.

## Entrega

A entrega prevê o código-fonte e um relatório técnico exportado para PDF. Resultados das quatro perguntas de aceitação somente devem ser adicionados ao relatório após execução real e conferência com as ferramentas pandas.

## Licença

MIT. Consulte `LICENSE`.
