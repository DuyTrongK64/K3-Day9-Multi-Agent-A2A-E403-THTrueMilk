"""Typed A2A payloads. DataFrames never cross agent boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Optional


@dataclass(frozen=True)
class CaseContext:
    case_id: str
    opened_at: str
    language: str
    message: str
    claimed_order_id: str
    policy_version: str


@dataclass(frozen=True)
class OrderFacts:
    exists: bool
    order_id: str
    customer_id: Optional[str]
    customer_unique_id: Optional[str]
    order_status: Optional[str]
    purchase_timestamp: Optional[str]
    approved_timestamp: Optional[str]
    delivered_carrier_date: Optional[str]
    delivered_customer_date: Optional[str]
    estimated_delivery_date: Optional[str]
    null_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ItemFact:
    order_item_id: str
    product_id: str
    seller_id: str
    shipping_limit_date: Optional[str]
    price: Decimal
    freight_value: Decimal


@dataclass(frozen=True)
class ItemSellerFacts:
    order_id: str
    items: tuple[ItemFact, ...]
    item_total: Decimal
    freight_total: Decimal
    late_handoff_seller_ids: tuple[str, ...]


@dataclass(frozen=True)
class PaymentFact:
    payment_sequential: str
    payment_type: str
    payment_installments: int
    payment_value: Decimal


@dataclass(frozen=True)
class PaymentFacts:
    order_id: str
    payments: tuple[PaymentFact, ...]
    payment_total: Decimal
    item_freight_delta: Decimal
    matches_order_total: bool
    valid_split_payment: bool


@dataclass(frozen=True)
class DeliveryFacts:
    order_id: str
    delivered: bool
    delivered_late: bool
    delivered_on_or_before_estimate: bool
    late_handoff_seller_ids: tuple[str, ...]
    carrier_handoff_not_late: bool


@dataclass(frozen=True)
class ResponsibleParty:
    party_type: str
    party_id: str


@dataclass(frozen=True)
class PolicyDecision:
    primary_issue: str
    case_status: str
    root_cause: str
    responsible_parties: tuple[ResponsibleParty, ...]
    action: str


@dataclass(frozen=True)
class EvidenceBundle:
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class FinancialResolution:
    currency: str
    item_total_brl: Decimal
    freight_total_brl: Decimal
    payment_total_brl: Decimal
    recommended_refund_brl: Decimal


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentMessage:
    message_id: str
    case_id: str
    sender: str
    recipient: str
    task: str
    status: str
    input_refs: tuple[str, ...]
    payload: dict[str, Any]
    errors: tuple[str, ...]
    started_at: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentTraceEvent:
    event: str
    timestamp: str
    case_id: Optional[str] = None
    agent: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinalCaseOutput:
    case_id: str
    assessment: dict[str, Any]
    affected_entities: dict[str, list[str]]
    root_cause_analysis: dict[str, list[dict[str, Any]]]
    evidence_ids: list[str]
    financial_resolution: dict[str, Any]
    resolution_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
