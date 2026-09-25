from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
import pandas as pd

from core.config import Settings
from core.utils import read_json, safe_slug, write_json
from retrieval.embeddings import MiniLMEmbeddings


@dataclass(frozen=True)
class SearchResult:
    paper_id: str
    title: str
    score: float
    content: str
    metadata: dict[str, Any]


class LocalEmbeddingIndex:
    def __init__(
        self,
        settings: Settings,
        collection_name: str | None = None,
        documents: list[dict[str, Any]] | None = None,
        persist_path: Path | None = None,
    ):
        self.settings = settings
        self.collection_name = collection_name or settings.baseline_collection_name
        self.documents = documents or []
        self.persist_path = persist_path or settings.paths.chroma_dir
        self.embedding_backend = "chroma"
        self.embedding_model = MiniLMEmbeddings(settings.embedding_model)
        self.client = chromadb.PersistentClient(path=str(self.persist_path))
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
        except Exception:
            self.collection = None
        self._refresh_lookup_maps()

    def _refresh_lookup_maps(self) -> None:
        self.documents_by_paper_id = {
            document["paper_id"].lower(): document for document in self.documents
        }
        self.documents_by_title = {
            document["title"].lower(): document for document in self.documents
        }

    @staticmethod
    def _build_documents(df: pd.DataFrame) -> list[dict[str, Any]]:
        records = df.to_dict(orient="records")
        documents: list[dict[str, Any]] = []
        for index, row in enumerate(records):
            documents.append(
                {
                    "record_id": f"{row['paper_id']}::{index}",
                    "paper_id": str(row["paper_id"]),
                    "title": str(row["title"]),
                    "content": str(row["text_for_embedding"]),
                    "metadata": {
                        "paper_id": str(row["paper_id"]),
                        "title": str(row["title"]),
                        "published": str(row["published"]),
                        "authors_joined": str(row["authors_joined"]),
                        "categories_joined": str(row["categories_joined"]),
                        "summary": str(row["summary"]),
                        "abs_url": str(row["abs_url"]),
                        "pdf_url": str(row["pdf_url"]),
                    },
                }
            )
        return documents

    @staticmethod
    def _derive_collection_name(settings: Settings, embeddings_output_path: Path | None) -> str:
        if embeddings_output_path is None:
            return settings.baseline_collection_name

        name_map = {
            settings.paths.embeddings_json.resolve(): settings.baseline_collection_name,
            settings.paths.corrupted_embeddings_json.resolve(): settings.corrupted_collection_name,
            settings.paths.repaired_embeddings_json.resolve(): settings.repaired_collection_name,
        }
        resolved_path = embeddings_output_path.resolve()
        if resolved_path in name_map:
            return name_map[resolved_path]
        return safe_slug(embeddings_output_path.stem)

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        settings: Settings,
        embeddings_output_path: Path | None = None,
        collection_name: str | None = None,
    ) -> "LocalEmbeddingIndex":
        collection_name = collection_name or cls._derive_collection_name(settings, embeddings_output_path)
        documents = cls._build_documents(df)
        if not documents:
            raise ValueError("Cannot build a vector index from an empty dataframe.")
        persist_path = settings.paths.chroma_dir
        persist_path.mkdir(parents=True, exist_ok=True)

        embedding_model = MiniLMEmbeddings(settings.embedding_model)
        client = chromadb.PersistentClient(path=str(persist_path))
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass
        collection = client.create_collection(
            name=collection_name,
            configuration={"hnsw": {"space": "cosine"}},
        )
        embeddings = embedding_model.embed_documents([document["content"] for document in documents])
        collection.add(
            ids=[document["record_id"] for document in documents],
            embeddings=embeddings,
            documents=[document["content"] for document in documents],
            metadatas=[document["metadata"] for document in documents],
        )

        manifest_path = embeddings_output_path or settings.paths.embeddings_json
        write_json(
            manifest_path,
            {
                "backend": "chroma",
                "embedding_model": settings.embedding_model,
                "persist_path": str(persist_path),
                "collection_name": collection_name,
                "documents": documents,
            },
        )
        return cls(
            settings=settings,
            collection_name=collection_name,
            documents=documents,
            persist_path=persist_path,
        )

    def build_from_clean(self) -> "LocalEmbeddingIndex":
        """Build this collection from the canonical clean JSON artifact."""
        if not self.settings.paths.clean_json.exists():
            raise FileNotFoundError(
                f"Clean dataset not found: {self.settings.paths.clean_json}. Run phase 1 cleaning first."
            )
        df = pd.read_json(self.settings.paths.clean_json)
        built = type(self).build(
            df,
            self.settings,
            embeddings_output_path=self.settings.paths.embeddings_json,
            collection_name=self.collection_name,
        )
        self.documents = built.documents
        self.persist_path = built.persist_path
        self.client = built.client
        self.collection = built.collection
        self._refresh_lookup_maps()
        return self

    @classmethod
    def load(cls, settings: Settings, embeddings_path: Path | None = None) -> "LocalEmbeddingIndex":
        payload = read_json(embeddings_path or settings.paths.embeddings_json)
        return cls(
            settings=settings,
            collection_name=payload["collection_name"],
            documents=payload["documents"],
            persist_path=Path(payload["persist_path"]),
        )

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        if self.collection is None:
            raise RuntimeError(
                f"Chroma collection '{self.collection_name}' does not exist. Build the index first."
            )
        query_embedding = self.embedding_model.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k or self.settings.top_k,
            include=["documents", "metadatas", "distances"],
        )
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        scored: list[SearchResult] = []
        for record_id, content, metadata, distance in zip(ids, documents, metadatas, distances, strict=False):
            if not record_id or not metadata or not content:
                continue
            scored.append(
                SearchResult(
                    paper_id=str(metadata["paper_id"]),
                    title=str(metadata["title"]),
                    score=max(0.0, 1.0 - float(distance or 0.0)),
                    content=str(content),
                    metadata=dict(metadata),
                )
            )
        return scored

    def semantic_search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        """Compatibility name used by the lab smoke-test command."""
        return self.search(query, top_k=top_k)

    def lookup(self, value: str) -> dict[str, Any] | None:
        needle = value.strip().lower()
        if needle in self.documents_by_paper_id:
            return self.documents_by_paper_id[needle]
        if needle in self.documents_by_title:
            return self.documents_by_title[needle]
        return None
