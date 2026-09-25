from __future__ import annotations

import json

from core.config import load_settings
from core.utils import now_utc, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import load_or_create_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """Run the complete clean-data baseline pipeline."""
    settings = load_settings()
    records = fetch_source_records(settings)
    clean_df = build_clean_dataframe(records, now_utc())
    write_csv(clean_df, settings.paths.clean_csv)
    clean_payload = json.loads(clean_df.to_json(orient="records"))
    write_json(settings.paths.clean_json, clean_payload)

    quality = run_data_quality_checks(clean_df, settings, "baseline")
    freshness = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    if not quality["success"]:
        raise RuntimeError(
            "Baseline data failed the quality gate; see "
            f"{settings.paths.baseline_quality_report}"
        )

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )
    test_set = load_or_create_test_set(
        clean_df,
        settings.paths.eval_testset,
        refresh=settings.refresh_test_set,
    )
    evaluation = evaluate_pipeline(
        settings,
        index,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
    )
    source_summary = {
        "source": settings.source_api,
        "raw_records": len(records),
        "clean_records": len(clean_df),
        "collection": settings.baseline_collection_name,
        "test_samples": len(test_set.samples),
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary,
        evaluation.summary,
        quality,
        freshness,
    )
    print(
        "Phase 1 complete: "
        f"{len(clean_df)} clean papers, {len(test_set.samples)} benchmark questions, "
        f"quality={quality['success']}, hit_rate={evaluation.summary['retrieval_hit_rate']:.3f}"
    )
