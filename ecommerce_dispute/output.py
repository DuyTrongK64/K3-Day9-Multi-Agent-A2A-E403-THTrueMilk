from __future__ import annotations

from typing import Any

from .domain import AgentState, money_float


def build_output(state: AgentState) -> dict[str, Any]:
    if not state.order_facts or not state.payment_facts or not state.financial_facts or not state.policy_decision:
        raise ValueError("Cannot build output from incomplete agent state")
    decision = state.policy_decision
    financial = state.financial_facts
    order_facts = state.order_facts
    payment_facts = state.payment_facts
    return {
        "case_id": state.bundle.case.case_id,
        "assessment": {
            "primary_issue": decision.primary_issue.value,
            "case_status": decision.case_status.value,
            "confidence": decision.confidence,
        },
        "affected_entities": {
            "order_ids": [order_facts.order_id] if order_facts.exists else [],
            "item_ids": list(order_facts.item_ids[:5]),
            "seller_ids": list(order_facts.seller_ids[:5]),
            "payment_ids": list(payment_facts.payment_ids[:5]),
        },
        "root_cause_analysis": {
            "ranked_causes": [
                {"cause_code": cause.value, "rank": index + 1}
                for index, cause in enumerate(decision.root_causes[:3])
            ],
            "responsible_parties": [
                {"party_type": party_type, "party_id": party_id}
                for party_type, party_id in decision.responsible_parties[:3]
            ],
        },
        "evidence_ids": list(state.evidence_ids[:10]),
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": money_float(financial.item_total),
            "freight_total_brl": money_float(financial.freight_total),
            "payment_total_brl": money_float(financial.payment_total),
            "recommended_refund_brl": money_float(financial.recommended_refund),
        },
        "resolution_actions": [action.value for action in decision.actions[:5]],
    }

