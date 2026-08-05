from __future__ import annotations

from core.models import DeliveryFacts, ItemSellerFacts, OrderFacts


class DeliveryAgent:
    name = "DeliveryAgent"

    def analyze(self, order: OrderFacts, item_seller: ItemSellerFacts) -> DeliveryFacts:
        delivered = bool(order.delivered_customer_date)
        has_estimate = bool(order.estimated_delivery_date)
        delivered_late = bool(
            delivered
            and has_estimate
            and order.delivered_customer_date > order.estimated_delivery_date
        )
        on_or_before = bool(
            delivered
            and has_estimate
            and order.delivered_customer_date <= order.estimated_delivery_date
        )
        has_late_handoff = bool(item_seller.late_handoff_seller_ids)
        carrier_not_late = bool(
            order.delivered_carrier_date
            and item_seller.items
            and all(
                item.shipping_limit_date
                and order.delivered_carrier_date <= item.shipping_limit_date
                for item in item_seller.items
            )
        )
        return DeliveryFacts(
            order_id=order.order_id,
            delivered=delivered,
            delivered_late=delivered_late,
            delivered_on_or_before_estimate=on_or_before,
            late_handoff_seller_ids=item_seller.late_handoff_seller_ids,
            carrier_handoff_not_late=carrier_not_late and not has_late_handoff,
        )
