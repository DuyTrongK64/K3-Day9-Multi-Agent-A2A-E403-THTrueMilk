from __future__ import annotations

from core.models import EvidenceBundle, ItemSellerFacts, OrderFacts, PaymentFacts, PolicyDecision


class EvidenceAgent:
    name = "EvidenceAgent"

    def build(
        self,
        order: OrderFacts,
        items: ItemSellerFacts,
        payments: PaymentFacts,
        decision: PolicyDecision,
    ) -> EvidenceBundle:
        evidence: list[str] = [f"order:{order.order_id}"]
        if decision.primary_issue not in {"canceled_order_paid", "unavailable_order_paid"}:
            evidence.extend(
                f"item:{order.order_id}:{item.order_item_id}" for item in items.items
            )
        evidence.extend(
            f"payment:{order.order_id}:{payment.payment_sequential}"
            for payment in payments.payments
        )
        if decision.primary_issue.startswith("late_delivery"):
            evidence.extend(
                f"seller:{party.party_id}"
                for party in decision.responsible_parties
                if party.party_type == "seller"
            )
        evidence.append(f"policy:{decision.root_cause}")
        unique = tuple(dict.fromkeys(evidence))
        if len(unique) > 10:
            raise ValueError(f"Evidence cardinality exceeds 10: {len(unique)}")
        return EvidenceBundle(unique)
