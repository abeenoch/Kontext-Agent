"""Unit tests for hybrid retrieval helpers and speaker-turn chunking."""
import pytest

from app.services.vector_store import (
    _bm25_scores,
    _chunk_transcript_by_speaker,
    _rrf_fuse,
    _tokenize,
)


class TestSpeakerTurnChunking:
    def test_groups_turns_by_speaker(self):
        transcript = "\n".join([
            "[Speaker 0] Hello team, let's start.",
            "[Speaker 1] Great, I have the budget numbers.",
            "[Speaker 0] Perfect, go ahead.",
        ])
        chunks = _chunk_transcript_by_speaker(transcript)
        assert len(chunks) == 1
        assert "[Speaker 0]" in chunks[0]
        assert "[Speaker 1]" in chunks[0]
        assert "budget numbers" in chunks[0]

    def test_respects_max_chars_never_splits_mid_turn(self):
        turns = []
        for i in range(10):
            turns.append(f"[Speaker {i % 2}] Turn {i} " + "word " * 40)
        transcript = "\n".join(turns)
        chunks = _chunk_transcript_by_speaker(transcript, max_chars=400)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c) <= 400
        # Every turn survives intact somewhere in the chunks.
        joined = "\n".join(chunks)
        for i in range(10):
            assert f"Turn {i}" in joined

    def test_long_single_turn_is_hard_split(self):
        transcript = "[Speaker 3] " + "long " * 500
        chunks = _chunk_transcript_by_speaker(transcript, max_chars=300)
        assert len(chunks) > 1
        assert all(len(c) <= 300 for c in chunks)

    def test_falls_back_without_speaker_markers(self):
        transcript = "Plain text without any speaker markers. " * 30
        chunks = _chunk_transcript_by_speaker(transcript)
        assert chunks
        assert all("[Speaker" not in c for c in chunks)

    def test_empty_input(self):
        assert _chunk_transcript_by_speaker("") == []
        assert _chunk_transcript_by_speaker("   \n  ") == []


class TestBM25:
    def test_exact_term_match_scores_highest(self):
        corpus = [
            _tokenize("the team discussed the roadmap for next quarter"),
            _tokenize("alice presented the Q3 budget review"),
            _tokenize("weather was nice during the offsite"),
        ]
        scores = _bm25_scores("Q3 budget review", corpus)
        assert scores[1] > scores[0]
        assert scores[1] > scores[2]
        assert scores[1] > 0.0

    def test_embeddings_miss_but_keywords_hit(self):
        # Exact figures/codenames — classic dense-retrieval failure mode.
        corpus = [
            _tokenize("we agreed the launch is on track"),
            _tokenize("internal codename is Project Zephyr-7, budget 42,000"),
        ]
        scores = _bm25_scores("Zephyr-7 42,000", corpus)
        assert scores[1] > 0.0
        assert scores[0] == 0.0

    def test_stopwords_only_query_scores_zero(self):
        corpus = [_tokenize("some content here"), _tokenize("other content")]
        assert all(s == 0.0 for s in _bm25_scores("the was is", corpus))

    def test_empty_corpus(self):
        assert _bm25_scores("anything", []) == []


class TestRRF:
    def test_items_in_both_lists_rank_first(self):
        fused = _rrf_fuse([[0, 1, 2], [1, 0, 3]], top_n=4)
        # 0 and 1 appear in both lists → should outrank 2 and 3.
        assert set(fused[:2]) == {0, 1}

    def test_respects_top_n(self):
        fused = _rrf_fuse([[0, 1, 2, 3], [4, 5]], top_n=3)
        assert len(fused) == 3

    def test_single_list_preserves_order(self):
        fused = _rrf_fuse([[5, 2, 9]], top_n=10)
        assert fused == [5, 2, 9]

    def test_empty_lists(self):
        assert _rrf_fuse([[], []], top_n=5) == []


class TestTokenize:
    def test_lowercases_and_strips_stopwords(self):
        toks = _tokenize("The Q3 Budget REVIEW was discussed")
        assert "q3" in toks and "budget" in toks and "review" in toks
        assert "the" not in toks and "was" not in toks

    def test_keeps_numbers_and_codenames(self):
        toks = _tokenize("Project Zephyr-7 costs 42,000")
        assert "zephyr" in toks and ("7" in toks or "42" in toks or "000" in toks)

    def test_empty_string(self):
        assert _tokenize("") == []


