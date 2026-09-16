import asyncio
import re
import time
from typing import Dict, List, Optional

# Chroma's telemetry stack imports LogData from opentelemetry.sdk._logs in some versions;
# older/newer opentelemetry builds omit it, which can break startup. Patch in a stub
# before importing chromadb to keep the service bootable.
try:  # pragma: no cover - defensive compatibility shim
    import opentelemetry.sdk._logs as _otel_logs

    if not hasattr(_otel_logs, "LogData"):
        class _LogData:  # minimal placeholder
            pass

        _otel_logs.LogData = _LogData
except Exception:
    pass

import chromadb

from app.config import get_settings
from app.logger import get_logger
from app.utils.embedding_utils import get_embedding

logger = get_logger(__name__)
settings = get_settings()

# Single persistent client shared across the app
_client = chromadb.PersistentClient(path=settings.chroma_dir)




_SAFE_PATTERN = re.compile(r"[^a-zA-Z0-9_-]")


def _slugify(user_id: str) -> str:
    """Sanitize user identifier for collection names."""
    return _SAFE_PATTERN.sub("_", user_id)


def docs_collection_name(user_id: str, tab_id: str | None = None) -> str:
    if tab_id:
        return f"docs_{_slugify(user_id)}_{_slugify(tab_id)}"
    return f"docs_{_slugify(user_id)}"


def meetings_collection_name(user_id: str) -> str:
    return f"meetings_{_slugify(user_id)}"


def legacy_docs_collection_name(user_id: str) -> str:
    """Legacy name used in earlier versions; kept for backwards compatibility."""
    return f"user_{_slugify(user_id)}"





def _get_or_create(name: str):
    return _client.get_or_create_collection(name=name)


def _maybe_get(name: str):
    try:
        return _client.get_collection(name=name)
    except Exception:
        return None


def _chunk_text(text: str, max_chars: int = 800, overlap: int = 120) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks


_SPEAKER_LINE_RE = re.compile(r"^\[Speaker (\d+)\]\s*(.*)$", re.MULTILINE)


def _chunk_transcript_by_speaker(text: str, max_chars: int = 800) -> list[str]:
    """
    Chunk a diarized transcript by speaker turns instead of blind character windows.

    Transcript lines look like ``[Speaker 2] some text``. Consecutive turns are
    grouped into windows of at most ``max_chars`` characters; each window keeps
    the speaker labels inline so the embedding carries speaker context. Falls
    back to :func:`_chunk_text` when no speaker markers are present.
    """
    if not text or not text.strip():
        return []

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not any(_SPEAKER_LINE_RE.match(ln) for ln in lines):
        return _chunk_text(text)

    # Build turn tuples (speaker, text), merging consecutive turns of the same speaker.
    turns: list[tuple[str, str]] = []
    current_speaker: str | None = None
    buffer: list[str] = []
    for line in lines:
        m = _SPEAKER_LINE_RE.match(line)
        if m:
            if current_speaker is not None and buffer:
                turns.append((current_speaker, " ".join(buffer).strip()))
                buffer = []
            current_speaker = f"Speaker {m.group(1)}"
            buffer.append(m.group(2))
        else:
            # Continuation line (no marker) — keep in the current turn.
            if current_speaker is None:
                current_speaker = "Speaker ?"
            buffer.append(line)
    if current_speaker is not None and buffer:
        turns.append((current_speaker, " ".join(buffer).strip()))

    # Group turns into chunks <= max_chars, never splitting mid-turn.
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for speaker, body in turns:
        piece = f"[{speaker}] {body}"
        piece_len = len(piece) + 1  # +1 for joining space/newline
        # A single over-long turn is hard-split by character window.
        if piece_len > max_chars:
            if current:
                chunks.append("\n".join(current))
                current, current_len = [], 0
            for sub in _chunk_text(piece, max_chars=max_chars, overlap=80):
                chunks.append(sub)
            continue
        if current_len + piece_len > max_chars and current:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        current.append(piece)
        current_len += piece_len
    if current:
        chunks.append("\n".join(current))

    return [c for c in chunks if c.strip()]


