from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from core.utils import write_json


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Inject six deterministic failure modes while preserving row count."""
    if df.empty:
        raise ValueError("Cannot corrupt an empty dataframe.")
    required = {
        "paper_id", "title", "summary", "published", "age_days",
        "authors_joined", "categories_joined", "text_for_embedding",
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Cannot corrupt dataframe; missing columns: {', '.join(missing)}")

    original_rows = int(len(df))
    working = df.copy(deep=True).reset_index(drop=True)
    actions: list[dict[str, object]] = []

    # 1) Remove the latest 20%; the same number is duplicated at the end so the
    # checkpoint retains 24 rows while both data-loss and duplication are real.
    drop_count = max(1, round(original_rows * 0.20))
    latest_indices = (
        pd.to_datetime(working["published"], errors="coerce")
        .sort_values(ascending=False)
        .index[:drop_count]
        .tolist()
    )
    dropped_ids = working.loc[latest_indices, "paper_id"].astype(str).tolist()
    working = working.drop(index=latest_indices).reset_index(drop=True)
    actions.append(
        {
            "scenario": "drop_latest_records",
            "affected_count": drop_count,
            "paper_ids": dropped_ids,
            "details": "Removed the newest 20% of papers.",
        }
    )

    # Select mutations by stable paper-id order instead of dataframe position.
    # This keeps the experiment reproducible even if the clean frame is sorted
    # differently on another machine.
    ordered_indices = working.sort_values("paper_id").index.tolist()
    blank_indices = [ordered_indices[pos] for pos in (0, 2, 4) if pos < len(ordered_indices)]
    working.loc[blank_indices, "summary"] = ""
    working.loc[blank_indices, "summary_chars"] = 0
    actions.append(
        {
            "scenario": "blank_summary",
            "affected_count": len(blank_indices),
            "paper_ids": working.loc[blank_indices, "paper_id"].astype(str).tolist(),
            "details": "Replaced summaries with empty strings.",
        }
    )

    title_indices = [ordered_indices[pos] for pos in (3, 5, 7) if pos < len(ordered_indices)]
    working.loc[title_indices, "title"] = working.loc[title_indices, "title"].astype(str).str[:7]
    actions.append(
        {
            "scenario": "truncate_title",
            "affected_count": len(title_indices),
            "paper_ids": working.loc[title_indices, "paper_id"].astype(str).tolist(),
            "details": "Truncated titles to at most 7 characters.",
        }
    )

    stale_count = max(7, round(original_rows * 0.30))
    stale_indices = ordered_indices[: min(stale_count, len(working))]
    old_dates = pd.to_datetime(working.loc[stale_indices, "published"], errors="coerce") - pd.DateOffset(years=5)
    working.loc[stale_indices, "published"] = old_dates.dt.strftime("%Y-%m-%d").values
    working.loc[stale_indices, "age_days"] = (
        pd.Timestamp.now(tz="UTC").normalize().tz_localize(None) - old_dates.dt.normalize()
    ).dt.days.values
    actions.append(
        {
            "scenario": "stale_date",
            "affected_count": len(stale_indices),
            "paper_ids": working.loc[stale_indices, "paper_id"].astype(str).tolist(),
            "details": "Shifted publication dates five years into the past.",
        }
    )

    # Rebuild structured embedding text after field-level mutations.
    working["text_for_embedding"] = working.apply(
        lambda row: "\n".join(
            [
                f"Title: {row['title']}",
                f"Authors: {row['authors_joined']}",
                f"Published: {row['published']}",
                f"Categories: {row['categories_joined']}",
                f"Summary: {row['summary']}",
            ]
        ),
        axis=1,
    )

    noise_indices = [ordered_indices[pos] for pos in (0, 2, 3) if pos < len(ordered_indices)]
    noise = " ZXQJ-9999 !!! NULL_VECTOR GARBAGE_TOKEN " * 8
    working.loc[noise_indices, "text_for_embedding"] = (
        working.loc[noise_indices, "text_for_embedding"].astype(str) + noise
    )
    actions.append(
        {
            "scenario": "inject_text_noise",
            "affected_count": len(noise_indices),
            "paper_ids": working.loc[noise_indices, "paper_id"].astype(str).tolist(),
            "details": "Appended repeated meaningless tokens to embedding text.",
        }
    )

    duplicate_count = original_rows - len(working)
    duplicate_source = working.iloc[:duplicate_count].copy(deep=True)
    working = pd.concat([working, duplicate_source], ignore_index=True)
    actions.append(
        {
            "scenario": "duplicate_rows",
            "affected_count": duplicate_count,
            "paper_ids": duplicate_source["paper_id"].astype(str).tolist(),
            "details": "Appended exact duplicate rows to restore the original row count.",
        }
    )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "input_rows": original_rows,
        "output_rows": int(len(working)),
        "scenario_count": len(actions),
        "actions": actions,
    }
    write_json(output_log_path, payload)
    return working.reset_index(drop=True)
