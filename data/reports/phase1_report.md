# Phase 1 Baseline Report

## Data source

| Field | Value |
|---|---:|
| Source | Crossref REST API |
| Raw records | 24 |
| Clean records | 24 |
| Vector collection | papers-baseline |
| Benchmark samples | 5 |

## Baseline metrics

| Metric | Value |
|---|---:|
| Retrieval hit rate | 100.00% |
| Mean token F1 | 1.000 |
| LLM judge accuracy | 100.00% |
| Mean LLM judge score | 5.000 / 5 |

## Data Quality Gate

Overall status: **PASS**

| Expectation | Column | Status |
|---|---|---:|
| expect_table_row_count_to_be_between | — | PASS |
| expect_column_values_to_not_be_null | paper_id | PASS |
| expect_column_values_to_not_be_null | title | PASS |
| expect_column_values_to_not_be_null | text_for_embedding | PASS |
| expect_column_values_to_be_unique | paper_id | PASS |
| expect_column_value_lengths_to_be_between | summary | PASS |

## Freshness SLA

| Metric | Value |
|---|---:|
| Status | FRESH |
| Latest publication | 2026-07-22 |
| Oldest publication | 2026-03-28 |
| Stale rows | 1 / 24 |
| Stale ratio | 4.17% |
| Allowed stale ratio | 25.00% |

The baseline passed the gate before indexing, so the evaluation metrics describe the clean corpus.
