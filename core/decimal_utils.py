"""Decimal-safe monetary helpers."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

CENT = Decimal("0.01")
PAYMENT_TOLERANCE = Decimal("0.10")


def money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def sum_money(values: Iterable[Decimal | str | int | float]) -> Decimal:
    return money(sum((Decimal(str(value)) for value in values), Decimal("0")))


def json_money(value: Decimal) -> float:
    return float(money(value))
