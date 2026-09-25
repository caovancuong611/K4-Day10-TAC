from __future__ import annotations

import json

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import main as run_phase1
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """Run controlled corruption, measurement, and idempotent raw repair."""
    settings = load_settings()
    prerequisites = (
        settings.paths.clean_json,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
    )
    if not all(path.exists() for path in prerequisites):
        run_phase1()

    baseline_metrics = read_json(settings.paths.baseline_metrics)
    clean_df = pd.read_json(settings.paths.clean_json)

    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(
        settings.paths.corrupted_clean_json,
        json.loads(corrupted_df.to_json(orient="records")),
    )
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness_path = settings.paths.quality_dir / "corrupted_freshness_report.json"
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, corrupted_freshness_path
    )
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    corrupted_evaluation = evaluate_pipeline(
        settings,
        corrupted_index,
        settings.paths.eval_testset,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
    )

    repaired_df = build_clean_dataframe(
        load_raw_records(settings.paths.raw_records_json),
        now_utc(),
    )
    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(
        settings.paths.repaired_clean_json,
        json.loads(repaired_df.to_json(orient="records")),
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness_path = settings.paths.quality_dir / "repaired_freshness_report.json"
    repaired_freshness = build_freshness_report(repaired_df, settings, repaired_freshness_path)
    if not repaired_quality["success"]:
        raise RuntimeError("Raw-data repair did not pass the quality gate.")
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    repaired_evaluation = evaluate_pipeline(
        settings,
        repaired_index,
        settings.paths.eval_testset,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
    )

    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics,
        corrupted_evaluation.summary,
        repaired_evaluation.summary,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
    )
    print(
        "Corruption flow complete: "
        f"corrupted_quality={corrupted_quality['success']}, "
        f"repaired_quality={repaired_quality['success']}, "
        f"rows={len(corrupted_df)}"
    )
