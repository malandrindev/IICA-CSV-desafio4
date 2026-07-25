# Plano inicial de trabalho

A divisão abaixo organiza responsáveis principais, sem criar silos. Todos podem revisar, testar e contribuir em qualquer área.

## Vitor — ingestão e integração

- [ ] Definir e validar o contrato do ZIP de entrada.
- [ ] Implementar extração segura do ZIP e descoberta de CSVs/dicionário.
- [ ] Implementar leitura, normalização e catálogo de conjuntos de dados.
- [ ] Integrar configuração, tratamento de erros e fluxo ponta a ponta.
- [ ] Apoiar a consolidação do relatório técnico.

## leo-vilelela — agente e ferramentas

- [ ] Projetar prompt e fluxo do agente em LangChain.
- [ ] Implementar ferramentas determinísticas de consulta e agregação.
- [ ] Impedir respostas sem sustentação nos dados carregados.
- [ ] Tratar perguntas inválidas, ambíguas e fora do escopo.
- [ ] Criar testes do agente e das ferramentas com LLM simulada.

## wabassis — interface, visualização e qualidade

- [ ] Implementar a interface de upload e feedback de processamento.
- [ ] Implementar a interface de perguntas e histórico da sessão.
- [ ] Renderizar respostas em texto, tabela e gráfico.
- [ ] Criar testes de interface e cenários de aceitação.
- [ ] Organizar exemplos, evidências e instruções de execução.

## Equipe — marcos compartilhados

- [ ] Escolher uma amostra pública ou sintética e documentar sua origem.
- [ ] Demonstrar quatro perguntas com respostas verificadas.
- [ ] Revisar segurança, credenciais e tratamento de dados.
- [ ] Validar instalação limpa e execução do MVP.
- [ ] Finalizar relatório PDF e ZIP do código-fonte.
- [ ] Conferir docs/checklist_entrega.md antes do prazo.
