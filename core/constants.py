"""Auditable constants; deterministic Python is the declared reasoning runtime."""

from __future__ import annotations

POLICY_VERSION = "EC_POLICY_V1"
SYSTEM_NAME = "Olist Multi-Agent Dispute Resolution"

# No LLM is invoked for case classification. The explicit model identifier is kept
# in source so metadata is truthful and machine-checkable.
MODEL_NAME = "deterministic-python-rules-v1"
MODEL_PARAMETER_SIZE = "0B (no LLM)"
MODEL_PROVIDER = "local"
FRAMEWORK = "custom-python-dataclass-agents"

PRIMARY_ISSUES = {
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
}
CASE_STATUSES = {"action_required", "no_action"}
ACTIONS = {
    "issue_full_refund",
    "refund_freight",
    "explain_valid_split_payment",
    "reject_late_refund",
}
ROOT_CAUSES = {
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
}

AGENT_ROLES = [
    ("SupervisorAgent", "coordination"),
    ("CaseLoaderAgent", "input validation"),
    ("OrderAgent", "order and customer facts"),
    ("ItemSellerAgent", "item and seller facts"),
    ("PaymentAgent", "payment reconciliation"),
    ("DeliveryAgent", "delivery timeline analysis"),
    ("PolicyAgent", "ordered policy evaluation"),
    ("EvidenceAgent", "evidence selection"),
    ("FinancialAgent", "decimal-safe financial calculation"),
    ("VerifierAgent", "independent hard-gate verification"),
    ("ArtifactAgent", "run artifacts and packaging support"),
]
