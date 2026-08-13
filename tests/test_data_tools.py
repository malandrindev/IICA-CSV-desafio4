"""Testes das operações pandas expostas ao agente."""

import json

import pandas as pd
import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_groq import ChatGroq

from iica_csv.processing.data_manager import DataManager
from iica_csv.tools.data_tools import DataTools, MAX_RESULT_ROWS, ToolResult


@pytest.fixture
def tools() -> DataTools:
    frame = pd.DataFrame(
        {
            "Fornecedor": ["Alfa", "Beta", "Alfa", "Gama", "Beta"],
            "Produto": ["X", "Y", "X", "Z", "Y"],
            "Valor Total": [10.0, 20.0, 15.0, 5.0, 30.0],
            "Quantidade": [1.0, 2.0, 3.0, 4.0, 5.0],
            "Data Emissão": pd.to_datetime(
                [
                    "2024-01-02",
                    "2024-01-10",
                    "2024-02-01",
                    "2024-02-15",
                    "2025-01-01",
                ]
            ),
        }
    )
    manager = DataManager()
    manager.add_dataset(
        "Notas_Fiscais",
        frame,
        encoding="utf-8",
        separator=",",
        decimal=".",
        data_dictionary={
            "descricao": "Compras de teste",
            "colunas": {
                "Valor Total": {"descricao": "Valor monetário do item"}
            },
        },
    )
    return DataTools(manager)


def test_list_and_describe_return_only_metadata(tools: DataTools) -> None:
    listed = tools.list_datasets()
    described = tools.describe_dataset("notas fiscais")

    assert listed.result_type == "table"
    assert listed.rows[0]["linhas"] == 5
    assert "Valor Total" not in listed.rows[0]
    assert described.result_type == "table"
    assert described.metadata["rows"] == 5
    value_row = next(row for row in described.rows if row["coluna"] == "Valor Total")
    assert value_row["descricao"] == "Valor monetário do item"


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("sum", 80.0),
        ("mean", 16.0),
        ("min", 5.0),
        ("max", 30.0),
    ],
)
def test_scalar_aggregations(
    tools: DataTools, operation: str, expected: float
) -> None:
    result = tools.aggregate_data("Notas_Fiscais", operation, "valor total")

    assert result.result_type == "scalar"
    assert result.rows == [{"valor": pytest.approx(expected)}]


def test_count_rows_and_groupby_sum(tools: DataTools) -> None:
    count = tools.aggregate_data("Notas_Fiscais", "count")
    grouped = tools.aggregate_data(
        "Notas_Fiscais", "sum", "Valor Total", "Fornecedor"
    )

    assert count.rows == [{"valor": 5}]
    assert grouped.result_type == "table"
    assert grouped.chart_hint == "bar"
    assert grouped.rows == [
        {"Fornecedor": "Beta", "sum_Valor Total": 50.0},
        {"Fornecedor": "Alfa", "sum_Valor Total": 25.0},
        {"Fornecedor": "Gama", "sum_Valor Total": 5.0},
    ]


def test_groupby_supports_more_than_one_column(tools: DataTools) -> None:
    result = tools.aggregate_data(
        "Notas_Fiscais",
        "count",
        group_by=["Fornecedor", "Produto"],
    )

    assert result.result_type == "table"
    assert result.columns == ["Fornecedor", "Produto", "count_linhas"]
    assert sum(row["count_linhas"] for row in result.rows) == 5


def test_top_n_supports_largest_and_smallest(tools: DataTools) -> None:
    largest = tools.top_n(
        "Notas_Fiscais", "Fornecedor", "Valor Total", "sum", 2, "maiores"
    )
    smallest = tools.top_n(
        "Notas_Fiscais", "Fornecedor", "Valor Total", "sum", 1, "menores"
    )

    assert [row["Fornecedor"] for row in largest.rows] == ["Beta", "Alfa"]
    assert largest.rows[0]["sum_Valor Total"] == pytest.approx(50.0)
    assert smallest.rows == [{"Fornecedor": "Gama", "sum_Valor Total": 5.0}]


@pytest.mark.parametrize(
    ("n", "expected_count"),
    [(1, 1), ("1", 1), (5, 3), ("5", 3)],
)
def test_top_n_accepts_integer_or_numeric_string(
    tools: DataTools, n: int | str, expected_count: int
) -> None:
    result = tools.top_n(
        "Notas_Fiscais", "Fornecedor", "Valor Total", "sum", n, "desc"
    )

    assert result.result_type == "table"
    assert len(result.rows) == expected_count
    assert result.metadata["n"] == int(n)


@pytest.mark.parametrize("n", ["abc", "", 0, "0", -1, "-1"])
def test_top_n_rejects_invalid_limits(tools: DataTools, n: int | str) -> None:
    result = tools.top_n(
        "Notas_Fiscais", "Fornecedor", "Valor Total", "sum", n, "desc"
    )

    assert result.result_type == "error"
    assert "limite" in result.summary.casefold()


