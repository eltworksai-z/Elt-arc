import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

HEADING = re.compile(
    r"^(#{1,4}\s+.+|(\d+(\.\d+){0,3})\s+[A-Z][^\n]{2,80}|[A-Z][A-Z0-9 /&\-]{4,70}|(Chapter|Section|Appendix)\s+\S+.*)$"
)
SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt"}


@dataclass
class Page:
    number: int
    text: str


@dataclass
class Chunk:
    ordinal: int
    page_start: int
    page_end: int
    section: str
    text: str


def load_pages(path: Path) -> list[Page]:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return [Page(i + 1, (page.extract_text() or "").replace("\x00", "")) for i, page in enumerate(reader.pages)]
    return [Page(1, path.read_text(encoding="utf-8", errors="replace"))]


def document_title(path: Path, pages: list[Page]) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            meta_title = PdfReader(str(path)).metadata.title
        except Exception:
            meta_title = None
        if meta_title and len(meta_title.strip()) > 3:
            return meta_title.strip()
    for line in (pages[0].text.splitlines() if pages else []):
        stripped = line.strip().lstrip("#").strip()
        if len(stripped) > 3:
            return stripped[:120]
    return path.stem


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    return 3 < len(stripped) < 90 and bool(HEADING.match(stripped)) and not stripped.endswith(".")


def chunk_pages(pages: list[Page], max_chars: int = 2200, overlap_chars: int = 300) -> list[Chunk]:
    """Structure-aware chunking: split on headings, pack paragraphs up to max_chars, carry a short overlap."""
    chunks: list[Chunk] = []
    section = "Introduction"
    buffer: list[str] = []
    start_page = pages[0].number if pages else 1
    current_page = start_page

    def flush(end_page: int) -> None:
        nonlocal buffer, start_page
        text = "\n".join(buffer).strip()
        if len(text) > 40:
            chunks.append(Chunk(len(chunks), start_page, end_page, section, text))
            tail = text[-overlap_chars:]
            buffer = [tail[tail.find(" ") + 1 :]] if overlap_chars and len(text) > overlap_chars else []
        else:
            buffer = []
        start_page = end_page

    for page in pages:
        current_page = page.number
        for raw in re.split(r"\n\s*\n|\n(?=#{1,4}\s)", page.text):
            block = raw.strip()
            if not block:
                continue
            first_line = block.splitlines()[0]
            if _is_heading(first_line):
                if buffer:
                    flush(current_page)
                    buffer = []
                section = first_line.strip().lstrip("#").strip()
                start_page = current_page
            if sum(len(b) for b in buffer) + len(block) > max_chars and buffer:
                flush(current_page)
            while len(block) > max_chars:
                buffer.append(block[:max_chars])
                flush(current_page)
                block = block[max_chars:]
            buffer.append(block)
    if buffer:
        flush(current_page)
    return chunks
