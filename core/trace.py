"""Thread-safe JSONL trace containing facts and actions, never chain-of-thought."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def emit(
        self,
        event: str,
        *,
        case_id: str | None = None,
        agent: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "event": event,
            "timestamp": utc_now(),
            "case_id": case_id,
            "agent": agent,
            "details": details or {},
        }
        line = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True)
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def message_id() -> str:
    return str(uuid4())
