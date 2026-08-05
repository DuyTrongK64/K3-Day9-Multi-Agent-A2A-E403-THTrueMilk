# Architecture - Olist Multi-Agent Dispute Resolution

## 1. Submission Context

This document describes the current source implementation used for the 95-point baseline submission.

Team repository: K3 Day 09 Multi-Agent E-commerce Dispute Resolution  
Selected submission maintainer: Bùi Thế Huy  
Maintainer student ID: 2A202601881  
Policy version: `EC_POLICY_V1`  
Model: `rule-engine-no-llm`  
Parameter size: `0B`

The system is deterministic. It does not use an LLM for scored decisions. Refunds, evidence, entities, root cause, policy branch selection and financial calculation are all produced by code.

Team members:

| STT | Full name | Student ID | Group role |
| ---: | --- | --- | --- |
| 1 | Nguyễn Duy Trọng | 2A202601333 | Leader |
| 2 | Nguyễn Hoàng Tín | 2A202601603 | Member |
| 3 | Bùi Thế Huy | 2A202601881 | Member |

The group worked collaboratively on the same assignment. Each member contributed implementations, reviewed outputs and discussed scoring behavior. The team compared submitted variants and kept the highest-scoring stable version as the group baseline. This document describes the selected baseline source and artifacts.

## 2. Scoring Objective

The real target is to generate one valid JSON output for each input case by joining Olist CSV facts and applying the business rules in the exact priority order from the assignment.

The grader scores:

| Component | Weight | Current Strategy |
| --- | ---: | --- |
| Primary issue and confidence | 20% | Rule-based issue selection with calibrated branch confidence. |
| Affected entities | 20% | Emit order, item, seller and payment IDs related to the claimed order, capped by schema limits. |
| Root cause and responsible parties | 15% | Emit the single primary root cause required by the selected policy branch. |
| Evidence IDs | 15% | Emit only reconstructable IDs from CSV or policy root-cause codes. |
| Financial resolution | 20% | Use `Decimal`, 2-decimal rounding and exact refund mapping. |
| Resolution actions | 10% | Emit the policy action for the selected branch. |

## 3. Hard Gates Avoided

- No hallucinated order, item, payment, seller or tracking IDs.
- No model larger than 10B parameters; the current model size is `0B`.
- No free-text agent output in the scored JSON.
- No stale output files: `runner.py` removes existing `output/EC_*.json` before writing a new run.
- No output is written before the final object passes the independent verifier.
- Zip packaging contains only the 50 JSON outputs when prepared for submission.

## 4. Data Layer

Implemented in `ecommerce_dispute/repository.py`.

`OlistRepository` loads CSV files once at startup and builds lookup indexes:

- `orders_by_id: order_id -> OrderRecord`
- `items_by_order_id: order_id -> list[ItemRecord]`
- `payments_by_order_id: order_id -> list[PaymentRecord]`
- `seller_ids: set[seller_id]`

The 50 official inputs use `customer_request.claimed_order_id` as the retrieval key. The repository returns sorted item/payment tuples so output order is stable.

## 5. Agent List

### Coordinator Agent

- File: `ecommerce_dispute/coordinator.py`
- Input: `CustomerCase`
- Output: final JSON object and trace events
- Role: orchestrates all agents, calls verifier, returns only verified output
- Data access: injected repository and verifier only

### Retriever Agent

- File: `ecommerce_dispute/agents.py`
- Input: `AgentState` with case
- Output: `CaseBundle`
- Role: retrieves order, items and payments for `claimed_order_id`
- Data access: repository indexes

### OrderSeller Agent

- Input: `CaseBundle`
- Output: `OrderFacts`
- Role: determines order status, item IDs, seller IDs and seller handoff lateness
- Data access: order row and order item rows

### Payment Agent

- Input: `CaseBundle`
- Output: `PaymentFacts`
- Role: computes payment IDs, total payment, split payment count and reconciliation
- Data access: order item rows and payment rows
- Rule: payment matches charge when `abs(payment_total - item_total - freight_total) <= 0.10 BRL`

### Delivery Agent

- Input: `CaseBundle`
- Output: `DeliveryFacts`
- Role: compares `order_delivered_customer_date` with `order_estimated_delivery_date`
- Data access: order delivery timestamps

