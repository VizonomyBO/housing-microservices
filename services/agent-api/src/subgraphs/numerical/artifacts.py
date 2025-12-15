"""Artifact helpers for numerical table/charts streaming."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from state.agent_state import ComparisonAttachment, NumericalTable

_NUMERIC_TYPES = {"int", "integer", "float", "double", "decimal", "numeric", "number", "percent"}


def build_numerical_artifacts(
    table: NumericalTable,
    rows: list[dict[str, Any]],
    *,
    table_preview_rows: int = 20,
    chart_preview_rows: int = 50,
) -> list[ComparisonAttachment]:
    """Return table + chart attachments (chart optional when axes unavailable)."""

    artifacts: list[ComparisonAttachment] = []
    artifacts.append(
        _build_table_attachment(
            table=table,
            rows=rows,
            limit=table_preview_rows,
        )
    )
    chart = _build_chart_attachment(
        table=table,
        rows=rows,
        limit=chart_preview_rows,
    )
    if chart is not None:
        artifacts.append(chart)
    return artifacts


def _build_table_attachment(
    *, table: NumericalTable, rows: list[dict[str, Any]], limit: int
) -> ComparisonAttachment:
    preview_rows = rows[:limit]
    payload = {
        "schema": [
            {
                "name": column.name,
                "type": column.data_type,
                "description": column.description,
            }
            for column in table.columns
        ],
        "rows": preview_rows,
        "row_count": len(rows),
        "table_id": table.table_id,
    }
    return ComparisonAttachment(
        attachment_type="table",
        label=f"{table.table_name} preview",
        payload=payload,
    )


def _build_chart_attachment(
    *, table: NumericalTable, rows: list[dict[str, Any]], limit: int
) -> ComparisonAttachment | None:
    if not rows:
        return None
    x_column, y_column = _infer_chart_axes(table)
    if not x_column or not y_column:
        return None
    preview = rows[:limit]
    if len(preview) < 2:
        return None
    mark = "line" if _looks_sequential(preview, x_column) else "bar"
    payload = {
        "spec": {
            "mark": mark,
            "encoding": {
                "x": {"field": x_column, "type": "ordinal"},
                "y": {"field": y_column, "type": "quantitative"},
            },
            "data": preview,
        },
        "row_count": len(preview),
        "table_id": table.table_id,
    }
    label = f"{table.table_name}: {y_column} by {x_column}"
    return ComparisonAttachment(attachment_type="chart", label=label, payload=payload)


def _infer_chart_axes(table: NumericalTable) -> tuple[str | None, str | None]:
    numeric_column = next(
        (column.name for column in table.columns if _is_numeric_type(column.data_type)),
        None,
    )
    if numeric_column is None:
        return None, None
    dimension_column = next(
        (column.name for column in table.columns if column.name != numeric_column),
        None,
    )
    if dimension_column is None:
        return None, None
    return dimension_column, numeric_column


def _is_numeric_type(data_type: str) -> bool:
    return data_type.lower() in _NUMERIC_TYPES


def _looks_sequential(rows: Iterable[dict[str, Any]], column: str) -> bool:
    """Heuristic to determine whether to use a line chart."""

    seen = []
    for row in rows:
        value = row.get(column)
        if value is None:
            continue
        seen.append(value)
        if len(seen) >= 3:
            break
    return all(isinstance(value, (int, float)) for value in seen)


__all__ = ["build_numerical_artifacts"]
