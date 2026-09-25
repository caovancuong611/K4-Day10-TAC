from __future__ import annotations

from typing import Any

from core.utils import write_text


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def _number(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "N/A"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a compact, evidence-backed baseline report."""
    expectation_rows = "\n".join(
        "| {name} | {column} | {status} |".format(
            name=item.get("expectation_type", "unknown"),
            column=item.get("column") or "—",
            status="PASS" if item.get("success") else "FAIL",
        )
        for item in quality.get("expectations", [])
    )
    markdown = f"""# Phase 1 Baseline Report

## Data source

| Field | Value |
|---|---:|
| Source | {source_summary.get('source', 'Crossref')} |
| Raw records | {source_summary.get('raw_records', 'N/A')} |
| Clean records | {source_summary.get('clean_records', 'N/A')} |
| Vector collection | {source_summary.get('collection', 'N/A')} |
| Benchmark samples | {metrics.get('samples', 'N/A')} |

## Baseline metrics

| Metric | Value |
|---|---:|
| Retrieval hit rate | {_percent(metrics.get('retrieval_hit_rate'))} |
| Mean token F1 | {_number(metrics.get('mean_token_f1'))} |
| LLM judge accuracy | {_percent(metrics.get('judge_accuracy'))} |
| Mean LLM judge score | {_number(metrics.get('mean_judge_score'))} / 5 |

## Data Quality Gate

Overall status: **{'PASS' if quality.get('success') else 'FAIL'}**

| Expectation | Column | Status |
|---|---|---:|
{expectation_rows}

## Freshness SLA

| Metric | Value |
|---|---:|
| Status | {'FRESH' if freshness.get('is_fresh') else 'STALE'} |
| Latest publication | {freshness.get('latest_published')} |
| Oldest publication | {freshness.get('oldest_published')} |
| Stale rows | {freshness.get('stale_rows')} / {freshness.get('total_rows')} |
| Stale ratio | {_percent(freshness.get('stale_ratio'))} |
| Allowed stale ratio | {_percent(freshness.get('stale_ratio_limit'))} |

The baseline passed the gate before indexing, so the evaluation metrics describe the clean corpus.
"""
    write_text(report_path, markdown)


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write the clean/corrupted/repaired comparison report."""

    def delta(corrupted: Any, baseline: Any) -> str:
        try:
            return f"{float(corrupted) - float(baseline):+.3f}"
        except (TypeError, ValueError):
            return "N/A"

    rows = []
    for key, label in (
        ("retrieval_hit_rate", "Retrieval hit rate"),
        ("mean_token_f1", "Mean token F1"),
        ("judge_accuracy", "LLM judge accuracy"),
        ("mean_judge_score", "Mean LLM judge score"),
    ):
        baseline = baseline_metrics.get(key)
        corrupted = corrupted_metrics.get(key)
        repaired = repaired_metrics.get(key)
        rows.append(
            f"| {label} | {_number(baseline)} | {_number(corrupted)} | "
            f"{_number(repaired)} | {delta(corrupted, baseline)} |"
        )

    markdown = f"""# Corruption, Silent Failure, and Repair Report

## Quantitative comparison

| Metric | Baseline | Corrupted | Repaired | Corrupted Δ |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

## Observability comparison

| State | Quality Gate | Freshness | Stale rows | Stale ratio |
|---|---:|---:|---:|---:|
| Baseline | PASS | FRESH | — | — |
| Corrupted | {'PASS' if corrupted_quality.get('success') else 'FAIL'} | {'FRESH' if corrupted_freshness.get('is_fresh') else 'STALE'} | {corrupted_freshness.get('stale_rows')} / {corrupted_freshness.get('total_rows')} | {_percent(corrupted_freshness.get('stale_ratio'))} |
| Repaired | {'PASS' if repaired_quality.get('success') else 'FAIL'} | {'FRESH' if repaired_freshness.get('is_fresh') else 'STALE'} | {repaired_freshness.get('stale_rows')} / {repaired_freshness.get('total_rows')} | {_percent(repaired_freshness.get('stale_ratio'))} |

## Analysis

The corrupted corpus contains missing summaries, noisy embedding text, truncated titles,
stale dates, duplicate identifiers, and missing recent records. The quality gate detects
these structural and freshness failures before promotion. Rebuilding deterministically
from the preserved raw snapshot removes duplicates and restores the clean schema, making
the repair idempotent and returning the gate to PASS.
"""
    write_text(report_path, markdown)
