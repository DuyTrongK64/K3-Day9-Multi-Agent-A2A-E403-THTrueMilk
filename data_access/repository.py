"""Load only the four domain tables required by EC_POLICY_V1 plus customers/sellers."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence


class OlistRepository:
    """Immutable, narrow-query access used by agents and the independent verifier."""

    REQUIRED_CSV_HEADERS = {
        "olist_customers_dataset.csv": {"customer_id", "customer_unique_id"},
        "olist_geolocation_dataset.csv": {"geolocation_zip_code_prefix"},
        "olist_order_items_dataset.csv": {
            "order_id", "order_item_id", "product_id", "seller_id",
            "shipping_limit_date", "price", "freight_value",
        },
        "olist_order_payments_dataset.csv": {
            "order_id", "payment_sequential", "payment_type",
            "payment_installments", "payment_value",
        },
        "olist_order_reviews_dataset.csv": {"review_id", "order_id"},
        "olist_orders_dataset.csv": {
            "order_id", "customer_id", "order_status", "order_purchase_timestamp",
            "order_approved_at", "order_delivered_carrier_date",
            "order_delivered_customer_date", "order_estimated_delivery_date",
        },
        "olist_products_dataset.csv": {"product_id"},
        "olist_sellers_dataset.csv": {"seller_id"},
        "product_category_name_translation.csv": {
            "product_category_name", "product_category_name_english"
        },
    }

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._validate_all_nine_csvs()
        self._orders = MappingProxyType(self._index_one("olist_orders_dataset.csv", "order_id"))
        self._customers = MappingProxyType(
            self._index_one("olist_customers_dataset.csv", "customer_id")
        )
        self._items = self._index_many("olist_order_items_dataset.csv", "order_id")
        self._payments = self._index_many("olist_order_payments_dataset.csv", "order_id")
        self._sellers = frozenset(
            row["seller_id"] for row in self._rows("olist_sellers_dataset.csv")
        )

    def _rows(self, filename: str):
        with (self.data_dir / filename).open(encoding="utf-8-sig", newline="") as handle:
            yield from csv.DictReader(handle)

    def _validate_all_nine_csvs(self) -> None:
        actual = {path.name for path in self.data_dir.glob("*.csv")}
        if actual != set(self.REQUIRED_CSV_HEADERS):
            raise ValueError(f"Expected exactly 9 known CSVs, found: {sorted(actual)}")
        for filename, required in self.REQUIRED_CSV_HEADERS.items():
            with (self.data_dir / filename).open(encoding="utf-8-sig", newline="") as handle:
                headers = set(csv.DictReader(handle).fieldnames or [])
            missing = required - headers
            if missing:
                raise ValueError(f"{filename} missing columns: {sorted(missing)}")

    def _index_one(self, filename: str, key: str) -> dict[str, dict[str, str]]:
        return {row[key]: dict(row) for row in self._rows(filename)}

    def _index_many(self, filename: str, key: str) -> Mapping[str, Sequence[dict[str, str]]]:
        result: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self._rows(filename):
            result[row[key]].append(dict(row))
        return MappingProxyType({k: tuple(v) for k, v in result.items()})

    # OrderAgent-only query surface.
    def get_order(self, order_id: str) -> dict[str, str] | None:
        row = self._orders.get(order_id)
        return dict(row) if row else None

    def get_customer(self, customer_id: str) -> dict[str, str] | None:
        row = self._customers.get(customer_id)
        return dict(row) if row else None

    # ItemSellerAgent-only query surface.
    def get_items(self, order_id: str) -> tuple[dict[str, str], ...]:
        return tuple(dict(row) for row in self._items.get(order_id, ()))

    def seller_exists(self, seller_id: str) -> bool:
        return seller_id in self._sellers

    # PaymentAgent-only query surface.
    def get_payments(self, order_id: str) -> tuple[dict[str, str], ...]:
        return tuple(dict(row) for row in self._payments.get(order_id, ()))

    # Verifier referential-integrity queries.
    def order_exists(self, order_id: str) -> bool:
        return order_id in self._orders

    def item_exists(self, order_id: str, item_id: str) -> bool:
        return any(row["order_item_id"] == item_id for row in self._items.get(order_id, ()))

    def payment_exists(self, order_id: str, sequential: str) -> bool:
        return any(
            row["payment_sequential"] == sequential
            for row in self._payments.get(order_id, ())
        )
