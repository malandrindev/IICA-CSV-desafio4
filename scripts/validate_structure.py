"""Valida se a estrutura mínima colaborativa do projeto está presente."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRECTORIES = (
    "src/iica_csv/agents",
    "src/iica_csv/processing",
    "src/iica_csv/tools",
    "src/iica_csv/ui",
    "tests",
    "data/raw",
    "data/processed",
    "data/samples",
    "docs/relatorio_tecnico",
    "notebooks/shared",
    "outputs/figures",
    "outputs/tables",
    "outputs/entrega",
    "workspaces/vitor",
    "workspaces/leo-vilelela",
    "workspaces/wabassis",
    ".github",
)

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "TASKS.md",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".env.example",
    "requirements.txt",
    "docs/requisitos.md",
    "docs/arquitetura.md",
    "docs/decisoes.md",
    "docs/checklist_entrega.md",
    "docs/relatorio_tecnico/README.md",
    "notebooks/shared/README.md",
    "workspaces/vitor/README.md",
    "workspaces/leo-vilelela/README.md",
    "workspaces/wabassis/README.md",
    ".github/pull_request_template.md",
)


def main() -> int:
    missing = [
        f"diretório: {item}"
        for item in REQUIRED_DIRECTORIES
        if not (ROOT / item).is_dir()
    ]
    missing.extend(
        f"arquivo: {item}" for item in REQUIRED_FILES if not (ROOT / item).is_file()
    )

    if missing:
        print("Estrutura incompleta:")
        for item in missing:
            print(f"- {item}")
        return 1

    print("Estrutura válida: todos os diretórios e arquivos obrigatórios estão presentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
