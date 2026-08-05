#!/usr/bin/env python3
"""Independent full-submission validator with all hard gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.artifact_agent import ArtifactAgent
from agents.case_loader import CaseLoaderAgent
from agents.delivery_agent import DeliveryAgent
from agents.evidence_agent import EvidenceAgent
from agents.financial_agent import FinancialAgent
from agents.item_seller_agent import ItemSellerAgent
from agents.order_agent import OrderAgent
from agents.payment_agent import PaymentAgent
from agents.policy_agent import PolicyAgent
from agents.verifier_agent import VerifierAgent
from core.constants import MODEL_NAME, POLICY_VERSION, SYSTEM_NAME
from data_access.repository import OlistRepository


def _expected_entities(order, items, payments) -> dict[str, list[str]]:
    return {
        "order_ids": [order.order_id] if order.exists else [],
        "item_ids": [f"{order.order_id}:{item.order_item_id}" for item in items.items[:5]],
        "seller_ids": list(dict.fromkeys(item.seller_id for item in items.items))[:5],
        "payment_ids": [
            f"{order.order_id}:{payment.payment_sequential}"
            for payment in payments.payments[:5]
        ],
    }


def validate_submission(root: Path = REPO_ROOT, quiet: bool = False) -> dict[str, Any]:
    expected_names = [f"EC_{index:03d}.json" for index in range(1, 51)]
    input_names = sorted(path.name for path in (root / "input").glob("EC_*.json"))
    output_entries = sorted((root / "output").iterdir())
    output_files = [path for path in output_entries if path.is_file()]
    output_names = [path.name for path in output_files]
    errors: list[str] = []
    if input_names != expected_names:
        errors.append("input set is not exactly EC_001.json..EC_050.json")
    if output_names != expected_names:
        errors.append(f"output set mismatch; found {len(output_names)} files")
    unexpected_entries = [path.name for path in output_entries if path.name not in expected_names]
    if unexpected_entries:
        errors.append(f"unexpected entries in output/: {unexpected_entries}")

    repository = OlistRepository(root / "data")
    case_loader = CaseLoaderAgent()
    order_agent = OrderAgent(repository)
    item_agent = ItemSellerAgent(repository)
    payment_agent = PaymentAgent(repository)
    delivery_agent = DeliveryAgent()
    policy_agent = PolicyAgent()
    evidence_agent = EvidenceAgent()
    financial_agent = FinancialAgent()
    verifier = VerifierAgent(repository)

    schema_passed = business_passed = evidence_passed = financial_passed = 0
    seen_case_ids: set[str] = set()
    for name in expected_names:
        input_path, output_path = root / "input" / name, root / "output" / name
        if not input_path.is_file() or not output_path.is_file():
            continue
        try:
            draft = json.loads(output_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{name}: invalid UTF-8 JSON: {exc}")
            continue
        case_id = name[:-5]
        if draft.get("case_id") != case_id:
            errors.append(f"{name}: case_id does not match filename")
        if draft.get("case_id") in seen_case_ids:
            errors.append(f"{name}: duplicate case_id")
        seen_case_ids.add(draft.get("case_id"))

        context = case_loader.load(input_path)
        order = order_agent.inspect(context.claimed_order_id)
        items = item_agent.inspect(context.claimed_order_id)
        items = item_agent.identify_late_handoffs(items, order.delivered_carrier_date)
        payment_rows = payment_agent.load_payments(context.claimed_order_id)
        payments = payment_agent.reconcile(
            context.claimed_order_id, payment_rows, items.item_total, items.freight_total
        )
        delivery = delivery_agent.analyze(order, items)
        decision = policy_agent.decide(case_id, order, payments, delivery)
        evidence = evidence_agent.build(order, items, payments, decision)
        financial = financial_agent.calculate(items, payments, decision)
        result = verifier.verify(
            context, order, items, payments, delivery, decision,
            evidence, financial, draft,
        )
        if result.passed:
            schema_passed += 1
            business_passed += 1
            evidence_passed += 1
            financial_passed += 1
        else:
            errors.extend(f"{name}: {error}" for error in result.errors)
        if draft.get("affected_entities") != _expected_entities(order, items, payments):
            errors.append(f"{name}: affected entities are incomplete or not deterministic")

    required = (
        "architecture.md", "individual_5SoCuoiMHV_HoVaTen.md",
        "trace.jsonl", "metadata.json",
    )
    for filename in required:
        path = root / filename
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"missing or empty artifact: {filename}")
    metadata_path = root / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("system_name") != SYSTEM_NAME:
                errors.append("metadata system_name mismatch")
            if metadata.get("policy_version") != POLICY_VERSION:
                errors.append("metadata policy_version mismatch")
            if metadata.get("case_count") != 50:
                errors.append("metadata case_count must be 50")
            if metadata.get("model", {}).get("name") != MODEL_NAME:
                errors.append("metadata model name differs from source")
        except json.JSONDecodeError as exc:
            errors.append(f"metadata.json invalid: {exc}")
    try:
        ArtifactAgent().validate_artifacts(root)
    except ValueError as exc:
        errors.append(str(exc))

    summary = {
        "cases_expected": 50,
        "cases_generated": len(output_files),
        "schema_passed": schema_passed,
        "business_rules_passed": business_passed,
        "evidence_passed": evidence_passed,
        "financial_checks_passed": financial_passed,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }
    if not quiet:
        print("Cases expected: 50")
        print(f"Cases generated: {len(output_files)}")
        print(f"Schema passed: {schema_passed}")
        print(f"Business rules passed: {business_passed}")
        print(f"Evidence passed: {evidence_passed}")
        print(f"Financial checks passed: {financial_passed}")
        print(f"Submission status: {summary['status']}")
        for error in errors:
            print(f"ERROR: {error}")
    return summary


if __name__ == "__main__":
    result = validate_submission()
    raise SystemExit(0 if result["status"] == "PASS" else 1)
