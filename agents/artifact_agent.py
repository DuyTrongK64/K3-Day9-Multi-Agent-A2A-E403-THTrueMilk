from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from core.constants import (
    AGENT_ROLES,
    FRAMEWORK,
    MODEL_NAME,
    MODEL_PARAMETER_SIZE,
    MODEL_PROVIDER,
    POLICY_VERSION,
    SYSTEM_NAME,
)


class ArtifactAgent:
    name = "ArtifactAgent"

    def write_metadata(self, repo_root: Path, case_count: int) -> Path:
        metadata = {
            "system_name": SYSTEM_NAME,
            "model": {
                "name": MODEL_NAME,
                "parameter_size": MODEL_PARAMETER_SIZE,
                "provider": MODEL_PROVIDER,
                "usage": "No LLM is invoked; deterministic Python rules classify cases.",
            },
            "framework": FRAMEWORK,
            "runtime": {
                "language": "Python",
                "python_version": platform.python_version(),
                "platform": platform.platform(),
            },
            "agents": [{"name": name, "role": role} for name, role in AGENT_ROLES],
            "policy_version": POLICY_VERSION,
            "case_count": case_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        path = repo_root / "metadata.json"
        path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return path

    def validate_artifacts(self, repo_root: Path) -> None:
        for filename in ("architecture.md", "individual_5SoCuoiMHV_HoVaTen.md"):
            path = repo_root / filename
            if not path.exists() or not path.read_text(encoding="utf-8").strip():
                raise ValueError(f"Required artifact missing or empty: {filename}")
        trace = repo_root / "trace.jsonl"
        if not trace.exists() or not trace.read_text(encoding="utf-8").strip():
            raise ValueError("trace.jsonl is missing or empty")
        required_events = {
            "run_start", "case_start", "supervisor_dispatch", "agent_start",
            "agent_result", "handoff", "verification_pass", "output_write",
            "case_complete", "run_summary",
        }
        seen: set[str] = set()
        for line_number, line in enumerate(trace.read_text(encoding="utf-8").splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid trace JSON at line {line_number}: {exc}") from exc
            seen.add(event.get("event", ""))
        missing = required_events - seen
        if missing:
            raise ValueError(f"Trace missing required event types: {sorted(missing)}")
