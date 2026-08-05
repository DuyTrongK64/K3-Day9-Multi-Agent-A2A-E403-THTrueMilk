from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .domain import (
    PAYMENT_TOLERANCE,
    Action,
    AgentState,
    CaseBundle,
    CaseStatus,
    DeliveryFacts,
    FinancialFacts,
    OrderFacts,
    PaymentFacts,
    PolicyDecision,
    PrimaryIssue,
    RootCause,
    money,
    parse_timestamp,
)
from .repository import OlistRepository


class RetrieverAgent:
    def __init__(self, repository: OlistRepository):
        self.repository = repository

    def run(self, state: AgentState) -> AgentState:
        case = state.bundle.case
        order = self.repository.get_order(case.claimed_order_id)
        bundle = CaseBundle(
            case=case,
            order=order,
            items=self.repository.get_items(case.claimed_order_id),
            payments=self.repository.get_payments(case.claimed_order_id),
        )
        return replace(state, bundle=bundle)


class OrderSellerAgent:
    def run(self, state: AgentState) -> AgentState:
        bundle = state.bundle
        order_id = bundle.case.claimed_order_id
        carrier_dt = parse_timestamp(bundle.order.order_delivered_carrier_date) if bundle.order else None
        late_items = []
        late_sellers = []
        for item in bundle.items:
            limit_dt = parse_timestamp(item.shipping_limit_date)
            if carrier_dt and limit_dt and carrier_dt > limit_dt:
                late_items.append(f"{item.order_id}:{item.order_item_id}")
                late_sellers.append(item.seller_id)
        facts = OrderFacts(
            order_id=order_id,
            exists=bundle.order is not None,
            status=bundle.order.order_status if bundle.order else None,
            item_ids=tuple(f"{item.order_id}:{item.order_item_id}" for item in bundle.items)[:5],
            seller_ids=tuple(dict.fromkeys(item.seller_id for item in bundle.items))[:5],
            late_seller_item_ids=tuple(dict.fromkeys(late_items))[:5],
            late_seller_ids=tuple(dict.fromkeys(late_sellers))[:5],
        )
        return replace(state, order_facts=facts)


class PaymentAgent:
    def run(self, state: AgentState) -> AgentState:
        item_total = sum((item.price for item in state.bundle.items), Decimal("0.00"))
        freight_total = sum((item.freight_value for item in state.bundle.items), Decimal("0.00"))
        payment_total = sum((payment.payment_value for payment in state.bundle.payments), Decimal("0.00"))
        expected_charge = money(item_total + freight_total)
        facts = PaymentFacts(
            payment_ids=tuple(f"{payment.order_id}:{payment.payment_sequential}" for payment in state.bundle.payments)[:5],
            payment_total=money(payment_total),
            has_multiple_payments=len(state.bundle.payments) >= 2,
            payment_matches_charge=abs(money(payment_total) - expected_charge) <= PAYMENT_TOLERANCE,
        )
        return replace(state, payment_facts=facts)


class DeliveryAgent:
    def run(self, state: AgentState) -> AgentState:
        order = state.bundle.order
        delivered = parse_timestamp(order.order_delivered_customer_date) if order else None
        estimated = parse_timestamp(order.order_estimated_delivery_date) if order else None
        has_dates = delivered is not None and estimated is not None
        facts = DeliveryFacts(
            delivered_after_estimate=bool(has_dates and delivered > estimated),
            delivered_within_estimate=bool(has_dates and delivered <= estimated),
            has_delivery_dates=has_dates,
        )
        return replace(state, delivery_facts=facts)


class FinancialAgent:
    def run(self, state: AgentState) -> AgentState:
        item_total = money(sum((item.price for item in state.bundle.items), Decimal("0.00")))
        freight_total = money(sum((item.freight_value for item in state.bundle.items), Decimal("0.00")))
        payment_total = money(sum((payment.payment_value for payment in state.bundle.payments), Decimal("0.00")))
        decision = state.policy_decision
        refund = Decimal("0.00")
        if decision:
            if Action.ISSUE_FULL_REFUND in decision.actions:
                refund = payment_total
            elif Action.REFUND_FREIGHT in decision.actions:
                refund = freight_total
        facts = FinancialFacts(
            item_total=item_total,
            freight_total=freight_total,
            payment_total=payment_total,
            recommended_refund=money(refund),
        )
        return replace(state, financial_facts=facts)


