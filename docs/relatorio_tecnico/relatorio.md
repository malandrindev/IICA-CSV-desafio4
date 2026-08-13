# Relatório técnico — Interface Inteligente para Consulta de Arquivos CSV

> Documento-fonte do Desafio 4. Campos entre colchetes devem ser preenchidos somente após confirmação pela equipe ou execução real. Não substituir placeholders de resultados por estimativas.

## 1. Identificação do grupo

- **Nome do grupo:** `[PREENCHER]`
- **Integrantes e identificação:** `[CONFIRMAR NOMES COMPLETOS E DADOS EXIGIDOS PELO CURSO]`
- **Curso:** InsurMinds / I2A2
- **Desafio:** Desafio 4 — Interface Inteligente para Consulta de Arquivos CSV
- **Data da entrega:** `[PREENCHER]`

## 2. Introdução

O desafio propõe uma interface capaz de receber conjuntos de dados em CSV e responder perguntas formuladas em linguagem natural. A solução precisa combinar uma LLM e ferramentas de análise sem perder rastreabilidade: interpretar a pergunta é responsabilidade do agente, enquanto números, filtros, agrupamentos e rankings devem ser obtidos diretamente dos dados.

O MVP descrito neste relatório utiliza uma aplicação Streamlit única, um agente LangChain conectado à Groq e operações pandas determinísticas. Essa divisão permite demonstrar uso real de IA sem delegar ao modelo cálculos que podem ser executados e testados localmente.

## 3. Objetivo

Construir um MVP funcional que:

- receba um ZIP contendo um ou mais CSVs e, quando disponível, um dicionário de dados;
- reconheça os formatos presentes nos dois pacotes oficiais;
- mantenha os dados somente na sessão da aplicação;
- interprete perguntas em português por meio de um agente;
- execute consultas seguras por tools com pandas;
- apresente resposta textual, tabela e gráfico quando apropriado;
- trate entradas inválidas e limitações sem inventar resultados.

## 4. Framework escolhido

Foi escolhido **LangChain 1.x**, usando a API `create_agent`. O modelo de chat é fornecido por `ChatGroq`, do pacote `langchain-groq`, com modelo padrão `llama-3.3-70b-versatile` e temperatura zero.

LangChain foi selecionado por oferecer o ciclo de tool calling necessário ao desafio: o agente interpreta a solicitação, escolhe uma operação registrada, recebe o resultado e formula a resposta. A lógica de dados não depende do framework e pode ser testada sem chamada à LLM.

## 5. Tecnologias

| Tecnologia | Uso no MVP |
|---|---|
| Python 3.11+ | linguagem e runtime |
| Streamlit | carga do ZIP, chat e apresentação |
| LangChain 1.x | criação e orquestração do agente |
| langchain-groq / ChatGroq | acesso ao modelo Groq |
| NumPy | tipos numéricos usados pelo pandas e serialização segura |
| pandas | leitura e análise tabular local |
| Plotly | barras de ranking e linhas temporais |
| python-dotenv | configuração local por `.env` |
| pytest | testes determinísticos |

A chave Groq não é incluída no código. O arquivo `.env.example` documenta as variáveis esperadas e `.env` permanece ignorado pelo Git.

## 6. Arquitetura

O fluxo deliberadamente contém apenas um agente:

```text
Usuário
  → Streamlit
  → validação e leitura segura do ZIP
  → DataManager/catálogo em st.session_state
  → agente LangChain + ChatGroq
  → tools determinísticas
  → pandas
  → resultado estruturado e limitado
  → Streamlit: texto, tabela ou gráfico
```

As responsabilidades estão separadas em quatro áreas:

- `processing`: validação do ZIP, leitura de CSV e catálogo;
- `tools`: operações permitidas sobre pandas;
- `agents`: prompt, ChatGroq e orquestração das tools;
- `ui`: estado da sessão, upload, chat e visualização.

Não são usados multi-agent, RAG, banco vetorial, banco SQL, API web separada, frontend separado ou execução de código produzido pela LLM.

**Figura da arquitetura final:** `[INSERIR SOMENTE SE AJUDAR A APRESENTAÇÃO]`

## 7. Processamento dos dados

O ZIP é recebido diretamente do componente de upload. O processador verifica formato, limite e nomes de entradas, rejeitando caminho absoluto e componentes de travessia. Os arquivos são lidos diretamente do ZIP, sem `extractall`.

O leitor testa combinações controladas de:

