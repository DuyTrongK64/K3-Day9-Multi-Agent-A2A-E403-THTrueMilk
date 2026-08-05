from __future__ import annotations

from decimal import Decimal

from core.decimal_utils import PAYMENT_TOLERANCE, money, sum_money
from core.models import PaymentFact, PaymentFacts
from data_access.repository import OlistRepository


class PaymentAgent:
    name = "PaymentAgent"

    def __init__(self, repository: OlistRepository) -> None:
        self.repository = repository

    def load_payments(self, order_id: str) -> tuple[PaymentFact, ...]:
        return tuple(
            PaymentFact(
                payment_sequential=row["payment_sequential"],
                payment_type=row["payment_type"],
                payment_installments=int(row["payment_installments"]),
                payment_value=Decimal(row["payment_value"]),
            )
            for row in sorted(
                self.repository.get_payments(order_id),
                key=lambda value: int(value["payment_sequential"]),
            )
        )

    def reconcile(
        self,
        order_id: str,
        payments: tuple[PaymentFact, ...],
        item_total: Decimal,
        freight_total: Decimal,
    ) -> PaymentFacts:
        payment_total = sum_money(payment.payment_value for payment in payments)
        delta = money(payment_total - money(item_total + freight_total))
        matches = abs(delta) <= PAYMENT_TOLERANCE
        return PaymentFacts(
            order_id=order_id,
            payments=payments,
            payment_total=payment_total,
            item_freight_delta=delta,
            matches_order_total=matches,
            valid_split_payment=len(payments) >= 2 and matches,
        )
