from __future__ import annotations

from pathlib import Path
from typing import Any

import great_expectations as gx
from great_expectations import expectations as gxe
import pandas as pd

from core.config import Settings
from core.utils import safe_slug, write_json


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run the GX 1.x quality gate plus the freshness SLA.

    The dataframe asset API below is the supported GX 1.x interface.  A fresh
    ephemeral context is used on every invocation, so validation never creates
    a hidden GX project in the repository.
    """
    required_columns = {
        "paper_id", "title", "summary", "text_for_embedding", "age_days", "published"
    }
    missing_columns = sorted(required_columns.difference(df.columns))
    if missing_columns:
        payload = {
            "success": False,
            "report_name": report_name,
            "row_count": int(len(df)),
            "missing_columns": missing_columns,
            "expectations": [],
            "freshness": {
                "is_fresh": False,
                "reason": "Required columns are missing.",
            },
        }
        write_json(_quality_report_path(settings, report_name), payload)
        return payload

    validation_df = df.copy()
    # GX's not-null expectation treats an empty string as a value.  Turning
    # whitespace-only required values into NA enforces the stated "not blank"
    # contract while still using ExpectColumnValuesToNotBeNull.
    for column in ("paper_id", "title", "text_for_embedding"):
        validation_df[column] = validation_df[column].replace(r"^\s*$", pd.NA, regex=True)

    context = gx.get_context(mode="ephemeral")
    suffix = safe_slug(report_name)
    data_source = context.data_sources.add_pandas(name=f"papers_source_{suffix}")
    data_asset = data_source.add_dataframe_asset(name=f"papers_asset_{suffix}")
    batch_def = data_asset.add_batch_definition_whole_dataframe(f"papers_batch_{suffix}")
    batch = batch_def.get_batch(batch_parameters={"dataframe": validation_df})

    expectations = [
        gxe.ExpectTableRowCountToBeBetween(min_value=5, max_value=5000),
        gxe.ExpectColumnValuesToNotBeNull(column="paper_id"),
        gxe.ExpectColumnValuesToNotBeNull(column="title"),
        gxe.ExpectColumnValuesToNotBeNull(column="text_for_embedding"),
        gxe.ExpectColumnValuesToBeUnique(column="paper_id"),
        gxe.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=30),
    ]
    results: list[dict[str, Any]] = []
    for expectation in expectations:
        result = batch.validate(expectation, result_format="SUMMARY")
        serialized = result.to_json_dict()
        results.append(
            {
                "expectation_type": expectation.expectation_type,
                "column": getattr(expectation, "column", None),
                "success": bool(result.success),
                "result": serialized.get("result", {}),
                "exception_info": serialized.get("exception_info", {}),
            }
        )

    freshness = _freshness_payload(df, settings)
    gx_success = all(item["success"] for item in results)
    payload = {
        "success": bool(gx_success and freshness["is_fresh"]),
        "gx_success": gx_success,
        "report_name": report_name,
        "row_count": int(len(df)),
        "missing_columns": [],
        "expectations": results,
        "freshness": freshness,
    }
    write_json(_quality_report_path(settings, report_name), payload)
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Build and persist the freshness SLA report."""
    payload = _freshness_payload(df, settings)
    write_json(Path(report_path), payload)
    return payload


def _quality_report_path(settings: Settings, report_name: str) -> Path:
    normalized = safe_slug(report_name)
    if normalized in {"baseline", "phase1"}:
        return settings.paths.baseline_quality_report
    if normalized in {"corrupted", "corruption"}:
        return settings.paths.corrupted_quality_report
    return settings.paths.quality_dir / f"{normalized}_quality_report.json"


def _freshness_payload(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    total_rows = int(len(df))
    if "published" in df:
        published = pd.to_datetime(df["published"], errors="coerce", utc=True)
    else:
        published = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    if "age_days" in df:
        ages = pd.to_numeric(df["age_days"], errors="coerce")
    else:
        now = pd.Timestamp.now(tz="UTC").normalize()
        ages = (now - published).dt.days

    stale_mask = ages > settings.freshness_threshold_days
    stale_rows = int(stale_mask.fillna(False).sum())
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    valid_published = published.dropna()
    return {
        "latest_published": (
            valid_published.max().date().isoformat() if not valid_published.empty else None
        ),
        "oldest_published": (
            valid_published.min().date().isoformat() if not valid_published.empty else None
        ),
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 6),
        "stale_ratio_limit": 0.25,
        "threshold_days": settings.freshness_threshold_days,
        "is_fresh": bool(total_rows > 0 and stale_ratio <= 0.25),
    }
