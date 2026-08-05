from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .domain import ItemRecord, OrderRecord, PaymentRecord, money


class OlistRepository:
    """Load CSVs once and expose indexed lookups for agents."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.orders_by_id: dict[str, OrderRecord] = {}
        self.items_by_order_id: dict[str, list[ItemRecord]] = defaultdict(list)
        self.payments_by_order_id: dict[str, list[PaymentRecord]] = defaultdict(list)
        self.seller_ids: set[str] = set()
        self._load_all()

    def _load_all(self) -> None:
        self._load_orders()
        self._load_items()
        self._load_payments()
        self._load_sellers()

    def _load_orders(self) -> None:
        with (self.data_dir / "olist_orders_dataset.csv").open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                order = OrderRecord(
                    order_id=row["order_id"],
                    customer_id=row["customer_id"],
                    order_status=row["order_status"],
                    order_purchase_timestamp=row["order_purchase_timestamp"],
                    order_approved_at=row["order_approved_at"],
                    order_delivered_carrier_date=row["order_delivered_carrier_date"],
                    order_delivered_customer_date=row["order_delivered_customer_date"],
                    order_estimated_delivery_date=row["order_estimated_delivery_date"],
                )
                self.orders_by_id[order.order_id] = order

    def _load_items(self) -> None:
        with (self.data_dir / "olist_order_items_dataset.csv").open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                item = ItemRecord(
                    order_id=row["order_id"],
                    order_item_id=row["order_item_id"],
                    product_id=row["product_id"],
                    seller_id=row["seller_id"],
                    shipping_limit_date=row["shipping_limit_date"],
                    price=money(row["price"]),
                    freight_value=money(row["freight_value"]),
                )
                self.items_by_order_id[item.order_id].append(item)

    def _load_payments(self) -> None:
        with (self.data_dir / "olist_order_payments_dataset.csv").open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                payment = PaymentRecord(
                    order_id=row["order_id"],
                    payment_sequential=row["payment_sequential"],
                    payment_type=row["payment_type"],
                    payment_installments=row["payment_installments"],
                    payment_value=money(row["payment_value"]),
                )
                self.payments_by_order_id[payment.order_id].append(payment)

    def _load_sellers(self) -> None:
        with (self.data_dir / "olist_sellers_dataset.csv").open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                self.seller_ids.add(row["seller_id"])

    def get_order(self, order_id: str) -> OrderRecord | None:
        return self.orders_by_id.get(order_id)

    def get_items(self, order_id: str) -> tuple[ItemRecord, ...]:
        return tuple(sorted(self.items_by_order_id.get(order_id, ()), key=lambda item: int(item.order_item_id)))

    def get_payments(self, order_id: str) -> tuple[PaymentRecord, ...]:
        return tuple(
            sorted(self.payments_by_order_id.get(order_id, ()), key=lambda payment: int(payment.payment_sequential))
        )