def test_top_n_langchain_schema_accepts_integer_or_string(tools: DataTools) -> None:
    top_tool = next(tool for tool in tools.langchain_tools() if tool.name == "top_n")
    schema = convert_to_openai_tool(top_tool)["function"]["parameters"]

    assert schema["properties"]["n"]["anyOf"] == [
        {"type": "integer"},
        {"type": "string"},
    ]
    assert schema["properties"]["n"]["default"] == 5
    invoked = top_tool.invoke(
        {
            "dataset_name": "Notas_Fiscais",
            "group_by": "Fornecedor",
            "value_column": "Valor Total",
            "aggregation": "sum",
            "n": "1",
            "order": "desc",
        }
    )
    assert invoked["metadata"]["n"] == 1

    # Confirma o contrato efetivamente preparado para a Groq, sem chamada de rede.
    bound = ChatGroq(
        model="llama-3.3-70b-versatile", api_key="test-only-no-network"
    ).bind_tools([top_tool])
    provider_schema = bound.kwargs["tools"][0]["function"]["parameters"]
    assert provider_schema["properties"]["n"]["anyOf"] == [
        {"type": "integer"},
        {"type": "string"},
    ]


def test_filter_data_is_controlled_and_limited(tools: DataTools) -> None:
    numeric = tools.filter_data(
        "Notas_Fiscais",
        "Quantidade",
        "gte",
        3,
        limit=2,
        columns=["Fornecedor", "Quantidade"],
    )
    contains = tools.filter_data(
        "Notas_Fiscais", "Fornecedor", "contains", "ALF", limit=10
    )

    assert numeric.metadata["matched_rows"] == 3
    assert numeric.metadata["truncated"] is True
    assert len(numeric.rows) == 2
    assert contains.metadata["matched_rows"] == 2


def test_unique_values_are_limited(tools: DataTools) -> None:
    result = tools.unique_values("Notas_Fiscais", "Fornecedor", limit=2)

    assert result.result_type == "series"
    assert result.metadata["total_unique"] == 3
    assert result.metadata["truncated"] is True
    assert len(result.rows) == 2


def test_time_aggregation_returns_ordered_series(tools: DataTools) -> None:
    result = tools.time_aggregation(
        "Notas_Fiscais",
        "Data Emissão",
        "year-month",
        "sum",
        "Valor Total",
    )

    assert result.result_type == "series"
    assert result.chart_hint == "line"
    assert result.rows == [
        {"periodo": "2024-01", "sum_Valor Total": 30.0},
        {"periodo": "2024-02", "sum_Valor Total": 20.0},
        {"periodo": "2025-01", "sum_Valor Total": 30.0},
    ]


def test_missing_column_and_invalid_operation_return_structured_error(
    tools: DataTools,
) -> None:
    missing = tools.aggregate_data("Notas_Fiscais", "sum", "Coluna X")
    invalid = tools.aggregate_data("Notas_Fiscais", "median", "Valor Total")

    assert missing.result_type == "error"
    assert "Coluna X" in missing.summary
    assert invalid.result_type == "error"
    assert "inválida" in invalid.summary


def test_results_and_langchain_wrappers_are_small_and_json_safe(
    tools: DataTools,
) -> None:
    result = tools.filter_data(
        "Notas_Fiscais", "Quantidade", "gte", 0, limit=10_000
    )
    wrappers = tools.langchain_tools()

    assert len(result.rows) <= MAX_RESULT_ROWS
    json.loads(result.to_json())
    assert [wrapper.name for wrapper in wrappers] == [
        "list_datasets",
        "describe_dataset",
        "aggregate_data",
        "top_n",
        "filter_data",
        "unique_values",
        "time_aggregation",
    ]


def test_json_contract_converts_non_finite_and_nat_to_null() -> None:
    result = ToolResult(
        result_type="table",
        summary="valores especiais",
        columns=["infinito", "data"],
        rows=[{"infinito": float("inf"), "data": pd.NaT}],
    )

    payload = json.loads(result.to_json())

    assert payload["rows"] == [{"infinito": None, "data": None}]


def test_boolean_filter_is_not_treated_as_numeric() -> None:
    manager = DataManager(
        {"flags": pd.DataFrame({"Ativo": [True, False, True], "Nome": ["A", "B", "C"]})}
    )

    result = DataTools(manager).filter_data("flags", "Ativo", "eq", True)

    assert result.result_type == "table"
    assert result.metadata["matched_rows"] == 2


def test_filter_rejects_too_many_explicit_columns() -> None:
    frame = pd.DataFrame({f"c{index}": [index] for index in range(13)})
    tools = DataTools(DataManager({"largo": frame}))

    result = tools.filter_data(
        "largo", "c0", "eq", 0, columns=list(frame.columns)
    )

    assert result.result_type == "error"
    assert "no máximo 12" in result.summary


def test_sum_of_all_missing_values_is_not_reported_as_zero() -> None:
    manager = DataManager(
        {"vazio": pd.DataFrame({"Grupo": ["A", "A"], "Valor": [None, None]})}
    )
    tools = DataTools(manager)

    scalar = tools.aggregate_data("vazio", "sum", "Valor")
    grouped = tools.top_n("vazio", "Grupo", "Valor", "sum")

    assert scalar.result_type == "error"
    assert "não contém valores válidos" in scalar.summary
    assert grouped.result_type == "error"
    assert "Nenhum grupo" in grouped.summary
