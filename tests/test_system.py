from __future__ import annotations

import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from agents.delivery_agent import DeliveryAgent
from agents.evidence_agent import EvidenceAgent
from agents.financial_agent import FinancialAgent
from agents.payment_agent import PaymentAgent
from agents.policy_agent import PolicyAgent, PolicyNoMatchError
from agents.verifier_agent import VerifierAgent
from core.models import (
    CaseContext,
    EvidenceBundle,
    ItemFact,
    ItemSellerFacts,
    OrderFacts,
    PaymentFact,
)
from core.trace import TraceWriter


class FakeRepository:
    def __init__(self) -> None:
        self.orders = {"o1"}
        self.items = {("o1", "1"), ("o1", "2")}
        self.payments = {("o1", "1"), ("o1", "2"), ("o1", "3")}
        self.sellers = {"s1", "s2"}

    def order_exists(self, order_id):
        return order_id in self.orders

    def item_exists(self, order_id, item_id):
        return (order_id, item_id) in self.items

    def payment_exists(self, order_id, sequence):
        return (order_id, sequence) in self.payments

    def seller_exists(self, seller_id):
        return seller_id in self.sellers


class SystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = FakeRepository()
        self.payment_agent = PaymentAgent(self.repo)  # reconcile() uses structured rows only
        self.policy = PolicyAgent()
        self.delivery = DeliveryAgent()
        self.financial = FinancialAgent()
        self.evidence = EvidenceAgent()
        self.verifier = VerifierAgent(self.repo)

    def order(self, status="delivered", carrier="2018-01-01 00:00:00",
              delivered="2018-01-05 00:00:00", estimate="2018-01-08 00:00:00"):
        return OrderFacts(True, "o1", "c1", "u1", status,
                          "2017-12-20 00:00:00", "2017-12-21 00:00:00",
                          carrier, delivered, estimate, ())

    def items(self, count=1, shipping_limit="2018-01-02 00:00:00"):
        rows = tuple(
            ItemFact(str(index), f"p{index}", "s1", shipping_limit,
                     Decimal("100.00") if index == 1 else Decimal("20.00"),
                     Decimal("10.00") if index == 1 else Decimal("2.00"))
            for index in range(1, count + 1)
        )
        return ItemSellerFacts(
            "o1", rows, sum((row.price for row in rows), Decimal(0)),
            sum((row.freight_value for row in rows), Decimal(0)), (),
        )

    def payments(self, values=("110.00",), item_total=Decimal("100.00"),
                 freight_total=Decimal("10.00")):
        rows = tuple(
            PaymentFact(str(index), "credit_card", index, Decimal(value))
            for index, value in enumerate(values, 1)
        )
        return self.payment_agent.reconcile(
            "o1", rows, item_total, freight_total
        )

    def scenario(self):
        context = CaseContext("EC_001", "2018-10-18", "vi", "claim", "o1", "EC_POLICY_V1")
        order = self.order()
        items = self.items()
        payments = self.payments()
        delivery = self.delivery.analyze(order, items)
        decision = self.policy.decide(context.case_id, order, payments, delivery)
        evidence = self.evidence.build(order, items, payments, decision)
        financial = self.financial.calculate(items, payments, decision)
        draft = {
            "case_id": "EC_001",
            "assessment": {"primary_issue": decision.primary_issue,
                           "case_status": decision.case_status, "confidence": 0.99},
            "affected_entities": {"order_ids": ["o1"], "item_ids": ["o1:1"],
                                  "seller_ids": ["s1"], "payment_ids": ["o1:1"]},
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": decision.root_cause, "rank": 1}],
                "responsible_parties": [],
            },
            "evidence_ids": list(evidence.evidence_ids),
            "financial_resolution": {"currency": "BRL", "item_total_brl": 100.0,
                                     "freight_total_brl": 10.0,
                                     "payment_total_brl": 110.0,
                                     "recommended_refund_brl": 0.0},
            "resolution_actions": [decision.action],
        }
        return context, order, items, payments, delivery, decision, evidence, financial, draft

    def test_01_canceled_order_paid(self):
        order, items, payments = self.order("canceled", None, None, "2018-01-08"), self.items(), self.payments()
        decision = self.policy.decide("EC_X", order, payments, self.delivery.analyze(order, items))
        self.assertEqual(decision.primary_issue, "canceled_order_paid")

    def test_02_unavailable_order_paid(self):
        order, items, payments = self.order("unavailable", None, None, "2018-01-08"), self.items(), self.payments()
        decision = self.policy.decide("EC_X", order, payments, self.delivery.analyze(order, items))
        self.assertEqual(decision.primary_issue, "unavailable_order_paid")

    def test_03_seller_handoff_late(self):
        order, items = self.order(carrier="2018-01-03", delivered="2018-01-10", estimate="2018-01-08"), self.items()
        items = ItemSellerFacts(items.order_id, items.items, items.item_total,
                                items.freight_total, ("s1",))
        decision = self.policy.decide("EC_X", order, self.payments(), self.delivery.analyze(order, items))
        self.assertEqual(decision.primary_issue, "late_delivery_seller")

    def test_04_logistics_delivery_late(self):
        order, items = self.order(carrier="2018-01-01", delivered="2018-01-10", estimate="2018-01-08"), self.items()
        decision = self.policy.decide("EC_X", order, self.payments(), self.delivery.analyze(order, items))
        self.assertEqual(decision.primary_issue, "late_delivery_logistics")

    def test_05_valid_split_payment(self):
        payments = self.payments(("40.00", "70.00"))
        decision = self.policy.decide("EC_X", self.order(), payments,
                                      self.delivery.analyze(self.order(), self.items()))
        self.assertEqual(decision.primary_issue, "valid_split_payment")

    def test_06_unsupported_late_claim(self):
        decision = self.scenario()[5]
        self.assertEqual(decision.primary_issue, "unsupported_late_claim")

    def test_07_payment_tolerance_exactly_point_10(self):
        self.assertTrue(self.payments(("110.10",)).matches_order_total)

    def test_08_payment_tolerance_exceeded(self):
        self.assertFalse(self.payments(("110.11",)).matches_order_total)

    def test_09_order_without_items(self):
        items = ItemSellerFacts("o1", (), Decimal("0"), Decimal("0"), ())
        payments = self.payments(("25.00",), Decimal("0"), Decimal("0"))
        order = self.order("canceled", None, None, "2018-01-08")
        decision = self.policy.decide("EC_X", order, payments, self.delivery.analyze(order, items))
        result = self.financial.calculate(items, payments, decision)
        self.assertEqual((result.item_total_brl, result.freight_total_brl),
                         (Decimal("0.00"), Decimal("0.00")))

    def test_10_multiple_items(self):
        items = self.items(2)
        payments = self.payments(("132.00",), items.item_total, items.freight_total)
        result = self.financial.calculate(items, payments,
            self.policy.decide("EC_X", self.order(), payments,
                               self.delivery.analyze(self.order(), items)))
        self.assertEqual(result.item_total_brl, Decimal("120.00"))

    def test_11_multiple_payment_rows_not_installment_multiplied(self):
        payments = self.payments(("40.00", "70.00"))
        self.assertEqual(payments.payment_total, Decimal("110.00"))

    def test_12_evidence_invalid_format(self):
        values = list(self.scenario())
        values[6] = EvidenceBundle(("transaction:made-up",))
        values[8]["evidence_ids"] = ["transaction:made-up"]
        result = self.verifier.verify(*values[:8], values[8])
        self.assertTrue(any("invalid format" in error for error in result.errors))

    def test_13_evidence_unknown_reference(self):
        values = list(self.scenario())
        values[6] = EvidenceBundle(("order:missing", "policy:DELIVERY_WITHIN_ESTIMATE"))
        values[8]["evidence_ids"] = list(values[6].evidence_ids)
        result = self.verifier.verify(*values[:8], values[8])
        self.assertTrue(any("unknown order" in error for error in result.errors))

    def test_14_cardinality_limit(self):
        values = list(self.scenario())
        values[8]["affected_entities"]["order_ids"] = [f"o{x}" for x in range(6)]
        result = self.verifier.verify(*values[:8], values[8])
        self.assertTrue(any("cardinality" in error for error in result.errors))

    def test_15_confidence_out_of_range(self):
        values = list(self.scenario())
        values[8]["assessment"]["confidence"] = 1.1
        result = self.verifier.verify(*values[:8], values[8])
        self.assertTrue(any("within [0,1]" in error for error in result.errors))

    def test_16_refund_status_inconsistent(self):
        values = list(self.scenario())
        values[8]["assessment"]["case_status"] = "action_required"
        result = self.verifier.verify(*values[:8], values[8])
        self.assertTrue(any("inconsistent" in error for error in result.errors))

    def test_17_output_missing_field(self):
        values = list(self.scenario())
        del values[8]["financial_resolution"]
        result = self.verifier.verify(*values[:8], values[8])
        self.assertTrue(any("top-level" in error for error in result.errors))

    def test_18_output_invalid_enum(self):
        values = list(self.scenario())
        values[8]["assessment"]["primary_issue"] = "invented_issue"
        result = self.verifier.verify(*values[:8], values[8])
        self.assertTrue(any("enum" in error for error in result.errors))

    def test_19_policy_priority_canceled_before_delivery(self):
        order, items = self.order("canceled", "2018-01-03", "2018-01-10", "2018-01-08"), self.items()
        items = ItemSellerFacts(items.order_id, items.items, items.item_total,
                                items.freight_total, ("s1",))
        decision = self.policy.decide("EC_X", order, self.payments(), self.delivery.analyze(order, items))
        self.assertEqual(decision.primary_issue, "canceled_order_paid")

    def test_20_trace_is_overwritten_not_appended(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            first = TraceWriter(path)
            first.emit("old")
            second = TraceWriter(path)
            second.emit("new")
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["event"], "new")


if __name__ == "__main__":
    unittest.main()
