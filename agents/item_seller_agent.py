from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from core.decimal_utils import sum_money
from core.models import ItemFact, ItemSellerFacts
from data_access.repository import OlistRepository


class ItemSellerAgent:
    name = "ItemSellerAgent"

    def __init__(self, repository: OlistRepository) -> None:
        self.repository = repository

    def inspect(self, order_id: str) -> ItemSellerFacts:
        items = tuple(
            ItemFact(
                order_item_id=row["order_item_id"],
                product_id=row["product_id"],
                seller_id=row["seller_id"],
                shipping_limit_date=row.get("shipping_limit_date") or None,
                price=Decimal(row["price"]),
                freight_value=Decimal(row["freight_value"]),
            )
            for row in sorted(
                self.repository.get_items(order_id),
                key=lambda value: int(value["order_item_id"]),
            )
        )
        return ItemSellerFacts(
            order_id=order_id,
            items=items,
            item_total=sum_money(item.price for item in items),
            freight_total=sum_money(item.freight_value for item in items),
            late_handoff_seller_ids=(),
        )

    def identify_late_handoffs(
        self,
        facts: ItemSellerFacts,
        carrier_date: str | None,
    ) -> ItemSellerFacts:
        if not carrier_date:
            return facts
        late = sorted(
            {
                item.seller_id
                for item in facts.items
                if item.shipping_limit_date and carrier_date > item.shipping_limit_date
            }
        )
        return replace(facts, late_handoff_seller_ids=tuple(late))
