from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any


MONEY = Decimal("0.01")
PAYMENT_TOLERANCE = Decimal("0.10")
POLICY_VERSION = "EC_POLICY_V1"
MODEL_NAME = "rule-engine-no-llm"
MODEL_PARAMETER_SIZE = "0B"


class PrimaryIssue(str, Enum):
    CANCELED_ORDER_PAID = "canceled_order_paid"
    UNAVAILABLE_ORDER_PAID = "unavailable_order_paid"
    LATE_DELIVERY_SELLER = "late_delivery_seller"
    LATE_DELIVERY_LOGISTICS = "late_delivery_logistics"
    VALID_SPLIT_PAYMENT = "valid_split_payment"
    UNSUPPORTED_LATE_CLAIM = "unsupported_late_claim"


class CaseStatus(str, Enum):
    ACTION_REQUIRED = "action_required"
    NO_ACTION = "no_action"


class RootCause(str, Enum):
    SELLER_HANDOFF_AFTER_LIMIT = "SELLER_HANDOFF_AFTER_LIMIT"
    CARRIER_DELIVERED_AFTER_ESTIMATE = "CARRIER_DELIVERED_AFTER_ESTIMATE"
    ORDER_CANCELED_AFTER_PAYMENT = "ORDER_CANCELED_AFTER_PAYMENT"
    ORDER_UNAVAILABLE_AFTER_PAYMENT = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
    MULTIPLE_PAYMENTS_RECONCILED = "MULTIPLE_PAYMENTS_RECONCILED"
    DELIVERY_WITHIN_ESTIMATE = "DELIVERY_WITHIN_ESTIMATE"


class Action(str, Enum):
    ISSUE_FULL_REFUND = "issue_full_refund"
    REFUND_FREIGHT = "refund_freight"
    EXPLAIN_VALID_SPLIT_PAYMENT = "explain_valid_split_payment"
    REJECT_LATE_REFUND = "reject_late_refund"


@dataclass(frozen=True)
class CustomerCase:
    case_id: str
    opened_at: str
    language: str
    message: str
    claimed_order_id: str
    policy_version: str


@dataclass(frozen=True)
class OrderRecord:
    order_id: str
    customer_id: str
    order_status: str
    order_purchase_timestamp: str
    order_approved_at: str
    order_delivered_carrier_date: str
    order_delivered_customer_date: str
    order_estimated_delivery_date: str


@dataclass(frozen=True)
class ItemRecord:
    order_id: str
    order_item_id: str
    product_id: str
    seller_id: str
    shipping_limit_date: str
    price: Decimal
    freight_value: Decimal


@dataclass(frozen=True)
class PaymentRecord:
    order_id: str
    payment_sequential: str
    payment_type: str
    payment_installments: str
    payment_value: Decimal


@dataclass(frozen=True)
class CaseBundle:
    case: CustomerCase
    order: OrderRecord | None
    items: tuple[ItemRecord, ...]
    payments: tuple[PaymentRecord, ...]


@dataclass(frozen=True)
class OrderFacts:
    order_id: str
    exists: bool
    status: str | None
    item_ids: tuple[str, ...]
    seller_ids: tuple[str, ...]
    late_seller_item_ids: tuple[str, ...]
    late_seller_ids: tuple[str, ...]


@dataclass(frozen=True)
class PaymentFacts:
    payment_ids: tuple[str, ...]
    payment_total: Decimal
    has_multiple_payments: bool
    payment_matches_charge: bool


@dataclass(frozen=True)
class DeliveryFacts:
    delivered_after_estimate: bool
    delivered_within_estimate: bool
    has_delivery_dates: bool


@dataclass(frozen=True)
class FinancialFacts:
    item_total: Decimal
    freight_total: Decimal
    payment_total: Decimal
    recommended_refund: Decimal


@dataclass(frozen=True)
class PolicyDecision:
    primary_issue: PrimaryIssue
    case_status: CaseStatus
    confidence: float
    root_causes: tuple[RootCause, ...]
    responsible_parties: tuple[tuple[str, str], ...]
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class AgentState:
    bundle: CaseBundle
    order_facts: OrderFacts | None = None
    payment_facts: PaymentFacts | None = None
    delivery_facts: DeliveryFacts | None = None
    financial_facts: FinancialFacts | None = None
    policy_decision: PolicyDecision | None = None
    evidence_ids: tuple[str, ...] = ()


def money(value: str | int | float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        raw = value
    else:
        raw = Decimal(str(value or "0"))
    return raw.quantize(MONEY, rounding=ROUND_HALF_UP)


def money_float(value: Decimal) -> float:
    return float(money(value))


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def case_from_json(payload: dict[str, Any]) -> CustomerCase:
    request = payload.get("customer_request") or {}
    return CustomerCase(
        case_id=str(payload.get("case_id", "")),
        opened_at=str(payload.get("opened_at", "")),
        language=str(request.get("language", "")),
        message=str(request.get("message", "")),
        claimed_order_id=str(request.get("claimed_order_id", "")),
        policy_version=str(payload.get("policy_version", "")),
    )

