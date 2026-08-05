from __future__ import annotations

from dataclasses import replace

from .agents import (
    DeliveryAgent,
    EvidenceAgent,
    FinancialAgent,
    OrderSellerAgent,
    PaymentAgent,
    PolicyAgent,
    RetrieverAgent,
)
from .domain import AgentState, CaseBundle, CustomerCase
from .output import build_output
from .repository import OlistRepository
from .verifier import VerifierAgent


class CoordinatorAgent:
    def __init__(self, repository: OlistRepository):
        self.repository = repository
        self.retriever = RetrieverAgent(repository)
        self.order_seller = OrderSellerAgent()
        self.payment = PaymentAgent()
        self.delivery = DeliveryAgent()
        self.policy = PolicyAgent()
        self.evidence = EvidenceAgent()
        self.financial = FinancialAgent()
        self.verifier = VerifierAgent(repository)

    def run_case(self, case: CustomerCase) -> tuple[dict, list[dict]]:
        state = AgentState(bundle=CaseBundle(case=case, order=None, items=(), payments=()))
        trace: list[dict] = []
        for name, agent in (
            ("RetrieverAgent", self.retriever),
            ("OrderSellerAgent", self.order_seller),
            ("PaymentAgent", self.payment),
            ("DeliveryAgent", self.delivery),
            ("PolicyAgent", self.policy),
            ("EvidenceAgent", self.evidence),
            ("FinancialAgent", self.financial),
        ):
            state = agent.run(state)
            trace.append(self._trace_event(name, state))
        output = build_output(state)
        self.verifier.verify(output)
        trace.append({"agent": "VerifierAgent", "case_id": case.case_id, "status": "passed"})
        return output, trace

    def _trace_event(self, agent_name: str, state: AgentState) -> dict:
        event = {
            "agent": agent_name,
            "case_id": state.bundle.case.case_id,
            "order_id": state.bundle.case.claimed_order_id,
            "status": "completed",
        }
        if state.policy_decision:
            event["primary_issue"] = state.policy_decision.primary_issue.value
            event["actions"] = [action.value for action in state.policy_decision.actions]
        if state.financial_facts:
            event["recommended_refund_brl"] = str(state.financial_facts.recommended_refund)
        return event

