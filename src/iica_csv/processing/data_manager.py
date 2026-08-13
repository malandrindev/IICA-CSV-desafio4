"""Catálogo em memória dos DataFrames carregados na sessão."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

import pandas as pd

from .csv_reader import CSVReadResult


class DataManagerError(ValueError):
    """Erro de cadastro ou consulta no catálogo de datasets."""


class DatasetNotFoundError(DataManagerError):
    """O dataset solicitado não existe no catálogo atual."""


def _dictionary_details(data_dictionary: Any) -> tuple[str | None, dict[str, str]]:
    if not isinstance(data_dictionary, Mapping):
        return None, {}
    description = data_dictionary.get("descricao") or data_dictionary.get("description")
    raw_columns = data_dictionary.get("colunas") or data_dictionary.get("columns") or {}
    descriptions: dict[str, str] = {}
    if isinstance(raw_columns, Mapping):
        for column, details in raw_columns.items():
            if isinstance(details, Mapping):
                value = details.get("descricao") or details.get("description")
            else:
                value = details
            if value is not None:
                descriptions[str(column)] = str(value)
    return str(description) if description is not None else None, descriptions


@dataclass(frozen=True, slots=True)
class DatasetMetadata:
    """Metadados suficientes para orientar o agente sem enviar os dados."""

    name: str
    source_name: str
    row_count: int
    column_count: int
    columns: tuple[str, ...]
    dtypes: dict[str, str]
    null_counts: dict[str, int]
    encoding: str | None
    separator: str | None
    decimal: str | None
    dictionary: Any = None
    description: str | None = None
    column_descriptions: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Converte para um contrato serializável e amigável às tools."""

        return {
            "name": self.name,
            "source_name": self.source_name,
            "rows": self.row_count,
            "row_count": self.row_count,
            "columns_count": self.column_count,
            "column_count": self.column_count,
            "columns": list(self.columns),
            "dtypes": dict(self.dtypes),
            "null_counts": dict(self.null_counts),
            "encoding": self.encoding,
            "separator": self.separator,
            "decimal": self.decimal,
            "dictionary": self.dictionary,
            "description": self.description,
            "column_descriptions": dict(self.column_descriptions or {}),
        }


class DataManager:
    """Mantém DataFrames e catálogo somente em memória.

    Uma instância deve ser guardada em ``st.session_state`` pela interface; o
    módulo não cria estado global nem qualquer persistência.
    """

    def __init__(
        self,
        datasets: Mapping[str, pd.DataFrame] | None = None,
        *,
        data_dictionary: Any = None,
    ) -> None:
        self._datasets: dict[str, pd.DataFrame] = {}
        self._metadata: dict[str, DatasetMetadata] = {}
        self._data_dictionary = data_dictionary
        if datasets:
            for name, dataframe in datasets.items():
                self.add_dataset(name, dataframe)

    @property
    def dataset_names(self) -> list[str]:
        return list(self._datasets)

    @property
    def has_data(self) -> bool:
        return bool(self._datasets)

    @property
    def datasets(self) -> dict[str, pd.DataFrame]:
        """Retorna uma visão rasa do catálogo, sem copiar os DataFrames."""

        return dict(self._datasets)

    @property
    def metadata(self) -> dict[str, dict[str, Any]]:
        return {name: item.to_dict() for name, item in self._metadata.items()}

    @property
    def data_dictionary(self) -> Any:
        return self._data_dictionary

    def set_data_dictionary(self, data_dictionary: Any) -> None:
        self._data_dictionary = data_dictionary

    def __len__(self) -> int:
        return len(self._datasets)

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        try:
            self._resolve_name(name)
            return True
        except DatasetNotFoundError:
            return False

    def _resolve_name(self, name: str) -> str:
        if name in self._datasets:
            return name
        requested = name.casefold()
        requested_stem = PurePosixPath(name.replace("\\", "/")).stem.casefold()
        matches = [
            candidate
            for candidate in self._datasets
            if candidate.casefold() == requested
            or PurePosixPath(candidate.replace("\\", "/")).stem.casefold()
            == requested_stem
        ]
        if len(matches) == 1:
            return matches[0]
        available = ", ".join(self.dataset_names) or "nenhum"
        raise DatasetNotFoundError(
            f"Dataset '{name}' não encontrado. Disponíveis: {available}."
        )

    def add_dataset(
        self,
        name: str,
        data: pd.DataFrame | CSVReadResult,
        *,
        source_name: str | None = None,
        encoding: str | None = None,
        separator: str | None = None,
        decimal: str | None = None,
        data_dictionary: Any = None,
    ) -> None:
        """Adiciona um DataFrame e calcula seus metadados básicos."""

        clean_name = name.strip()
        if not clean_name:
            raise DataManagerError("O nome do dataset não pode ser vazio.")
        if any(existing.casefold() == clean_name.casefold() for existing in self._datasets):
            raise DataManagerError(f"Já existe um dataset chamado '{clean_name}'.")

        if isinstance(data, CSVReadResult):
            dataframe = data.dataframe
            encoding = encoding or data.encoding
            separator = separator or data.separator
            decimal = decimal or data.decimal
        elif isinstance(data, pd.DataFrame):
            dataframe = data
        else:
            raise TypeError("data deve ser um pandas.DataFrame ou CSVReadResult.")

        related_dictionary = (
            data_dictionary if data_dictionary is not None else self._data_dictionary
        )
        description, column_descriptions = _dictionary_details(related_dictionary)
        metadata = DatasetMetadata(
            name=clean_name,
            source_name=source_name or clean_name,
            row_count=int(len(dataframe)),
            column_count=int(len(dataframe.columns)),
            columns=tuple(str(column) for column in dataframe.columns),
            dtypes={str(column): str(dtype) for column, dtype in dataframe.dtypes.items()},
            null_counts={
                str(column): int(count) for column, count in dataframe.isna().sum().items()
            },
            encoding=encoding,
            separator=separator,
            decimal=decimal,
            dictionary=related_dictionary,
            description=description,
            column_descriptions=column_descriptions,
        )
        self._datasets[clean_name] = dataframe
        self._metadata[clean_name] = metadata

    register_dataset = add_dataset

    def get_dataframe(self, name: str) -> pd.DataFrame:
        return self._datasets[self._resolve_name(name)]

    get_dataset = get_dataframe

    def get_metadata(self, name: str) -> dict[str, Any]:
        return self._metadata[self._resolve_name(name)].to_dict()

    def list_metadata(self) -> list[dict[str, Any]]:
        return [metadata.to_dict() for metadata in self._metadata.values()]
