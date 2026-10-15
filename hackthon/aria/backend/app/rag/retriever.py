from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.core import db
from app.core.config import get_settings
from app.core.llm import embed, structured
from app.rag.lexical import BM25, reciprocal_rank_fusion
from app.rag.vectors import cosine_scores, from_blob

RERANK_PROMPT = """You grade retrieved passages from industrial equipment manuals for a maintenance question.
Score each passage: 3 = directly answers or gives the procedure, 2 = clearly relevant, 1 = loosely related, 0 = irrelevant.
Judge only by passage content."""


class PassageScore(BaseModel):
    chunk_id: str
    score: int


class RerankResult(BaseModel):
    scores: list[PassageScore]


@dataclass
class _Corpus:
    rows: list[dict[str, Any]]
    bm25: BM25
    vectors: list[Any]


_corpus: _Corpus | None = None


def invalidate_cache() -> None:
    global _corpus
    _corpus = None


def _load() -> _Corpus:
    global _corpus
    if _corpus is None:
        rows = db.query(
            """SELECT c.id, c.doc_id, c.page_start, c.page_end, c.section, c.text, c.context_header, c.embedding,
                      d.title, d.simulated FROM chunks c JOIN documents d ON d.id = c.doc_id"""
        )
        _corpus = _Corpus(
            rows=rows,
            bm25=BM25([f"{r['context_header']} {r['text']}" for r in rows]),
            vectors=[from_blob(r["embedding"]) for r in rows],
        )
    return _corpus


async def search(query: str, top_k: int = 5, rerank: bool = True, candidates: int = 16) -> dict[str, Any]:
    corpus = _load()
    if not corpus.rows:
        return {"hits": [], "retrieval": {"mode": "empty", "note": "No manuals indexed. Add PDFs to data/manuals."}}
    settings = get_settings()
    lexical = corpus.bm25.scores(query)
    rankings = [[i for i in sorted(range(len(corpus.rows)), key=lambda i: -lexical[i]) if lexical[i] > 0]]
    mode = "lexical"
    dense_index = [i for i, v in enumerate(corpus.vectors) if v is not None]
    if settings.has_api_key and dense_index:
        query_vec = (await embed([query]))[0]
        dense = cosine_scores(query_vec, [corpus.vectors[i] for i in dense_index])
        order = sorted(range(len(dense_index)), key=lambda j: -dense[j])
        rankings.append([dense_index[j] for j in order])
        mode = "hybrid"
    fused = reciprocal_rank_fusion(rankings)
    shortlist = sorted(fused, key=lambda i: -fused[i])[:candidates]
    rerank_scores: dict[str, int] = {}
    if rerank and settings.has_api_key and shortlist:
        passages = "\n\n".join(
            f"[{corpus.rows[i]['id']}] {corpus.rows[i]['context_header']}\n{corpus.rows[i]['text'][:1200]}" for i in shortlist
        )
        result, _ = await structured(
            model=settings.fast_model,
            instructions=RERANK_PROMPT,
            input_text=f"Question: {query}\n\nPassages:\n{passages}",
            schema=RerankResult,
        )
        rerank_scores = {s.chunk_id: s.score for s in result.scores}
        mode += "+rerank"
        shortlist = [i for i in shortlist if rerank_scores.get(corpus.rows[i]["id"], 0) >= 1]
        shortlist.sort(key=lambda i: (-rerank_scores.get(corpus.rows[i]["id"], 0), -fused[i]))
    hits = []
    for i in shortlist[:top_k]:
        row = corpus.rows[i]
        pages = f"p.{row['page_start']}" if row["page_start"] == row["page_end"] else f"pp.{row['page_start']}-{row['page_end']}"
        hits.append(
            {
                "chunk_id": row["id"],
                "doc_id": row["doc_id"],
                "document": row["title"],
                "section": row["section"],
                "pages": pages,
                "citation": f"{row['title']} — {row['section']} ({pages})",
                "excerpt": row["text"][:1400],
                "rrf_score": round(fused[i], 4),
                "rerank_score": rerank_scores.get(row["id"]),
                "simulated_document": bool(row["simulated"]),
            }
        )
    return {"hits": hits, "retrieval": {"mode": mode, "candidates": len(fused), "corpus_chunks": len(corpus.rows)}}
