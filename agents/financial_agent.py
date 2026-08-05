from __future__ import annotations

from core.decimal_utils import money, sum_money
from core.models import FinancialResolution, ItemSellerFacts, PaymentFacts, PolicyDecision


class FinancialAgent:
    name = "FinancialAgent"

    def calculate(
        self,
        items: ItemSellerFacts,
        payments: PaymentFacts,
        decision: PolicyDecision,
    ) -> FinancialResolution:
        item_total = sum_money(item.price for item in items.items)
        freight_total = sum_money(item.freight_value for item in items.items)
        payment_total = sum_money(payment.payment_value for payment in payments.payments)
        if decision.primary_issue in {"canceled_order_paid", "unavailable_order_paid"}:
            refund = payment_total
        elif decision.primary_issue in {"late_delivery_seller", "late_delivery_logistics"}:
            refund = freight_total
        else:
            refund = money(0)
        return FinancialResolution(
            currency="BRL",
            item_total_brl=item_total,
            freight_total_brl=freight_total,
            payment_total_brl=payment_total,
            recommended_refund_brl=refund,
        )
