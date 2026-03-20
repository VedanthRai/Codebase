"""
CodeOracle — RAG Pipeline
Hybrid retrieval: semantic (embeddings) + keyword (BM25) + graph-expanded.
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger

import numpy as np
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

from core.models import CodeChunk, RetrievalResult, RepositoryContext, Language
from core.config import settings


# ─── Embedding Model ──────────────────────────────────────────────────────────

class EmbeddingModel:
    """Wraps sentence-transformers for code embedding."""

    _instance: Optional["EmbeddingModel"] = None

    def __init__(self):
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        self.model = SentenceTransformer(settings.embedding_model)

    @classmethod
    def get(cls) -> "EmbeddingModel":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def encode(self, texts: List[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


# ─── Vector Store ─────────────────────────────────────────────────────────────

class VectorStore:
    """ChromaDB-backed vector store per repository."""

    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self.collection_name = f"codeoracle_{repo_id[:32]}"
        self.client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.embedder = EmbeddingModel.get()

    def add_chunks(self, chunks: List[CodeChunk]) -> None:
        if not chunks:
            return

        # Batch processing
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]

            texts = [self._chunk_to_text(c) for c in batch]
            embeddings = self.embedder.encode(texts).tolist()
            ids = [c.chunk_id for c in batch]
            metadatas = [
                {
                    "file_path": c.file_path,
                    "chunk_type": c.chunk_type,
                    "name": c.name or "",
                    "language": c.language.value,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "dependencies": json.dumps(c.dependencies),
                }
                for c in batch
            ]

            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )

        logger.info(f"Added {len(chunks)} chunks to vector store for repo {self.repo_id}")

    def semantic_search(self, query: str, k: int = 8,
                        filter_language: Optional[Language] = None) -> List[Tuple[CodeChunk, float]]:
        query_embedding = self.embedder.encode_single(query).tolist()

        where = None
        if filter_language:
            where = {"language": filter_language.value}

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, self.collection.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        chunks_scores = []
        if not results["ids"][0]:
            return chunks_scores

        for idx, (doc_id, doc, meta, dist) in enumerate(zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            chunk = CodeChunk(
                chunk_id=doc_id,
                content=doc,
                file_path=meta["file_path"],
                chunk_type=meta["chunk_type"],
                name=meta.get("name") or None,
                start_line=meta.get("start_line", 0),
                end_line=meta.get("end_line", 0),
                language=Language(meta["language"]),
                dependencies=json.loads(meta.get("dependencies", "[]")),
            )
            score = 1.0 - dist  # cosine similarity
            chunks_scores.append((chunk, score))

        return chunks_scores

    def _chunk_to_text(self, chunk: CodeChunk) -> str:
        """Rich text representation for embedding."""
        parts = [f"[{chunk.chunk_type.upper()}]"]
        if chunk.name:
            parts.append(f"Name: {chunk.name}")
        parts.append(f"File: {chunk.file_path}")
        if chunk.metadata.get("docstring"):
            parts.append(f"Description: {chunk.metadata['docstring']}")
        parts.append(chunk.content)
        return "\n".join(parts)

    def count(self) -> int:
        return self.collection.count()


# ─── BM25 Keyword Index ───────────────────────────────────────────────────────

class BM25Index:
    """Keyword-based retrieval using BM25."""

    def __init__(self):
        self.chunks: List[CodeChunk] = []
        self.bm25: Optional[BM25Okapi] = None

    def build(self, chunks: List[CodeChunk]) -> None:
        self.chunks = chunks
        tokenized = [self._tokenize(c.content) for c in chunks]
        self.bm25 = BM25Okapi(tokenized)
        logger.info(f"BM25 index built with {len(chunks)} chunks")

    def search(self, query: str, k: int = 8) -> List[Tuple[CodeChunk, float]]:
        if not self.bm25 or not self.chunks:
            return []
        tokens = self._tokenize(query)
        scores = self.bm25.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][:k]
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((self.chunks[idx], float(scores[idx])))
        return results

    def _tokenize(self, text: str) -> List[str]:
        import re
        # Split on non-alphanumeric, lowercase, filter short tokens
        tokens = re.sub(r'[^a-zA-Z0-9_]', ' ', text).lower().split()
        return [t for t in tokens if len(t) > 2]


# ─── Hybrid Retriever ─────────────────────────────────────────────────────────

class HybridRetriever:
    """
    Combines semantic + keyword retrieval with graph-based expansion.
    Uses Reciprocal Rank Fusion (RRF) for score merging.
    """

    def __init__(self, repo_id: str):
        self.vector_store = VectorStore(repo_id)
        self.bm25 = BM25Index()
        self.repo_context: Optional[RepositoryContext] = None

    def index(self, chunks: List[CodeChunk], context: RepositoryContext) -> None:
        """Index chunks and build BM25."""
        self.vector_store.add_chunks(chunks)
        self.bm25.build(chunks)
        self.repo_context = context
        self.all_chunks = chunks

    def retrieve(self, query: str, k: int = None) -> RetrievalResult:
        """Hybrid retrieval with graph expansion."""
        k = k or settings.top_k_retrieval

        # 1. Semantic search
        semantic_results = self.vector_store.semantic_search(query, k=k * 2)

        # 2. Keyword search
        keyword_results = self.bm25.search(query, k=k * 2)

        # 3. Reciprocal Rank Fusion
        fused = self._rrf_fusion(semantic_results, keyword_results, k=k)

        # 4. Graph-based context expansion
        expanded = self._graph_expand(fused, budget=2)

        # Deduplicate
        seen_ids = set()
        final_chunks = []
        final_scores = []
        for chunk, score in expanded:
            if chunk.chunk_id not in seen_ids:
                seen_ids.add(chunk.chunk_id)
                final_chunks.append(chunk)
                final_scores.append(score)

        return RetrievalResult(
            chunks=final_chunks[:k],
            query_enhanced=query,
            retrieval_method="hybrid+graph",
            scores=final_scores[:k],
        )

    def _rrf_fusion(self, semantic: List[Tuple[CodeChunk, float]],
                    keyword: List[Tuple[CodeChunk, float]], k: int = 8,
                    rrf_k: int = 60) -> List[Tuple[CodeChunk, float]]:
        """Reciprocal Rank Fusion."""
        scores: Dict[str, float] = {}
        chunk_map: Dict[str, CodeChunk] = {}

        for rank, (chunk, _) in enumerate(semantic):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1.0 / (rrf_k + rank + 1)
            chunk_map[chunk.chunk_id] = chunk

        for rank, (chunk, _) in enumerate(keyword):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1.0 / (rrf_k + rank + 1)
            chunk_map[chunk.chunk_id] = chunk

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return [(chunk_map[cid], scores[cid]) for cid in sorted_ids[:k]]

    def _graph_expand(self, chunks_scores: List[Tuple[CodeChunk, float]],
                      budget: int = 2) -> List[Tuple[CodeChunk, float]]:
        """Add chunks for dependencies of retrieved chunks."""
        if not self.repo_context:
            return chunks_scores

        expanded = list(chunks_scores)
        existing_names = {c.name for c, _ in chunks_scores if c.name}
        base_score = min(s for _, s in chunks_scores) * 0.5 if chunks_scores else 0.1

        added = 0
        for chunk, _ in chunks_scores[:budget]:
            for dep_name in chunk.dependencies:
                if dep_name not in existing_names and added < budget * 3:
                    # Find chunk for this dependency
                    dep_chunk = self._find_chunk_by_name(dep_name)
                    if dep_chunk:
                        expanded.append((dep_chunk, base_score))
                        existing_names.add(dep_name)
                        added += 1

        return expanded

    def _find_chunk_by_name(self, name: str) -> Optional[CodeChunk]:
        if not hasattr(self, 'all_chunks'):
            return None
        for chunk in self.all_chunks:
            if chunk.name == name and chunk.chunk_type == "function":
                return chunk
        return None
