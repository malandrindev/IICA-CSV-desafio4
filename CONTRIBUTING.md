# Como contribuir

## Fluxo recomendado

1. Atualize sua branch a partir da branch principal.
2. Crie uma branch curta: feat/tema, fix/tema, docs/tema ou test/tema.
3. Faça commits pequenos e objetivos, de preferência no padrão Conventional Commits.
4. Execute os testes e o validador de estrutura.
5. Abra um pull request explicando contexto, solução e como validar.
6. Integre a mudança após revisão de pelo menos outro integrante sempre que possível.

## Comandos de validação

    python scripts/validate_structure.py
    pytest

## Organização do trabalho

- Código oficial: src/iica_csv.
- Documentação oficial: docs.
- Exploração compartilhada: notebooks/shared.
- Rascunhos pessoais: workspaces/<integrante>.
- Um rascunho só passa a integrar a solução quando for movido para a área compartilhada, revisado e testado.

## Regras essenciais

- Não versione .env, tokens, chaves ou credenciais.
- Não publique dados pessoais, confidenciais ou arquivos recebidos sem autorização.
- Não inclua o PDF do enunciado nem grandes arquivos gerados no repositório.
- Atualize documentação e testes quando alterar comportamento.
- Prefira componentes pequenos e responsabilidades bem separadas.
- Registre decisões arquiteturais relevantes em docs/decisoes.md.
