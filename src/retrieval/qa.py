from __future__ import annotations

from dataclasses import dataclass
import re

from core.config import Settings
from core.utils import first_sentence
from retrieval.index import LocalEmbeddingIndex, SearchResult


@dataclass(frozen=True)
class AnswerResult:
    question: str
    answer: str
    retrieved_doc_ids: list[str]
    retrieved_contexts: list[str]
    retrieved_titles: list[str]


def _extract_answer(question: str, top_result: SearchResult) -> str:
    lowered = question.lower()
    metadata = top_result.metadata
    if "who authored" in lowered or "list the authors" in lowered:
        return metadata["authors_joined"]
    if "when was" in lowered or "publication date" in lowered or "published on" in lowered:
        return metadata["published"]
    if "what categories" in lowered or "what category" in lowered:
        return metadata["categories_joined"]
    return first_sentence(metadata["summary"])


def answer_question(question: str, settings: Settings, index: LocalEmbeddingIndex, top_k: int | None = None) -> AnswerResult:
    title_matches = re.findall(r"'([^']+)'", question)
    exact_matches = [match for title in title_matches if (match := index.lookup(title))]
    retrieved = index.search(question, top_k=top_k)
    exact_results = [
        SearchResult(
            paper_id=exact["paper_id"],
            title=exact["title"],
            score=1.0,
            content=exact["content"],
            metadata=exact["metadata"],
        )
        for exact in exact_matches
    ]
    if exact_results:
        exact_ids = {item.paper_id for item in exact_results}
        deduped = exact_results + [item for item in retrieved if item.paper_id not in exact_ids]
        retrieved = deduped[: (top_k or settings.top_k)]
    if not retrieved:
        answer = "I don't know from the indexed corpus."
    elif "combine the findings" in question.lower() and len(exact_results) >= 2:
        answer = " ".join(
            f"{item.title}: {first_sentence(item.metadata['summary'])}"
            for item in exact_results[:2]
        )
    else:
        answer = _extract_answer(question, retrieved[0])
    return AnswerResult(
        question=question,
        answer=answer,
        retrieved_doc_ids=[item.paper_id for item in retrieved],
        retrieved_contexts=[item.content for item in retrieved],
        retrieved_titles=[item.title for item in retrieved],
    )
