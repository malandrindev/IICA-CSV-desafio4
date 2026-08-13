# Checklist de entrega

Prazo oficial: **16/08/2026 às 23h59**.

As caixas marcadas abaixo foram verificadas localmente em 11/08/2026. Itens que dependem da Groq, de revisão humana ou do empacotamento final permanecem abertos.

## Instalação e configuração

- [x] Ambiente inicialmente vazio criado com Python 3.11 e dependências instaladas.
- [x] `python -m pip install -r requirements.txt` conclui sem conflito.
- [x] `.env.example` corresponde às variáveis lidas pelo código.
- [x] `GROQ_API_KEY` ausente gera orientação clara, sem traceback bruto.
- [x] `.env`, dados oficiais, ZIPs e credenciais não estão rastreados.
- [x] A aplicação inicia no smoke test Streamlit/AppTest pelo ponto de entrada documentado.

## Carga e processamento

- [x] Upload aceita um ZIP válido diretamente do Streamlit.
- [x] Arquivo que não é ZIP é rejeitado com mensagem compreensível.
- [x] ZIP sem CSV é rejeitado com mensagem compreensível.
- [x] Zip Slip/caminho absoluto é rejeitado e nenhuma entrada é extraída.
- [x] Mais de um CSV e CSVs em subdiretório são encontrados.
- [x] Limites de upload e de resultados são aplicados.
- [x] UTF-8/UTF-8-SIG funciona.
- [x] CP1252/Latin-1 funciona.
- [x] Separador vírgula funciona.
- [x] Separador ponto e vírgula funciona.
- [x] Decimal com ponto funciona.
- [x] Decimal com vírgula funciona.
- [x] Uma leitura incorreta em coluna única é evitada.
- [x] Metadados exibem linhas, colunas, encoding e separador.
- [x] Dicionário é carregado quando presente.
- [x] Ausência do dicionário não interrompe a carga e exibe a mensagem prevista.
- [x] `DataManager` mantém DataFrames e catálogo somente na sessão.

## Agente e tools

- [x] Existe exatamente um agente funcional criado com LangChain 1.x `create_agent`.
- [x] `ChatGroq` usa `GROQ_MODEL` e temperatura zero.
- [x] O loop real do agente chama tools em teste com modelo falso, sem rede.
- [x] `list_datasets` e `describe_dataset` retornam metadados corretos.
- [x] `aggregate_data` cobre soma, média, contagem, mínimo, máximo e agrupamento.
- [x] `top_n`, `filter_data`, `unique_values` e `time_aggregation` funcionam.
- [x] Coluna/dataset/operação inexistente retorna erro estruturado.
- [x] Resultados têm limites e contrato estruturado para texto, tabela ou série.
- [x] Cálculos são executados localmente com pandas.
- [x] Nenhum DataFrame completo é enviado à LLM pelas tools.
- [x] Não existem `eval`, `exec`, Python/SQL arbitrário ou shell orientado pelo usuário.
- [ ] Pergunta ambígua pede esclarecimento quando necessário.
- [ ] Pergunta fora dos dados não produz fatos inventados.
- [x] Toda afirmação numérica demonstrada nos testes é sustentada por resultado de tool.

## Interface

- [x] A Interface A mostra arquivos, datasets, dimensões, formato e dicionário.
- [x] A Interface B fica indisponível antes de uma carga válida.
- [x] Chat usa `st.chat_message`, `st.chat_input` e histórico em `st.session_state`.
- [x] Resposta textual funciona no contrato testado do agente.
- [x] Resultado tabular funciona.
- [x] Renderização Plotly de barras/linha funciona para o contrato estruturado.
- [x] Erros esperados não exibem traceback bruto ao usuário.

## Testes e validações locais

- [x] `python scripts/validate_structure.py` passa.
- [x] `pytest` passa sem chamada real à Groq.
- [x] `python -m compileall -q src scripts` passa.
- [x] Smoke test do Streamlit conclui sem erro de importação/inicialização.
- [x] `scripts/build_demo_package.py` gera o pacote demo sem alterar `data/raw`.
- [x] `data/raw/202401_NFs.zip` carrega os dois CSVs e suporta as operações das perguntas de aceitação.
- [x] `data/raw/202505_NFe.zip` valida volume, CP1252, `;` e decimal `,`.
- [x] Uso de memória/tempo do dataset 202505 foi medido e documentado.

## Evidências e documentação

- [ ] Pergunta 1 possui resposta real e evidência determinística.
- [ ] Pergunta 2 possui resposta real e evidência determinística.
- [ ] Pergunta 3 possui resposta real e evidência determinística.
- [ ] Pergunta 4 possui resposta real e evidência determinística.
- [x] README corresponde aos comandos e ao comportamento final.
- [x] Arquitetura, decisões, segurança, erros e limitações estão atualizados.
- [ ] `docs/relatorio_tecnico/relatorio.md` foi preenchido sem números inventados.
- [ ] O relatório final foi exportado em PDF e revisado.
- [x] O notebook de Leonardo Vilela permanece preservado em `workspaces/`.
- [x] Nenhuma funcionalidade exigida existe somente em `workspaces/`.

## Pacote final

- [ ] ZIP de entrega contém todo o código-fonte necessário.
- [ ] ZIP de entrega não contém `.env`, credenciais, ambiente virtual ou dados proibidos.
- [ ] Instalação foi repetida a partir de uma cópia limpa.
- [ ] `git status` foi revisado antes do empacotamento.
- [ ] E-mail será enviado pelo representante com cópia aos integrantes.
- [ ] Assunto do e-mail: `InsurMinds – Desafio 4`.
- [ ] Corpo do e-mail identifica corretamente o grupo.
