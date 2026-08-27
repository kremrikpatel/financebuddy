"""RAG over pgvector: knowledge doc ingestion, cosine retrieval, rerank-lite."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeDoc
from app.services.embeddings import embed_texts


async def ingest_document(db: AsyncSession, title: str, content: str,
                          user_id: uuid.UUID | None = None,
                          source_type: str = "guide",
                          chunk_size: int = 900,
                          meta: dict | None = None) -> int:
    """Chunk + embed + store. Returns number of chunks written."""
    chunks = _chunk_text(content, chunk_size)
    vectors = await embed_texts([c["text"] for c in chunks])
    count = 0
    for chunk, vec in zip(chunks, vectors):
        db.add(KnowledgeDoc(
            user_id=user_id, title=title,
            source_type=source_type,
            content=chunk["text"],
            embedding=vec,
            meta={**(meta or {}), **chunk["meta"]},
        ))
        count += 1
    await db.flush()
    return count


def _chunk_text(text: str, size: int) -> list[dict]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[dict] = []
    buf: list[str] = []
    length = 0
    start_para = 0
    for i, para in enumerate(paragraphs):
        if length + len(para) > size and buf:
            chunks.append({"text": "\n\n".join(buf),
                           "meta": {"chunk": len(chunks), "paras": f"{start_para}-{i - 1}"}})
            buf, length, start_para = [], 0, i
        buf.append(para)
        length += len(para)
    if buf:
        chunks.append({"text": "\n\n".join(buf),
                       "meta": {"chunk": len(chunks), "paras": f"{start_para}-"}})
    return chunks


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    if not a or not b:
        return 0.0
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(x * x for x in b)) or 1e-9
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


async def retrieve(db: AsyncSession, query: str, user_id: uuid.UUID,
                   top_k: int = 5, min_score: float = 0.25) -> list[dict]:
    """Global corpus + user docs, pgvector cosine via SQL ordering with python fallback."""
    qvec = (await embed_texts([query]))[0]
    try:
        rows = (await db.execute(
            select(KnowledgeDoc)
            .where((KnowledgeDoc.user_id.is_(None)) | (KnowledgeDoc.user_id == user_id))
            .order_by(KnowledgeDoc.embedding.cosine_distance(qvec))
            .limit(top_k * 4)
        )).scalars().all()
    except Exception:
        # Fallback for SQLite or environments without pgvector cosine_distance operator in SQL
        rows = (await db.execute(
            select(KnowledgeDoc)
            .where((KnowledgeDoc.user_id.is_(None)) | (KnowledgeDoc.user_id == user_id))
        )).scalars().all()

    results = []
    for r in rows:
        score = _cosine(qvec, r.embedding) if r.embedding is not None else 0.0
        if score >= min_score:
            results.append({
                "id": str(r.id), "title": r.title, "content": r.content[:1200],
                "score": round(float(score), 3), "source_type": r.source_type,
            })
    # rerank-lite: lexical overlap boost
    qlow = set(query.lower().split())
    results.sort(key=lambda d: d["score"] + 0.05 * len(qlow & set(d["content"].lower().split())) / max(len(qlow), 1),
                 reverse=True)
    return results[:top_k]


async def build_context(db: AsyncSession, query: str, user_id: uuid.UUID,
                        max_chars: int = 4000) -> tuple[str, list[str]]:
    docs = await retrieve(db, query, user_id)
    parts, titles = [], []
    used = 0
    for d in docs:
        if used + len(d["content"]) > max_chars:
            break
        parts.append(f"[{d['title']}] {d['content']}")
        titles.append(d["title"])
        used += len(d["content"])
    return ("\n\n".join(parts), titles) if parts else ("", [])
