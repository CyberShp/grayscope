"""Shared data utilities."""

from __future__ import annotations

from typing import Any


def flatten_list(value: Any) -> list[str]:
    """Flatten nested lists to a flat list of strings.
    
    Handles cases where a value might be:
    - None -> []
    - str -> [str]
    - list[str] -> list[str]
    - list[list[str]] -> flattened list[str]
    - other -> [str(other)]
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, list):
                result.extend(str(x) for x in item)
            else:
                result.append(str(item))
        return result
    return [str(value)]
