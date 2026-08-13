"""Leitura robusta e conservadora de arquivos CSV.

A detecção é deliberadamente pequena: apenas os encodings, separadores e
convenções decimais exigidos pelo desafio. Identificadores são mantidos como
texto e apenas colunas semanticamente numéricas ou temporais são convertidas.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import codecs
import csv
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
from typing import Any, BinaryIO, Iterator
import unicodedata

import pandas as pd
from pandas.errors import EmptyDataError, ParserError


SUPPORTED_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
SUPPORTED_SEPARATORS = (",", ";")
SAMPLE_BYTES = 256 * 1024


class CSVReadError(ValueError):
    """Erro amigável ao ler ou interpretar um CSV."""


class CSVEncodingError(CSVReadError):
    """O conteúdo não pôde ser decodificado com os encodings suportados."""


class CSVFormatError(CSVReadError):
    """A estrutura do CSV é vazia, inconsistente ou possui uma única coluna."""


@dataclass(slots=True)
class CSVReadResult:
    """Resultado da leitura, acompanhado das escolhas de formato."""

    dataframe: pd.DataFrame
    encoding: str
    separator: str
    decimal: str

    @property
    def sep(self) -> str:
        """Alias curto compatível com a nomenclatura do pandas."""

        return self.separator

    @property
    def df(self) -> pd.DataFrame:
        """Alias conveniente para consumidores que usam ``df``."""

        return self.dataframe


def _normalise_label(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _tokens(column: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _normalise_label(column)))


_IDENTIFIER_TOKENS = {
    "chave",
    "cpf",
    "cnpj",
    "codigo",
    "ncm",
    "cfop",
    "numero",
    "serie",
    "modelo",
    "inscricao",
    "id",
    "identificador",
    "cep",
    "uf",
}
_NUMERIC_TOKENS = {
    "valor",
    "quantidade",
    "qtd",
    "preco",
    "total",
    "custo",
    "peso",
    "aliquota",
    "amount",
    "price",
    "quantity",
}
_DATE_TOKENS = {"data", "date", "hora", "datetime", "timestamp"}


def _is_identifier_column(column: object) -> bool:
    tokens = _tokens(column)
    return bool(tokens & _IDENTIFIER_TOKENS) or any(token.endswith("id") for token in tokens)


def _is_numeric_column(column: object) -> bool:
    tokens = _tokens(column)
    return not _is_identifier_column(column) and bool(tokens & _NUMERIC_TOKENS)


def _is_date_column(column: object) -> bool:
    return bool(_tokens(column) & _DATE_TOKENS)


def _utf8_sample_is_valid(sample: bytes) -> bool:
    try:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
        decoder.decode(sample, final=False)
        return True
    except UnicodeDecodeError:
        return False


def _encoding_candidates(sample: bytes) -> tuple[str, ...]:
    if sample.startswith(codecs.BOM_UTF8):
        return ("utf-8-sig", "cp1252", "latin-1")
    if _utf8_sample_is_valid(sample):
        return ("utf-8", "cp1252", "latin-1")
    return ("cp1252", "latin-1")


def _decode_sample(sample: bytes, encodings: tuple[str, ...]) -> tuple[str, str]:
    for encoding in encodings:
        try:
            decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
            return decoder.decode(sample, final=False), encoding
        except UnicodeDecodeError:
            continue
    raise CSVEncodingError(
        "Não foi possível interpretar o CSV como UTF-8, CP1252 ou Latin-1."
    )


def _delimiter_score(text: str, separator: str) -> tuple[float, int, int]:
    try:
        rows: list[list[str]] = []
        reader = csv.reader(text.splitlines(), delimiter=separator)
        for row in reader:
            if row:
                rows.append(row)
            if len(rows) >= 51:
                break
    except csv.Error:
        return (0.0, 0, 0)

    if not rows:
        return (0.0, 0, 0)
    widths = [len(row) for row in rows]
    mode_width, mode_count = Counter(widths).most_common(1)[0]
    if mode_width <= 1:
        return (0.0, mode_width, mode_count)
    consistency = mode_count / len(widths)
    header_matches = int(widths[0] == mode_width)
    return (consistency, header_matches, mode_width)


def _detect_separator(text: str) -> str:
    scores = {
        separator: _delimiter_score(text, separator)
        for separator in SUPPORTED_SEPARATORS
    }
    separator, score = max(scores.items(), key=lambda item: item[1])
    if score[0] == 0.0 or score[2] <= 1:
        raise CSVFormatError(
            "O CSV não possui uma estrutura válida com separador vírgula ou ponto e vírgula."
        )
    return separator


_COMMA_DECIMAL = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+),\d+$")
_DOT_DECIMAL = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)\.\d+$")


def _detect_decimal(text: str, separator: str) -> str:
    comma_count = 0
    dot_count = 0
    try:
        reader = csv.reader(text.splitlines(), delimiter=separator)
        next(reader, None)
        for index, row in enumerate(reader):
            for raw_value in row:
                value = raw_value.strip()
                comma_count += bool(_COMMA_DECIMAL.fullmatch(value))
                dot_count += bool(_DOT_DECIMAL.fullmatch(value))
            if index >= 199:
                break
    except csv.Error:
        pass
    if comma_count == dot_count:
        return "," if separator == ";" else "."
    return "," if comma_count > dot_count else "."


@contextmanager
def _open_binary_source(source: Any) -> Iterator[BinaryIO]:
    should_close = False
    original_position: int | None = None

    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise CSVReadError(f"Arquivo CSV não encontrado: {path}")
        handle: BinaryIO = path.open("rb")
        should_close = True
    elif isinstance(source, (bytes, bytearray, memoryview)):
        handle = BytesIO(bytes(source))
        should_close = True
    elif hasattr(source, "read"):
        handle = source
        try:
            original_position = handle.tell()
            handle.seek(0)
        except (AttributeError, OSError):
            content = handle.read()
            if isinstance(content, str):
                content = content.encode("utf-8")
            handle = BytesIO(content)
            should_close = True
    else:
        raise TypeError("A fonte do CSV deve ser bytes, caminho ou objeto de arquivo.")

    try:
        yield handle
    finally:
        if should_close:
            handle.close()
        elif original_position is not None:
            try:
                handle.seek(original_position)
            except (AttributeError, OSError):
                pass


def _normalise_number_text(series: pd.Series, decimal: str) -> pd.Series:
    values = series.astype("string").str.strip()
    if decimal == ",":
        thousands = values.str.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?", na=False)
        values = values.where(~thousands, values.str.replace(".", "", regex=False))
        return values.str.replace(",", ".", regex=False)
    thousands = values.str.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", na=False)
    return values.where(~thousands, values.str.replace(",", "", regex=False))


def _convert_numeric_series(series: pd.Series, decimal: str) -> pd.Series | None:
    non_empty = series.notna() & series.astype("string").str.strip().ne("")
    if not non_empty.any():
        return None
    normalised = _normalise_number_text(series, decimal)
    parsed = pd.to_numeric(normalised, errors="coerce")
    if parsed[non_empty].isna().any():
        return None
    non_null = parsed.dropna()
    if not non_null.empty and (non_null % 1 == 0).all():
        try:
            return parsed.astype("Int64")
        except (TypeError, ValueError, OverflowError):
            pass
    return parsed.astype("Float64")


_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y",
)


def _convert_date_series(series: pd.Series) -> pd.Series | None:
    non_empty = series.notna() & series.astype("string").str.strip().ne("")
    if not non_empty.any():
        return None
    for date_format in _DATE_FORMATS:
        parsed = pd.to_datetime(series, format=date_format, errors="coerce")
        if not parsed[non_empty].isna().any():
            return parsed
    return None


def _normalise_safe_columns(dataframe: pd.DataFrame, decimal: str) -> pd.DataFrame:
    result = dataframe.copy(deep=False)
    for column in result.columns:
        series = result[column]
        if _is_identifier_column(column):
            continue
        converted: pd.Series | None = None
        if _is_date_column(column):
            converted = _convert_date_series(series)
        elif _is_numeric_column(column):
            converted = _convert_numeric_series(series, decimal)
        if converted is not None:
            result[column] = converted
    return result


def read_csv(source: Any, filename: str | None = None) -> CSVReadResult:
    """Lê um CSV de bytes, caminho ou objeto binário.

    ``filename`` é apenas contextual e não é necessário para detectar o
    formato. Nenhum código ou expressão contida no CSV é executado.
    """

    del filename  # Reservado para mensagens/telemetria futuras.
    with _open_binary_source(source) as handle:
        try:
            handle.seek(0)
            sample = handle.read(SAMPLE_BYTES)
            handle.seek(0)
        except (AttributeError, OSError) as exc:
            raise CSVReadError("Não foi possível ler o arquivo CSV enviado.") from exc

        if isinstance(sample, str):
            sample = sample.encode("utf-8")
        if not sample:
            raise CSVFormatError("O arquivo CSV está vazio.")
        if b"\x00" in sample:
            raise CSVFormatError("O arquivo informado não parece ser um CSV de texto.")

        encodings = _encoding_candidates(sample)
        sample_text, sample_encoding = _decode_sample(sample, encodings)
        separator = _detect_separator(sample_text)
        decimal = _detect_decimal(sample_text, separator)

        dataframe: pd.DataFrame | None = None
        encoding_used: str | None = None
        last_decode_error: UnicodeDecodeError | None = None
        ordered_encodings = (sample_encoding,) + tuple(
            encoding for encoding in encodings if encoding != sample_encoding
        )
        for encoding in ordered_encodings:
            try:
                handle.seek(0)
                dataframe = pd.read_csv(
                    handle,
                    encoding=encoding,
                    sep=separator,
                    decimal=decimal,
                    dtype=str,
                    keep_default_na=False,
                    na_filter=False,
                    on_bad_lines="error",
                    low_memory=False,
                )
                encoding_used = encoding
                break
            except UnicodeDecodeError as exc:
                last_decode_error = exc
                continue
            except EmptyDataError as exc:
                raise CSVFormatError("O arquivo CSV está vazio.") from exc
            except ParserError as exc:
                raise CSVFormatError(f"O CSV possui linhas inconsistentes: {exc}") from exc
            except (OSError, ValueError) as exc:
                raise CSVReadError(f"Não foi possível ler o CSV: {exc}") from exc

    if dataframe is None or encoding_used is None:
        raise CSVEncodingError(
            "Não foi possível interpretar o CSV como UTF-8, CP1252 ou Latin-1."
        ) from last_decode_error
    if len(dataframe.columns) <= 1:
        raise CSVFormatError(
            "O CSV foi interpretado como uma única coluna; verifique o separador."
        )

    dataframe = dataframe.replace(r"^\s*$", pd.NA, regex=True)
    dataframe = _normalise_safe_columns(dataframe, decimal)
    return CSVReadResult(
        dataframe=dataframe,
        encoding=encoding_used,
        separator=separator,
        decimal=decimal,
    )


class CSVReader:
    """Interface orientada a objeto para injeção em outros componentes."""

    def read(self, source: Any, filename: str | None = None) -> CSVReadResult:
        return read_csv(source, filename=filename)

    read_csv = read


read_csv_robust = read_csv
