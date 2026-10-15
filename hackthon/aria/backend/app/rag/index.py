import hashlib
from pathlib import Path
from typing import Any

from app.core import db
from app.core.config import get_settings
from app.core.llm import embed
from app.core.timeutil import utc_now_iso
from app.rag.loader import SUPPORTED_SUFFIXES, chunk_pages, document_title, load_pages
from app.rag.vectors import to_blob


def _doc_id(path: Path) -> str:
    stat = path.stat()
    return "doc_" + hashlib.sha1(f"{path.name}:{stat.st_size}".encode()).hexdigest()[:12]


async def ingest_document(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported file type {path.suffix}. Use PDF, Markdown or text.")
    doc_id = _doc_id(path)
    pages = load_pages(path)
    title = document_title(path, pages)
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError(f"No extractable text in {path.name}. Scanned PDFs need OCR before indexing.")
    headers = [f"{title} > {c.section} (p.{c.page_start})" for c in chunks]
    settings = get_settings()
    vectors: list[list[float] | None] = [None] * len(chunks)
    status = "lexical_only"
    if settings.has_api_key:
        vectors = await embed([f"{h}\n{c.text}" for h, c in zip(headers, chunks, strict=True)])
        status = "indexed"
    simulated = "SIMULATED" in path.name.upper()
    with db.transaction() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.execute(
            """INSERT INTO documents (id, title, source_path, kind, pages, chunk_count, simulated, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, title, str(path), path.suffix.lower().lstrip("."), len(pages), len(chunks), int(simulated), status, utc_now_iso()),
        )
        for chunk, header, vector in zip(chunks, headers, vectors, strict=True):
            conn.execute(
                """INSERT INTO chunks (id, doc_id, ordinal, page_start, page_end, section, text, context_header, embedding)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"{doc_id}_{chunk.ordinal:04d}",
                    doc_id,
                    chunk.ordinal,
                    chunk.page_start,
                    chunk.page_end,
                    chunk.section,
                    chunk.text,
                    header,
                    to_blob(vector) if vector else None,
                ),
            )
    from app.rag.retriever import invalidate_cache

    invalidate_cache()
    return {"doc_id": doc_id, "title": title, "pages": len(pages), "chunks": len(chunks), "status": status}


async def sync_manuals_folder() -> list[dict[str, Any]]:
    """Indexes new or changed files in data/manuals and upgrades lexical-only docs once an API key exists."""
    settings = get_settings()
    known = {row["id"]: row for row in db.query("SELECT id, status FROM documents")}
    results = []
    for path in sorted(settings.manuals_dir.iterdir()):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        existing = known.get(_doc_id(path))
        if existing and not (existing["status"] == "lexical_only" and settings.has_api_key):
            continue
        results.append(await ingest_document(path))
    return results


def list_documents() -> list[dict[str, Any]]:
    return db.query(
        "SELECT id, title, source_path, kind, pages, chunk_count, simulated, status, created_at FROM documents ORDER BY created_at DESC"
    )


def delete_document(doc_id: str) -> None:
    row = db.query_one("SELECT source_path FROM documents WHERE id = ?", (doc_id,))
    if row is None:
        raise KeyError(doc_id)
    db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    path = Path(row["source_path"])
    if path.exists() and path.parent == get_settings().manuals_dir:
        path.unlink()
    from app.rag.retriever import invalidate_cache

    invalidate_cache()
