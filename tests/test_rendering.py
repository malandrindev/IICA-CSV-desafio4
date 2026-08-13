"""Testes pequenos da escolha determinística de eixos para Plotly."""

import pandas as pd
import pytest

import iica_csv.ui.rendering as rendering
from iica_csv.ui.rendering import (
    _chart_axes,
    render_tool_result,
    render_tool_results,
    result_payload,
)
from iica_csv.tools.data_tools import ToolResult


def test_chart_axes_follow_structured_column_contract() -> None:
    frame = pd.DataFrame(
        {"codigo": [1, 2], "grupo": [10, 20], "sum_valor": [30.0, 40.0]}
    )

    x_column, y_column = _chart_axes(
        frame, ["codigo", "grupo", "sum_valor"]
    )

    assert y_column == "sum_valor"
    assert x_column == "grupo_combinado"
    assert frame["grupo_combinado"].tolist() == ["1 | 10", "2 | 20"]


def test_result_payload_accepts_tool_result() -> None:
    payload = result_payload(
        ToolResult(
            result_type="series",
            summary="série",
            columns=["periodo", "valor"],
            rows=[{"periodo": "2024-01", "valor": 1.0}],
            chart_hint="line",
        )
    )

    assert payload["result_type"] == "series"
    assert payload["chart_hint"] == "line"


def test_source_details_uses_only_structured_metadata() -> None:
    source = rendering._source_details(
        {
            "summary": "texto que não deve ser interpretado",
            "metadata": {
                "dataset": "Documentos",
                "group_by": ["Fornecedor"],
                "value_column": "Valor",
                "date_column": "Emissão",
            },
        }
    )

    assert source is not None
    assert "Documentos" in source
    assert "Fornecedor" in source
    assert "Valor" in source
    assert "Emissão" in source
    assert "texto que não deve ser interpretado" not in source


@pytest.mark.parametrize(
    ("chart_hint", "expected_trace"), [("bar", "bar"), ("line", "scatter")]
)
def test_render_tool_result_builds_expected_plotly_chart(
    monkeypatch, chart_hint: str, expected_trace: str
) -> None:
    figures = []
    monkeypatch.setattr(rendering.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(rendering.st, "dataframe", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        rendering.st,
        "plotly_chart",
        lambda figure, **kwargs: figures.append(figure),
    )

    render_tool_result(
        ToolResult(
            result_type="series",
            summary="resultado",
            columns=["grupo", "valor"],
            rows=[{"grupo": "A", "valor": 1.0}, {"grupo": "B", "valor": 2.0}],
            chart_hint=chart_hint,
        )
    )

    assert len(figures) == 1
    assert figures[0].data[0].type == expected_trace
    assert figures[0].layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert figures[0].layout.plot_bgcolor == "#FFFFFF"


def test_render_tool_results_preserves_multiple_evidences(monkeypatch) -> None:
    captions = []
    tables = []
    monkeypatch.setattr(rendering.st, "caption", lambda value, **_: captions.append(value))
    monkeypatch.setattr(rendering.st, "dataframe", lambda value, **_: tables.append(value))
    monkeypatch.setattr(rendering.st, "plotly_chart", lambda *args, **kwargs: None)
    results = [
        ToolResult(
            "table", "maior fornecedor", ["entidade", "valor"],
            [{"entidade": "F2", "valor": 200.0}],
        ),
        ToolResult(
            "table", "maior cliente", ["entidade", "valor"],
            [{"entidade": "C2", "valor": 200.0}],
        ),
    ]

    render_tool_results(results)

    assert len(captions) == 2
    assert len(tables) == 2
    assert "maior fornecedor" in captions[0]
    assert "maior cliente" in captions[1]


def _comparable_top_n_result(
    summary: str,
    group_column: str,
    rows: list[dict[str, object]],
    n: int,
) -> ToolResult:
    return ToolResult(
        "table",
        summary,
        [group_column, "sum_valor"],
        rows,
        chart_hint="bar",
        metadata={
            "tool": "top_n",
            "dataset": "Documentos",
            "operation": "sum",
            "value_column": "valor",
            "group_by": [group_column],
            "order": "desc",
            "n": n,
        },
    )


@pytest.mark.parametrize(
    ("supplier_rows", "client_rows", "expected_charts"),
    [
        ([{"fornecedor": "F1", "sum_valor": 20.0}],
         [{"cliente": "C1", "sum_valor": 30.0}], 0),
        ([{"fornecedor": "F1", "sum_valor": 20.0},
          {"fornecedor": "F2", "sum_valor": 10.0}],
         [{"cliente": "C1", "sum_valor": 30.0}], 0),
        ([{"fornecedor": "F1", "sum_valor": 20.0},
          {"fornecedor": "F2", "sum_valor": 10.0}],
         [{"cliente": "C1", "sum_valor": 30.0},
          {"cliente": "C2", "sum_valor": 15.0}], 2),
    ],
    ids=["dois-singletons", "tamanhos-mistos", "ambos-com-grafico"],
)
def test_comparable_top_n_results_use_symmetric_chart_policy(
    monkeypatch,
    supplier_rows: list[dict[str, object]],
    client_rows: list[dict[str, object]],
    expected_charts: int,
) -> None:
    tables = []
    figures = []
    requested_n = max(len(supplier_rows), len(client_rows))
    monkeypatch.setattr(rendering.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        rendering.st, "dataframe", lambda value, **_: tables.append(value)
    )
    monkeypatch.setattr(
        rendering.st,
        "plotly_chart",
        lambda figure, **_: figures.append(figure),
    )

    render_tool_results(
        [
            _comparable_top_n_result(
                "fornecedores", "fornecedor", supplier_rows, requested_n
            ),
            _comparable_top_n_result(
                "clientes", "cliente", client_rows, requested_n
            ),
        ]
    )

    assert len(tables) == 2
    assert len(figures) == expected_charts
