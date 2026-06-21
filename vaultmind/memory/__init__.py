"""
vaultmind/memory/__init__.py — Redis vector memory using RedisVL + RediSearch.

Provides semantic search over vault nodes so the Connector can find related
nodes beyond simple keyword/title heuristics.

Index schema:
  - node_id  (tag)   — the node basename, e.g. "2026-06-21-1432-supabase-rls"
  - title    (text)  — node title for BM25 fallback
  - node_type (tag)  — NodeType enum value
  - embedding (vector, FLAT, FLOAT32, dim=384) — sentence-transformers embedding

Uses "all-MiniLM-L6-v2" (384-dim, ~90MB, runs fully offline) via
sentence-transformers. Falls back gracefully if the model isn't installed.

Usage:
    from vaultmind.memory import VaultMemory
    mem = VaultMemory()          # connects to REDIS_URL env var
    mem.upsert(node_id, title, body, node_type)
    results = mem.search(query_text, k=5)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6380")
INDEX_NAME = "vaultmind:nodes"
VECTOR_DIM = 384  # all-MiniLM-L6-v2


@dataclass
class MemoryResult:
    node_id: str
    title: str
    node_type: str
    score: float  # cosine similarity, higher = more similar


class VaultMemory:
    """
    Redis vector store for vault nodes.

    Lazy-initialises the sentence-transformer model and the RedisVL index
    on first use so import is always fast.
    """

    def __init__(self, redis_url: str = REDIS_URL) -> None:
        self._redis_url = redis_url
        self._index: Optional[object] = None
        self._embedder: Optional[object] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Loaded sentence-transformer: all-MiniLM-L6-v2")
            except ImportError:
                logger.warning(
                    "sentence-transformers not installed — vector search disabled. "
                    "Install with: uv add sentence-transformers"
                )
        return self._embedder

    def _embed(self, text: str) -> list[float] | None:
        embedder = self._get_embedder()
        if embedder is None:
            return None
        vec = embedder.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def _get_index(self):
        if self._index is not None:
            return self._index

        try:
            from redisvl.index import SearchIndex  # type: ignore
            from redisvl.schema import IndexSchema  # type: ignore
        except ImportError:
            logger.error("redisvl not installed — cannot create vector index")
            return None

        schema = IndexSchema.from_dict({
            "index": {
                "name": INDEX_NAME,
                "prefix": "vaultmind:node:",
                "storage_type": "hash",
            },
            "fields": [
                {"name": "node_id",   "type": "tag"},
                {"name": "title",     "type": "text"},
                {"name": "node_type", "type": "tag"},
                {
                    "name": "embedding",
                    "type": "vector",
                    "attrs": {
                        "algorithm": "flat",
                        "datatype": "float32",
                        "dims": VECTOR_DIM,
                        "distance_metric": "cosine",
                    },
                },
            ],
        })

        index = SearchIndex(schema, redis_url=self._redis_url)
        try:
            index.connect()
            if not index.exists():
                index.create(overwrite=False)
                logger.info("Created RedisVL index: %s", INDEX_NAME)
            else:
                logger.info("RedisVL index already exists: %s", INDEX_NAME)
        except Exception as exc:
            logger.error("Failed to connect/create RedisVL index: %s", exc)
            return None

        self._index = index
        return self._index

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert(
        self,
        node_id: str,
        title: str,
        body: str,
        node_type: str = "decision",
    ) -> bool:
        """
        Index (or re-index) a vault node for vector search.

        Returns True if the upsert succeeded, False if vector search is
        unavailable (missing deps or Redis connectivity issue).
        """
        index = self._get_index()
        if index is None:
            return False

        embedding = self._embed(f"{title}\n\n{body}")
        if embedding is None:
            return False

        import struct
        embedding_bytes = struct.pack(f"{VECTOR_DIM}f", *embedding)

        key = f"vaultmind:node:{node_id}"
        data = {
            "node_id": node_id,
            "title": title,
            "node_type": node_type,
            "embedding": embedding_bytes,
        }

        try:
            index.client.hset(key, mapping=data)
            logger.debug("Upserted node into vector index: %s", node_id)
            return True
        except Exception as exc:
            logger.error("Failed to upsert node %s: %s", node_id, exc)
            return False

    def search(self, query: str, k: int = 5) -> list[MemoryResult]:
        """
        Find the k most semantically similar nodes to query.

        Returns an empty list if vector search is unavailable.
        """
        index = self._get_index()
        if index is None:
            return []

        embedding = self._embed(query)
        if embedding is None:
            return []

        try:
            from redisvl.query import VectorQuery  # type: ignore
            import struct

            embedding_bytes = struct.pack(f"{VECTOR_DIM}f", *embedding)

            query_obj = VectorQuery(
                vector=embedding_bytes,
                vector_field_name="embedding",
                return_fields=["node_id", "title", "node_type", "vector_distance"],
                num_results=k,
            )
            results = index.query(query_obj)
            return [
                MemoryResult(
                    node_id=r["node_id"],
                    title=r["title"],
                    node_type=r["node_type"],
                    score=1.0 - float(r.get("vector_distance", 1.0)),
                )
                for r in results
            ]
        except Exception as exc:
            logger.error("Vector search failed: %s", exc)
            return []

    def delete(self, node_id: str) -> None:
        """Remove a node from the vector index."""
        index = self._get_index()
        if index is None:
            return
        try:
            index.client.delete(f"vaultmind:node:{node_id}")
        except Exception as exc:
            logger.error("Failed to delete node %s from index: %s", node_id, exc)

    def close(self) -> None:
        """Disconnect from Redis."""
        if self._index is not None:
            try:
                self._index.disconnect()
            except Exception:
                pass
            self._index = None
