"""Embedding service with provider fallback.

1. OpenAI embeddings when OPENAI_API_KEY is set.
2. Deterministic local feature-hashing embedder otherwise (offline-safe).

Both produce fixed-dimension vectors so pgvector storage stays consistent.
"""
from __future__ import annotations

import hashlib
import math
import re

import numpy as np

from app.core.config import settings

_word_re = re.compile(r"[a-z0-9]{2,}")


class LocalHashingEmbeddings:
    """Feature hashing of word unigrams/bigrams + char trigrams → L2-normalized vector.
    Deterministic, dependency-free, good enough for merchant similarity."""

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def _bucket(self, token: str) -> tuple[int, float]:
        h = hashlib.md5(token.encode()).digest()
        idx = int.from_bytes(h[:4], "little") % self.dim
        sign = 1.0 if (h[4] & 1) else -1.0
        return idx, sign

    def _add(self, vec: np.ndarray, text: str, weight: float) -> None:
        for tok in _word_re.findall(text.lower()):
            idx, sign = self._bucket(tok)
            vec[idx] += sign * weight
            # bigram context handled by caller via prefixed tokens
        for i in range(len(text.lower()) - 2):
            idx, sign = self._bucket("#" + text.lower()[i : i + 3])
            vec[idx] += sign * 0.35

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = np.zeros(self.dim, dtype=np.float32)
            words = _word_re.findall(t.lower())
            for w in words:
                idx, sign = self._bucket(w)
                v[idx] += sign * 1.0
            for a, b in zip(words, words[1:]):
                idx, sign = self._bucket(f"{a}_{b}")
                v[idx] += sign * 0.6
            norm = float(np.linalg.norm(v))
            if norm > 0:
                v /= norm
            out.append(v.tolist())
        return out


_openai_client = None


def _get_openai():
    global _openai_client
    if not settings.openai_api_key:
        return None
    if _openai_client is None:
        try:
            from openai import AsyncOpenAI

            _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        except Exception:
            return None
    return _openai_client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = _get_openai()
    if client:
        try:
            resp = await client.embeddings.create(model=settings.embedding_model, input=texts)
            vectors = [d.embedding for d in resp.data]
            dim = len(vectors[0])
            if dim != settings.embedding_dim:
                vectors = [_fit_dim(v) for v in vectors]
            return vectors
        except Exception:
            pass  # fall through to local
    return LocalHashingEmbeddings(settings.embedding_dim).embed(texts)


def _fit_dim(v: list[float]) -> list[float]:
    d = settings.embedding_dim
    if len(v) >= d:
        return v[:d]
    return v + [0.0] * (d - len(v))


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))
