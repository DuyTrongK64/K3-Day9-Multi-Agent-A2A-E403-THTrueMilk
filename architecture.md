# Architecture - Deterministic Multi-Agent E-commerce Dispute Resolution

## Exam-Oriented Analysis

### Real Objective

The scoring target is not to write a persuasive support reply. The target is to produce one strictly valid JSON file per input case, using only verifiable Olist CSV facts and the supplied `EC_POLICY_V1` rules.

The system is deliberately deterministic and does not depend on a large language model. All final decisions for refund, evidence, affected entities, policy, root cause and financial calculation are made by code.

### Scored Components

| Component | Weight | Optimization Strategy |
| --- | ---: | --- |
| Primary issue and confidence | 20% | Apply policy priority exactly as written. |
| Affected entities | 20% | Only emit IDs that exist in CSV and cap at schema limits. |
| Root cause and responsible parties | 15% | Derive from the selected policy branch. |
| Evidence IDs | 15% | Build only allowed formats from existing order/item/payment/seller/policy rows. |
| Financial resolution | 20% | Use Decimal money arithmetic and round to 2 decimals. |
| Resolution actions | 10% | Map one-to-one from policy branch. |

### Hard Gates

- Missing or malformed output JSON.
- Evidence IDs that cannot be reconstructed from CSV.
- Output files not matching the input case set.
- Depending on a model larger than 10B parameters.
- Hallucinating transactions, refund ledgers, tracking checkpoints or item-level delivery facts not present in Olist.
- Writing an output after verifier failure.

### Common Failure Modes

- Classifying late logistics as seller late without checking `shipping_limit_date`.
- Checking split payment before higher-priority cancellation/unavailability/late delivery rules.
- Treating `payment_value` as installment value instead of payment-row value.
- Comparing money with float arithmetic rather than Decimal plus 0.10 BRL tolerance.
- Emitting more than 5 entity IDs, 10 evidence IDs, 3 causes, 3 parties or 5 actions.
- Treating null timestamps as proof of on-time/late delivery.
- Keeping stale output files from a prior run.

### Hidden Assumptions

- `claimed_order_id` is the retrieval key.
- One Olist `customer_id` maps to one order; customer history is not needed for the policy.
- CSV timestamps are compared directly without timezone conversion.
- The official 50 cases avoid ambiguous multi-seller responsibility, but the implementation still caps and validates IDs.
- If an order has no item row, item and seller entity sets are empty and item/freight totals are 0.00.

## Pre-Code Checklist

- [x] Read all assignment rules and output limits.
- [x] Use no LLM for policy, evidence, entity, root cause or money decisions.
- [x] Load CSV data once into cache/index structures.
- [x] Join by `order_id` for order, items and payments.
- [x] Preserve policy priority order.
- [x] Use Decimal for all BRL totals and refunds.
- [x] Generate only allowed evidence ID formats.
- [x] Cap all output arrays to rubric limits.
- [x] Run independent verifier before writing output.
- [x] Overwrite trace with the newest run.
- [x] Remove stale `EC_*.json` outputs before a new run.
- [x] Record model metadata with parameter size <= 10B.
- [x] Cover policy, schema, edge and integration tests.

## Agent Design

### Coordinator Agent

- Input: `CustomerCase`
- Output: final output object and trace events
- Data access: no direct CSV access except through injected repository and verifier
- Responsibility: orchestrates handoff order, stops if any agent or verifier fails

### Retriever Agent

- Input: case with `claimed_order_id`
- Output: `CaseBundle(order, items, payments)`
- Data access: repository indexes for orders, items and payments
- Responsibility: one retrieval pass per case after repository has loaded CSVs once

### Order & Seller Agent

- Input: `CaseBundle`
- Output: `OrderFacts`
- Data access: order row and item rows only
- Responsibility: status, item IDs, seller IDs, seller handoff lateness

### Payment Agent

- Input: `CaseBundle`
- Output: `PaymentFacts`
- Data access: payment rows and item/freight totals
- Responsibility: payment IDs, total payment, split payment detection and 0.10 BRL reconciliation

### Delivery Agent

- Input: order row
- Output: `DeliveryFacts`
- Data access: delivery and estimated timestamps
- Responsibility: delivered after estimate vs within estimate

### Policy Agent

- Input: order, payment and delivery facts
- Output: `PolicyDecision`
- Data access: no raw CSV
- Responsibility: apply `EC_POLICY_V1` in priority order:
  canceled paid, unavailable paid, seller late, logistics late, valid split payment, unsupported late claim

### Evidence Agent

- Input: bundle, facts and policy decision
- Output: `evidence_ids`
- Data access: structured facts only
- Responsibility: create only `order:`, `item:`, `payment:`, `seller:` and `policy:` IDs

### Financial Agent

- Input: bundle and policy decision
- Output: `FinancialFacts`
- Data access: item and payment rows
- Responsibility: item total, freight total, payment total and recommended refund

### Verifier Agent

- Input: final output object
- Output: pass or `VerificationError`
- Data access: repository indexes
- Responsibility: schema, enum, confidence, ID existence, evidence format, policy consistency, refund consistency and output limits

### Output Writer

- Input: verifier-approved output object
- Output: `output/EC_XXX.json`
- Data access: filesystem only
- Responsibility: write JSON with stable formatting

## Handoff Flow

```text
Coordinator
  -> Retriever
  -> OrderSeller
  -> Payment
  -> Delivery
  -> Policy
  -> Evidence
  -> Financial
  -> Verifier
  -> Output Writer
```

Every handoff is a dataclass, never free text.

## Shared State

The shared state is `AgentState`, an immutable dataclass updated with `dataclasses.replace`. It contains:

- `CaseBundle`
- `OrderFacts`
- `PaymentFacts`
- `DeliveryFacts`
- `PolicyDecision`
- `FinancialFacts`
- `evidence_ids`

## Retry and Failure Handling

This implementation is deterministic, so transient retries are not useful for policy decisions. The fail strategy is:

- Invalid policy version: raise error.
- Missing order or invalid evidence: verifier fails.
- Verifier failure: no output file is written for that case.
- Re-run safety: stale `output/EC_*.json` files are deleted before processing new inputs.

## Logging and Trace

`trace.jsonl` is overwritten on each run. Each line records:

- agent name
- case ID
- order ID
- completion status
- selected issue/action once available
- refund once available

## Validation

Validation is independent of the policy agent and checks:

- exact schema keys
- enum values
- confidence range
- output array limits
- order/item/payment/seller ID existence
- evidence ID format and existence
- action and root cause consistency
- responsible party consistency
- financial totals and refund amount

## Edge Cases Covered

- multiple payments
- valid split payment
- multiple items
- multiple sellers
- seller handoff late
- logistics late
- canceled paid order
- unavailable paid order
- unsupported late claim
- order with no item rows
- payment missing or extra rows
- small payment mismatch within 0.10 BRL
- Decimal money rounding
- null or invalid timestamps
- duplicate entity/evidence IDs
- nonexistent order IDs
- seller ID not belonging to order
- payment evidence not belonging to order
- output length limits
- stale output from prior runs
- unsupported policy version

## Model Constraint

Model: `rule-engine-no-llm`

Parameter size: `0B`

The architecture is compatible with adding a <=10B language model later for optional message normalization, but no scored decision depends on natural language generation or model reasoning.