class TestHybridEndToEnd:
    """Integration: fused query pipeline against an in-memory Chroma-like store."""

    class FakeCollection:
        """Implements the subset of the Chroma API that the query paths use."""

        def __init__(self, docs):
            self.docs = list(docs)  # list of (id, text, metadata)

        @staticmethod
        def _match(meta, where):
            if not where:
                return True
            for key, cond in where.items():
                if key == "$and":
                    if not all(
                        TestHybridEndToEnd.FakeCollection._match(meta, sub) for sub in cond
                    ):
                        return False
                elif isinstance(cond, dict):
                    v = meta.get(key)
                    for op, val in cond.items():
                        if op == "$gte" and not (v is not None and v >= val):
                            return False
                        if op == "$gt" and not (v is not None and v > val):
                            return False
                        if op == "$lt" and not (v is not None and v < val):
                            return False
                else:
                    if meta.get(key) != cond:
                        return False
            return True

        def count(self):
            return len(self.docs)

        def query(self, query_embeddings=None, n_results=3, where=None, **_kw):
            import numpy as np

            qv = np.array(query_embeddings[0])
            hits = [
                (d, m)
                for (_id, d, m) in self.docs
                if self._match(m, where)
            ]
            scored = []
            for d, m in hits:
                dv = np.array(embed_fn(d))
                denom = (np.linalg.norm(qv) * np.linalg.norm(dv)) or 1.0
                scored.append((float(np.dot(qv, dv) / denom), d, m))
            scored.sort(key=lambda t: -t[0])
            top = scored[:n_results]
            return {
                "documents": [[t[1] for t in top]],
                "metadatas": [[t[2] for t in top]],
            }

        def get(self, where=None, include=None, limit=None, **_kw):
            hits = [(d, m) for (_id, d, m) in self.docs if self._match(m, where)]
            if limit:
                hits = hits[:limit]
            return {
                "documents": [[d for d, _ in hits]],
                "metadatas": [[m for _, m in hits]],
            }

    @pytest.fixture()
    def store(self, monkeypatch):
        from app.services import vector_store as vs

        global embed_fn

        def embed_fn(text: str):
            import numpy as np

            vec = np.zeros(64, dtype=np.float32)
            text = text.lower()
            for i in range(len(text) - 3):
                vec[hash(text[i : i + 4]) % 64] += 1.0
            norm = np.linalg.norm(vec) or 1.0
            return vec / norm

        collections: dict = {}

        class FakeClient:
            def get_or_create_collection(self, name):
                return collections.setdefault(
                    name, TestHybridEndToEnd.FakeCollection([])
                )

        monkeypatch.setattr(vs, "_client", FakeClient())
        monkeypatch.setattr(vs, "get_embedding", embed_fn)
        return collections

    def test_codename_query_recovered_by_keyword_pass(self, store):
        import asyncio
        from app.services.vector_store import query_meetings_detailed

        col = store.setdefault(
            "meetings_testuser", TestHybridEndToEnd.FakeCollection([])
        )
        docs = [
            "[Speaker 0] Let's review the roadmap for the quarter ahead.",
            "[Speaker 1] Internal codename is Project Zephyr-7, budget is 42,000.",
            "[Speaker 2] The weather offsite was very productive this year.",
            "[Speaker 0] Agreed launching soon with the marketing team sync.",
        ]
        for i, d in enumerate(docs):
            col.docs.append(
                (f"m1_{i}", d, {"meeting_id": "m1", "timestamp": 1700000000.0 + i, "kind": "chunk"})
            )

        items = asyncio.run(
            query_meetings_detailed("testuser", "Zephyr-7 42,000 budget", n_results=3)
        )
        assert items, "expected results"
        joined = " ".join(it["text"] for it in items)
        assert "Zephyr-7" in joined
        # The keyword pass must rank the codename doc at/near the top.
        assert "Zephyr-7" in items[0]["text"] or "Zephyr-7" in items[1]["text"]

    def test_semantic_only_when_no_keyword_hits(self, store):
        import asyncio
        from app.services.vector_store import query_meetings_detailed

        col = store.setdefault(
            "meetings_testuser2", TestHybridEndToEnd.FakeCollection([])
        )
        docs = [
            "[Speaker 0] We discussed happy golden meadows in the countryside.",
            "[Speaker 1] The purple elephant danced gracefully at midnight.",
        ]
        for i, d in enumerate(docs):
            col.docs.append(
                (f"m2_{i}", d, {"meeting_id": "m2", "timestamp": 1700000000.0 + i, "kind": "chunk"})
            )
        items = asyncio.run(
            query_meetings_detailed("testuser2", "countryside meadows", n_results=2)
        )
        assert items
        assert all(it.get("match") in ("semantic", "hybrid", "keyword") for it in items)

    def test_meeting_filter_respected(self, store):
        import asyncio
        from app.services.vector_store import query_meetings_detailed

        col = store.setdefault(
            "meetings_testuser3", TestHybridEndToEnd.FakeCollection([])
        )
        for mid, text in [
            ("mA", "[Speaker 0] Zephyr-7 status update here"),
            ("mB", "[Speaker 1] Zephyr-7 mentioned in another meeting"),
        ]:
            col.docs.append(
                (mid, text, {"meeting_id": mid, "timestamp": 1700000000.0, "kind": "chunk"})
            )
        items = asyncio.run(
            query_meetings_detailed("testuser3", "Zephyr-7", meeting_id="mB", n_results=5)
        )
        assert items
        assert all(it["meeting_id"] == "mB" for it in items)

    def test_degenerate_single_char_docs_ignored(self, store):
        import asyncio
        from app.services.vector_store import query_meetings_detailed

        col = store.setdefault(
            "meetings_testuser4", TestHybridEndToEnd.FakeCollection([])
        )
        col.docs.append(
            ("junk", "[", {"meeting_id": "mJ", "timestamp": 1700000000.0})
        )
        col.docs.append(
            ("real", "[Speaker 0] Zephyr-7 budget talk",
             {"meeting_id": "mJ", "timestamp": 1700000001.0})
        )
        items = asyncio.run(
            query_meetings_detailed("testuser4", "Zephyr-7 budget", n_results=5)
        )
        assert items
        assert not any(it["text"] == "[" for it in items)
        assert any("Zephyr-7" in it["text"] for it in items)
