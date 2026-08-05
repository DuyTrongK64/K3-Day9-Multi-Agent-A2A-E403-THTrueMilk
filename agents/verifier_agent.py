"""Independent hard gates. This module intentionally reimplements policy and sums."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from core.constants import ACTIONS, CASE_STATUSES, PRIMARY_ISSUES, ROOT_CAUSES
from core.decimal_utils import PAYMENT_TOLERANCE, money, sum_money
from core.models import (
    CaseContext,
    DeliveryFacts,
    EvidenceBundle,
    FinancialResolution,
    ItemSellerFacts,
    OrderFacts,
    PaymentFacts,
    PolicyDecision,
    ResponsibleParty,
    VerificationResult,
)
from data_access.repository import OlistRepository


class VerifierAgent:
    name = "VerifierAgent"
    _HEX_OR_TOKEN = r"[^:]+"
    _EVIDENCE_RE = re.compile(
        rf"^(order:{_HEX_OR_TOKEN}|item:{_HEX_OR_TOKEN}:{_HEX_OR_TOKEN}|"
        rf"payment:{_HEX_OR_TOKEN}:{_HEX_OR_TOKEN}|seller:{_HEX_OR_TOKEN}|"
        rf"policy:{_HEX_OR_TOKEN})$"
    )

    def __init__(self, repository: OlistRepository) -> None:
        self.repository = repository

    @staticmethod
    def expected_confidence(
        order: OrderFacts,
        items: ItemSellerFacts,
        payments: PaymentFacts,
    ) -> float:
        if len(items.items) > 1 or len(payments.payments) > 1:
            return 0.95
        if order.null_fields:
            return 0.97
        return 0.99

    def verify(
        self,
        context: CaseContext,
        order: OrderFacts,
        items: ItemSellerFacts,
        payments: PaymentFacts,
        delivery: DeliveryFacts,
        decision: PolicyDecision,
        evidence: EvidenceBundle,
        financial: FinancialResolution,
        draft: dict[str, Any],
    ) -> VerificationResult:
        errors: list[str] = []
        self._schema_gate(draft, errors)
        if errors:
            return VerificationResult(False, tuple(errors))
        self._enum_and_cardinality_gate(draft, errors)
        self._referential_gate(draft, errors)
        expected_decision = self._independent_policy(order, items, payments)
        if expected_decision is None:
            errors.append("policy: no EC_POLICY_V1 rule matches independently")
        else:
            self._business_gate(draft, decision, expected_decision, errors)
        self._financial_gate(draft, items, payments, decision, financial, errors)
        self._confidence_gate(draft, order, items, payments, errors)
        self._evidence_gate(draft, evidence, decision, errors)
        if draft["case_id"] != context.case_id:
            errors.append("schema: case_id differs from CaseContext")
        return VerificationResult(not errors, tuple(errors))

    @staticmethod
    def _schema_gate(draft: dict[str, Any], errors: list[str]) -> None:
        top = {
            "case_id", "assessment", "affected_entities", "root_cause_analysis",
            "evidence_ids", "financial_resolution", "resolution_actions",
        }
        if not isinstance(draft, dict) or set(draft) != top:
            errors.append("schema: top-level fields must match exactly")
            return
        expected_nested = {
            "assessment": {"primary_issue", "case_status", "confidence"},
            "affected_entities": {"order_ids", "item_ids", "seller_ids", "payment_ids"},
            "root_cause_analysis": {"ranked_causes", "responsible_parties"},
            "financial_resolution": {
                "currency", "item_total_brl", "freight_total_brl",
                "payment_total_brl", "recommended_refund_brl",
            },
        }
        if not isinstance(draft["case_id"], str):
            errors.append("schema: case_id must be string")
        for key, fields in expected_nested.items():
            value = draft[key]
            if not isinstance(value, dict) or set(value) != fields:
                errors.append(f"schema: {key} fields must match exactly")
        for key in ("evidence_ids", "resolution_actions"):
            if not isinstance(draft[key], list):
                errors.append(f"schema: {key} must be an array")
        if errors:
            return
        entities = draft["affected_entities"]
        for key in ("order_ids", "item_ids", "seller_ids", "payment_ids"):
            if not isinstance(entities[key], list) or not all(
                isinstance(value, str) for value in entities[key]
            ):
                errors.append(f"schema: affected_entities.{key} must be string array")
        root = draft["root_cause_analysis"]
        if not isinstance(root["ranked_causes"], list) or not all(
            isinstance(value, dict) and set(value) == {"cause_code", "rank"}
            for value in root["ranked_causes"]
        ):
            errors.append("schema: ranked_causes has invalid objects")
        if not isinstance(root["responsible_parties"], list) or not all(
            isinstance(value, dict) and set(value) == {"party_type", "party_id"}
            for value in root["responsible_parties"]
        ):
            errors.append("schema: responsible_parties has invalid objects")

    @staticmethod
    def _enum_and_cardinality_gate(draft: dict[str, Any], errors: list[str]) -> None:
        assessment = draft["assessment"]
        if assessment["primary_issue"] not in PRIMARY_ISSUES:
            errors.append("enum: primary_issue is invalid")
        if assessment["case_status"] not in CASE_STATUSES:
            errors.append("enum: case_status is invalid")
        actions = draft["resolution_actions"]
        if any(action not in ACTIONS for action in actions):
            errors.append("enum: resolution action is invalid")
        causes = draft["root_cause_analysis"]["ranked_causes"]
        if any(cause.get("cause_code") not in ROOT_CAUSES for cause in causes):
            errors.append("enum: root cause is invalid")
        limits = {"order_ids": 5, "item_ids": 5, "seller_ids": 5, "payment_ids": 5}
        for key, limit in limits.items():
            values = draft["affected_entities"][key]
            if len(values) > limit:
                errors.append(f"cardinality: {key} exceeds {limit}")
            if len(values) != len(set(values)):
                errors.append(f"cardinality: {key} contains duplicates")
        bounded = (
            ("evidence_ids", draft["evidence_ids"], 10),
            ("ranked_causes", causes, 3),
            ("responsible_parties", draft["root_cause_analysis"]["responsible_parties"], 3),
            ("resolution_actions", actions, 5),
        )
        for key, values, limit in bounded:
            if len(values) > limit:
                errors.append(f"cardinality: {key} exceeds {limit}")
        if len(draft["evidence_ids"]) != len(set(draft["evidence_ids"])):
            errors.append("cardinality: evidence_ids contains duplicates")

    def _referential_gate(self, draft: dict[str, Any], errors: list[str]) -> None:
        entities = draft["affected_entities"]
        for order_id in entities["order_ids"]:
            if not self.repository.order_exists(order_id):
                errors.append(f"referential: unknown order {order_id}")
        for item_id in entities["item_ids"]:
            parts = item_id.split(":")
            if len(parts) != 2 or not self.repository.item_exists(parts[0], parts[1]):
                errors.append(f"referential: unknown item {item_id}")
        for seller_id in entities["seller_ids"]:
            if not self.repository.seller_exists(seller_id):
                errors.append(f"referential: unknown seller {seller_id}")
        for payment_id in entities["payment_ids"]:
            parts = payment_id.split(":")
            if len(parts) != 2 or not self.repository.payment_exists(parts[0], parts[1]):
                errors.append(f"referential: unknown payment {payment_id}")

    @staticmethod
    def _independent_policy(
        order: OrderFacts,
        items: ItemSellerFacts,
        payments: PaymentFacts,
    ) -> PolicyDecision | None:
        # Recompute raw predicates without calling PolicyAgent or trusting derived
        # PaymentFacts/DeliveryFacts booleans, which detects calculation drift too.
        payment_total = sum_money(payment.payment_value for payment in payments.payments)
        order_total = sum_money(
            [*(item.price for item in items.items),
             *(item.freight_value for item in items.items)]
        )
        payment_matches = abs(payment_total - order_total) <= PAYMENT_TOLERANCE
        delivered_late = bool(
            order.delivered_customer_date
            and order.estimated_delivery_date
            and order.delivered_customer_date > order.estimated_delivery_date
        )
        delivered_on_time = bool(
            order.delivered_customer_date
            and order.estimated_delivery_date
            and order.delivered_customer_date <= order.estimated_delivery_date
        )
        late_sellers = tuple(sorted({
            item.seller_id
            for item in items.items
            if order.delivered_carrier_date
            and item.shipping_limit_date
            and order.delivered_carrier_date > item.shipping_limit_date
        }))
        carrier_not_late = bool(
            order.delivered_carrier_date
            and items.items
            and all(
                item.shipping_limit_date
                and order.delivered_carrier_date <= item.shipping_limit_date
                for item in items.items
            )
        )
        if order.order_status == "canceled" and payment_total > 0:
            return PolicyDecision(
                "canceled_order_paid", "action_required", "ORDER_CANCELED_AFTER_PAYMENT",
                (ResponsibleParty("platform", "OLIST_PLATFORM"),), "issue_full_refund",
            )
        if order.order_status == "unavailable" and payment_total > 0:
            return PolicyDecision(
                "unavailable_order_paid", "action_required",
                "ORDER_UNAVAILABLE_AFTER_PAYMENT",
                (ResponsibleParty("platform", "OLIST_PLATFORM"),), "issue_full_refund",
            )
        if delivered_late and late_sellers:
            return PolicyDecision(
                "late_delivery_seller", "action_required", "SELLER_HANDOFF_AFTER_LIMIT",
                tuple(
                    ResponsibleParty("seller", seller_id)
                    for seller_id in late_sellers[:3]
                ), "refund_freight",
            )
        if delivered_late and carrier_not_late:
            return PolicyDecision(
                "late_delivery_logistics", "action_required",
                "CARRIER_DELIVERED_AFTER_ESTIMATE",
                (ResponsibleParty("logistics_provider", "LOGISTICS_PROVIDER"),),
                "refund_freight",
            )
        if len(payments.payments) >= 2 and payment_matches:
            return PolicyDecision(
                "valid_split_payment", "no_action", "MULTIPLE_PAYMENTS_RECONCILED",
                (), "explain_valid_split_payment",
            )
        if delivered_on_time and payment_matches:
            return PolicyDecision(
                "unsupported_late_claim", "no_action", "DELIVERY_WITHIN_ESTIMATE",
                (), "reject_late_refund",
            )
        return None

    @staticmethod
    def _business_gate(
        draft: dict[str, Any],
        declared: PolicyDecision,
        expected: PolicyDecision,
        errors: list[str],
    ) -> None:
        if declared != expected:
            errors.append("policy: PolicyAgent decision differs from independent rule result")
        assessment = draft["assessment"]
        if assessment["primary_issue"] != expected.primary_issue:
            errors.append("policy: draft primary_issue differs from independent result")
        if assessment["case_status"] != expected.case_status:
            errors.append("policy: draft case_status differs from independent result")
        causes = draft["root_cause_analysis"]["ranked_causes"]
        if causes != [{"cause_code": expected.root_cause, "rank": 1}]:
            errors.append("policy: ranked cause mapping is invalid")
        parties = draft["root_cause_analysis"]["responsible_parties"]
        expected_parties = [
            {"party_type": party.party_type, "party_id": party.party_id}
            for party in expected.responsible_parties
        ]
        if parties != expected_parties:
            errors.append("policy: responsible parties differ from independent result")
        if draft["resolution_actions"] != [expected.action]:
            errors.append("policy: resolution action differs from independent result")

    @staticmethod
    def _financial_gate(
        draft: dict[str, Any],
        items: ItemSellerFacts,
        payments: PaymentFacts,
        decision: PolicyDecision,
        declared: FinancialResolution,
        errors: list[str],
    ) -> None:
        expected_item = sum_money(item.price for item in items.items)
        expected_freight = sum_money(item.freight_value for item in items.items)
        expected_payment = sum_money(payment.payment_value for payment in payments.payments)
        if decision.primary_issue in {"canceled_order_paid", "unavailable_order_paid"}:
            expected_refund = expected_payment
        elif decision.primary_issue in {"late_delivery_seller", "late_delivery_logistics"}:
            expected_refund = expected_freight
        else:
            expected_refund = money(0)
        expected = {
            "currency": "BRL",
            "item_total_brl": expected_item,
            "freight_total_brl": expected_freight,
            "payment_total_brl": expected_payment,
            "recommended_refund_brl": expected_refund,
        }
        if declared.currency != "BRL" or any(
            getattr(declared, key) != value
            for key, value in expected.items()
            if key != "currency"
        ):
            errors.append("financial: FinancialAgent result differs from independent sums")
        output = draft["financial_resolution"]
        if output.get("currency") != "BRL":
            errors.append("financial: currency must be BRL")
        for key, expected_value in expected.items():
            if key == "currency":
                continue
            value = output.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"financial: {key} must be a JSON number")
                continue
            try:
                actual = Decimal(str(value))
            except InvalidOperation:
                errors.append(f"financial: {key} is not decimal-compatible")
                continue
            if actual != money(actual) or money(actual) != expected_value:
                errors.append(f"financial: {key} amount mismatch or not rounded")
        status = draft["assessment"]["case_status"]
        if (expected_refund > 0 and status != "action_required") or (
            expected_refund == 0 and status != "no_action"
        ):
            errors.append("financial: refund and case_status are inconsistent")

    @classmethod
    def _confidence_gate(
        cls,
        draft: dict[str, Any],
        order: OrderFacts,
        items: ItemSellerFacts,
        payments: PaymentFacts,
        errors: list[str],
    ) -> None:
        confidence = draft["assessment"].get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            errors.append("confidence: must be numeric")
            return
        if not 0 <= confidence <= 1:
            errors.append("confidence: must be within [0,1]")
        if confidence != cls.expected_confidence(order, items, payments):
            errors.append("confidence: differs from deterministic criteria")

    def _evidence_gate(
        self,
        draft: dict[str, Any],
        declared: EvidenceBundle,
        decision: PolicyDecision,
        errors: list[str],
    ) -> None:
        values = draft["evidence_ids"]
        if values != list(declared.evidence_ids):
            errors.append("evidence: draft differs from EvidenceAgent bundle")
        for evidence_id in values:
            if not isinstance(evidence_id, str) or not self._EVIDENCE_RE.match(evidence_id):
                errors.append(f"evidence: invalid format {evidence_id!r}")
                continue
            kind, rest = evidence_id.split(":", 1)
            if kind == "order" and not self.repository.order_exists(rest):
                errors.append(f"evidence: unknown order {rest}")
            elif kind == "seller" and not self.repository.seller_exists(rest):
                errors.append(f"evidence: unknown seller {rest}")
            elif kind == "policy" and rest != decision.root_cause:
                errors.append(f"evidence: policy code is not selected root cause {rest}")
            elif kind in {"item", "payment"}:
                parts = rest.split(":")
                exists = len(parts) == 2 and (
                    self.repository.item_exists(parts[0], parts[1])
                    if kind == "item"
                    else self.repository.payment_exists(parts[0], parts[1])
                )
                if not exists:
                    errors.append(f"evidence: unknown {kind} {rest}")
