# Decisões arquiteturais

Registre aqui decisões que afetem mais de um componente. Inclua contexto, decisão, consequências e data.

## 001 — Um agente no primeiro MVP

**Status:** aceita.

**Decisão:** implementar primeiro um único agente de consulta com ferramentas determinísticas.

**Motivo:** atende ao requisito mínimo, reduz coordenação desnecessária e facilita testar a fidelidade das respostas.

## 002 — LangChain como framework obrigatório

**Status:** aceita.

**Decisão:** usar LangChain, uma das opções expressamente aceitas no enunciado.

**Consequência:** manter a lógica de dados desacoplada do framework para permitir troca futura sem reescrever processamento e UI.

## 003 — Streamlit para as duas interfaces

**Status:** aceita.

**Decisão:** uma aplicação Streamlit terá etapas claras de carga e consulta.

**Motivo:** entrega rápida, demonstração simples e suporte nativo a tabelas e gráficos.

## 004 — Processamento em memória no MVP

**Status:** aceita, com revisão após testes de volume.

**Decisão:** usar pandas e estado de sessão antes de adicionar banco de dados.

**Consequência:** definir limite de upload e comunicar limitações de volume no relatório.

## 005 — Dados e credenciais fora do versionamento

**Status:** aceita.

**Decisão:** ignorar entradas, dados processados, saídas geradas e .env. Somente pequenas amostras públicas ou sintéticas poderão ser incluídas após revisão.
