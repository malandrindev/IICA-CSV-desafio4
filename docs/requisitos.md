# Requisitos do Desafio 4

Resumo fiel do enunciado nas páginas impressas 11 a 15 do documento Desafios.pdf. Este arquivo não substitui o documento oficial.

## Objetivo

Desenvolver um ou mais agentes capazes de responder perguntas em linguagem natural sobre conjuntos de dados em arquivos CSV, demonstrando agentes, LLMs, ferramentas, orquestração e automação.

## Interfaces mínimas

### A — Carga dos dados

- Receber um arquivo ZIP.
- O ZIP deve conter um ou mais arquivos CSV.
- O ZIP deve conter um dicionário de dados que descreva as colunas.
- Após o processamento, disponibilizar a interface de consulta.

### B — Consulta

- Receber perguntas em linguagem natural.
- Interpretar a solicitação por meio de pelo menos um agente.
- Consultar os dados carregados.
- Apresentar resposta em texto, tabela, gráfico ou combinação desses formatos.

## Requisitos mínimos

- [ ] Upload de ZIP com um ou mais CSVs.
- [ ] Processamento automático dos arquivos.
- [ ] Interface para perguntas em linguagem natural.
- [ ] Pelo menos um agente inteligente.
- [ ] Respostas corretas e sustentadas pelos dados carregados.
- [ ] Texto, tabela ou gráfico conforme apropriado.
- [ ] Pelo menos uma ferramenta apresentada no curso.

Ferramentas aceitas no enunciado: AutoGen, Pydantic AI, LangChain, LangFlow, LlamaIndex, CrewAI ou n8n. A decisão inicial deste projeto é LangChain.

## Boas práticas valorizadas

- Separar interface, agentes, ferramentas e processamento.
- Organizar o projeto em módulos.
- Criar prompts claros.
- Tratar erros de entrada e perguntas inválidas.
- Explicar no relatório como o agente decide.
- Manter código organizado e documentado.
- Ocultar credenciais e chaves de API.

## Entregáveis

- Relatório técnico PDF com framework, arquitetura, agentes, fluxo e pelo menos quatro perguntas com respostas.
- ZIP contendo todo o código-fonte.
- Link de repositório público no GitHub, opcional para este desafio.

## Restrições e conclusão

- As respostas não podem ser produzidas manualmente em ChatGPT, Claude ou Gemini; devem sair da aplicação criada pelo grupo.
- Múltiplos agentes e interface sofisticada não são obrigatórios.
- A entrega está completa quando execução, upload, consulta baseada nos dados, relatório, código-fonte e compreensão da arquitetura puderem ser demonstrados.
- Prazo: **16/08/2026 às 23h59**.
