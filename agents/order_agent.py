from __future__ import annotations

from core.models import OrderFacts
from data_access.repository import OlistRepository


class OrderAgent:
    name = "OrderAgent"

    def __init__(self, repository: OlistRepository) -> None:
        self.repository = repository

    def inspect(self, order_id: str) -> OrderFacts:
        row = self.repository.get_order(order_id)
        if row is None:
            return OrderFacts(
                exists=False,
                order_id=order_id,
                customer_id=None,
                customer_unique_id=None,
                order_status=None,
                purchase_timestamp=None,
                approved_timestamp=None,
                delivered_carrier_date=None,
                delivered_customer_date=None,
                estimated_delivery_date=None,
                null_fields=("order",),
            )
        customer = self.repository.get_customer(row["customer_id"])
        values = {
            "customer_id": row.get("customer_id") or None,
            "customer_unique_id": customer.get("customer_unique_id") if customer else None,
            "order_status": row.get("order_status") or None,
            "purchase_timestamp": row.get("order_purchase_timestamp") or None,
            "approved_timestamp": row.get("order_approved_at") or None,
            "delivered_carrier_date": row.get("order_delivered_carrier_date") or None,
            "delivered_customer_date": row.get("order_delivered_customer_date") or None,
            "estimated_delivery_date": row.get("order_estimated_delivery_date") or None,
        }
        return OrderFacts(
            exists=True,
            order_id=order_id,
            null_fields=tuple(key for key, value in values.items() if value is None),
            **values,
        )
