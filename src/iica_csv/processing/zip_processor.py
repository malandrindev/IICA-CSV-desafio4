"""Validação e processamento seguro de pacotes ZIP enviados pela interface."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Any, BinaryIO, Iterator, Mapping
import unicodedata
import zlib
from zipfile import BadZipFile, ZipFile, ZipInfo

import pandas as pd

from iica_csv.config import Settings, get_settings

from .csv_reader import CSVReadError, CSVReader
from .data_manager import DataManager


MEBIBYTE = 1024 * 1024
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
MISSING_DICTIONARY_WARNING = "Dicionário de dados não identificado no pacote."


class ZipProcessingError(ValueError):
    """Erro amigável no upload ou processamento do pacote."""


class InvalidZipError(ZipProcessingError):
    """O upload não possui extensão, assinatura ou estrutura ZIP válida."""


class ZipSecurityError(ZipProcessingError):
    """O pacote contém uma entrada potencialmente insegura."""


class ZipLimitError(ZipProcessingError):
    """O pacote excede um limite de tamanho, quantidade ou compressão."""


class CSVNotFoundError(ZipProcessingError):
    """Nenhum CSV analítico foi localizado no pacote."""


@dataclass(slots=True)
class ProcessedPackage:
    """Contrato devolvido à interface depois de uma carga bem-sucedida."""

    data_manager: DataManager
    files: list[str]
    csv_files: list[str]
    dictionary_files: list[str]
    warnings: list[str]
    dictionary_found: bool


def _normalise_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _safe_member_name(info: ZipInfo) -> str:
    raw_name = info.filename.replace("\\", "/")
    if not raw_name or "\x00" in raw_name:
        raise ZipSecurityError("O ZIP contém uma entrada com nome inválido.")
    raw_parts = raw_name.split("/")
    path = PurePosixPath(raw_name)
    if (
        path.is_absolute()
        or raw_name.startswith("/")
        or any(part == ".." for part in raw_parts)
        or (raw_parts and ":" in raw_parts[0])
    ):
        raise ZipSecurityError(
            f"Caminho inseguro identificado no ZIP: '{info.filename}'."
        )
    canonical = "/".join(part for part in raw_parts if part not in ("", "."))
    if not canonical and not info.is_dir():
        raise ZipSecurityError("O ZIP contém uma entrada com nome inválido.")
    return canonical


def _is_symlink(info: ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(unix_mode)


def _is_dictionary_file(filename: str) -> bool:
    path = PurePosixPath(filename)
    suffix = path.suffix.casefold()
    normalised_stem = _normalise_text(path.stem).replace("-", "_")
    if suffix not in {".csv", ".json"}:
        return False
    markers = (
        "dicionario",
        "dictionary",
        "data_dictionary",
        "schema",
        "metadados",
        "metadata",
    )
    return any(marker in normalised_stem for marker in markers)


def _decode_dictionary_json(raw: bytes) -> Any:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ZipProcessingError(f"Dicionário JSON inválido: {exc.msg}.") from exc
    raise ZipProcessingError("Não foi possível decodificar o dicionário JSON.")


def _records_without_nan(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    clean = dataframe.astype(object).where(pd.notna(dataframe), None)
    return clean.to_dict(orient="records")


def _name_variants(filename: str) -> set[str]:
    path = PurePosixPath(filename.replace("\\", "/"))
    return {
        filename.replace("\\", "/").casefold(),
        path.name.casefold(),
        path.stem.casefold(),
    }


def _matching_mapping_value(mapping: Mapping[Any, Any], filename: str) -> Any:
    wanted = _name_variants(filename)
    for key, value in mapping.items():
        if _name_variants(str(key)) & wanted:
            return value
    return None


def _dictionary_from_records(records: list[Any], filename: str) -> Any:
    rows = [row for row in records if isinstance(row, Mapping)]
    if not rows:
        return None
    normalised_keys = {
        _normalise_text(key).replace(" ", "_"): key for key in rows[0]
    }
    dataset_key = next(
        (
            normalised_keys[key]
            for key in ("arquivo", "dataset", "nome_arquivo", "file", "filename")
            if key in normalised_keys
        ),
        None,
    )
    column_key = next(
        (
            normalised_keys[key]
            for key in ("coluna", "campo", "column", "nome_coluna")
            if key in normalised_keys
        ),
        None,
    )
    description_key = next(
        (
            normalised_keys[key]
            for key in ("descricao", "description")
            if key in normalised_keys
        ),
        None,
    )
    type_key = next(
        (
            normalised_keys[key]
            for key in ("tipo_semantico", "tipo", "type")
            if key in normalised_keys
        ),
        None,
    )
    wanted = _name_variants(filename)
    if dataset_key is not None:
        rows = [
            row
            for row in rows
            if row.get(dataset_key) is not None
            and bool(_name_variants(str(row[dataset_key])) & wanted)
        ]
    if not rows:
        return None
    if column_key is None:
        return {"registros": rows}
    columns: dict[str, dict[str, Any]] = {}
    for row in rows:
        column = row.get(column_key)
        if column is None:
            continue
        details: dict[str, Any] = {}
        if description_key is not None and row.get(description_key) is not None:
            details["descricao"] = row[description_key]
        if type_key is not None and row.get(type_key) is not None:
            details["tipo_semantico"] = row[type_key]
        columns[str(column)] = details
    return {"colunas": columns, "registros": rows}


def _dictionary_for_dataset(
    dictionaries: Mapping[str, Any], dataset_filename: str
) -> Any:
    for payload in dictionaries.values():
        if isinstance(payload, Mapping):
            datasets = payload.get("datasets")
            if isinstance(datasets, Mapping):
                match = _matching_mapping_value(datasets, dataset_filename)
                if match is not None:
                    return match
            direct_match = _matching_mapping_value(payload, dataset_filename)
            if direct_match is not None:
                return direct_match
            if "colunas" in payload or "columns" in payload:
                return payload
            records = payload.get("registros") or payload.get("records")
            if isinstance(records, list):
                match = _dictionary_from_records(records, dataset_filename)
                if match is not None:
                    return match
        elif isinstance(payload, list):
            match = _dictionary_from_records(payload, dataset_filename)
            if match is not None:
                return match
    return None


def _dataset_name(filename: str, used_names: set[str]) -> str:
    path = PurePosixPath(filename)
    candidate = path.stem
    if candidate.casefold() not in used_names:
        used_names.add(candidate.casefold())
        return candidate
    candidate = "__".join((*path.parent.parts, path.stem)).strip("_")
    base = candidate or path.stem
    suffix = 2
    while candidate.casefold() in used_names:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_names.add(candidate.casefold())
    return candidate


@contextmanager
def _open_upload_source(source: Any, max_bytes: int) -> Iterator[tuple[BinaryIO, int]]:
    should_close = False
    original_position: int | None = None

    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise InvalidZipError(f"Arquivo ZIP não encontrado: {path}")
        size = path.stat().st_size
        handle: BinaryIO = path.open("rb")
        should_close = True
    elif isinstance(source, (bytes, bytearray, memoryview)):
        raw = bytes(source)
        size = len(raw)
        handle = BytesIO(raw)
        should_close = True
    elif hasattr(source, "read"):
        handle = source
        try:
            original_position = handle.tell()
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(0)
        except (AttributeError, OSError):
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = handle.read(min(1024 * 1024, max_bytes + 1 - size))
                if not chunk:
                    break
                if isinstance(chunk, str):
                    raise InvalidZipError("O upload do ZIP deve ser um arquivo binário.")
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    break
            handle = BytesIO(b"".join(chunks))
            should_close = True
    else:
        raise TypeError("A fonte do ZIP deve ser bytes, caminho ou objeto de arquivo.")

    try:
        if size > max_bytes:
            raise ZipLimitError(
                f"O ZIP excede o limite de upload de {max_bytes // MEBIBYTE} MB."
            )
        yield handle, size
    finally:
        if should_close:
            handle.close()
        elif original_position is not None:
            try:
                handle.seek(original_position)
            except (AttributeError, OSError):
                pass


class ZipProcessor:
    """Valida um ZIP e registra seus CSVs em um :class:`DataManager`."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        csv_reader: CSVReader | None = None,
        max_upload_mb: int | None = None,
        max_uncompressed_mb: int | None = None,
        max_dictionary_mb: float = 25,
        max_compression_ratio: float = 100.0,
        max_files: int = 100,
    ) -> None:
        self.settings = settings or get_settings()
        upload_mb = (
            max_upload_mb
            if max_upload_mb is not None
            else self.settings.app_max_upload_mb
        )
        expanded_mb = (
            max_uncompressed_mb
            if max_uncompressed_mb is not None
            else upload_mb * 4
        )
        if (
            upload_mb <= 0
            or expanded_mb <= 0
            or max_dictionary_mb <= 0
            or max_compression_ratio <= 0
            or max_files <= 0
        ):
            raise ValueError("Os limites do processador ZIP devem ser positivos.")
        self.max_upload_bytes = int(upload_mb * MEBIBYTE)
        self.max_uncompressed_bytes = int(expanded_mb * MEBIBYTE)
        self.max_dictionary_bytes = int(max_dictionary_mb * MEBIBYTE)
        self.max_compression_ratio = float(max_compression_ratio)
        self.max_files = int(max_files)
        self.csv_reader = csv_reader or CSVReader()

    def _validate_entries(self, infos: list[ZipInfo]) -> dict[str, ZipInfo]:
        files: dict[str, ZipInfo] = {}
        seen: set[str] = set()
        total_uncompressed = 0

        for info in infos:
            canonical = _safe_member_name(info)
            if _is_symlink(info):
                raise ZipSecurityError(
                    f"Links simbólicos não são permitidos no ZIP: '{canonical}'."
                )
            if info.is_dir():
                continue
            key = canonical.casefold()
            if key in seen:
                raise ZipSecurityError(
                    f"O ZIP contém entrada duplicada: '{canonical}'."
                )
            seen.add(key)
            if len(seen) > self.max_files:
                raise ZipLimitError(
                    f"O ZIP contém mais de {self.max_files} arquivos, acima do limite."
                )
            if info.flag_bits & 0x1:
                raise ZipSecurityError(
                    f"Arquivos criptografados não são suportados: '{canonical}'."
                )
            total_uncompressed += info.file_size
            if total_uncompressed > self.max_uncompressed_bytes:
                raise ZipLimitError(
                    "O conteúdo descompactado do ZIP excede o limite de segurança."
                )
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > self.max_compression_ratio:
                raise ZipLimitError(
                    f"Taxa de compressão suspeita na entrada '{canonical}'."
                )
            files[canonical] = info

        return files

    def process(self, source: Any, filename: str | None = None) -> ProcessedPackage:
        """Processa bytes, caminho ou o ``UploadedFile`` recebido do Streamlit."""

        inferred_name = filename
        if inferred_name is None and isinstance(source, (str, Path)):
            inferred_name = Path(source).name
        if inferred_name is None and getattr(source, "name", None):
            inferred_name = str(source.name)
        if inferred_name is not None and Path(inferred_name).suffix.casefold() != ".zip":
            raise InvalidZipError("O arquivo enviado deve possuir extensão .zip.")

        with _open_upload_source(source, self.max_upload_bytes) as (handle, _size):
            try:
                handle.seek(0)
                signature = handle.read(4)
                handle.seek(0)
            except (AttributeError, OSError) as exc:
                raise InvalidZipError("Não foi possível ler o arquivo ZIP enviado.") from exc
            if signature not in ZIP_SIGNATURES:
                raise InvalidZipError("O arquivo enviado não possui uma assinatura ZIP válida.")

            try:
                with ZipFile(handle) as archive:
                    entries = self._validate_entries(archive.infolist())
                    bad_member = archive.testzip()
                    if bad_member is not None:
                        raise InvalidZipError(
                            f"O ZIP está corrompido na entrada '{bad_member}'."
                        )

                    dictionary_entries = {
                        name: info
                        for name, info in entries.items()
                        if _is_dictionary_file(name)
                    }
                    csv_entries = {
                        name: info
                        for name, info in entries.items()
                        if PurePosixPath(name).suffix.casefold() == ".csv"
                        and name not in dictionary_entries
                    }
                    if not csv_entries:
                        raise CSVNotFoundError(
                            "Nenhum arquivo CSV de dados foi encontrado no ZIP."
                        )

                    warnings: list[str] = []
                    dictionaries: dict[str, Any] = {}
                    dictionary_bytes = sum(
                        info.file_size for info in dictionary_entries.values()
                    )
                    if dictionary_bytes > self.max_dictionary_bytes:
                        raise ZipLimitError(
                            "O(s) dicionário(s) de dados excede(m) o limite de "
                            f"{self.max_dictionary_bytes / MEBIBYTE:g} MB."
                        )
                    for member_name, info in dictionary_entries.items():
                        try:
                            if PurePosixPath(member_name).suffix.casefold() == ".json":
                                with archive.open(info) as member:
                                    dictionaries[member_name] = _decode_dictionary_json(
                                        member.read()
                                    )
                            else:
                                with archive.open(info) as member:
                                    result = self.csv_reader.read(member, filename=member_name)
                                dictionaries[member_name] = {
                                    "registros": _records_without_nan(result.dataframe)
                                }
                        except (CSVReadError, ZipProcessingError, OSError, RuntimeError) as exc:
                            warnings.append(
                                f"Não foi possível carregar o dicionário '{member_name}': {exc}"
                            )

                    if not dictionary_entries:
                        warnings.append(MISSING_DICTIONARY_WARNING)

                    if len(dictionaries) == 1:
                        combined_dictionary: Any = next(iter(dictionaries.values()))
                    else:
                        combined_dictionary = dict(dictionaries)
                    manager = DataManager(data_dictionary=combined_dictionary)
                    used_names: set[str] = set()
                    for member_name, info in csv_entries.items():
                        try:
                            with archive.open(info) as member:
                                result = self.csv_reader.read(member, filename=member_name)
                        except (CSVReadError, OSError, RuntimeError) as exc:
                            raise ZipProcessingError(
                                f"Não foi possível processar o CSV '{member_name}': {exc}"
                            ) from exc
                        name = _dataset_name(member_name, used_names)
                        manager.add_dataset(
                            name,
                            result,
                            source_name=member_name,
                            data_dictionary=_dictionary_for_dataset(
                                dictionaries, member_name
                            ),
                        )

                    return ProcessedPackage(
                        data_manager=manager,
                        files=list(entries),
                        csv_files=list(csv_entries),
                        dictionary_files=list(dictionary_entries),
                        warnings=warnings,
                        dictionary_found=bool(dictionary_entries),
                    )
            except BadZipFile as exc:
                raise InvalidZipError("O arquivo enviado não é um ZIP válido.") from exc
            except (EOFError, RuntimeError, zlib.error) as exc:
                raise InvalidZipError("O arquivo ZIP está corrompido ou ilegível.") from exc


def process_zip(source: Any, filename: str | None = None) -> ProcessedPackage:
    """Atalho funcional com os limites definidos nas configurações atuais."""

    return ZipProcessor().process(source, filename=filename)