### Policy Agent

- Input: `OrderFacts`, `PaymentFacts`, `DeliveryFacts`
- Output: `PolicyDecision`
- Role: applies `EC_POLICY_V1` in priority order
- Data access: structured facts only

Policy order:

1. `canceled_order_paid`
2. `unavailable_order_paid`
3. `late_delivery_seller`
4. `late_delivery_logistics`
5. `valid_split_payment`
6. `unsupported_late_claim`

Current confidence profile for the 95-point baseline:

| Issue | Confidence |
| --- | ---: |
| `canceled_order_paid` | 0.99 |
| `unavailable_order_paid` | 0.99 |
| `late_delivery_seller` | 0.96 |
| `late_delivery_logistics` | 0.95 |
| `valid_split_payment` | 0.94 |
| `unsupported_late_claim` | 0.91 or 0.82 if payment mismatch |

### Evidence Agent

- Input: case bundle, facts and policy decision
- Output: `evidence_ids`
- Role: emits allowed evidence IDs only
- Formats:
  - `order:<order_id>`
  - `item:<order_id>:<order_item_id>`
  - `payment:<order_id>:<payment_sequential>`
  - `seller:<seller_id>`
  - `policy:<root_cause_code>`

For seller-late cases, evidence uses late seller item IDs first. For other cases, it uses order item IDs as supporting order context. Evidence is deduplicated and capped at 10.

### Financial Agent

- Input: bundle and policy decision
- Output: `FinancialFacts`
- Role: computes item total, freight total, payment total and refund
- Refund rules:
  - full refund: total payment
  - freight refund: total freight
  - no action: `0.00`

### Verifier Agent

- File: `ecommerce_dispute/verifier.py`
- Input: final output object
- Output: pass or `VerificationError`
- Role: independent validation before writing output
- Checks:
  - top-level schema
  - enum values
  - confidence in `[0, 1]`
  - output list limits
  - order/item/payment/seller ID existence
  - evidence format and existence
  - root cause/action/responsible party consistency
  - financial totals and refund amount

## 6. Handoff Flow

```text
CustomerCase
  -> CoordinatorAgent
  -> RetrieverAgent
  -> OrderSellerAgent
  -> PaymentAgent
  -> DeliveryAgent
  -> PolicyAgent
  -> EvidenceAgent
  -> FinancialAgent
  -> VerifierAgent
  -> Output Writer
```

Each handoff is a typed dataclass held in `AgentState`. Agents do not pass free-form text.

## 7. Shared State

`AgentState` contains:

- `CaseBundle`
- `OrderFacts`
- `PaymentFacts`
- `DeliveryFacts`
- `PolicyDecision`
- `FinancialFacts`
- `evidence_ids`

The state is updated with `dataclasses.replace`, so each agent returns a structured object without mutating prior facts.

## 8. Logging and Trace

`trace.jsonl` is overwritten for each real run. The current trace contains 400 events for 50 cases:

- 7 completed agent events per case
- 1 verifier pass event per case

Trace fields include agent name, case ID, order ID, status, primary issue, action and refund after those facts become available.

## 9. Validation and Output

The runner writes `output/EC_XXX.json` only after `VerifierAgent.verify()` succeeds. Metadata is written to `metadata.json` with model, parameter size, framework, runtime, policy version and case count.

## 10. Edge Cases Covered

- multiple payment rows
- split payment reconciliation
- multiple item rows
- multiple sellers
- seller handoff after `shipping_limit_date`
- logistics late after seller handoff within limit
- canceled paid order
- unavailable paid order
- unsupported late claim
- order with no item rows
- null timestamps
- missing payments
- duplicate IDs
- invalid evidence format
- payment tolerance within 0.10 BRL
- Decimal rounding to 2 BRL decimals
- output list limits
- unsupported policy version

## 11. Team Review Process

The team used a competitive-but-collaborative workflow:

- each member inspected the rubric and proposed deterministic rule changes
- outputs were compared against leaderboard feedback
- changes that reduced score were rolled back
- high-risk changes to root cause, evidence and entity sets were reviewed before keeping
- the highest-scoring verified output was selected for the final group submission
- each member wrote or updated an individual report based on the shared architecture and their own understanding
