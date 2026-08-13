# Decisões arquiteturais

As decisões abaixo valem para o MVP do Desafio 4. Novas decisões devem registrar contexto, escolha, consequência e data.

## 001 — Um agente orquestrador

**Status:** aceita em 11/08/2026.

**Decisão:** usar um único agente de consulta.

**Motivo:** atende ao enunciado, reduz coordenação desnecessária e torna o fluxo explicável durante a apresentação.

**Consequência:** especialização ocorre em tools determinísticas, não em novos agentes.

## 002 — LangChain 1.x e Groq

**Status:** aceita em 11/08/2026.

**Decisão:** criar o agente com `langchain.agents.create_agent` e usar `langchain-groq`/`ChatGroq`, modelo padrão `llama-3.3-70b-versatile` e temperatura zero.

**Motivo:** LangChain é aceito no enunciado e a Groq é o provedor definido para este MVP.

**Consequência:** `langchain-openai` e configuração OpenAI não fazem parte do projeto. A lógica tabular permanece desacoplada do provedor.

## 003 — Uma aplicação Streamlit para as duas interfaces

**Status:** aceita em 11/08/2026.

**Decisão:** a aplicação contém uma área de carga e uma área de consulta, habilitada somente após carga válida.

**Motivo:** Streamlit oferece upload, chat, tabelas e Plotly com pouco código de infraestrutura.

**Consequência:** o estado e o histórico são mantidos em `st.session_state` e não sobrevivem ao encerramento da sessão.

## 004 — pandas e processamento em memória

**Status:** aceita, com validação de volume.

**Decisão:** manter os DataFrames em um `DataManager` de sessão, sem banco de dados.

**Motivo:** é a solução mais simples para o escopo e permite reaproveitar o conceito validado na prova de conceito.

**Consequência:** o upload padrão é limitado por `APP_MAX_UPLOAD_MB=500`; o dataset 202505 deve medir a viabilidade real e qualquer limitação de memória deve ser documentada.

## 005 — Dados e credenciais fora do versionamento

**Status:** aceita em 11/08/2026.

**Decisão:** ignorar `.env`, segredos Streamlit, dados brutos/processados, ZIPs e saídas geradas.

**Motivo:** proteger credenciais e impedir publicação indevida dos dados do curso.

**Consequência:** o repositório inclui apenas `.env.example`, código e um dicionário de dados sem registros fiscais. Datasets precisam existir localmente.

## 006 — ZIP processado sem extração insegura

**Status:** aceita em 11/08/2026.

**Decisão:** ler entradas com `zipfile`, validar nomes e tamanhos e nunca chamar `extractall` sobre o upload.

**Motivo:** impedir Zip Slip, gravação fora do destino e extração desnecessária de dados.

**Consequência:** CSVs e dicionário são lidos como streams; caminho absoluto e componentes `..` causam rejeição compreensível.

## 007 — Detecção controlada de formato CSV

**Status:** aceita em 11/08/2026.

**Decisão:** testar somente combinações suportadas de encoding, delimitador e decimal e validar a estrutura resultante.

**Motivo:** os pacotes oficiais 202401 e 202505 usam convenções diferentes e uma leitura que não lança exceção ainda pode estar errada.

**Consequência:** encoding e separador escolhidos integram os metadados. Conversões inseguras não substituem valores originais.

## 008 — Dicionário recomendado, mas ausência não fatal

**Status:** aceita em 11/08/2026.

**Decisão:** procurar e carregar um dicionário JSON/CSV; sem ele, manter a carga e informar sua ausência.

**Motivo:** o enunciado prevê dicionário, mas os ZIPs oficiais de validação podem não incluí-lo.

**Consequência:** o pacote demo adiciona `dicionario_dados.json`; fora dele, o agente deve evitar inventar semântica.

## 009 — Tools determinísticas e resultados estruturados

**Status:** aceita em 11/08/2026.

**Decisão:** restringir o agente a tools de catálogo, agregação, ranking, filtro, valores únicos e tempo, retornando escalares ou tabelas limitadas.

**Motivo:** números precisam ser reproduzíveis e resultados grandes não devem entrar no contexto da LLM.

**Consequência:** `eval`, `exec`, código Python gerado, SQL livre e comandos shell são proibidos. Novas operações exigem implementação e teste explícitos.

## 010 — Relação explícita entre cabeçalho e itens

**Status:** aceita em 11/08/2026.

**Decisão:** não oferecer join genérico. A relação conhecida por `CHAVE DE ACESSO` só poderá ser usada por uma operação determinística criada e testada para uma necessidade concreta.

**Motivo:** algumas análises podem combinar nota e item, mas joins arbitrários definidos pela LLM aumentariam risco e ambiguidade.

**Consequência:** as perguntas atuais usam diretamente cabeçalho ou itens. O agente não constrói código de junção; uma análise futura que dependa do relacionamento exigirá nova tool explícita.

## 011 — Contexto mínimo para a LLM

**Status:** aceita em 11/08/2026.

**Decisão:** enviar apenas schema, metadados, descrições, resultados de tools e pequenas amostras quando necessárias.

**Motivo:** reduzir exposição de dados, tokens, latência e risco de respostas baseadas em amostragem inadequada.

**Consequência:** toda análise numérica ocorre localmente; o DataFrame completo nunca é serializado para a Groq.

## 012 — Resolução semântica orientada pelo dicionário

**Status:** aceita em 11/08/2026.

**Decisão:** resolver localmente intenções de negócio inequívocas a partir do
schema e das descrições do dicionário, produzindo um plano de tool sem dados ou
resultados. Validar os metadados da tool executada contra esse plano.

**Motivo:** grounding numérico não é suficiente quando a LLM escolhe uma coluna
semanticamente errada ou confunde `SUM` de uma medida com `COUNT` de registros.

**Consequência:** fornecedor/emitente e destinatário/cliente permanecem papéis
distintos; volume comprado soma quantidade; total das notas usa o cabeçalho;
valor de itens usa o dataset de itens somente quando solicitado explicitamente.
Consultas não reconhecidas continuam sob o fluxo normal do agente e ambiguidades
materiais devem gerar pedido de esclarecimento.

## 013 — Contrato tolerante para parâmetros e evidências plurais

**Status:** aceita em 11/08/2026.

**Decisão:** permitir `n` inteiro ou string no JSON Schema de `top_n`, normalizar
localmente e preservar todos os `ToolResult` necessários à resposta.

**Motivo:** provedores podem serializar números de tool calls como strings; além
disso, uma resposta com fornecedor e cliente exige duas evidências distintas.

**Consequência:** entradas inválidas continuam gerando erro estruturado, e a UI
persiste uma lista de evidências com fallback para o formato singular anterior.
