from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ecommerce_dispute.coordinator import CoordinatorAgent
from ecommerce_dispute.domain import CustomerCase
from ecommerce_dispute.repository import OlistRepository
from ecommerce_dispute.runner import run
from ecommerce_dispute.verifier import VerificationError, VerifierAgent


DATA_DIR = Path("data")


def make_case(case_id: str, order_id: str) -> CustomerCase:
    return CustomerCase(
        case_id=case_id,
        opened_at="2018-10-18T00:00:00-03:00",
        language="vi",
        message="Kiem tra khieu nai don hang.",
        claimed_order_id=order_id,
        policy_version="EC_POLICY_V1",
    )


class PolicyPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = OlistRepository(DATA_DIR)
        cls.coordinator = CoordinatorAgent(cls.repository)

    def resolve(self, order_id: str) -> dict:
        output, _trace = self.coordinator.run_case(make_case("EC_TEST", order_id))
        return output

    def test_canceled_order_paid_gets_full_refund(self) -> None:
        output = self.resolve("1b9ecfe83cdc259250e1a8aca174f0ad")
        self.assertEqual(output["assessment"]["primary_issue"], "canceled_order_paid")
        self.assertEqual(output["resolution_actions"], ["issue_full_refund"])
        self.assertEqual(
            output["financial_resolution"]["recommended_refund_brl"],
            output["financial_resolution"]["payment_total_brl"],
        )

    def test_unavailable_order_paid_gets_full_refund(self) -> None:
        output = self.resolve("8e24261a7e58791d10cb1bf9da94df5c")
        self.assertEqual(output["assessment"]["primary_issue"], "unavailable_order_paid")
        self.assertEqual(output["root_cause_analysis"]["ranked_causes"][0]["cause_code"], "ORDER_UNAVAILABLE_AFTER_PAYMENT")

    def test_seller_late_gets_freight_refund_and_seller_party(self) -> None:
        output = self.resolve("203096f03d82e0dffbc41ebc2e2bcfb7")
        self.assertEqual(output["assessment"]["primary_issue"], "late_delivery_seller")
        self.assertEqual(output["resolution_actions"], ["refund_freight"])
        self.assertEqual(
            output["financial_resolution"]["recommended_refund_brl"],
            output["financial_resolution"]["freight_total_brl"],
        )
        self.assertEqual(output["root_cause_analysis"]["responsible_parties"][0]["party_type"], "seller")

    def test_logistics_late_gets_logistics_party(self) -> None:
        output = self.resolve("fbf9ac61453ac646ce8ad9783d7d0af6")
        self.assertEqual(output["assessment"]["primary_issue"], "late_delivery_logistics")
        self.assertEqual(
            output["root_cause_analysis"]["responsible_parties"],
            [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}],
        )

    def test_valid_split_payment_has_no_refund(self) -> None:
        output = self.resolve("e481f51cbdc54678b7cc49136f2d6af7")
        self.assertEqual(output["assessment"]["primary_issue"], "valid_split_payment")
        self.assertEqual(output["assessment"]["case_status"], "no_action")
        self.assertEqual(output["financial_resolution"]["recommended_refund_brl"], 0.0)

    def test_unsupported_late_claim_has_no_refund(self) -> None:
        output = self.resolve("53cdb2fc8bc7dce0b6741e2150273451")
        self.assertEqual(output["assessment"]["primary_issue"], "unsupported_late_claim")
        self.assertEqual(output["resolution_actions"], ["reject_late_refund"])


class VerificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = OlistRepository(DATA_DIR)
        cls.coordinator = CoordinatorAgent(cls.repository)
        cls.verifier = VerifierAgent(cls.repository)

    def test_verifier_rejects_false_positive_evidence(self) -> None:
        output, _trace = self.coordinator.run_case(make_case("EC_TEST", "53cdb2fc8bc7dce0b6741e2150273451"))
        output["evidence_ids"].append("payment:53cdb2fc8bc7dce0b6741e2150273451:999")
        with self.assertRaises(VerificationError):
            self.verifier.verify(output)

    def test_output_schema_limits(self) -> None:
        output, _trace = self.coordinator.run_case(make_case("EC_TEST", "203096f03d82e0dffbc41ebc2e2bcfb7"))
        self.assertLessEqual(len(output["evidence_ids"]), 10)
        self.assertLessEqual(len(output["affected_entities"]["item_ids"]), 5)
        self.assertLessEqual(len(output["root_cause_analysis"]["ranked_causes"]), 3)


class RunnerIntegrationTest(unittest.TestCase):
    def test_runner_writes_output_trace_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            case_payload = {
                "case_id": "EC_001",
                "opened_at": "2018-10-18T00:00:00-03:00",
                "customer_request": {
                    "language": "vi",
                    "message": "Don hang giao tre.",
                    "claimed_order_id": "fbf9ac61453ac646ce8ad9783d7d0af6",
                },
                "policy_version": "EC_POLICY_V1",
            }
            (input_dir / "EC_001.json").write_text(json.dumps(case_payload), encoding="utf-8")
            count = run(
                input_dir=input_dir,
                output_dir=output_dir,
                data_dir=DATA_DIR,
                trace_path=root / "trace.jsonl",
                metadata_path=root / "metadata.json",
            )
            self.assertEqual(count, 1)
            output = json.loads((output_dir / "EC_001.json").read_text(encoding="utf-8"))
            self.assertEqual(output["assessment"]["primary_issue"], "late_delivery_logistics")
            self.assertIn("VerifierAgent", (root / "trace.jsonl").read_text(encoding="utf-8"))
            metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["parameter_size"], "0B")


if __name__ == "__main__":
    unittest.main()

