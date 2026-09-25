from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, read_json, write_json


@dataclass(frozen=True)
class TestSet:
    samples: list[dict[str, Any]]

def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Create a deterministic five-type benchmark grounded in the dataframe."""
    required = {
        "paper_id", "title", "summary", "authors_joined", "published", "categories_joined"
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Cannot build test set; missing columns: {', '.join(missing)}")
    if len(df) < 6:
        raise ValueError("At least 6 clean papers are required to build the benchmark test set.")

    # Stable paper-id ordering keeps the benchmark fixed across repeated runs.
    rows = df.sort_values("paper_id").reset_index(drop=True)
    summary_row, authors_row, date_row, category_row, hop_a, hop_b = (
        rows.iloc[index] for index in range(6)
    )

    def sample(
        sample_id: str,
        question_type: str,
        question: str,
        ground_truth: str,
        doc_ids: list[str],
    ) -> dict[str, Any]:
        return {
            "id": sample_id,
            "type": question_type,
            # Kept for compatibility with the evaluation/reporting modules and
            # the original README schema.
            "question_type": question_type,
            "question": question,
            "ground_truth": ground_truth,
            "ground_truth_doc_ids": doc_ids,
        }

    multi_hop_truth = (
        f"{hop_a['title']}: {first_sentence(str(hop_a['summary']))} "
        f"{hop_b['title']}: {first_sentence(str(hop_b['summary']))}"
    )
    samples = [
        sample(
            "eval_001",
            "summary",
            f"What is the main research contribution of '{summary_row['title']}'?",
            first_sentence(str(summary_row["summary"])),
            [str(summary_row["paper_id"])],
        ),
        sample(
            "eval_002",
            "authors",
            f"Who authored the study '{authors_row['title']}'?",
            str(authors_row["authors_joined"]),
            [str(authors_row["paper_id"])],
        ),
        sample(
            "eval_003",
            "date",
            f"When was the study '{date_row['title']}' published?",
            str(date_row["published"]),
            [str(date_row["paper_id"])],
        ),
        sample(
            "eval_004",
            "category",
            f"What categories describe the paper '{category_row['title']}'?",
            str(category_row["categories_joined"]),
            [str(category_row["paper_id"])],
        ),
        sample(
            "eval_005",
            "multi_hop",
            (
                f"Combine the findings of '{hop_a['title']}' and '{hop_b['title']}'. "
                "What does each study contribute?"
            ),
            multi_hop_truth,
            [str(hop_a["paper_id"]), str(hop_b["paper_id"])],
        ),
    ]
    write_json(Path(output_path), samples)
    return samples


def load_or_create_test_set(
    df: pd.DataFrame,
    output_path,
    refresh: bool = False,
) -> TestSet:
    """Load a valid five-sample test set, otherwise rebuild it from clean data."""
    path = Path(output_path)
    samples: list[dict[str, Any]] | None = None
    if path.exists() and not refresh:
        payload = read_json(path)
        required = {"id", "type", "question", "ground_truth", "ground_truth_doc_ids"}
        available_ids = set(df["paper_id"].astype(str)) if "paper_id" in df else set()
        if (
            isinstance(payload, list)
            and len(payload) == 5
            and all(isinstance(item, dict) and required.issubset(item) for item in payload)
            and all(
                set(str(doc_id) for doc_id in item["ground_truth_doc_ids"]).issubset(available_ids)
                for item in payload
            )
        ):
            samples = [dict(item) for item in payload]
            for item in samples:
                item.setdefault("question_type", item["type"])
            write_json(path, samples)
    if samples is None:
        samples = build_test_set(df, path)
    return TestSet(samples=samples)
