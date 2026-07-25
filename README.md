# IICA-CSV — Desafio 4

Estrutura colaborativa para o desafio **Interface Inteligente para Consulta de Arquivos CSV**, do InsurMinds/I2A2.

## Objetivo

Construir um MVP que receba um arquivo ZIP com um ou mais CSVs e um dicionário de dados, processe esse conteúdo e permita consultas em linguagem natural por meio de pelo menos um agente inteligente.

A resposta deve usar os dados carregados e pode ser apresentada como texto, tabela, gráfico ou uma combinação desses formatos.

## Escopo do MVP

- Interface de carga do arquivo ZIP.
- Processamento automático dos CSVs e do dicionário de dados.
- Interface de consulta em linguagem natural.
- Um agente funcional, inicialmente implementado com LangChain.
- Ferramentas determinísticas para consultar e resumir os dados.
- Respostas em texto, tabela ou gráfico, conforme a pergunta.
- Tratamento de arquivo inválido, pergunta inválida e falhas do modelo.
- Registro de pelo menos quatro perguntas e respectivas respostas para o relatório.

> Estado atual: estrutura inicial do projeto. As funcionalidades do MVP serão desenvolvidas colaborativamente.

## Prazo

**16/08/2026 às 23h59.**

## Tecnologias propostas

- Python 3.11 ou superior
- Streamlit para as interfaces
- LangChain para o agente
- pandas para processamento tabular
- Plotly para gráficos
- pytest para testes

## Quickstart

No PowerShell:

    py -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    Copy-Item .env.example .env
    python scripts/validate_structure.py
    pytest
    streamlit run src/iica_csv/ui/app.py

Preencha a chave do provedor de LLM apenas no arquivo local .env. Nunca publique credenciais.

## Estrutura

    src/iica_csv/          solução compartilhada
      agents/              agente, prompts e orquestração
      processing/          leitura, validação e preparação dos dados
      tools/               operações determinísticas usadas pelo agente
      ui/                  carga e consulta pelo usuário
    tests/                 testes automatizados
    data/                  dados locais ou amostras permitidas
    docs/                  requisitos, arquitetura e relatório
    notebooks/shared/      exploração que beneficia toda a equipe
    outputs/               tabelas, figuras e artefatos gerados
    workspaces/            rascunhos individuais, não canônicos
    scripts/               utilitários do projeto

A solução oficial deve sempre ser integrada em src, docs ou notebooks/shared. As pastas em workspaces são áreas temporárias de experimentação e não substituem branches, revisão de código ou documentação compartilhada.

## Colaboração

Consulte CONTRIBUTING.md para o fluxo de trabalho e TASKS.md para a divisão inicial. Mudanças pequenas, revisáveis e acompanhadas de testes são preferíveis.

## Entrega prevista

- Relatório técnico em PDF com framework, arquitetura, agentes, fluxo e quatro perguntas com respostas.
- ZIP contendo todo o código-fonte.
- Repositório público no GitHub é opcional pelo enunciado, mas este projeto será mantido de forma colaborativa.

## Licença

MIT. Consulte LICENSE.