- `utf-8-sig`, `utf-8`, `cp1252` e `latin-1`;
- separador `,` ou `;`;
- decimal `.` ou `,`.

Uma combinação só é aceita quando produz estrutura plausível; isso reduz o risco de interpretar o arquivo inteiro como uma coluna. O catálogo registra nome, dimensões, colunas, tipos, nulos, encoding e separador. Conversões numéricas e de data são conservadoras.

O `DataManager`, baseado no conceito validado na prova de conceito de Leonardo Vilela, mantém os DataFrames e metadados em memória durante a sessão. Cabeçalho e itens compartilham `CHAVE DE ACESSO`, mas as perguntas atuais não exigem join. Uma necessidade futura de relacionamento deverá ser implementada como tool explícita e testada; o agente não cria junções arbitrárias.

Um dicionário JSON ou CSV é associado aos datasets quando localizado. Sua ausência não interrompe a carga; a aplicação informa “Dicionário de dados não identificado no pacote.”

## 8. Agente inteligente

O agente funciona como orquestrador, não como mecanismo de cálculo. Seu prompt exige que toda afirmação numérica provenha de uma tool e o impede de:

- inventar números, colunas ou significados;
- calcular mentalmente quando existe uma tool apropriada;
- atribuir causalidade ou julgamento qualitativo a um ranking;
- responder pergunta externa como se a informação estivesse no dataset;
- revelar a chave Groq;
- executar código ou comandos enviados pelo usuário.

Quando faltar uma coluna ou informação, a resposta deve declarar a limitação. Perguntas materialmente ambíguas devem gerar pedido de esclarecimento. A LLM recebe somente schema, metadados, descrições, resultados limitados e amostras pequenas quando indispensáveis; o DataFrame completo nunca é enviado.

Para reduzir erros de escolha semântica, o agente possui um resolvedor local que
deriva do schema e do dicionário um plano de chamada sem resultados. Esse plano
separa emitente de destinatário, volume (`SUM` de quantidade) de contagem de
registros e valor das notas no cabeçalho de valor dos itens. Depois do tool
calling, dataset, colunas e operação registrados nos metadados são conferidos
antes de a resposta ser aceita.

## 9. Tools

| Tool | Operações principais |
|---|---|
| `list_datasets` | nomes e resumo do catálogo |
| `describe_dataset` | schema, tipos, nulos e dicionário |
| `aggregate_data` | soma, média, contagem, mínimo e máximo; agrupamento opcional |
| `top_n` | maiores ou menores grupos com N limitado |
| `filter_data` | filtros simples por operadores autorizados |
| `unique_values` | valores distintos limitados |
| `time_aggregation` | agregação por ano, mês ou ano-mês |

As tools validam nomes, tipos, operações e limites antes de acessar pandas. Seus resultados distinguem `scalar`, `table`, `series` e `error`, com resumo, colunas, linhas limitadas, sugestão de gráfico e metadados. Não são permitidos `eval`, `exec`, Python gerado, SQL arbitrário ou shell.

## 10. Fluxo da aplicação

1. O usuário abre a aplicação e encontra a interface de carga.
2. O ZIP enviado é validado e suas entradas seguras são catalogadas.
3. Cada CSV é lido com a combinação adequada de encoding, separador e decimal.
4. O dicionário é carregado quando disponível.
5. O `DataManager` e o histórico são registrados em `st.session_state`.
6. A interface de consulta é habilitada.
7. O usuário envia uma pergunta em linguagem natural.
8. O agente seleciona uma tool e fornece argumentos estruturados.
9. A tool calcula localmente e retorna um resultado limitado.
10. O agente redige a resposta fundamentada.
11. A interface apresenta texto e, quando aplicável, tabela ou Plotly.

## 11. Tratamento de erros

| Situação | Comportamento esperado |
|---|---|
| extensão enganosa ou arquivo não ZIP | rejeitar com mensagem clara |
| Zip Slip ou caminho absoluto | rejeitar o pacote sem extrair entradas |
| ZIP sem CSV | informar que nenhum CSV foi encontrado |
| CSV ilegível/ambíguo | identificar o arquivo e explicar que o formato não pôde ser lido |
| dicionário ausente | continuar e informar a ausência |
| dataset ou coluna inexistente | retornar erro estruturado e não calcular |
| pergunta ambígua | pedir esclarecimento |
| pergunta fora do escopo | declarar que os dados não sustentam a resposta |
| chave Groq ausente | orientar edição do `.env` |
| falha do provedor | informar indisponibilidade sem traceback bruto |

