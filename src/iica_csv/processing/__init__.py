"""Carga, validação e preparação dos arquivos enviados."""

from .csv_reader import (
    CSVEncodingError,
    CSVFormatError,
    CSVReadError,
    CSVReader,
    CSVReadResult,
    read_csv,
    read_csv_robust,
)
from .data_manager import (
    DataManager,
    DataManagerError,
    DatasetMetadata,
    DatasetNotFoundError,
)
from .zip_processor import (
    CSVNotFoundError,
    InvalidZipError,
    MISSING_DICTIONARY_WARNING,
    ProcessedPackage,
    ZipLimitError,
    ZipProcessingError,
    ZipProcessor,
    ZipSecurityError,
    process_zip,
)

__all__ = [
    "CSVEncodingError",
    "CSVFormatError",
    "CSVNotFoundError",
    "CSVReadError",
    "CSVReader",
    "CSVReadResult",
    "DataManager",
    "DataManagerError",
    "DatasetMetadata",
    "DatasetNotFoundError",
    "InvalidZipError",
    "MISSING_DICTIONARY_WARNING",
    "ProcessedPackage",
    "ZipLimitError",
    "ZipProcessingError",
    "ZipProcessor",
    "ZipSecurityError",
    "process_zip",
    "read_csv",
    "read_csv_robust",
]
