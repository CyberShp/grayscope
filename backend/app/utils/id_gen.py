"""Deterministic and human-readable ID generators."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def task_id() -> str:
    short = uuid.uuid4().hex[:8]
    return f"tsk_{_ts()}_{short}"


def export_id() -> str:
    short = uuid.uuid4().hex[:8]
    return f"exp_{_ts()}_{short}"


def sync_id() -> str:
    short = uuid.uuid4().hex[:8]
    return f"sync_{_ts()}_{short}"