Logs devem ajudar no diagnóstico sem registrar credenciais ou despejar os dados completos.

## 12. Segurança

- proteção contra Zip Slip e rejeição de entrada insegura;
- nenhuma extração indiscriminada com `extractall`;
- limites de upload, entradas e linhas de resposta;
- nenhuma execução de código, SQL ou shell originado na pergunta;
- chave somente em variável de ambiente local;
- `.env`, datasets e ZIPs ignorados pelo Git;
- DataFrames restritos à sessão;
- contexto mínimo enviado à Groq;
- mensagens públicas sem segredo ou traceback bruto.

O script do pacote demo apenas lê `data/raw/202401_NFs.zip`, copia os dois CSVs para outro ZIP e adiciona um dicionário sem registros fiscais. Ele não modifica nem extrai o arquivo original.

## 13. Testes

Os testes determinísticos devem cobrir:

- ZIP válido, não ZIP, ZIP sem CSV e Zip Slip;
- UTF-8 com vírgula e CP1252 com ponto e vírgula;
- decimal com ponto e decimal com vírgula;
- soma, média, contagem, agrupamento e top N;
- filtro, valores únicos e coluna inexistente;
- contrato do agente com modelo falso, se aplicável, sem chamada real à Groq.
- resolução semântica de aliases, granularidade e `SUM` versus `COUNT` com
  catálogos sintéticos adversariais e com o dicionário demonstrativo.

**Comandos da validação final:**

```powershell
python scripts/validate_structure.py
pytest
python -m compileall -q src scripts
```

- **Saída do validador em 11/08/2026:** `Estrutura válida: todos os diretórios e arquivos obrigatórios estão presentes.`
- **Saída do pytest em 11/08/2026:** `139 passed in 3.81s` (sem chamada real à Groq).
- **Resultado de compilação/importação:** `compileall: OK`; imports dos módulos de configuração, processamento, tools, agente e UI concluídos.
- **Resultado do smoke test Streamlit:** `AppTest` iniciou sem exceção, processou um ZIP com CSV+dicionário, exibiu dois resumos tabulares e manteve o chat desabilitado sem `GROQ_API_KEY`.

## 14. Pergunta 1 — fornecedor com maior valor

**Pergunta:** “Qual fornecedor recebeu o maior valor no período?”

**Interpretação a confirmar na execução:** agrupar `RAZÃO SOCIAL EMITENTE` no dataset de cabeçalho e somar `VALOR NOTA FISCAL`, evitando duplicar o valor da nota pelas linhas de itens.

- **Pacote e período analisados:** `[PREENCHER APÓS EXECUÇÃO REAL]`
- **Resposta gerada pela aplicação:** `[NÃO PREENCHIDO — EXECUTAR A APLICAÇÃO]`
- **Tool e argumentos registrados:** `[PREENCHER COM O TOOL CALL REAL]`
- **Resultado determinístico de conferência:** `[NÃO PREENCHIDO — CAPTURAR SAÍDA REAL]`
- **Evidência:** `[INSERIR TABELA/CAPTURA E INFORMAR COMO O VALOR FOI CONFERIDO]`

## 15. Pergunta 2 — cinco maiores fornecedores

**Pergunta:** “Quais foram os cinco maiores fornecedores por valor total?”

**Interpretação a confirmar na execução:** ranking decrescente de `RAZÃO SOCIAL EMITENTE` pela soma de `VALOR NOTA FISCAL` no cabeçalho, com N igual a cinco.

- **Pacote e período analisados:** `[PREENCHER APÓS EXECUÇÃO REAL]`
- **Resposta gerada pela aplicação:** `[NÃO PREENCHIDO — EXECUTAR A APLICAÇÃO]`
- **Tool e argumentos registrados:** `[PREENCHER COM O TOOL CALL REAL]`
- **Resultado determinístico de conferência:** `[NÃO PREENCHIDO — CAPTURAR SAÍDA REAL]`
- **Evidência:** `[INSERIR TABELA/GRÁFICO DE BARRAS E CONFERÊNCIA]`

## 16. Pergunta 3 — produto com maior volume

**Pergunta:** “Qual produto apresentou o maior volume comprado?”

**Interpretação a confirmar na execução:** agrupar `DESCRIÇÃO DO PRODUTO/SERVIÇO` no dataset de itens, somar `QUANTIDADE` e ordenar de forma decrescente. “Volume” significa quantidade na unidade registrada, sem afirmar comparabilidade entre unidades incompatíveis.