class PolicyAgent:
    def run(self, state: AgentState) -> AgentState:
        order = state.order_facts
        payment = state.payment_facts
        delivery = state.delivery_facts
        if order is None or payment is None or delivery is None:
            raise ValueError("PolicyAgent requires order, payment and delivery facts")

        if order.status == "canceled" and payment.payment_total > 0:
            decision = PolicyDecision(
                primary_issue=PrimaryIssue.CANCELED_ORDER_PAID,
                case_status=CaseStatus.ACTION_REQUIRED,
                confidence=1.0,
                root_causes=(RootCause.ORDER_CANCELED_AFTER_PAYMENT,),
                responsible_parties=(("platform", "OLIST_PLATFORM"),),
                actions=(Action.ISSUE_FULL_REFUND,),
            )
        elif order.status == "unavailable" and payment.payment_total > 0:
            decision = PolicyDecision(
                primary_issue=PrimaryIssue.UNAVAILABLE_ORDER_PAID,
                case_status=CaseStatus.ACTION_REQUIRED,
                confidence=1.0,
                root_causes=(RootCause.ORDER_UNAVAILABLE_AFTER_PAYMENT,),
                responsible_parties=(("platform", "OLIST_PLATFORM"),),
                actions=(Action.ISSUE_FULL_REFUND,),
            )
        elif delivery.delivered_after_estimate and order.late_seller_ids:
            decision = PolicyDecision(
                primary_issue=PrimaryIssue.LATE_DELIVERY_SELLER,
                case_status=CaseStatus.ACTION_REQUIRED,
                confidence=1.0,
                root_causes=(RootCause.SELLER_HANDOFF_AFTER_LIMIT,),
                responsible_parties=tuple(("seller", seller_id) for seller_id in order.late_seller_ids[:3]),
                actions=(Action.REFUND_FREIGHT,),
            )
        elif delivery.delivered_after_estimate:
            decision = PolicyDecision(
                primary_issue=PrimaryIssue.LATE_DELIVERY_LOGISTICS,
                case_status=CaseStatus.ACTION_REQUIRED,
                confidence=1.0,
                root_causes=(RootCause.CARRIER_DELIVERED_AFTER_ESTIMATE,),
                responsible_parties=(("logistics_provider", "LOGISTICS_PROVIDER"),),
                actions=(Action.REFUND_FREIGHT,),
            )
        elif payment.has_multiple_payments and payment.payment_matches_charge:
            decision = PolicyDecision(
                primary_issue=PrimaryIssue.VALID_SPLIT_PAYMENT,
                case_status=CaseStatus.NO_ACTION,
                confidence=1.0,
                root_causes=(RootCause.MULTIPLE_PAYMENTS_RECONCILED,),
                responsible_parties=(),
                actions=(Action.EXPLAIN_VALID_SPLIT_PAYMENT,),
            )
        else:
            decision = PolicyDecision(
                primary_issue=PrimaryIssue.UNSUPPORTED_LATE_CLAIM,
                case_status=CaseStatus.NO_ACTION,
                confidence=1.0,
                root_causes=(RootCause.DELIVERY_WITHIN_ESTIMATE,),
                responsible_parties=(),
                actions=(Action.REJECT_LATE_REFUND,),
            )
        return replace(state, policy_decision=decision)


class EvidenceAgent:
    def run(self, state: AgentState) -> AgentState:
        bundle = state.bundle
        decision = state.policy_decision
        if decision is None:
            raise ValueError("EvidenceAgent requires policy decision")

        evidence: list[str] = []
        if bundle.order:
            evidence.append(f"order:{bundle.order.order_id}")

        item_ids = state.order_facts.late_seller_item_ids if state.order_facts and state.order_facts.late_seller_item_ids else ()
        if not item_ids and state.order_facts:
            item_ids = state.order_facts.item_ids
        for item_id in item_ids:
            evidence.append(f"item:{item_id}")

        for payment_id in state.payment_facts.payment_ids if state.payment_facts else ():
            evidence.append(f"payment:{payment_id}")

        for party_type, party_id in decision.responsible_parties:
            if party_type == "seller":
                evidence.append(f"seller:{party_id}")

        for root_cause in decision.root_causes:
            evidence.append(f"policy:{root_cause.value}")

        return replace(state, evidence_ids=tuple(dict.fromkeys(evidence))[:10])
