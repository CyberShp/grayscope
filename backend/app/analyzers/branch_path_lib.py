"""分支路径分类与评分，供 branch_path 分析器与规则共用。"""

from __future__ import annotations

import re

_ERROR_RETURN_RE = re.compile(
    r"return\s+(-\s*\w+|NULL|false|errno|(-1))", re.IGNORECASE
)
_NULL_CHECK_RE = re.compile(
    r"(?:^|\b)(\w+)\s*(==|!=)\s*(NULL|nullptr|0)\b",
    re.VERBOSE | re.IGNORECASE,
)
_NEG_RETURN_RE = re.compile(r"<\s*0|==\s*-1|!=\s*0")
_CONSTANT_CMP_RE = re.compile(
    r"(\w+)\s*(==|!=)\s*([A-Z_][A-Z0-9_]+)", re.VERBOSE
)
_BOUNDARY_RE = re.compile(
    r"(\w+)\s*(<=|>=|<|>)\s*(\w+|\d+)", re.VERBOSE
)
_SIZE_VAR_RE = re.compile(
    r"\b(size|len|length|count|num|idx|index|offset|capacity|initlen|buflen|"
    r"maxlen|minlen|nread|nwrite|nelem|total|avail|remain)\b",
    re.IGNORECASE,
)


def classify_branch(label: str) -> str:
    """将分支分类为 error、cleanup、boundary、state 或 normal。"""
    text = label
    if text.startswith("if "):
        text = text[3:]
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    low = text.lower()

    if re.search(r"\bgoto\b", low) or any(kw in low for kw in ("cleanup", "out:", "bail")):
        return "cleanup"
    if "&&" in text or "||" in text:
        op = "&&" if "&&" in text else "||"
        parts = [p.strip() for p in text.split(op)]
        sub_types = [_classify_single_condition(p) for p in parts]
        _PRIORITY = {"error": 0, "cleanup": 1, "boundary": 2, "state": 3, "normal": 4}
        return min(sub_types, key=lambda t: _PRIORITY.get(t, 4))
    return _classify_single_condition(text)


def _classify_single_condition(text: str) -> str:
    low = text.lower().strip()
    if re.search(r"\b(err|error|fail|failure|rc|ret)\b", low):
        return "error"
    if _NEG_RETURN_RE.search(text):
        return "error"
    null_m = _NULL_CHECK_RE.search(text)
    if null_m:
        var_name = null_m.group(1)
        rhs_val = null_m.group(3)
        if rhs_val == "0" and _SIZE_VAR_RE.search(var_name):
            return "boundary"
        return "error"
    if re.match(r"^!\s*\w+$", text.strip()):
        return "error"
    if _BOUNDARY_RE.search(text):
        return "boundary"
    if _SIZE_VAR_RE.search(text) and re.search(r"[<>=!]", text):
        return "boundary"
    if _CONSTANT_CMP_RE.search(text):
        return "state"
    return "normal"


def score_branch(path_type: str) -> float:
    """单个分支的风险评分。"""
    return {"error": 0.8, "cleanup": 0.85, "boundary": 0.7, "state": 0.5, "normal": 0.3}.get(path_type, 0.3)
