# Individual Report - Day 9 Multi-Agent A2A

## 1. Personal Information

| Field | Value |
| --- | --- |
| Full name | 5SoCuoiMHV_HoVaTen |
| Student ID | 5SoCuoiMHV |
| Class | K3 |
| Main role | Principal AI Engineer / Multi-Agent Pipeline Owner |
| Completion date | 2026-08-05 |

## 2. Owned Scope

| Deliverable | Files | Input | Output | Status |
| --- | --- | --- | --- | --- |
| Deterministic agent pipeline | `ecommerce_dispute/agents.py`, `ecommerce_dispute/coordinator.py` | Case JSON and repository facts | Structured agent state and final decision | Complete |
| Data layer | `ecommerce_dispute/repository.py` | Olist CSV files | Cached lookup indexes | Complete |
| Verifier | `ecommerce_dispute/verifier.py` | Final output JSON | Pass/fail validation | Complete |
| Runner and artifacts | `ecommerce_dispute/runner.py` | `input/EC_*.json` | `output/*.json`, `trace.jsonl`, `metadata.json` | Complete |
| Tests | `tests/test_policy_pipeline.py` | Real Olist examples and temp cases | Unit, policy, verifier and integration checks | Complete |

## 3. Technical Summary

The solution avoids hallucination by not using an LLM for scored decisions. It loads orders, order items, payments and sellers once, then each case is resolved through separate agents with typed dataclass handoffs.

The policy engine implements `EC_POLICY_V1` in exact priority order:

1. paid canceled order
2. paid unavailable order
3. late delivery caused by seller handoff
4. late delivery caused by logistics
5. valid split payment
6. unsupported late claim

All money is calculated with `Decimal`, rounded to 2 decimals, and split-payment reconciliation uses the required 0.10 BRL tolerance.

## 4. Input / Output Contract

| Component | Contract |
| --- | --- |
| Input | `input/EC_XXX.json` with `case_id`, `customer_request.claimed_order_id`, `policy_version` |
| Output | One schema-compliant JSON per input case in `output/` |
| Trace | Fresh `trace.jsonl` generated per run |
| Metadata | Root `metadata.json` declaring `rule-engine-no-llm`, `0B` parameters |
| Failure behavior | Verifier failure raises an error and prevents output writing |

## 5. Verification Run

```bash
python3 -m unittest discover -s tests -v
```

Actual result:

```text
Ran 9 tests in 6.092s
OK
```

The tests cover all six policy branches, false-positive evidence rejection, output limits and runner integration.

## 6. Important Engineering Decision

Decision: use a deterministic rule engine instead of LLM reasoning.

Reason: the rubric rewards exact entity, evidence, root cause and financial correctness. The data already contains the required facts, while an LLM would increase nondeterminism and hallucination risk.

Trade-off: no natural-language interpretation beyond reading `claimed_order_id`, but the assignment explicitly states that this key is the retrieval anchor.

## 7. Blocker Handled

Blocker: the current repository has no official `input/EC_001.json` through `EC_050.json`; `input/` contains only `.gitkeep`.

Resolution: the runner is built to process all `EC_*.json` files when they are provided and to avoid generating fake outputs when inputs are absent.

## 8. End-to-End Understanding

Data flows from CSV into cached repository indexes, then from the input case into the coordinator. The coordinator passes structured state through domain-specific agents, applies the policy rule engine, builds evidence and financial totals, validates everything with an independent verifier, then writes output and trace artifacts.

Quality is measured by matching the rubric fields per case, not by answer fluency. The most important checks are policy priority, ID existence, evidence validity and exact refund calculation.

## 9. Commitment

- [x] The report reflects the implemented work.
- [x] I can explain the end-to-end pipeline and each agent contract.
- [x] I only report tests that were actually run.
- [x] No `.env`, API key, token or secret is included.
- [x] The solution does not depend on a model larger than 10B parameters.

