from __future__ import annotations

from core.models import (
    DeliveryFacts,
    OrderFacts,
    PaymentFacts,
    PolicyDecision,
    ResponsibleParty,
)


class PolicyNoMatchError(RuntimeError):
    def __init__(self, case_id: str, reason: str) -> None:
        self.code = "NO_POLICY_RULE_MATCHED"
        self.case_id = case_id
        super().__init__(f"{self.code}: {case_id}: {reason}")


class PolicyAgent:
    name = "PolicyAgent"

    def decide(
        self,
        case_id: str,
        order: OrderFacts,
        payments: PaymentFacts,
        delivery: DeliveryFacts,
    ) -> PolicyDecision:
        # The sequence below is deliberately explicit: first match wins.
        if order.order_status == "canceled" and payments.payment_total > 0:
            return PolicyDecision(
                "canceled_order_paid", "action_required", "ORDER_CANCELED_AFTER_PAYMENT",
                (ResponsibleParty("platform", "OLIST_PLATFORM"),), "issue_full_refund",
            )
        if order.order_status == "unavailable" and payments.payment_total > 0:
            return PolicyDecision(
                "unavailable_order_paid", "action_required",
                "ORDER_UNAVAILABLE_AFTER_PAYMENT",
                (ResponsibleParty("platform", "OLIST_PLATFORM"),), "issue_full_refund",
            )
        if delivery.delivered_late and delivery.late_handoff_seller_ids:
            parties = tuple(
                ResponsibleParty("seller", seller_id)
                for seller_id in delivery.late_handoff_seller_ids[:3]
            )
            return PolicyDecision(
                "late_delivery_seller", "action_required", "SELLER_HANDOFF_AFTER_LIMIT",
                parties, "refund_freight",
            )
        if delivery.delivered_late and delivery.carrier_handoff_not_late:
            return PolicyDecision(
                "late_delivery_logistics", "action_required",
                "CARRIER_DELIVERED_AFTER_ESTIMATE",
                (ResponsibleParty("logistics_provider", "LOGISTICS_PROVIDER"),),
                "refund_freight",
            )
        if payments.valid_split_payment:
            return PolicyDecision(
                "valid_split_payment", "no_action", "MULTIPLE_PAYMENTS_RECONCILED",
                (), "explain_valid_split_payment",
            )
        if delivery.delivered_on_or_before_estimate and payments.matches_order_total:
            return PolicyDecision(
                "unsupported_late_claim", "no_action", "DELIVERY_WITHIN_ESTIMATE",
                (), "reject_late_refund",
            )
        raise PolicyNoMatchError(case_id, "facts do not satisfy EC_POLICY_V1")
