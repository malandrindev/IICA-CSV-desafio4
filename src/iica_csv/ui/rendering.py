"""Renderização de resultados estruturados em tabela e Plotly."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping

import pandas as pd
import plotly.express as px
import streamlit as st


def result_payload(result: Any) -> dict[str, Any]:
    """Converte ``ToolResult`` (ou mapping equivalente) em dicionário."""

    if result is None:
        return {}
    if isinstance(result, Mapping):
        return dict(result)
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if is_dataclass(result):
        return asdict(result)
    return {}


def render_tool_result(
    result: Any,
    *,
    show_chart: bool = True,
    evidence_label: str = "Evidência calculada",
) -> None:
    """Mostra evidência pequena e um gráfico apenas quando houver indicação."""

    payload = result_payload(result)
    if not payload or payload.get("result_type") == "error":
        return

    with st.container(border=True):
        st.markdown(f"##### {evidence_label}")
        source = _source_details(payload)
        if source:
            st.markdown(source)

        summary = payload.get("summary")
        if summary:
            st.caption(f"Cálculo determinístico: {summary}")

        rows = payload.get("rows") or []
        columns = payload.get("columns") or []
        if not rows:
            return

        frame = pd.DataFrame(rows)
        ordered_columns = [column for column in columns if column in frame.columns]
        if ordered_columns:
            frame = frame[ordered_columns]

        if payload.get("result_type") in {"table", "series"}:
            st.markdown("**Evidência**")
            st.dataframe(frame, width="stretch", hide_index=True)

        if not show_chart:
            return

        chart_hint = payload.get("chart_hint", "none")
        if chart_hint not in {"bar", "line"} or len(frame) < 2:
            return

        axes = _chart_axes(frame, ordered_columns or list(frame.columns))
        if axes is None:
            return
        x_column, y_column = axes
        if chart_hint == "bar":
            figure = px.bar(
                frame,
                x=x_column,
                y=y_column,
                color_discrete_sequence=["#1677FF"],
            )
        else:
            figure = px.line(
                frame,
                x=x_column,
                y=y_column,
                markers=True,
                color_discrete_sequence=["#1677FF"],
            )
        _style_figure(figure, x_column, y_column)
        st.markdown("**Visualização**")
        st.plotly_chart(
            figure,
            width="stretch",
            config={"displaylogo": False, "responsive": True},
        )


def render_tool_results(results: Iterable[Any]) -> None:
    """Renderiza todas as evidências necessárias, preservando sua ordem."""

    payloads = [result_payload(result) for result in results]
    comparable_top_n = _are_comparable_top_n(payloads)
    show_comparison_charts = (
        all(_chart_is_applicable(payload) for payload in payloads)
        if comparable_top_n
        else True
    )
    for index, payload in enumerate(payloads, start=1):
        label = _evidence_label(payload, index, len(payloads))
        render_tool_result(
            payload,
            show_chart=show_comparison_charts if comparable_top_n else True,
            evidence_label=label,
        )


def _evidence_label(payload: Mapping[str, Any], index: int, total: int) -> str:
    """Gera um rótulo neutro usando somente o contrato do resultado."""

    metadata = payload.get("metadata") or {}
    groups = metadata.get("group_by") if isinstance(metadata, Mapping) else None
    if isinstance(groups, str):
        groups = [groups]
    if isinstance(groups, list) and groups:
        return " · ".join(str(group) for group in groups)
    return f"Evidência {index}" if total > 1 else "Evidência calculada"


def _source_details(payload: Mapping[str, Any]) -> str | None:
    """Apresenta fonte e colunas apenas a partir dos metadados estruturados."""

    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    dataset = metadata.get("dataset")
    columns: list[str] = []
    groups = metadata.get("group_by") or []
    if isinstance(groups, str):
        groups = [groups]
    if isinstance(groups, (list, tuple)):
        columns.extend(str(column) for column in groups if column)
    for key in (
        "value_column",
        "date_column",
        "filter_column",
        "column",
    ):
        value = metadata.get(key)
        if value:
            columns.append(str(value))
    columns = list(dict.fromkeys(columns))
    if not dataset and not columns:
        return None

    details = ["**Fonte dos dados**"]
    if dataset:
        details.append(f"Dataset: `{dataset}`")
    if columns:
        details.append("Colunas: " + " · ".join(f"`{column}`" for column in columns))
    return "  \n".join(details)


def _style_figure(figure: Any, x_column: str, y_column: str) -> None:
    """Aplica acabamento visual sem modificar dados, eixos ou tipo de gráfico."""

    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font={"color": "#344054", "family": "Arial, sans-serif", "size": 12},
        margin={"l": 18, "r": 18, "t": 18, "b": 18},
        hoverlabel={"bgcolor": "#FFFFFF", "font_color": "#172033"},
        showlegend=False,
    )
    figure.update_xaxes(
        title_text=x_column,
        showgrid=False,
        automargin=True,
        linecolor="#DFE6F0",
    )
    figure.update_yaxes(
        title_text=y_column,
        gridcolor="#E9EEF5",
        automargin=True,
        zerolinecolor="#DFE6F0",
    )


def _are_comparable_top_n(payloads: list[dict[str, Any]]) -> bool:
    """Identifica rankings irmãos para aplicar uma apresentação simétrica."""

    if len(payloads) < 2:
        return False
    metadata = [payload.get("metadata") for payload in payloads]
    if not all(
        isinstance(item, Mapping) and item.get("tool") == "top_n"
        for item in metadata
    ):
        return False

    comparison_fields = (
        "dataset",
        "operation",
        "value_column",
        "order",
        "n",
    )
    first_key = tuple(metadata[0].get(field) for field in comparison_fields)
    return all(
        tuple(item.get(field) for field in comparison_fields) == first_key
        for item in metadata[1:]
    )


def _chart_is_applicable(payload: Mapping[str, Any]) -> bool:
    """Aplica a mesma regra de gráfico sem produzir saída no Streamlit."""

    rows = payload.get("rows") or []
    if payload.get("chart_hint", "none") not in {"bar", "line"} or len(rows) < 2:
        return False
    frame = pd.DataFrame(rows)
    columns = payload.get("columns") or []
    ordered_columns = [column for column in columns if column in frame.columns]
    return _chart_axes(frame, ordered_columns or list(frame.columns)) is not None


def _chart_axes(
    frame: pd.DataFrame, contract_columns: list[str]
) -> tuple[str, str] | None:
    if frame.shape[1] < 2:
        return None

    available = [column for column in contract_columns if column in frame.columns]
    if len(available) < 2:
        return None
    y_column = available[-1]
    if not pd.api.types.is_numeric_dtype(frame[y_column]):
        return None
    x_candidates = available[:-1]
    if not x_candidates:
        return None

    if len(x_candidates) == 1:
        return x_candidates[0], y_column

    label_column = "grupo_combinado"
    while label_column in frame.columns:
        label_column = f"_{label_column}"
    frame[label_column] = frame[x_candidates].astype(str).agg(" | ".join, axis=1)
    return label_column, y_column
