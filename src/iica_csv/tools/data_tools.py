"""Ferramentas pandas determinísticas e limitadas usadas pelo agente."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import json
import math
from pathlib import PurePosixPath
import re
from typing import Any, Literal, Mapping, Sequence
import unicodedata

import numpy as np
import pandas as pd

from iica_csv.processing.data_manager import DataManager


ResultType = Literal["scalar", "table", "series", "error"]
ChartHint = Literal["none", "bar", "line"]
ALLOWED_AGGREGATIONS = {"sum", "mean", "count", "min", "max"}
DEFAULT_RESULT_LIMIT = 20
MAX_RESULT_ROWS = 50
MAX_FILTER_COLUMNS = 12
MAX_TEXT_LENGTH = 500


@dataclass(slots=True)
class ToolResult:
    """Contrato pequeno e serializável entre pandas, agente e interface."""

    result_type: ResultType
    summary: str
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    chart_hint: ChartHint = "none"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Retorna somente tipos seguros para JSON e mensagens de tool."""

        return _json_safe(asdict(self))

    def to_json(self) -> str:
        """Serializa sem permitir NaN ou representações pandas extensas."""

        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)


class DataToolError(ValueError):
    """Erro de validação convertido em ``ToolResult(result_type='error')``."""


def _normalise_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_accents.casefold()).strip()


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, (bool, np.bool_)) and missing:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, pd.Period):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        return (
            value
            if len(value) <= MAX_TEXT_LENGTH
            else f"{value[: MAX_TEXT_LENGTH - 1]}…"
        )
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _records(frame: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    raw = frame.head(limit).to_dict(orient="records")
    return [_json_safe(row) for row in raw]


def _format_number(value: Any) -> str:
    safe = _json_safe(value)
    if isinstance(safe, float):
        return f"{safe:,.6f}".rstrip("0").rstrip(".")
    return str(safe)


def _bounded_limit(
    value: int | str, *, default: int = DEFAULT_RESULT_LIMIT
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DataToolError("O limite deve ser um número inteiro.") from exc
    if parsed <= 0:
        raise DataToolError("O limite deve ser maior que zero.")
    return min(parsed or default, MAX_RESULT_ROWS)


def _aggregation_name(operation: str) -> str:
    aliases = {
        "sum": "sum",
        "soma": "sum",
        "mean": "mean",
        "media": "mean",
        "média": "mean",
        "count": "count",
        "contagem": "count",
        "min": "min",
        "minimum": "min",
        "minimo": "min",
        "mínimo": "min",
        "max": "max",
        "maximum": "max",
        "maximo": "max",
        "máximo": "max",
    }
    normalised = operation.strip().casefold()
    resolved = aliases.get(normalised)
    if resolved is None:
        allowed = ", ".join(sorted(ALLOWED_AGGREGATIONS))
        raise DataToolError(f"Agregação '{operation}' inválida. Use: {allowed}.")
    return resolved


class DataTools:
    """Executa somente operações explicitamente autorizadas sobre um catálogo."""

    def __init__(
        self,
        data_manager: DataManager,
        *,
        default_limit: int = DEFAULT_RESULT_LIMIT,
        max_result_rows: int = MAX_RESULT_ROWS,
    ) -> None:
        self.data_manager = data_manager
        self.default_limit = max(1, min(int(default_limit), MAX_RESULT_ROWS))
        self.max_result_rows = max(1, min(int(max_result_rows), MAX_RESULT_ROWS))
        self.execution_log: list[ToolResult] = []

    @property
    def last_result(self) -> ToolResult | None:
        return self.execution_log[-1] if self.execution_log else None

    def reset_execution_log(self) -> None:
        self.execution_log.clear()

    def _record(self, result: ToolResult) -> ToolResult:
        self.execution_log.append(result)
        return result

    def _error(self, message: str, **metadata: Any) -> ToolResult:
        return self._record(
            ToolResult(
                result_type="error",
                summary=message,
                metadata=_json_safe(metadata),
            )
        )

    def _dataset(self, requested: str) -> tuple[str, pd.DataFrame]:
        wanted = _normalise_name(PurePosixPath(requested.replace("\\", "/")).stem)
        matches = [
            name
            for name in self.data_manager.dataset_names
            if _normalise_name(name) == wanted
            or _normalise_name(PurePosixPath(name).stem) == wanted
        ]
        if len(matches) != 1:
            available = ", ".join(self.data_manager.dataset_names) or "nenhum"
            raise DataToolError(
                f"Dataset '{requested}' não encontrado ou ambíguo. Disponíveis: {available}."
            )
        name = matches[0]
        return name, self.data_manager.get_dataframe(name)

    @staticmethod
    def _column(frame: pd.DataFrame, requested: str) -> str:
        wanted = _normalise_name(requested)
        matches = [column for column in frame.columns if _normalise_name(column) == wanted]
        if len(matches) != 1:
            available = ", ".join(str(column) for column in frame.columns)
            raise DataToolError(
                f"Coluna '{requested}' não encontrada ou ambígua. Colunas: {available}."
            )
        return str(matches[0])

    def _group_columns(
        self, frame: pd.DataFrame, group_by: str | Sequence[str] | None
    ) -> list[str]:
        if group_by is None:
            return []
        requested = [group_by] if isinstance(group_by, str) else list(group_by)
        if not requested:
            return []
        if len(requested) > 3:
            raise DataToolError("Use no máximo três colunas de agrupamento.")
        resolved = [self._column(frame, column) for column in requested]
        if len(set(resolved)) != len(resolved):
            raise DataToolError("As colunas de agrupamento não podem se repetir.")
        return resolved

    @staticmethod
    def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
        series = frame[column]
        if pd.api.types.is_numeric_dtype(series):
            return series
        parsed = pd.to_numeric(series, errors="coerce")
        present = series.notna()
        if present.any() and parsed[present].isna().any():
            raise DataToolError(
                f"A coluna '{column}' não é numérica e não pode ser agregada."
            )
        return parsed

    def list_datasets(self) -> ToolResult:
        """Lista datasets e dimensões sem incluir registros dos CSVs."""

        metadata = self.data_manager.list_metadata()
        rows = [
            {
                "dataset": item["name"],
                "linhas": item["row_count"],
                "colunas": item["column_count"],
                "encoding": item.get("encoding"),
                "separador": item.get("separator"),
                "decimal": item.get("decimal"),
                "dicionario": bool(item.get("column_descriptions")),
            }
            for item in metadata[: self.max_result_rows]
        ]
        return self._record(
            ToolResult(
                result_type="table",
                summary=f"{len(metadata)} dataset(s) carregado(s).",
                columns=list(rows[0]) if rows else [],
                rows=rows,
                metadata={
                    "tool": "list_datasets",
                    "total_datasets": len(metadata),
                    "truncated": len(metadata) > len(rows),
                },
            )
        )

    def describe_dataset(self, dataset_name: str) -> ToolResult:
        """Retorna schema, tipos, nulos e descrições do dicionário."""

        try:
            name, frame = self._dataset(dataset_name)
            metadata = self.data_manager.get_metadata(name)
            descriptions = metadata.get("column_descriptions") or {}
            rows = [
                {
                    "coluna": str(column),
                    "dtype": str(frame[column].dtype),
                    "nulos": int(metadata["null_counts"].get(str(column), 0)),
                    "descricao": descriptions.get(str(column)),
                }
                for column in frame.columns
            ]
            return self._record(
                ToolResult(
                    result_type="table",
                    summary=(
                        f"Dataset '{name}': {len(frame)} linhas e "
                        f"{len(frame.columns)} colunas."
                    ),
                    columns=["coluna", "dtype", "nulos", "descricao"],
                    rows=rows[: self.max_result_rows],
                    metadata={
                        "dataset": name,
                        "tool": "describe_dataset",
                        "source_name": metadata.get("source_name"),
                        "rows": len(frame),
                        "column_count": len(frame.columns),
                        "description": metadata.get("description"),
                        "truncated": len(rows) > self.max_result_rows,
                    },
                )
            )
        except DataToolError as exc:
            return self._error(str(exc), tool="describe_dataset", dataset=dataset_name)

    def aggregate_data(
        self,
        dataset_name: str,
        operation: str,
        value_column: str | None = None,
        group_by: str | list[str] | None = None,
    ) -> ToolResult:
        """Executa sum/mean/count/min/max com agrupamento opcional."""

        try:
            name, frame = self._dataset(dataset_name)
            aggregation = _aggregation_name(operation)
            groups = self._group_columns(frame, group_by)
            value = self._column(frame, value_column) if value_column else None
            if aggregation != "count" and value is None:
                raise DataToolError(
                    f"A operação '{aggregation}' exige value_column."
                )

            working = frame
            if value is not None and aggregation != "count":
                working = frame.assign(**{value: self._numeric(frame, value)})

            if not groups:
                if aggregation == "count":
                    computed: Any = len(working) if value is None else working[value].count()
                else:
                    if aggregation == "sum":
                        computed = working[value].sum(min_count=1)
                    else:
                        computed = getattr(working[value], aggregation)()
                if pd.isna(computed):
                    raise DataToolError(
                        f"A coluna '{value}' não contém valores válidos para {aggregation}."
                    )
                computed = int(computed) if aggregation == "count" else computed
                return self._record(
                    ToolResult(
                        result_type="scalar",
                        summary=(
                            f"{aggregation} de '{value or 'linhas'}' em '{name}': "
                            f"{_format_number(computed)}."
                        ),
                        columns=["valor"],
                        rows=[{"valor": _json_safe(computed)}],
                        metadata={
                            "dataset": name,
                            "tool": "aggregate_data",
                            "operation": aggregation,
                            "value_column": value,
                            "group_by": [],
                        },
                    )
                )

            grouped = working.groupby(groups, dropna=False, observed=True)
            if aggregation == "count" and value is None:
                series = grouped.size()
            elif aggregation == "count":
                series = grouped[value].count()
            else:
                series = (
                    grouped[value].sum(min_count=1)
                    if aggregation == "sum"
                    else grouped[value].agg(aggregation)
                )
            missing_groups = int(series.isna().sum())
            series = series.dropna()
            if series.empty:
                raise DataToolError(
                    f"Nenhum grupo contém valores válidos para {aggregation}."
                )
            result_column = f"{aggregation}_{value or 'linhas'}"
            output = series.rename(result_column).reset_index()
            output = output.sort_values(result_column, ascending=False, na_position="last")
            total_groups = len(output)
            output = output.head(self.max_result_rows)
            return self._record(
                ToolResult(
                    result_type="table",
                    summary=(
                        f"{aggregation} de '{value or 'linhas'}' por "
                        f"{', '.join(groups)} em '{name}': {total_groups} grupo(s)."
                    ),
                    columns=[*groups, result_column],
                    rows=_records(output, self.max_result_rows),
                    chart_hint="bar",
                    metadata={
                        "dataset": name,
                        "tool": "aggregate_data",
                        "operation": aggregation,
                        "value_column": value,
                        "group_by": groups,
                        "total_groups": total_groups,
                        "groups_without_values": missing_groups,
                        "truncated": total_groups > len(output),
                    },
                )
            )
        except (DataToolError, TypeError, ValueError) as exc:
            return self._error(
                str(exc), tool="aggregate_data", dataset=dataset_name, operation=operation
            )

    def top_n(
        self,
        dataset_name: str,
        group_by: str | list[str],
        value_column: str | None = None,
        aggregation: str = "sum",
        n: int | str = 5,
        order: str = "desc",
    ) -> ToolResult:
        """Retorna os maiores ou menores grupos após agregação permitida."""

        try:
            name, frame = self._dataset(dataset_name)
            operation = _aggregation_name(aggregation)
            groups = self._group_columns(frame, group_by)
            if not groups:
                raise DataToolError("top_n exige ao menos uma coluna group_by.")
            value = self._column(frame, value_column) if value_column else None
            if operation != "count" and value is None:
                raise DataToolError(
                    f"A agregação '{operation}' exige value_column."
                )
            size = min(_bounded_limit(n), self.max_result_rows)
            order_key = order.strip().casefold()
            descending_terms = {"desc", "maiores", "maior", "largest", "top"}
            ascending_terms = {"asc", "menores", "menor", "smallest", "bottom"}
            if order_key in descending_terms:
                ascending = False
            elif order_key in ascending_terms:
                ascending = True
            else:
                raise DataToolError("order deve ser 'desc/maiores' ou 'asc/menores'.")

            working = frame
            if value is not None and operation != "count":
                working = frame.assign(**{value: self._numeric(frame, value)})
            grouped = working.groupby(groups, dropna=False, observed=True)
            if operation == "count" and value is None:
                series = grouped.size()
            elif operation == "count":
                series = grouped[value].count()
            else:
                series = (
                    grouped[value].sum(min_count=1)
                    if operation == "sum"
                    else grouped[value].agg(operation)
                )
            missing_groups = int(series.isna().sum())
            series = series.dropna()
            if series.empty:
                raise DataToolError(
                    f"Nenhum grupo contém valores válidos para {operation}."
                )
            result_column = f"{operation}_{value or 'linhas'}"
            output = (
                series.rename(result_column)
                .reset_index()
                .sort_values(result_column, ascending=ascending, na_position="last")
            )
            total_groups = len(output)
            output = output.head(size)
            direction = "menores" if ascending else "maiores"
            return self._record(
                ToolResult(
                    result_type="table",
                    summary=(
                        f"{len(output)} {direction} grupo(s) por {operation} de "
                        f"'{value or 'linhas'}' em '{name}'."
                    ),
                    columns=[*groups, result_column],
                    rows=_records(output, size),
                    chart_hint="bar",
                    metadata={
                        "dataset": name,
                        "tool": "top_n",
                        "operation": operation,
                        "value_column": value,
                        "group_by": groups,
                        "order": "asc" if ascending else "desc",
                        "n": size,
                        "total_groups": total_groups,
                        "groups_without_values": missing_groups,
                    },
                )
            )
        except (DataToolError, TypeError, ValueError) as exc:
            return self._error(str(exc), tool="top_n", dataset=dataset_name)

    def filter_data(
        self,
        dataset_name: str,
        column: str,
        operator: str,
        value: str | int | float | bool | list[str],
        limit: int = DEFAULT_RESULT_LIMIT,
        columns: list[str] | None = None,
    ) -> ToolResult:
        """Aplica um filtro simples autorizado e retorna poucas linhas."""

        try:
            name, frame = self._dataset(dataset_name)
            filter_column = self._column(frame, column)
            size = min(_bounded_limit(limit), self.max_result_rows)
            selected = (
                [self._column(frame, item) for item in columns]
                if columns
                else [str(item) for item in frame.columns[:MAX_FILTER_COLUMNS]]
            )
            if len(selected) > MAX_FILTER_COLUMNS:
                raise DataToolError(
                    f"Selecione no máximo {MAX_FILTER_COLUMNS} colunas no retorno."
                )
            if filter_column not in selected:
                selected = [filter_column, *selected[: MAX_FILTER_COLUMNS - 1]]

            series = frame[filter_column]
            op = operator.strip().casefold()
            aliases = {
                "=": "eq",
                "==": "eq",
                "eq": "eq",
                "!=": "ne",
                "ne": "ne",
                ">": "gt",
                "gt": "gt",
                ">=": "gte",
                "gte": "gte",
                "<": "lt",
                "lt": "lt",
                "<=": "lte",
                "lte": "lte",
                "contains": "contains",
                "contem": "contains",
                "contém": "contains",
                "in": "in",
            }
            resolved_op = aliases.get(op)
            if resolved_op is None:
                raise DataToolError(
                    "Operador inválido. Use eq, ne, gt, gte, lt, lte, contains ou in."
                )
            comparison = self._comparison_value(series, value)
            if resolved_op == "eq":
                mask = series.eq(comparison)
            elif resolved_op == "ne":
                mask = series.ne(comparison)
            elif resolved_op == "gt":
                mask = series.gt(comparison)
            elif resolved_op == "gte":
                mask = series.ge(comparison)
            elif resolved_op == "lt":
                mask = series.lt(comparison)
            elif resolved_op == "lte":
                mask = series.le(comparison)
            elif resolved_op == "contains":
                if isinstance(value, list):
                    raise DataToolError("contains aceita somente um valor.")
                mask = series.astype("string").str.contains(
                    str(value), case=False, regex=False, na=False
                )
            else:
                if not isinstance(value, list):
                    raise DataToolError("O operador in exige uma lista de valores.")
                comparisons = [self._comparison_value(series, item) for item in value]
                mask = series.isin(comparisons)

            matched_mask = mask.fillna(False)
            matched_array = matched_mask.to_numpy(dtype=bool)
            total = int(matched_array.sum())
            matched_positions = np.flatnonzero(matched_array)[:size]
            returned = frame.iloc[matched_positions][selected]
            return self._record(
                ToolResult(
                    result_type="table",
                    summary=(
                        f"Filtro {filter_column} {resolved_op} encontrou {total} "
                        f"registro(s) em '{name}'; retornando {len(returned)}."
                    ),
                    columns=selected,
                    rows=_records(returned, size),
                    metadata={
                        "dataset": name,
                        "tool": "filter_data",
                        "filter_column": filter_column,
                        "operator": resolved_op,
                        "matched_rows": total,
                        "returned_rows": len(returned),
                        "truncated": total > len(returned),
                    },
                )
            )
        except (DataToolError, TypeError, ValueError) as exc:
            return self._error(
                str(exc), tool="filter_data", dataset=dataset_name, column=column
            )

    @staticmethod
    def _comparison_value(series: pd.Series, value: Any) -> Any:
        if pd.api.types.is_bool_dtype(series) and not isinstance(value, list):
            if isinstance(value, bool):
                return value
            normalised = str(value).strip().casefold()
            if normalised in {"true", "1", "sim", "yes"}:
                return True
            if normalised in {"false", "0", "não", "nao", "no"}:
                return False
            raise DataToolError(
                f"O valor '{value}' não é compatível com a coluna booleana."
            )
        if pd.api.types.is_numeric_dtype(series) and not isinstance(value, list):
            try:
                return float(str(value).replace(",", "."))
            except ValueError as exc:
                raise DataToolError(
                    f"O valor '{value}' não é compatível com a coluna numérica."
                ) from exc
        if pd.api.types.is_datetime64_any_dtype(series) and not isinstance(value, list):
            parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
            if pd.isna(parsed):
                raise DataToolError(f"O valor temporal '{value}' é inválido.")
            return parsed
        return value

    def unique_values(
        self,
        dataset_name: str,
        column: str,
        limit: int = DEFAULT_RESULT_LIMIT,
    ) -> ToolResult:
        """Lista valores distintos sem retornar a coluna completa."""

        try:
            name, frame = self._dataset(dataset_name)
            resolved = self._column(frame, column)
            size = min(_bounded_limit(limit), self.max_result_rows)
            values = frame[resolved].drop_duplicates()
            total = int(frame[resolved].nunique(dropna=False))
            rows = [{"valor": _json_safe(item)} for item in values.head(size).tolist()]
            return self._record(
                ToolResult(
                    result_type="series",
                    summary=(
                        f"'{resolved}' possui {total} valor(es) distinto(s) em '{name}'; "
                        f"retornando {len(rows)}."
                    ),
                    columns=["valor"],
                    rows=rows,
                    metadata={
                        "dataset": name,
                        "tool": "unique_values",
                        "column": resolved,
                        "total_unique": total,
                        "truncated": total > len(rows),
                    },
                )
            )
        except (DataToolError, TypeError, ValueError) as exc:
            return self._error(
                str(exc), tool="unique_values", dataset=dataset_name, column=column
            )

    def time_aggregation(
        self,
        dataset_name: str,
        date_column: str,
        period: str,
        operation: str = "sum",
        value_column: str | None = None,
    ) -> ToolResult:
        """Agrega uma coluna por year, month ou year-month."""

        try:
            name, frame = self._dataset(dataset_name)
            date_name = self._column(frame, date_column)
            value = self._column(frame, value_column) if value_column else None
            aggregation = _aggregation_name(operation)
            if aggregation != "count" and value is None:
                raise DataToolError(
                    f"A operação '{aggregation}' exige value_column."
                )
            period_key = _normalise_name(period).replace(" ", "-")
            aliases = {
                "year": "year",
                "ano": "year",
                "month": "month",
                "mes": "month",
                "year-month": "year-month",
                "ano-mes": "year-month",
            }
            resolved_period = aliases.get(period_key)
            if resolved_period is None:
                raise DataToolError("Período inválido. Use year, month ou year-month.")

            dates = frame[date_name]
            if not pd.api.types.is_datetime64_any_dtype(dates):
                dates = pd.to_datetime(dates, errors="coerce", dayfirst=True)
            valid = dates.notna()
            if not valid.any():
                raise DataToolError(
                    f"A coluna '{date_name}' não contém datas válidas."
                )
            if resolved_period == "year":
                keys = dates.dt.year.astype("Int64").astype("string")
            elif resolved_period == "month":
                keys = dates.dt.month.astype("Int64").astype("string").str.zfill(2)
            else:
                keys = dates.dt.to_period("M").astype("string")

            working = pd.DataFrame({"periodo": keys})
            if value is not None:
                working["valor"] = (
                    frame[value]
                    if aggregation == "count"
                    else self._numeric(frame, value)
                )
            working = working.loc[valid]
            grouped = working.groupby("periodo", dropna=False, observed=True)
            if aggregation == "count" and value is None:
                series = grouped.size()
            elif aggregation == "count":
                series = grouped["valor"].count()
            else:
                series = (
                    grouped["valor"].sum(min_count=1)
                    if aggregation == "sum"
                    else grouped["valor"].agg(aggregation)
                )
            missing_periods = int(series.isna().sum())
            series = series.dropna()
            if series.empty:
                raise DataToolError(
                    f"Nenhum período contém valores válidos para {aggregation}."
                )
            result_column = f"{aggregation}_{value or 'linhas'}"
            output = series.rename(result_column).reset_index().sort_values("periodo")
            total_periods = len(output)
            output = output.head(self.max_result_rows)
            return self._record(
                ToolResult(
                    result_type="series",
                    summary=(
                        f"{aggregation} de '{value or 'linhas'}' por {resolved_period} "
                        f"em '{name}': {total_periods} período(s)."
                    ),
                    columns=["periodo", result_column],
                    rows=_records(output, self.max_result_rows),
                    chart_hint="line",
                    metadata={
                        "dataset": name,
                        "tool": "time_aggregation",
                        "date_column": date_name,
                        "value_column": value,
                        "operation": aggregation,
                        "period": resolved_period,
                        "total_periods": total_periods,
                        "invalid_dates": int((~valid).sum()),
                        "periods_without_values": missing_periods,
                        "truncated": total_periods > len(output),
                    },
                )
            )
        except (DataToolError, TypeError, ValueError) as exc:
            return self._error(
                str(exc),
                tool="time_aggregation",
                dataset=dataset_name,
                column=date_column,
            )

    def langchain_tools(self) -> list[Any]:
        """Expõe wrappers tipados; os DataFrames nunca entram no retorno."""

        from langchain.tools import tool

        service = self

        @tool
        def list_datasets() -> dict[str, Any]:
            """Liste os datasets carregados e seus metadados essenciais."""

            return service.list_datasets().to_dict()

        @tool
        def describe_dataset(dataset_name: str) -> dict[str, Any]:
            """Descreva schema, tipos, nulos e dicionário de um dataset."""

            return service.describe_dataset(dataset_name).to_dict()

        @tool
        def aggregate_data(
            dataset_name: str,
            operation: str,
            value_column: str | None = None,
            group_by: str | list[str] | None = None,
        ) -> dict[str, Any]:
            """Calcule por grupos. SUM soma medidas; COUNT conta linhas/valores."""

            return service.aggregate_data(
                dataset_name, operation, value_column, group_by
            ).to_dict()

        @tool
        def top_n(
            dataset_name: str,
            group_by: str | list[str],
            value_column: str | None = None,
            aggregation: str = "sum",
            n: int | str = 5,
            order: str = "desc",
        ) -> dict[str, Any]:
            """Ordene grupos após agregação; volume/quantidade acumulada usa SUM."""

            return service.top_n(
                dataset_name, group_by, value_column, aggregation, n, order
            ).to_dict()

        @tool
        def filter_data(
            dataset_name: str,
            column: str,
            operator: str,
            value: str | int | float | bool | list[str],
            limit: int = DEFAULT_RESULT_LIMIT,
            columns: list[str] | None = None,
        ) -> dict[str, Any]:
            """Filtre com eq/ne/gt/gte/lt/lte/contains/in e limite o retorno."""

            return service.filter_data(
                dataset_name, column, operator, value, limit, columns
            ).to_dict()

        @tool
        def unique_values(
            dataset_name: str,
            column: str,
            limit: int = DEFAULT_RESULT_LIMIT,
        ) -> dict[str, Any]:
            """Liste valores distintos de uma coluna com limite rígido."""

            return service.unique_values(dataset_name, column, limit).to_dict()

        @tool
        def time_aggregation(
            dataset_name: str,
            date_column: str,
            period: str,
            operation: str = "sum",
            value_column: str | None = None,
        ) -> dict[str, Any]:
            """Agregue por tempo; gasto acumulado usa SUM, não COUNT."""

            return service.time_aggregation(
                dataset_name, date_column, period, operation, value_column
            ).to_dict()

        return [
            list_datasets,
            describe_dataset,
            aggregate_data,
            top_n,
            filter_data,
            unique_values,
            time_aggregation,
        ]


def create_data_tools(data_manager: DataManager) -> DataTools:
    """Factory curta para uso pela camada de agente."""

    return DataTools(data_manager)