async def ensure_user_collections(user_id: str, tab_id: str | None = None) -> None:
    """Create docs + meetings collections for a user (and tab) if missing."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: (
            _get_or_create(docs_collection_name(user_id, tab_id)),
            _get_or_create(meetings_collection_name(user_id)),
        ),
    )


def get_docs_collection(user_id: str, tab_id: str | None = None):
    """
    Return the docs collection for a user (and tab), falling back to the legacy name
    if it still contains data.
    """
    new_col = _get_or_create(docs_collection_name(user_id, tab_id))
    try:
        if new_col.count() > 0:
            return new_col
    except Exception:
        pass

    legacy = _maybe_get(legacy_docs_collection_name(user_id))
    if legacy:
        try:
            if legacy.count() > 0:
                return legacy
        except Exception:
            pass
    return new_col


def get_meetings_collection(user_id: str):
    return _get_or_create(meetings_collection_name(user_id))


async def clear_docs_collection(user_id: str, tab_id: str | None = None) -> None:
    """Delete docs collections (new + legacy) for a user; if tab_id is None, clear all tabs."""
    loop = asyncio.get_running_loop()

    def _delete():
        names = {
            docs_collection_name(user_id, tab_id),
            legacy_docs_collection_name(user_id),
        }
        if tab_id is None:
            try:
                for col in _client.list_collections():
                    if col.name.startswith(f"docs_{_slugify(user_id)}_"):
                        names.add(col.name)
            except Exception:
                pass
        for name in names:
            try:
                _client.delete_collection(name=name)
            except Exception:
                continue

    await loop.run_in_executor(None, _delete)




async def add_meeting_chunk_embedding(
    user_id: str,
    meeting_id: str,
    text: str,
    *,
    speaker: str | None = None,
    chunk_index: Optional[int] = None,
    created_at: Optional[float] = None,
) -> None:
    """Embed and store an individual meeting transcript chunk."""
    if settings.app_env == "test":
        return
    if not text or _is_degenerate(text):
        return

    loop = asyncio.get_running_loop()
    embedding = await loop.run_in_executor(None, get_embedding, text)

    ts = created_at if created_at is not None else time.time()
    chunk_id = f"{meeting_id}_{int(ts * 1000)}"
    metadata: Dict[str, str | int | float | None] = {
        "meeting_id": meeting_id,
        "user_id": user_id,
        "kind": "chunk",
        "chunk_index": chunk_index if chunk_index is not None else int(ts * 1000),
        "timestamp": ts,
    }
    if speaker:
        metadata["speaker"] = speaker

    collection = get_meetings_collection(user_id)
    await loop.run_in_executor(
        None,
        lambda: collection.upsert(
            ids=[chunk_id],
            documents=[text],
            embeddings=[embedding.tolist()],
            metadatas=[metadata],
        ),
    )


async def add_meeting_summary_embedding(
    user_id: str, meeting_id: str, summary_text: str
) -> None:
    """Embed and store the final meeting summary."""
    if settings.app_env == "test":
        return
    if not summary_text or _is_degenerate(summary_text):
        return

    loop = asyncio.get_running_loop()
    embedding = await loop.run_in_executor(None, get_embedding, summary_text)

    ts = time.time()
    collection = get_meetings_collection(user_id)
    await loop.run_in_executor(
        None,
        lambda: collection.upsert(
            ids=[f"{meeting_id}_final_summary"],
            documents=[summary_text],
            embeddings=[embedding.tolist()],
            metadatas=[
                {
                    "meeting_id": meeting_id,
                    "user_id": user_id,
                    "kind": "final_summary",
                    "timestamp": ts,
                }
            ],
        ),
    )


async def add_full_transcript_embeddings(
    user_id: str, meeting_id: str, transcript_text: str
) -> None:
    """
    Embed the full meeting transcript in chunks after the meeting ends.

    This is a safety net — individual chunks are embedded live during the meeting,
    but this guarantees complete coverage regardless of any dropped chunks.
    """
    if settings.app_env == "test":
        return
    if not transcript_text or not transcript_text.strip():
        return

    chunks = _chunk_transcript_by_speaker(transcript_text)
    # Guard against degenerate fragments ever reaching the store.
    chunks = [c for c in chunks if not _is_degenerate(c)]
    if not chunks:
        return

    loop = asyncio.get_running_loop()
    ts = time.time()
    collection = get_meetings_collection(user_id)

    for idx, chunk in enumerate(chunks):
        embedding = await loop.run_in_executor(None, get_embedding, chunk)
        await loop.run_in_executor(
            None,
            lambda c=chunk, e=embedding, i=idx: collection.upsert(
                ids=[f"{meeting_id}_full_{i}"],
                documents=[c],
                embeddings=[e.tolist()],
                metadatas=[
                    {
                        "meeting_id": meeting_id,
                        "user_id": user_id,
                        "kind": "full_transcript",
                        "chunk_index": i,
                        "timestamp": ts,
                    }
                ],
            ),
        )


# ── Hybrid retrieval (dense + BM25 keyword, fused with RRF) ──────────────────

_STOPWORDS = frozenset(
    """a an and are as at be but by for from has have how i in is it its of on or
    say said she he they that the their them then there these this to was we were
    what when where which who will with you your about into over after before""".split()
)

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_']+")

# Cap on the keyword-pass corpus scan so huge collections can't blow up memory.
_BM25_MAX_CORPUS = 5000


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens minus stopwords — used by the BM25 keyword pass."""
    return [
        tok for tok in _TOKEN_RE.findall(text.lower())
        if tok not in _STOPWORDS and len(tok) > 1
    ]


