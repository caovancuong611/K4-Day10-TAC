from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from html import unescape
from pathlib import Path
import re
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Convert a Crossref response into normalized, serializable records.

    Crossref fields are not completely uniform: titles can be strings or lists,
    and dates can come from several objects.  This parser deliberately accepts
    those variants so the offline snapshot and live API use exactly one path.
    """

    def clean_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            value = " ".join(str(part) for part in value if part is not None)
        # Abstracts commonly contain JATS tags and HTML entities.
        without_tags = re.sub(r"<[^>]+>", " ", unescape(str(value)))
        return normalize_whitespace(without_tags)

    def normalize_doi(value: Any) -> str:
        doi = normalize_whitespace(str(value or "")).lower()
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.IGNORECASE)
        return doi.strip().rstrip(".")

    def date_from_parts(value: Any) -> str:
        try:
            parts = value.get("date-parts", [[]])[0]
            if not parts:
                return ""
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 1
            day = int(parts[2]) if len(parts) > 2 else 1
            return date(year, month, day).isoformat()
        except (AttributeError, IndexError, TypeError, ValueError):
            return ""

    def parse_date(item: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = item.get(key)
            parsed = date_from_parts(value)
            if parsed:
                return parsed
            if isinstance(value, dict):
                timestamp = value.get("date-time")
                if timestamp:
                    try:
                        return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).date().isoformat()
                    except ValueError:
                        pass
        return ""

    items = payload.get("message", {}).get("items", [])
    if not isinstance(items, list):
        raise ValueError("Invalid Crossref payload: message.items must be a list.")

    records: list[PaperRecord] = []
    seen_dois: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        paper_id = normalize_doi(item.get("DOI"))
        title = clean_text(item.get("title"))
        if not paper_id or not title or paper_id in seen_dois:
            continue

        authors: list[str] = []
        for author in item.get("author") or []:
            if not isinstance(author, dict):
                continue
            name = clean_text(
                " ".join(
                    part
                    for part in (author.get("given"), author.get("family"))
                    if part
                )
                or author.get("name")
                or author.get("literal")
            )
            if name:
                authors.append(name)

        categories = [clean_text(subject) for subject in (item.get("subject") or [])]
        categories = list(dict.fromkeys(category for category in categories if category))
        published = parse_date(
            item,
            ("published", "published-print", "published-online", "issued", "created"),
        )
        updated = parse_date(item, ("deposited", "indexed", "created")) or published
        if not published:
            # age_days cannot be computed reliably without a publication date.
            continue

        abs_url = clean_text(item.get("URL")) or f"https://doi.org/{paper_id}"
        pdf_url = ""
        for link in item.get("link") or []:
            if not isinstance(link, dict):
                continue
            content_type = str(link.get("content-type", "")).lower()
            if "pdf" in content_type or str(link.get("URL", "")).lower().endswith(".pdf"):
                pdf_url = clean_text(link.get("URL"))
                break
        pdf_url = pdf_url or abs_url

        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=clean_text(item.get("abstract")),
                authors=authors,
                categories=categories,
                primary_category=categories[0] if categories else "Uncategorized",
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=f"Crossref record {paper_id}",
            )
        )
        seen_dois.add(paper_id)
    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Load Crossref records in live/offline mode and preserve raw lineage.

    By default the checked-in snapshot is used.  With ``REFRESH_SOURCE=1`` the
    live API is attempted with retries; any HTTP/network/JSON failure falls back
    to the snapshot so a lab run remains reproducible offline.
    """
    snapshot_path = settings.paths.raw_api_response
    payload: dict[str, Any] | None = None

    if settings.refresh_source:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=retry))
        try:
            response = session.get(
                "https://api.crossref.org/works",
                params={
                    "query": settings.source_query,
                    "filter": settings.source_filter,
                    "rows": settings.max_results,
                },
                headers={"User-Agent": "day10-data-observability-lab/1.0 (mailto:student@example.com)"},
                timeout=(5, 30),
            )
            response.raise_for_status()
            candidate = response.json()
            # Parse before replacing the known-good offline snapshot.
            if not parse_crossref_payload(candidate):
                raise ValueError("Crossref returned no valid records.")
            payload = candidate
            write_json(snapshot_path, payload)
        except (requests.RequestException, ValueError, TypeError):
            payload = None

    if payload is None:
        if not snapshot_path.exists():
            raise RuntimeError(
                "Crossref is unavailable and the offline snapshot is missing: "
                f"{snapshot_path}"
            )
        payload = read_json(snapshot_path)

    records = parse_crossref_payload(payload)
    if not records:
        raise ValueError("No valid Crossref records could be parsed.")
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load a parsed raw snapshot and validate it against ``PaperRecord``."""
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Raw records file must contain a JSON list: {path}")

    records: list[PaperRecord] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Raw record at index {index} is not an object.")
        try:
            records.append(PaperRecord(**item))
        except TypeError as exc:
            raise ValueError(f"Raw record at index {index} has an invalid schema: {exc}") from exc
    return records
