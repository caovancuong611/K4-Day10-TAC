from __future__ import annotations

from datetime import datetime
from html import unescape
import re

import pandas as pd

from core.utils import normalize_whitespace
from ingestion.crossref import PaperRecord


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Normalize raw records into the canonical pre-embedding dataframe."""

    def clean_text(value: object) -> str:
        without_tags = re.sub(r"<[^>]+>", " ", unescape(str(value or "")))
        return normalize_whitespace(without_tags)

    run_timestamp = pd.Timestamp(run_date)
    if run_timestamp.tzinfo is not None:
        run_timestamp = run_timestamp.tz_convert("UTC").tz_localize(None)
    run_day = run_timestamp.normalize()

    rows: list[dict[str, object]] = []
    for record in records:
        paper_id = clean_text(record.paper_id).lower()
        title = clean_text(record.title)
        if not paper_id or not title:
            continue

        summary = clean_text(record.summary)
        authors = list(dict.fromkeys(clean_text(value) for value in record.authors if clean_text(value)))
        categories = list(
            dict.fromkeys(clean_text(value) for value in record.categories if clean_text(value))
        )
        published = pd.to_datetime(record.published, errors="coerce", utc=True)
        updated = pd.to_datetime(record.updated, errors="coerce", utc=True)
        if pd.isna(published):
            continue

        published_day = published.tz_convert("UTC").tz_localize(None).normalize()
        updated_day = (
            updated.tz_convert("UTC").tz_localize(None).normalize()
            if not pd.isna(updated)
            else published_day
        )
        authors_joined = ", ".join(authors) or "Unknown"
        categories_joined = ", ".join(categories) or "Uncategorized"
        published_iso = published_day.date().isoformat()
        text_for_embedding = "\n".join(
            [
                f"Title: {title}",
                f"Authors: {authors_joined}",
                f"Published: {published_iso}",
                f"Categories: {categories_joined}",
                f"Summary: {summary}",
            ]
        )
        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "categories": categories,
                "primary_category": clean_text(record.primary_category) or categories_joined.split(",", 1)[0],
                "published": published_iso,
                "updated": updated_day.date().isoformat(),
                "age_days": int((run_day - published_day).days),
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "summary_chars": len(summary),
                "text_for_embedding": text_for_embedding,
                "abs_url": clean_text(record.abs_url),
                "pdf_url": clean_text(record.pdf_url),
                "comment": clean_text(record.comment),
            }
        )

    columns = [
        "paper_id", "title", "summary", "authors", "categories", "primary_category",
        "published", "updated", "age_days", "authors_joined", "categories_joined",
        "summary_chars", "text_for_embedding", "abs_url", "pdf_url", "comment",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows, columns=columns)
    df = df.drop_duplicates(subset=["paper_id"], keep="first")
    return df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
