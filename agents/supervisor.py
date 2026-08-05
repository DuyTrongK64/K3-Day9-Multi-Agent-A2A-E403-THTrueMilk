from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, TypeVar

from agents.case_loader import CaseLoaderAgent
from agents.delivery_agent import DeliveryAgent
from agents.evidence_agent import EvidenceAgent
from agents.financial_agent import FinancialAgent
from agents.item_seller_agent import ItemSellerAgent
from agents.order_agent import OrderAgent
from agents.payment_agent import PaymentAgent
from agents.policy_agent import PolicyAgent
from agents.verifier_agent import VerifierAgent
from core.decimal_utils import json_money
from core.models import (
    AgentMessage,
    CaseContext,
    DeliveryFacts,
    EvidenceBundle,
    FinancialResolution,
    FinalCaseOutput,
    ItemSellerFacts,
    OrderFacts,
    PaymentFact,
    PaymentFacts,
    PolicyDecision,
)
from core.trace import TraceWriter, message_id, utc_now

T = TypeVar("T")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


class SupervisorAgent:
    """Coordinates agents; it never queries CSV data directly or classifies a case."""

    name = "SupervisorAgent"
    max_verification_attempts = 3

    def __init__(self, repository, trace: TraceWriter, output_dir: Path) -> None:
        self.trace = trace
        self.output_dir = output_dir
        self.case_loader = CaseLoaderAgent()
        self.order_agent = OrderAgent(repository)
        self.item_agent = ItemSellerAgent(repository)
        self.payment_agent = PaymentAgent(repository)
        self.delivery_agent = DeliveryAgent()
        self.policy_agent = PolicyAgent()
        self.evidence_agent = EvidenceAgent()
        self.financial_agent = FinancialAgent()
        self.verifier_agent = VerifierAgent(repository)

    def _summary(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, OrderFacts):
            return {"order_id": payload.order_id, "exists": payload.exists,
                    "status": payload.order_status, "null_fields": list(payload.null_fields)}
        if isinstance(payload, ItemSellerFacts):
            return {"order_id": payload.order_id, "item_count": len(payload.items),
                    "seller_count": len({item.seller_id for item in payload.items}),
                    "late_handoff_seller_ids": list(payload.late_handoff_seller_ids)}
        if isinstance(payload, PaymentFacts):
            return {"order_id": payload.order_id, "payment_count": len(payload.payments),
                    "matches_order_total": payload.matches_order_total,
                    "valid_split_payment": payload.valid_split_payment}
        if isinstance(payload, DeliveryFacts):
            return _jsonable(payload)
        if isinstance(payload, PolicyDecision):
            return {"primary_issue": payload.primary_issue,
                    "root_cause": payload.root_cause, "action": payload.action}
        if isinstance(payload, EvidenceBundle):
            return {"evidence_count": len(payload.evidence_ids)}
        if isinstance(payload, FinancialResolution):
            return {"currency": payload.currency,
                    "recommended_refund_brl": str(payload.recommended_refund_brl)}
        if isinstance(payload, tuple) and all(isinstance(x, PaymentFact) for x in payload):
            return {"payment_count": len(payload)}
        if isinstance(payload, CaseContext):
            return {"claimed_order_id": payload.claimed_order_id,
                    "policy_version": payload.policy_version}
        return {"type": type(payload).__name__}

    def _dispatch(
        self,
        *,
        case_id: str,
        agent_name: str,
        task: str,
        input_refs: list[str],
        operation: Callable[[], T],
    ) -> T:
        self.trace.emit(
            "supervisor_dispatch", case_id=case_id, agent=self.name,
            details={"recipient": agent_name, "task": task, "input_refs": input_refs},
        )
        started = utc_now()
        self.trace.emit(
            "agent_start", case_id=case_id, agent=agent_name,
            details={"task": task, "input_refs": input_refs},
        )
        try:
            payload = operation()
            status, errors = "completed", ()
        except Exception as exc:
            payload = None
            status, errors = "failed", (f"{type(exc).__name__}: {exc}",)
        completed = utc_now()
        summary = self._summary(payload) if payload is not None else {}
        message = AgentMessage(
            message_id=message_id(), case_id=case_id, sender=agent_name,
            recipient=self.name, task=task, status=status,
            input_refs=tuple(input_refs), payload=summary, errors=errors,
            started_at=started, completed_at=completed,
        )
        self.trace.emit(
            "agent_result", case_id=case_id, agent=agent_name,
            details={"message": message.to_dict()},
        )
        self.trace.emit(
            "handoff", case_id=case_id, agent=agent_name,
            details={"sender": agent_name, "recipient": self.name,
                     "message_id": message.message_id, "status": status},
        )
        if errors:
            raise RuntimeError(errors[0])
        return payload  # type: ignore[return-value]

    def run_case(self, case_path: Path) -> dict[str, Any]:
        case_id = case_path.stem
        self.trace.emit("case_start", case_id=case_id, agent=self.name,
                        details={"input": str(case_path.name)})
        context = self._dispatch(
            case_id=case_id, agent_name=self.case_loader.name, task="load_case",
            input_refs=[f"input:{case_path.name}"],
            operation=lambda: self.case_loader.load(case_path),
        )
        order_id = context.claimed_order_id

        # Domain extraction is concurrent; each operation uses a disjoint query API.
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix=case_id) as executor:
            order_future = executor.submit(
                self._dispatch, case_id=case_id, agent_name=self.order_agent.name,
                task="inspect_order", input_refs=[f"order:{order_id}"],
                operation=lambda: self.order_agent.inspect(order_id),
            )
            item_future = executor.submit(
                self._dispatch, case_id=case_id, agent_name=self.item_agent.name,
                task="inspect_items_and_sellers", input_refs=[f"order:{order_id}"],
                operation=lambda: self.item_agent.inspect(order_id),
            )
            payment_future = executor.submit(
                self._dispatch, case_id=case_id, agent_name=self.payment_agent.name,
                task="load_payments", input_refs=[f"order:{order_id}"],
                operation=lambda: self.payment_agent.load_payments(order_id),
            )
            order = order_future.result()
            items = item_future.result()
            payment_rows = payment_future.result()

        items = self._dispatch(
            case_id=case_id, agent_name=self.item_agent.name,
            task="identify_late_handoffs",
            input_refs=[f"facts:items:{case_id}", f"facts:order:{case_id}"],
            operation=lambda: self.item_agent.identify_late_handoffs(
                items, order.delivered_carrier_date
            ),
        )
        payments = self._dispatch(
            case_id=case_id, agent_name=self.payment_agent.name,
            task="reconcile_payments",
            input_refs=[f"facts:payments:{case_id}", f"facts:items:{case_id}"],
            operation=lambda: self.payment_agent.reconcile(
                order_id, payment_rows, items.item_total, items.freight_total
            ),
        )
        delivery = self._dispatch(
            case_id=case_id, agent_name=self.delivery_agent.name,
            task="analyze_delivery",
            input_refs=[f"facts:order:{case_id}", f"facts:items:{case_id}"],
            operation=lambda: self.delivery_agent.analyze(order, items),
        )
        decision = self._dispatch(
            case_id=case_id, agent_name=self.policy_agent.name,
            task="apply_ec_policy_v1",
            input_refs=[f"facts:order:{case_id}", f"facts:payments:{case_id}",
                        f"facts:delivery:{case_id}"],
            operation=lambda: self.policy_agent.decide(case_id, order, payments, delivery),
        )
        evidence, financial = self._post_policy(case_id, order, items, payments, decision)

        draft = self._build_draft(
            context, order, items, payments, decision, evidence, financial
        )
        verification = None
        for attempt in range(1, self.max_verification_attempts + 1):
            verification = self._dispatch(
                case_id=case_id, agent_name=self.verifier_agent.name,
                task="verify_draft",
                input_refs=[f"draft:{case_id}", f"facts:all:{case_id}"],
                operation=lambda: self.verifier_agent.verify(
                    context, order, items, payments, delivery, decision,
                    evidence, financial, draft,
                ),
            )
            if verification.passed:
                self.trace.emit(
                    "verification_pass", case_id=case_id, agent=self.verifier_agent.name,
                    details={"attempt": attempt},
                )
                break
            self.trace.emit(
                "verifier_errors", case_id=case_id, agent=self.verifier_agent.name,
                details={"attempt": attempt, "errors": list(verification.errors)},
            )
            if attempt == self.max_verification_attempts:
                raise RuntimeError(
                    f"Verification failed after {attempt} attempts: {verification.errors}"
                )
            self.trace.emit(
                "retry", case_id=case_id, agent=self.name,
                details={"attempt": attempt + 1,
                         "targets": self._retry_targets(verification.errors)},
            )
            # Route validation feedback to responsible agents and rebuild dependants.
            decision = self._dispatch(
                case_id=case_id, agent_name=self.policy_agent.name,
                task="retry_policy_after_verifier",
                input_refs=[f"verifier_errors:{case_id}"],
                operation=lambda: self.policy_agent.decide(case_id, order, payments, delivery),
            )
            evidence, financial = self._post_policy(
                case_id, order, items, payments, decision
            )
            draft = self._build_draft(
                context, order, items, payments, decision, evidence, financial
            )

        self._write_output(case_id, draft)
        self.trace.emit("case_complete", case_id=case_id, agent=self.name,
                        details={"status": "completed"})
        return draft

    def _post_policy(
        self,
        case_id: str,
        order: OrderFacts,
        items: ItemSellerFacts,
        payments: PaymentFacts,
        decision: PolicyDecision,
    ) -> tuple[EvidenceBundle, FinancialResolution]:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"{case_id}-post") as executor:
            evidence_future = executor.submit(
                self._dispatch, case_id=case_id, agent_name=self.evidence_agent.name,
                task="build_evidence", input_refs=[f"decision:{case_id}", f"facts:all:{case_id}"],
                operation=lambda: self.evidence_agent.build(order, items, payments, decision),
            )
            financial_future = executor.submit(
                self._dispatch, case_id=case_id, agent_name=self.financial_agent.name,
                task="calculate_resolution", input_refs=[f"decision:{case_id}",
                                                         f"facts:money:{case_id}"],
                operation=lambda: self.financial_agent.calculate(items, payments, decision),
            )
            return evidence_future.result(), financial_future.result()

    @staticmethod
    def _retry_targets(errors: tuple[str, ...]) -> list[str]:
        targets: set[str] = set()
        for error in errors:
            prefix = error.split(":", 1)[0]
            targets.add({
                "policy": "PolicyAgent", "financial": "FinancialAgent",
                "evidence": "EvidenceAgent", "confidence": "SupervisorAgent",
                "referential": "EvidenceAgent", "schema": "SupervisorAgent",
                "cardinality": "SupervisorAgent", "enum": "PolicyAgent",
            }.get(prefix, "SupervisorAgent"))
        return sorted(targets)

    def _build_draft(
        self,
        context: CaseContext,
        order: OrderFacts,
        items: ItemSellerFacts,
        payments: PaymentFacts,
        decision: PolicyDecision,
        evidence: EvidenceBundle,
        financial: FinancialResolution,
    ) -> dict[str, Any]:
        seller_ids = list(dict.fromkeys(item.seller_id for item in items.items))[:5]
        output = FinalCaseOutput(
            case_id=context.case_id,
            assessment={
                "primary_issue": decision.primary_issue,
                "case_status": decision.case_status,
                "confidence": self.verifier_agent.expected_confidence(order, items, payments),
            },
            affected_entities={
                "order_ids": [order.order_id] if order.exists else [],
                "item_ids": [
                    f"{order.order_id}:{item.order_item_id}" for item in items.items[:5]
                ],
                "seller_ids": seller_ids,
                "payment_ids": [
                    f"{order.order_id}:{payment.payment_sequential}"
                    for payment in payments.payments[:5]
                ],
            },
            root_cause_analysis={
                "ranked_causes": [{"cause_code": decision.root_cause, "rank": 1}],
                "responsible_parties": [
                    {"party_type": party.party_type, "party_id": party.party_id}
                    for party in decision.responsible_parties
                ],
            },
            evidence_ids=list(evidence.evidence_ids),
            financial_resolution={
                "currency": financial.currency,
                "item_total_brl": json_money(financial.item_total_brl),
                "freight_total_brl": json_money(financial.freight_total_brl),
                "payment_total_brl": json_money(financial.payment_total_brl),
                "recommended_refund_brl": json_money(financial.recommended_refund_brl),
            },
            resolution_actions=[decision.action],
        )
        return output.to_dict()

    def _write_output(self, case_id: str, draft: dict[str, Any]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.output_dir / f"{case_id}.json"
        temp_path = self.output_dir / f".{case_id}.json.tmp"
        temp_path.write_text(
            json.dumps(draft, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, final_path)
        self.trace.emit("output_write", case_id=case_id, agent=self.name,
                        details={"path": str(final_path.name), "atomic": True})
