"""Monta o pacote demo 202401 sem extrair ou alterar os dados brutos."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = ROOT / "data" / "raw"
DEFAULT_SOURCE = RAW_DIRECTORY / "202401_NFs.zip"
DEFAULT_OUTPUT = ROOT / "outputs" / "entrega" / "pacote_demo_202401.zip"
DEFAULT_DICTIONARY = (
    ROOT / "data" / "dictionaries" / "dicionario_dados_202401.json"
)
EXPECTED_CSVS = (
    "202401_NFs_Cabecalho.csv",
    "202401_NFs_Itens.csv",
)
DICTIONARY_ARCHIVE_NAME = "dicionario_dados.json"


class DemoPackageError(ValueError):
    """Erro de entrada esperado durante a montagem do pacote demo."""


def _is_within(path: Path, directory: Path) -> bool:
    """Retorna se ``path`` está dentro de ``directory`` após resolução."""

    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _safe_member_name(filename: str) -> PurePosixPath:
    """Normaliza um nome de entrada e rejeita componentes inseguros."""

    normalized = filename.replace("\\", "/")
    member_path = PurePosixPath(normalized)
    parts = member_path.parts
    has_drive_prefix = bool(parts) and parts[0].endswith(":")
    if (
        not normalized
        or member_path.is_absolute()
        or has_drive_prefix
        or ".." in parts
    ):
        raise DemoPackageError(
            f"O ZIP de origem contém caminho inseguro: {filename!r}."
        )
    return member_path


def _find_expected_entries(
    archive: zipfile.ZipFile,
) -> dict[str, zipfile.ZipInfo]:
    """Localiza de forma inequívoca os dois CSVs esperados no ZIP."""

    matches: dict[str, list[zipfile.ZipInfo]] = {name: [] for name in EXPECTED_CSVS}
    for info in archive.infolist():
        member_path = _safe_member_name(info.filename)
        if info.is_dir():
            continue
        basename = member_path.name
        if basename in matches:
            matches[basename].append(info)

    missing = [name for name, entries in matches.items() if not entries]
    if missing:
        formatted = ", ".join(missing)
        raise DemoPackageError(
            f"O ZIP de origem não contém o(s) CSV(s) esperado(s): {formatted}."
        )

    duplicated = [name for name, entries in matches.items() if len(entries) > 1]
    if duplicated:
        formatted = ", ".join(duplicated)
        raise DemoPackageError(
            f"O ZIP de origem contém nomes de CSV duplicados: {formatted}."
        )

    selected = {name: entries[0] for name, entries in matches.items()}
    for name, info in selected.items():
        if info.file_size <= 0:
            raise DemoPackageError(f"O CSV esperado está vazio: {name}.")
        if info.flag_bits & 0x1:
            raise DemoPackageError(f"O CSV esperado está criptografado: {name}.")
    return selected


def _load_dictionary(path: Path) -> bytes:
    """Valida o JSON do dicionário e devolve seus bytes originais."""

    if not path.is_file():
        raise DemoPackageError(f"Dicionário não encontrado: {path}")
    if path.suffix.lower() != ".json":
        raise DemoPackageError("O dicionário do pacote demo deve ser um arquivo JSON.")

    payload = path.read_bytes()
    try:
        parsed = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DemoPackageError(f"Dicionário JSON inválido: {path}") from exc

    if not isinstance(parsed, dict) or not parsed:
        raise DemoPackageError("O dicionário JSON deve conter um objeto não vazio.")
    return payload


def build_demo_package(source: Path, output: Path, dictionary: Path) -> Path:
    """Cria um novo ZIP com os dois CSVs oficiais e o dicionário demo.

    O arquivo de origem é aberto apenas para leitura. As entradas são lidas por
    ``ZipFile.open`` e gravadas com ``writestr`` no ZIP de saída; nenhum CSV é
    extraído para o sistema de arquivos.
    """

    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    dictionary = dictionary.expanduser().resolve()
    raw_directory = RAW_DIRECTORY.resolve()

    if not source.is_file():
        raise DemoPackageError(f"ZIP de origem não encontrado: {source}")
    if output.suffix.lower() != ".zip":
        raise DemoPackageError("O caminho de saída deve terminar em .zip.")
    if output == source:
        raise DemoPackageError("A saída não pode sobrescrever o ZIP de origem.")
    if _is_within(output, raw_directory):
        raise DemoPackageError(
            "A saída não pode ser criada dentro de data/raw; dados brutos são somente leitura."
        )
    if not zipfile.is_zipfile(source):
        raise DemoPackageError(f"O arquivo de origem não é um ZIP válido: {source}")

    dictionary_payload = _load_dictionary(dictionary)
    output.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with zipfile.ZipFile(source, mode="r") as source_archive:
            selected = _find_expected_entries(source_archive)

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{output.stem}-",
                suffix=".tmp",
                dir=output.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)

            with zipfile.ZipFile(
                temporary_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as target_archive:
                for csv_name in EXPECTED_CSVS:
                    with source_archive.open(selected[csv_name], mode="r") as stream:
                        target_archive.writestr(csv_name, stream.read())
                target_archive.writestr(
                    DICTIONARY_ARCHIVE_NAME,
                    dictionary_payload,
                )

        temporary_path.replace(output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return output


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Gera um ZIP demo 202401 com os dois CSVs oficiais e um dicionário, "
            "sem extrair nem modificar data/raw."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"ZIP oficial de origem (padrão: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"ZIP demo a criar (padrão: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--dictionary",
        type=Path,
        default=DEFAULT_DICTIONARY,
        help=f"Dicionário JSON a incluir (padrão: {DEFAULT_DICTIONARY})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        output = build_demo_package(args.source, args.output, args.dictionary)
    except (DemoPackageError, OSError, zipfile.BadZipFile) as exc:
        print(f"Erro ao criar pacote demo: {exc}", file=sys.stderr)
        return 1

    print(f"Pacote demo criado: {output}")
    print("Arquivos incluídos:")
    for name in (*EXPECTED_CSVS, DICTIONARY_ARCHIVE_NAME):
        print(f"- {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
