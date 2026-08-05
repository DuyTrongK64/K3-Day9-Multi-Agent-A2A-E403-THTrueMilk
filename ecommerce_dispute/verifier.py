from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from .domain import (
    Action,
    CaseStatus,
    PrimaryIssue,
    RootCause,
    money,
)
from .repository import OlistRepository


ORDER_RE = re.compile(r"^order:(?P<order_id>[^:]+)$")
ITEM_RE = re.compile(r"^item:(?P<order_id>[^:]+):(?P<item_id>\d+)$")
PAYMENT_RE = re.compile(r"^payment:(?P<order_id>[^:]+):(?P<payment_id>\d+)$")
SELLER_RE = re.compile(r"^seller:(?P<seller_id>[^:]+)$")
POLICY_RE = re.compile(r"^policy:(?P<cause_code>[A-Z_]+)$")


class VerificationError(ValueError):
    pass


class VerifierAgent:
    def __init__(self, repository: OlistRepository):
        self.repository = repository

    def verify(self, output: dict[str, Any]) -> None:
        errors: list[str] = []
        self._verify_schema(output, errors)
        if errors:
            raise VerificationError("; ".join(errors))

        order_ids = output["affected_entities"]["order_ids"]
        order_id = order_ids[0] if order_ids else None
        self._verify_entities(output, order_id, errors)
        self._verify_evidence(output, order_id, errors)
        self._verify_policy(output, order_id, errors)
        self._verify_financials(output, order_id, errors)
        if errors:
            raise VerificationError("; ".join(errors))

    def _verify_schema(self, output: dict[str, Any], errors: list[str]) -> None:
        required = {
            "case_id",
            "assessment",
            "affected_entities",
            "root_cause_analysis",
            "evidence_ids",
            "financial_resolution",
            "resolution_actions",
        }
        if set(output) != required:
            errors.append("top-level keys mismatch")
            return
        assessment = output["assessment"]
        entities = output["affected_entities"]
        root = output["root_cause_analysis"]
        financial = output["financial_resolution"]
        try:
            PrimaryIssue(assessment["primary_issue"])
            CaseStatus(assessment["case_status"])
            confidence = float(assessment["confidence"])
            if not 0 <= confidence <= 1:
                errors.append("confidence outside [0,1]")
            for key, limit in {
                "order_ids": 5,
                "item_ids": 5,
                "seller_ids": 5,
                "payment_ids": 5,
            }.items():
                if not isinstance(entities[key], list) or len(entities[key]) > limit:
                    errors.append(f"{key} invalid")
            if len(root["ranked_causes"]) > 3 or len(root["responsible_parties"]) > 3:
                errors.append("root cause limits exceeded")
            for row in root["ranked_causes"]:
                RootCause(row["cause_code"])
                if not isinstance(row["rank"], int) or row["rank"] < 1:
                    errors.append("invalid cause rank")
            if not isinstance(output["evidence_ids"], list) or len(output["evidence_ids"]) > 10:
                errors.append("evidence limit exceeded")
            for action in output["resolution_actions"]:
                Action(action)
            if len(output["resolution_actions"]) > 5:
                errors.append("action limit exceeded")
            if financial["currency"] != "BRL":
                errors.append("currency must be BRL")
            for key in ("item_total_brl", "freight_total_brl", "payment_total_brl", "recommended_refund_brl"):
                money(financial[key])
        except (KeyError, TypeError, ValueError):
            errors.append("schema enum/type validation failed")

    def _verify_entities(self, output: dict[str, Any], order_id: str | None, errors: list[str]) -> None:
        if not order_id:
            errors.append("order id missing")
            return
        if order_id not in self.repository.orders_by_id:
            errors.append("order id does not exist")
        valid_items = {f"{item.order_id}:{item.order_item_id}" for item in self.repository.get_items(order_id)}
        valid_sellers = {item.seller_id for item in self.repository.get_items(order_id)}
        valid_payments = {
            f"{payment.order_id}:{payment.payment_sequential}" for payment in self.repository.get_payments(order_id)
        }
        entities = output["affected_entities"]
        if set(entities["item_ids"]) - valid_items:
            errors.append("affected item id does not exist")
        if set(entities["seller_ids"]) - valid_sellers:
            errors.append("affected seller id does not belong to order")
        if set(entities["payment_ids"]) - valid_payments:
            errors.append("affected payment id does not exist")

    def _verify_evidence(self, output: dict[str, Any], order_id: str | None, errors: list[str]) -> None:
        if not order_id:
            return
        valid_items = {item.order_item_id for item in self.repository.get_items(order_id)}
        valid_payments = {payment.payment_sequential for payment in self.repository.get_payments(order_id)}
        valid_sellers = {item.seller_id for item in self.repository.get_items(order_id)}
        valid_causes = {cause.value for cause in RootCause}
        for evidence_id in output["evidence_ids"]:
            if match := ORDER_RE.match(evidence_id):
                if match["order_id"] != order_id:
                    errors.append("evidence order id mismatch")
            elif match := ITEM_RE.match(evidence_id):
                if match["order_id"] != order_id or match["item_id"] not in valid_items:
                    errors.append("evidence item id does not exist")
            elif match := PAYMENT_RE.match(evidence_id):
                if match["order_id"] != order_id or match["payment_id"] not in valid_payments:
                    errors.append("evidence payment id does not exist")
            elif match := SELLER_RE.match(evidence_id):
                if match["seller_id"] not in valid_sellers:
                    errors.append("evidence seller id does not belong to order")
            elif match := POLICY_RE.match(evidence_id):
                if match["cause_code"] not in valid_causes:
                    errors.append("evidence policy id invalid")
            else:
                errors.append(f"invalid evidence id format: {evidence_id}")

    def _verify_policy(self, output: dict[str, Any], order_id: str | None, errors: list[str]) -> None:
        if not order_id:
            return
        primary_issue = output["assessment"]["primary_issue"]
        case_status = output["assessment"]["case_status"]
        actions = output["resolution_actions"]
        causes = [row["cause_code"] for row in output["root_cause_analysis"]["ranked_causes"]]
        parties = output["root_cause_analysis"]["responsible_parties"]
        expected = {
            "canceled_order_paid": ("action_required", ["ORDER_CANCELED_AFTER_PAYMENT"], ["issue_full_refund"]),
            "unavailable_order_paid": ("action_required", ["ORDER_UNAVAILABLE_AFTER_PAYMENT"], ["issue_full_refund"]),
            "late_delivery_seller": ("action_required", ["SELLER_HANDOFF_AFTER_LIMIT"], ["refund_freight"]),
            "late_delivery_logistics": ("action_required", ["CARRIER_DELIVERED_AFTER_ESTIMATE"], ["refund_freight"]),
            "valid_split_payment": ("no_action", ["MULTIPLE_PAYMENTS_RECONCILED"], ["explain_valid_split_payment"]),
            "unsupported_late_claim": ("no_action", ["DELIVERY_WITHIN_ESTIMATE"], ["reject_late_refund"]),
        }[primary_issue]
        if case_status != expected[0]:
            errors.append("case_status does not match issue")
        if causes[: len(expected[1])] != expected[1]:
            errors.append("root cause does not match issue")
        if actions != expected[2]:
            errors.append("action does not match issue")
        if primary_issue == "late_delivery_seller":
            if not parties or any(party["party_type"] != "seller" for party in parties):
                errors.append("seller late requires seller responsible party")
        elif primary_issue == "late_delivery_logistics":
            if parties != [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}]:
                errors.append("logistics late requires logistics provider")
        elif primary_issue in {"canceled_order_paid", "unavailable_order_paid"}:
            if parties != [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]:
                errors.append("paid canceled/unavailable requires platform")
        elif parties:
            errors.append("no-action issue should not have responsible parties")

    def _verify_financials(self, output: dict[str, Any], order_id: str | None, errors: list[str]) -> None:
        if not order_id:
            return
        item_total = money(sum((item.price for item in self.repository.get_items(order_id)), Decimal("0.00")))
        freight_total = money(sum((item.freight_value for item in self.repository.get_items(order_id)), Decimal("0.00")))
        payment_total = money(
            sum((payment.payment_value for payment in self.repository.get_payments(order_id)), Decimal("0.00"))
        )
        financial = output["financial_resolution"]
        if money(financial["item_total_brl"]) != item_total:
            errors.append("item total mismatch")
        if money(financial["freight_total_brl"]) != freight_total:
            errors.append("freight total mismatch")
        if money(financial["payment_total_brl"]) != payment_total:
            errors.append("payment total mismatch")
        issue = output["assessment"]["primary_issue"]
        expected_refund = Decimal("0.00")
        if issue in {"canceled_order_paid", "unavailable_order_paid"}:
            expected_refund = payment_total
        elif issue in {"late_delivery_seller", "late_delivery_logistics"}:
            expected_refund = freight_total
        if money(financial["recommended_refund_brl"]) != money(expected_refund):
            errors.append("refund amount mismatch")