- **Pacote e período analisados:** `[PREENCHER APÓS EXECUÇÃO REAL]`
- **Resposta gerada pela aplicação:** `[NÃO PREENCHIDO — EXECUTAR A APLICAÇÃO]`
- **Tool e argumentos registrados:** `[PREENCHER COM O TOOL CALL REAL]`
- **Resultado determinístico de conferência:** `[NÃO PREENCHIDO — CAPTURAR SAÍDA REAL]`
- **Evidência e ressalva de unidade:** `[INSERIR TABELA/CAPTURA E VERIFICAR UNIDADE]`

## 17. Pergunta 4 — total gasto em cada mês

**Pergunta:** “Qual foi o total gasto em cada mês?”

**Interpretação a confirmar na execução:** derivar ano-mês de `DATA EMISSÃO` e somar `VALOR NOTA FISCAL` no cabeçalho, sem replicar valores por item.

- **Pacote e período analisados:** `[PREENCHER APÓS EXECUÇÃO REAL]`
- **Resposta gerada pela aplicação:** `[NÃO PREENCHIDO — EXECUTAR A APLICAÇÃO]`
- **Tool e argumentos registrados:** `[PREENCHER COM O TOOL CALL REAL]`
- **Resultado determinístico de conferência:** `[NÃO PREENCHIDO — CAPTURAR SAÍDA REAL]`
- **Evidência:** `[INSERIR TABELA/GRÁFICO DE LINHA E CONFERÊNCIA]`

## 18. Validação adicional com dataset 202505

O arquivo local `data/raw/202505_NFe.zip` deve validar o cenário de maior volume, encoding CP1252/Windows-1252, separador `;` e decimal brasileiro `,`. Essa execução não deve enviar DataFrames completos à LLM.

- **Data e ambiente da execução:** 11/08/2026, Windows, Python 3.11.0, processo isolado no `.venv`.
- **Arquivos localizados:** `202505_NFe_NotaFiscal.csv` e `202505_NFe_NotaFiscalItem.csv`.
- **Encoding/separador/decimal identificados:** `cp1252`, `;` e `,` nos dois arquivos.
- **Linhas e colunas carregadas:** 150.976 × 21 e 549.431 × 27, totalizando 700.407 registros.
- **Tempo de carga:** 20,253 s na validação final desta máquina.
- **Memória observada ou método de aferição:** Windows `GetProcessMemoryInfo`; working set inicial 71,6 MiB, final 602,4 MiB e pico 1.096,2 MiB.
- **Consulta determinística executada:** `aggregate_data(operation="count")` nos dois datasets e `time_aggregation` no cabeçalho.
- **Resultado:** contagens de 150.976 notas e 549.431 itens; uma série mensal foi produzida, com zero chamada à LLM.
- **Limitação encontrada:** o pico próximo de 1,1 GiB confirma que o processamento pandas integral em memória exige folga de RAM, embora a carga tenha concluído sem arquitetura adicional.

## 19. Limitações

- Todo o conteúdo descompactado é mantido em memória; arquivos muito grandes podem exceder os recursos da máquina ou da hospedagem.
- A aplicação depende de acesso à Groq para interpretar novas perguntas.
- A linguagem natural pode ser ambígua; o agente deve pedir esclarecimento em vez de escolher silenciosamente entre interpretações materiais.
- As tools cobrem operações frequentes, não uma linguagem analítica irrestrita.
- Detecção de formato e conversão de tipos são heurísticas controladas e podem exigir ajuste para CSVs incomuns.
- Sem dicionário, o agente conhece nomes e tipos observados, mas não deve inferir significados de negócio não demonstrados.
- Somar quantidades de produtos com unidades diferentes pode não representar um volume fisicamente comparável.
- O estado não é persistente e desaparece ao encerrar a sessão.

**Limitações adicionais observadas nos testes finais:** o dataset 202505 atingiu pico de working set de aproximadamente 1,1 GiB. A validação real do texto produzido pela Groq continua dependente de uma chave local e deve ser feita pela equipe antes de preencher as seções 14–17.

## 20. Conclusão

O desenho do MVP separa interpretação de linguagem e cálculo: o agente decide qual ferramenta usar, enquanto pandas produz os resultados verificáveis. A solução mantém um fluxo didático, evita execução arbitrária e suporta os dois formatos oficiais sem introduzir infraestrutura desnecessária.

**Conclusão após validação final e confirmação das quatro respostas:** `[ATUALIZAR SOMENTE APÓS EXECUTAR TODOS OS ITENS DO CHECKLIST]`
