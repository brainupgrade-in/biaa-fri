"""Deterministic computation sandbox for financial metrics."""

from __future__ import annotations

import math
import sys
from typing import Any

from RestrictedPython import compile_restricted
from RestrictedPython.PrintCollector import PrintCollector

from shared.schemas import ComputationResult, ExtractedFigure, SourceLocation


def _safe_eval(formula: str, local_vars: dict[str, float]) -> Any:
    """Safely evaluate a formula using RestrictedPython."""
    # Compile the formula with restrictions
    byte_code = compile_restricted(
        formula,
        filename="<computation>",
        mode="eval"
    )
    
    # Create restricted globals
    restricted_globals = {
        "__builtins__": {
            "abs": abs,
            "min": min,
            "max": max,
            "sum": sum,
            "round": round,
            "pow": pow,
        },
        "__metaclass__": type,
        "__name__": "__main__",
        "_print_": PrintCollector,
        "_getattr_": getattr,
        "_write_": lambda x: x,
    }
    
    # Execute in restricted environment
    result = eval(byte_code, restricted_globals, local_vars)
    return result


def execute_computation(
    formula: str,
    inputs: dict[str, float],
    metric: str = "",
    unit: str = "ratio",
    sources: dict[str, ExtractedFigure] | None = None,
) -> ComputationResult:
    """Execute a formula in a sandboxed environment."""
    sources = sources or {}

    try:
        # Validate inputs exist - check if formula references variables not in inputs
        import re
        # Find all variable names in formula (simple regex for alphanumeric + underscore)
        formula_vars = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', formula))
        # Filter out builtins and keywords
        builtins = {'abs', 'min', 'max', 'sum', 'round', 'pow'}
        formula_vars = {v for v in formula_vars if v not in builtins and v not in ('True', 'False', 'None')}
        missing = [v for v in formula_vars if v not in inputs]
        if missing:
            return ComputationResult(
                result=None, formula=formula, unit=unit, metric=metric,
                error=f"Missing inputs: {missing}",
            )

        # Validate unit consistency (skip for ratio)
        units = set()
        for name in inputs:
            if name in sources:
                units.add(sources[name].unit)
        non_ratio = {u for u in units if u not in ("ratio", "%", "")}
        if len(non_ratio) > 1:
            return ComputationResult(
                result=None, formula=formula, unit=unit, metric=metric,
                error=f"Unit mismatch: {non_ratio}",
            )

        # Execute in sandbox
        local_vars = dict(inputs)
        result = _safe_eval(formula, local_vars)

        if math.isinf(result) or math.isnan(result):
            return ComputationResult(
                result=None, formula=formula, unit=unit, metric=metric,
                error="Overflow or invalid result",
            )

        # Build inputs_with_sources
        inputs_with_sources = []
        for name, val in inputs.items():
            if name in sources:
                inputs_with_sources.append(sources[name])
            else:
                inputs_with_sources.append(ExtractedFigure(
                    value=val, unit=unit,
                    source_loc=SourceLocation(doc_id="unknown", page=0, table_or_figure="", row_col_or_line=name),
                    confidence="unverified",
                ))

        return ComputationResult(
            result=round(result, 2),
            formula=formula,
            inputs_with_sources=inputs_with_sources,
            unit=unit,
            metric=metric,
            error=None,
        )
    except ZeroDivisionError:
        return ComputationResult(
            result=None, formula=formula, unit=unit, metric=metric,
            error="Division by zero",
        )
    except SyntaxError as e:
        return ComputationResult(
            result=None, formula=formula, unit=unit, metric=metric,
            error=f"Syntax error: {e}",
        )
    except Exception as e:
        return ComputationResult(
            result=None, formula=formula, unit=unit, metric=metric,
            error=str(e),
        )


def compute_z_score(values: list[float], current: float) -> float:
    """Compute z-score for a value against historical values."""
    if not values or len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return 0.0
    return (current - mean) / std
