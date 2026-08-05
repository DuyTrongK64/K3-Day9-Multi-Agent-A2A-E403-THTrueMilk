# Individual Report - Day 9 Multi-Agent A2A

## 1. Personal Information

| Field | Value |
| --- | --- |
| Full name | Bùi Thế Huy |
| Student ID | 2A202601881 |
| Last 5 digits | 01881 |
| Class | K3 |
| Main role | Team member / Multi-Agent Pipeline and Rule Engine contributor |
| Completion date | 2026-08-05 |

## 2. Team Information

| STT | Full name | Student ID | Group role |
| ---: | --- | --- | --- |
| 1 | Nguyễn Duy Trọng | 2A202601333 | Leader |
| 2 | Nguyễn Hoàng Tín | 2A202601603 | Member |
| 3 | Bùi Thế Huy | 2A202601881 | Member |

This was a team assignment. All members contributed by reading the problem, discussing edge cases, testing output variants and giving feedback to improve the final group submission. The group compared different runs and selected the version with the best stable score as the shared baseline.

## 3. Owned Scope

| Deliverable | Files | Input | Output | Status |
| --- | --- | --- | --- | --- |
| Agent orchestration | `ecommerce_dispute/coordinator.py` | `CustomerCase` | verified output object and trace events | Complete |
| Domain agents | `ecommerce_dispute/agents.py` | typed `AgentState` | order, payment, delivery, policy, evidence and financial facts | Complete |
| Data layer | `ecommerce_dispute/repository.py` | Olist CSV files | cached lookup indexes | Complete |
| Output schema | `ecommerce_dispute/output.py` | complete `AgentState` | scoring JSON object | Complete |
| Independent verifier | `ecommerce_dispute/verifier.py` | final JSON object | pass/fail validation | Complete |
| Runner artifacts | `ecommerce_dispute/runner.py` | `input/EC_*.json` | `output/*.json`, `trace.jsonl`, `metadata.json` | Complete |
| Tests | `tests/test_policy_pipeline.py` | real Olist examples and temp cases | unit, policy, verifier and integration checks | Complete |

## 4. My Contribution and Peer Review

My contribution focused on the deterministic multi-agent pipeline, data-driven policy rules, output validation and score-oriented debugging. I also reviewed leaderboard feedback with the team, compared variants and helped identify which changes should be kept or rolled back.

Team collaboration notes:

- Nguyễn Duy Trọng coordinated the group workflow and helped decide which version should be treated as the final baseline.
- Nguyễn Hoàng Tín joined the review of outputs, edge cases and report consistency.
- Bùi Thế Huy implemented and refined the rule-based multi-agent pipeline, verifier and artifact documentation.

The team gave feedback to each other while writing reports so that the final documents describe the same shared system but still reflect each member's own role and understanding.

## 5. Technical Summary

The selected implementation resolves each dispute deterministically from Olist data. It does not use an LLM for scored decisions, so the system avoids hallucinating orders, sellers, tracking checkpoints, refund ledgers or transaction IDs that do not exist in the CSV files.

The policy engine applies `EC_POLICY_V1` in this exact order:

1. paid canceled order
2. paid unavailable order
3. late delivery caused by seller handoff
4. late delivery caused by logistics
5. valid split payment
6. unsupported late claim

All money is calculated with `Decimal`, rounded to 2 decimal places. Split payment is considered reconciled when the total payment matches item plus freight within the required `0.10 BRL` tolerance.

This report describes the current 95-point baseline version, not the experimental confidence-1.0 variant.

## 6. Input, Output and Contract

| Component | Contract |
| --- | --- |
| Input | `input/EC_XXX.json` with `case_id`, `customer_request.claimed_order_id`, `policy_version` |
| Data | Olist CSV files in `data/` |
| Output | one schema-compliant JSON per input case in `output/` |
| Trace | `trace.jsonl`, overwritten on each run |
| Metadata | `metadata.json`, declares `rule-engine-no-llm` and `0B` parameters |
| Failure behavior | verifier failure raises an error and prevents output writing |

## 7. Work Performed

| Task | Artifact | Result | Verification |
| --- | --- | --- | --- |
| Built CSV repository | `ecommerce_dispute/repository.py` | CSV files are loaded once and indexed by order ID | integration runner |
| Implemented rule agents | `ecommerce_dispute/agents.py` | six policy branches produce structured decisions | policy tests |
| Implemented verifier | `ecommerce_dispute/verifier.py` | catches invalid schema, evidence, entity IDs and financial mismatch | verifier tests |
| Generated run artifacts | `trace.jsonl`, `metadata.json`, `output/` | 50 official cases processed | runner output and trace count |
| Packaged output | `output.zip` | 50 JSON files only | archive inspection |

## 8. Verification Run

Command:

```bash
python3 -m unittest discover -s tests -v
```

Observed result:

```text
Ran 9 tests
OK
```

The tests cover all six primary policy branches, false-positive evidence rejection, output limits and runner integration.

## 9. Important Engineering Decision

Decision: use a deterministic rule engine instead of LLM reasoning.

Reason: the scoring rubric rewards exact values. The needed facts are present in CSV files, while an LLM would increase nondeterminism and hallucination risk. A rule engine also satisfies the assignment constraint that all models must be `<= 10B` parameters; this implementation uses no model at all for decisions.

Trade-off: the system does not try to infer extra meaning from the free-text customer message beyond `claimed_order_id`. This is acceptable because the assignment explicitly gives `claimed_order_id` as the retrieval key and the six official policies are fully data-driven.

## 10. Issue Handled During Development

Issue: adding extra root causes to seller-late cases reduced score because the grader penalized false-positive causes and policy evidence.

Resolution: the current baseline emits only the primary root cause for each selected policy branch. For `late_delivery_seller`, it emits `SELLER_HANDOFF_AFTER_LIMIT` only.

Verification: regenerated outputs and confirmed that seller-late cases contain one ranked cause and one policy evidence ID.

## 11. End-to-End Understanding

The case starts with `claimed_order_id`. The retriever joins that ID to order, item and payment indexes. Domain agents compute order status, seller handoff timing, delivery lateness, payment reconciliation and monetary totals. The policy agent selects exactly one primary issue. Evidence and financial agents build structured facts. The verifier checks schema, enum values, entity existence, evidence validity, policy consistency and refund correctness before the runner writes the JSON output.

Quality is measured by rubric fields, not by natural-language quality. The highest-risk fields are entity IDs, evidence IDs, financial totals and root-cause/action consistency.

## 12. Commitment

- [x] The report reflects my implemented work.
- [x] The report acknowledges this as a team assignment.
- [x] I contributed to peer review and score-based selection of the final version.
- [x] I can explain the end-to-end multi-agent flow.
- [x] I only report tests and artifacts that were actually produced.
- [x] The report contains no `.env`, API key, token or secret.
- [x] The implementation does not depend on any model larger than 10B parameters.

Signed: Bùi Thế Huy  
Date: 2026-08-05