def _is_degenerate(text: str) -> bool:
    """
    True for fragments that carry no retrievable meaning — single characters,
    empty strings, or stopword-only blobs. Guards both ingestion and query
    assembly against the character-level junk that polluted some collections.
    """
    if not text or len(text.strip()) <= 2:
        return True
    return not _tokenize(text)


def _bm25_idf(doc_freq: int, n_docs: int) -> float:
    """Standard BM25 IDF with 0.5 smoothing, floored at 0."""
    import math

    return max(0.0, math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0))


def _bm25_scores(
    query: str,
    corpus_tokens: list[list[str]],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """
    Okapi BM25 over a pre-tokenized corpus. Returns one score per document.
    Pure-python so it adds no dependency; fine for personal-scale corpora.
    """
    n_docs = len(corpus_tokens)
    if n_docs == 0:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return [0.0] * n_docs

    doc_lens = [len(toks) for toks in corpus_tokens]
    avg_len = sum(doc_lens) / n_docs

    df: dict[str, int] = {}
    for toks in corpus_tokens:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1

    scores = [0.0] * n_docs
    for i, toks in enumerate(corpus_tokens):
        tf: dict[str, int] = {}
        for term in toks:
            tf[term] = tf.get(term, 0) + 1
        score = 0.0
        for term in query_tokens:
            freq = tf.get(term)
            if not freq:
                continue
            idf = _bm25_idf(df.get(term, 0), n_docs)
            denom = freq + k1 * (1 - b + b * doc_lens[i] / avg_len)
            score += idf * (freq * (k1 + 1)) / denom
        scores[i] = score
    return scores


def _rrf_fuse(ranked_lists: list[list[int]], k: int = 60, top_n: int = 10) -> list[int]:
    """
    Reciprocal Rank Fusion across ranked lists of indices.
    Returns fused indices ordered by score, best first.
    """
    fused: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, idx in enumerate(ranked):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(fused, key=lambda i: fused[i], reverse=True)[:top_n]


async def query_meetings(
    user_id: str,
    query: str,
    *,
    meeting_id: Optional[str] = None,
    after_ts: Optional[float] = None,
    before_ts: Optional[float] = None,
    n_results: int = 5,
) -> List[str]:
    """Semantic search over meeting transcripts/summaries with optional filters.

    Convenience wrapper around :func:`query_meetings_detailed` that returns only
    the chunk texts.
    """
    items = await query_meetings_detailed(
        user_id,
        query,
        meeting_id=meeting_id,
        after_ts=after_ts,
        before_ts=before_ts,
        n_results=n_results,
    )
    return [item["text"] for item in items]


async def query_meetings_detailed(
    user_id: str,
    query: str,
    *,
    meeting_id: Optional[str] = None,
    after_ts: Optional[float] = None,
    before_ts: Optional[float] = None,
    n_results: int = 5,
) -> List[dict]:
    """Hybrid semantic + keyword search over meeting transcripts/summaries.

    Dense (embedding) results from Chroma are fused with a BM25 keyword pass
    via Reciprocal Rank Fusion. Exact-match content (names, project codenames,
    budget figures) that embeddings miss gets recovered by the keyword pass.

    Returns dicts with keys ``text``, ``meeting_id`` and ``match``
    (``"hybrid"`` | ``"semantic"`` | ``"keyword"``).
    """
    if not query or not query.strip():
        return []

    collection = get_meetings_collection(user_id)
    total = collection.count()
    if total == 0:
        return []

    loop = asyncio.get_running_loop()

    where: Dict[str, object] = {}
    if meeting_id:
        where["meeting_id"] = meeting_id
    ts_filter: Dict[str, float] = {}
    if after_ts is not None:
        ts_filter["$gt"] = after_ts
    if before_ts is not None:
        ts_filter["$lt"] = before_ts
    if ts_filter:
        where["timestamp"] = ts_filter

    def _dense_pass() -> list[tuple[str, dict | None]]:
        try:
            query_embedding = get_embedding(query)
            results = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=min(max(n_results * 3, 12), max(1, total)),
                where=where or None,
            )
            docs = results.get("documents", [[]])[0] or []
            metas = results.get("metadatas", [[]])[0] or []
            return [
                (d, m) for d, m in zip(docs, metas) if not _is_degenerate(d)
            ]
        except Exception as exc:
            logger.warning("Meeting dense query failed: %s", exc)
            return []

    def _keyword_pass() -> list[tuple[str, dict | None]]:
        try:
            # Prefer a time-bounded window (recent 90 days) so the keyword scan
            # stays cheap on very large collections; fall back to a capped
            # full scan when the window has no data.
            kw_where = where or None
            cutoff = time.time() - 90 * 86400
            if kw_where:
                window_where = {"$and": [dict(kw_where), {"timestamp": {"$gte": cutoff}}]}
            else:
                window_where = {"timestamp": {"$gte": cutoff}}

            def _fetch(w):
                data = collection.get(
                    where=w, include=["documents", "metadatas"], limit=_BM25_MAX_CORPUS
                )
                docs: list[str] = []
                metas: list[dict | None] = []
                for batch_docs, batch_metas in zip(
                    data.get("documents", []) or [], data.get("metadatas", []) or []
                ):
                    for d, m in zip(batch_docs or [], batch_metas or []):
                        # Skip degenerate fragments (single chars, stopwords-only)
                        if not _is_degenerate(d):
                            docs.append(d)
                            metas.append(m)
                return docs, metas

            docs, metas = _fetch(window_where)
            if not docs:
                docs, metas = _fetch(kw_where)
            if not docs:
                return []
            corpus_tokens = [_tokenize(d) for d in docs]
            scores = _bm25_scores(query, corpus_tokens)
            ranked = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
            ranked = [i for i in ranked if scores[i] > 0.0][: max(n_results * 3, 12)]
            return [(docs[i], metas[i]) for i in ranked]
        except Exception as exc:
            logger.debug("Meeting keyword query failed: %s", exc)
            return []

    dense_pairs, keyword_pairs = await asyncio.gather(
        loop.run_in_executor(None, _dense_pass),
        loop.run_in_executor(None, _keyword_pass),
    )

    if not dense_pairs and not keyword_pairs:
        return []

    # Single-signal fallbacks keep behaviour sane when one pass finds nothing.
    if not keyword_pairs:
        return [
            {"text": d, "meeting_id": (m or {}).get("meeting_id"), "match": "semantic"}
            for d, m in dense_pairs[:n_results]
        ]
    if not dense_pairs:
        return [
            {"text": d, "meeting_id": (m or {}).get("meeting_id"), "match": "keyword"}
            for d, m in keyword_pairs[:n_results]
        ]

    # Fuse: dense is the primary signal; keyword rescues exact matches.
    fused_idx = _rrf_fuse(
        [list(range(len(dense_pairs))), list(range(len(keyword_pairs)))],
        top_n=max(n_results, 10),
    )

    # Deduplicate identical texts (both passes can surface the same chunk).
    seen: set[str] = set()
    items: List[dict] = []
    for idx in fused_idx:
        if idx < len(dense_pairs):
            text, meta = dense_pairs[idx]
            match = "hybrid"
        else:
            text, meta = keyword_pairs[idx - len(dense_pairs)]
            match = "keyword"
        if text in seen:
            continue
        seen.add(text)
        items.append(
            {
                "text": text,
                "meeting_id": (meta or {}).get("meeting_id"),
                "match": match,
            }
        )
        if len(items) >= n_results:
            break
    return items


def delete_meeting_embeddings(user_id: str, meeting_id: str) -> None:
    """Remove all embeddings for a specific meeting."""
    collection = get_meetings_collection(user_id)
    try:
        ids = collection.get(where={"meeting_id": meeting_id}).get("ids", [])
        if ids:
            collection.delete(ids=ids)
    except Exception as exc:
        logger.warning("Failed to delete meeting embeddings for %s/%s: %s", user_id, meeting_id, exc)


def prune_old_meeting_embeddings(retention_days: int) -> None:
    """Delete meeting embeddings older than retention window across all users."""
    cutoff_ts = time.time() - retention_days * 86400
    try:
        for col in _client.list_collections():
            if not col.name.startswith("meetings_"):
                continue
            try:
                col_ref = _client.get_collection(col.name)
                data = col_ref.get(where={"timestamp": {"$lt": cutoff_ts}})
                ids = data.get("ids", [])
                if ids:
                    col_ref.delete(ids=ids)
            except Exception as exc:
                logger.debug("Prune failed for collection %s: %s", col.name, exc)
    except Exception as exc:
        logger.debug("Meeting embedding retention sweep failed: %s", exc)
