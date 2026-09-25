# Corruption, Silent Failure, and Repair Report

## Quantitative comparison

| Metric | Baseline | Corrupted | Repaired | Corrupted Δ |
|---|---:|---:|---:|---:|
| Retrieval hit rate | 1.000 | 0.600 | 1.000 | -0.400 |
| Mean token F1 | 1.000 | 0.400 | 1.000 | -0.600 |
| LLM judge accuracy | 1.000 | 0.400 | 1.000 | -0.600 |
| Mean LLM judge score | 5.000 | 2.600 | 5.000 | -2.400 |

## Observability comparison

| State | Quality Gate | Freshness | Stale rows | Stale ratio |
|---|---:|---:|---:|---:|
| Baseline | PASS | FRESH | — | — |
| Corrupted | FAIL | STALE | 8 / 24 | 33.33% |
| Repaired | PASS | FRESH | 1 / 24 | 4.17% |

## Analysis

The corrupted corpus contains missing summaries, noisy embedding text, truncated titles,
stale dates, duplicate identifiers, and missing recent records. The quality gate detects
these structural and freshness failures before promotion. Rebuilding deterministically
from the preserved raw snapshot removes duplicates and restores the clean schema, making
the repair idempotent and returning the gate to PASS.
