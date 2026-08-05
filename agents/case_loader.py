from __future__ import annotations

import json
from pathlib import Path

from core.constants import POLICY_VERSION
from core.models import CaseContext


class CaseLoaderAgent:
    name = "CaseLoaderAgent"

    def load(self, path: Path) -> CaseContext:
        raw = json.loads(path.read_text(encoding="utf-8"))
        expected_case_id = path.stem
        if raw.get("case_id") != expected_case_id:
            raise ValueError(
                f"case_id mismatch: filename={expected_case_id}, payload={raw.get('case_id')}"
            )
        if raw.get("policy_version") != POLICY_VERSION:
            raise ValueError(f"Unsupported policy_version: {raw.get('policy_version')}")
        request = raw.get("customer_request")
        if not isinstance(request, dict):
            raise ValueError("customer_request must be an object")
        required = ("language", "message", "claimed_order_id")
        missing = [key for key in required if not isinstance(request.get(key), str)]
        if missing:
            raise ValueError(f"Invalid customer_request fields: {missing}")
        if not isinstance(raw.get("opened_at"), str):
            raise ValueError("opened_at must be a string")
        return CaseContext(
            case_id=raw["case_id"],
            opened_at=raw["opened_at"],
            language=request["language"],
            message=request["message"],
            claimed_order_id=request["claimed_order_id"],
            policy_version=raw["policy_version"],
        )
