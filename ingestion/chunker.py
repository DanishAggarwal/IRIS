"""Structure-aware document chunking for IRIS.

Splits cleaned page text into coherent retrieval units on heading, section,
and paragraph boundaries while preserving markdown tables, clause integrity,
and page-level provenance.

Target parameters:
- Target chunk size: ~500–800 tokens (~1,900–3,000 characters).
- Target overlap: ~75–100 tokens (~300–400 characters).
- Provenance: every chunk records exact start_page and end_page.
- Tables: kept intact as atomic blocks wherever possible.
"""

import re
from dataclasses import dataclass
from typing import Optional

CHUNKING_VERSION = "chunk-v1"
TARGET_MIN_TOKENS = 350
TARGET_MAX_TOKENS = 750
TARGET_OVERLAP_TOKENS = 85

# Regex to detect headings
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$")
_UPPERCASE_HEADING_RE = re.compile(
    r"^(?:[0-9]{1,2}(?:\.[0-9]{1,2})*\s+)?(?:COURSE\s+(?:OBJECTIVE|OUTCOME|HANDOUT|CONTENT|SCHEME)|UNIT\s+[0-9IVX]+|SYLLABUS|EVALUATION\s+SCHEME|TEXT\s+BOOKS?|REFERENCE\s+BOOKS?|SEMESTER\s+SCHEME|PROGRAMME\s+STRUCTURE|DEPARTMENT\s+OF\s+[A-Z\s&]+)[A-Z0-9\s:,-]*$",
    re.IGNORECASE,
)

# Regex to detect HTML table elements (case-insensitive)
_HTML_TABLE_OPEN_RE = re.compile(r"<table[\s>]", re.IGNORECASE)
_HTML_TABLE_CLOSE_RE = re.compile(r"</table\s*>", re.IGNORECASE)


def estimate_tokens(text: str) -> int:
    """Accurately estimate token count for English/technical text.

    Uses ~3.8 characters per token heuristic, checked against word count.
    """
    if not text:
        return 0
    char_estimate = int(len(text) / 3.8)
    word_estimate = int(len(text.split()) * 1.25)
    return max(1, max(char_estimate, word_estimate))


@dataclass
class StructuralBlock:
    """An atomic structural unit of text with page provenance."""
    text: str
    page_number: int
    is_heading: bool = False
    is_table: bool = False
    heading_title: Optional[str] = None

    @property
    def token_count(self) -> int:
        return estimate_tokens(self.text)


@dataclass
class ChunkOutput:
    """A fully assembled chunk ready for persistence and retrieval."""
    chunk_index: int
    chunk_text: str
    start_page: int
    end_page: int
    char_count: int
    token_count: int
    section_title: Optional[str] = None
    metadata: Optional[dict] = None
    chunking_version: str = CHUNKING_VERSION

    def to_dict(self) -> dict:
        return {
            "chunk_index": self.chunk_index,
            "chunk_text": self.chunk_text,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "char_count": self.char_count,
            "token_count": self.token_count,
            "section_title": self.section_title,
            "metadata": self.metadata or {},
            "chunking_version": self.chunking_version,
        }


def compute_page_spans(blocks: list[StructuralBlock]) -> list[dict[str, int]]:
    """Compute exact character spans for each page represented in the chunk blocks.

    For each page represented in a chunk, records:
      - page: original 1-based page number
      - char_start: zero-based inclusive character offset in the stored chunk_text
      - char_end: exclusive character offset in the stored chunk_text

    Offsets refer to the exact final chunk_text, including separators inserted
    between page blocks.
    """
    if not blocks:
        return []

    spans_by_page: dict[int, dict[str, int]] = {}
    current_offset = 0

    for b in blocks:
        block_len = len(b.text)
        block_start = current_offset
        block_end = current_offset + block_len

        p = b.page_number
        if p not in spans_by_page:
            spans_by_page[p] = {"page": p, "char_start": block_start, "char_end": block_end}
        else:
            # Extend existing span for this page (covers intermediate separators within the page)
            spans_by_page[p]["char_end"] = block_end

        # Account for "\n\n" separator between blocks in chunk_text
        current_offset = block_end + 2

    return sorted(spans_by_page.values(), key=lambda s: s["page"])


def extract_structural_blocks(page_number: int, page_text: str) -> list[StructuralBlock]:
    """Parse page text into atomic structural blocks (Markdown tables, HTML tables, headings, paragraphs)."""
    if not page_text or not page_text.strip():
        return []

    lines = page_text.split("\n")
    blocks: list[StructuralBlock] = []

    current_para_lines: list[str] = []
    current_table_lines: list[str] = []
    in_markdown_table = False
    in_html_table = False

    def flush_para():
        nonlocal current_para_lines
        if current_para_lines:
            para_text = "\n".join(current_para_lines).strip()
            if para_text:
                if estimate_tokens(para_text) > TARGET_MAX_TOKENS:
                    # Subdivide oversized paragraph on sentence boundaries
                    sentences = re.split(r"(?<=[.!?])\s+", para_text)
                    curr: list[str] = []
                    curr_tok = 0
                    for s in sentences:
                        st = estimate_tokens(s)
                        if (curr_tok + st) > TARGET_MAX_TOKENS and curr:
                            blocks.append(
                                StructuralBlock(text=" ".join(curr), page_number=page_number, is_heading=False)
                            )
                            curr = []
                            curr_tok = 0
                        curr.append(s)
                        curr_tok += st
                    if curr:
                        blocks.append(
                            StructuralBlock(text=" ".join(curr), page_number=page_number, is_heading=False)
                        )
                else:
                    blocks.append(
                        StructuralBlock(text=para_text, page_number=page_number, is_heading=False)
                    )
            current_para_lines = []

    def flush_table():
        nonlocal current_table_lines, in_markdown_table, in_html_table
        if current_table_lines:
            table_text = "\n".join(current_table_lines).strip()
            if table_text:
                blocks.append(
                    StructuralBlock(text=table_text, page_number=page_number, is_table=True)
                )
            current_table_lines = []
            in_markdown_table = False
            in_html_table = False

    for line in lines:
        stripped = line.strip()

        # 1. If currently inside an HTML table
        if in_html_table:
            current_table_lines.append(line)
            if _HTML_TABLE_CLOSE_RE.search(stripped):
                flush_table()
            continue

        # 2. Check if this line starts an HTML table (case-insensitive)
        if _HTML_TABLE_OPEN_RE.search(stripped):
            if in_markdown_table:
                flush_table()
            flush_para()
            in_html_table = True
            current_table_lines.append(line)
            if _HTML_TABLE_CLOSE_RE.search(stripped):
                flush_table()
            continue

        # 3. Markdown table detection
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            flush_para()
            in_markdown_table = True
            current_table_lines.append(line)
            continue
        elif in_markdown_table:
            flush_table()

        if not stripped:
            # Blank line: paragraph boundary
            flush_para()
            continue

        # Check if line is a heading
        md_match = _MARKDOWN_HEADING_RE.match(stripped)
        upper_match = _UPPERCASE_HEADING_RE.match(stripped)
        if md_match:
            flush_para()
            title = md_match.group(2).strip()
            blocks.append(
                StructuralBlock(
                    text=stripped,
                    page_number=page_number,
                    is_heading=True,
                    heading_title=title,
                )
            )
            continue
        elif upper_match and len(stripped) < 100:
            flush_para()
            blocks.append(
                StructuralBlock(
                    text=stripped,
                    page_number=page_number,
                    is_heading=True,
                    heading_title=stripped,
                )
            )
            continue

        current_para_lines.append(line)

    flush_table()
    flush_para()
    return blocks


def chunk_document_pages(
    pages: list[tuple[int, str]],
    document_metadata: Optional[dict] = None,
    target_min_tokens: int = TARGET_MIN_TOKENS,
    target_max_tokens: int = TARGET_MAX_TOKENS,
    target_overlap_tokens: int = TARGET_OVERLAP_TOKENS,
) -> list[ChunkOutput]:
    """Assemble cleaned pages into structure-aware, overlapping chunks.

    Args:
        pages:                 List of (page_number, cleaned_text) in ascending page order.
        document_metadata:     Optional metadata dictionary for document.
        target_min_tokens:     Minimum preferred token size before splitting on headings.
        target_max_tokens:     Upper limit for chunk token capacity.
        target_overlap_tokens: Target token count for overlapping context.

    Returns:
        List of ChunkOutput objects with precise start_page, end_page provenance.
    """
    # 1. Parse all pages into sequential structural blocks
    raw_blocks: list[StructuralBlock] = []
    for page_num, text in pages:
        raw_blocks.extend(extract_structural_blocks(page_num, text))

    if not raw_blocks:
        return []

    # Ensure no non-table block exceeds target_max_tokens
    all_blocks: list[StructuralBlock] = []
    for b in raw_blocks:
        if b.token_count > target_max_tokens and not b.is_table:
            sentences = re.split(r"(?<=[.!?])\s+", b.text)
            curr_parts: list[str] = []
            curr_tok = 0
            for s in sentences:
                st = estimate_tokens(s)
                if (curr_tok + st) > target_max_tokens and curr_parts:
                    all_blocks.append(
                        StructuralBlock(
                            text=" ".join(curr_parts),
                            page_number=b.page_number,
                            is_heading=b.is_heading,
                            heading_title=b.heading_title,
                        )
                    )
                    curr_parts = []
                    curr_tok = 0
                curr_parts.append(s)
                curr_tok += st
            if curr_parts:
                all_blocks.append(
                    StructuralBlock(
                        text=" ".join(curr_parts),
                        page_number=b.page_number,
                        is_heading=b.is_heading,
                        heading_title=b.heading_title,
                    )
                )
        else:
            all_blocks.append(b)

    chunks: list[ChunkOutput] = []
    current_blocks: list[StructuralBlock] = []
    current_tokens = 0
    active_section_title: Optional[str] = None
    chunk_index = 0

    def emit_chunk(blocks: list[StructuralBlock], section: Optional[str]) -> None:
        nonlocal chunk_index
        if not blocks:
            return

        chunk_text = "\n\n".join(b.text for b in blocks).strip()
        if not chunk_text:
            return

        start_p = min(b.page_number for b in blocks)
        end_p = max(b.page_number for b in blocks)
        c_tokens = estimate_tokens(chunk_text)

        meta = {}
        if document_metadata:
            meta["category"] = document_metadata.get("category")
            meta["labels"] = document_metadata.get("labels", [])

        has_tables = any(b.is_table for b in blocks)
        if has_tables:
            meta["has_table"] = True

        meta["page_spans"] = compute_page_spans(blocks)

        chunks.append(
            ChunkOutput(
                chunk_index=chunk_index,
                chunk_text=chunk_text,
                start_page=start_p,
                end_page=end_p,
                char_count=len(chunk_text),
                token_count=c_tokens,
                section_title=section,
                metadata=meta,
                chunking_version=CHUNKING_VERSION,
            )
        )
        chunk_index += 1

    def compute_overlap_blocks(blocks: list[StructuralBlock]) -> list[StructuralBlock]:
        """Select trailing blocks or sentences for overlap without exceeding target_overlap_tokens."""
        if not blocks:
            return []

        last_block = blocks[-1]
        if last_block.is_table or last_block.is_heading:
            return []

        # If the last block is within overlap budget, collect trailing blocks
        if last_block.token_count <= target_overlap_tokens * 1.25:
            overlap: list[StructuralBlock] = []
            tokens = 0
            for b in reversed(blocks):
                if b.is_table or b.is_heading:
                    break
                if (tokens + b.token_count) > (target_overlap_tokens * 1.5) and overlap:
                    break
                tokens += b.token_count
                overlap.insert(0, b)
            return overlap

        # If the last block is large, extract only trailing sentences for overlap
        sentences = re.split(r"(?<=[.!?])\s+", last_block.text)
        tail_sentences: list[str] = []
        tok = 0
        for s in reversed(sentences):
            st = estimate_tokens(s)
            tail_sentences.insert(0, s)
            tok += st
            if tok >= target_overlap_tokens:
                break

        if tail_sentences:
            return [
                StructuralBlock(
                    text=" ".join(tail_sentences),
                    page_number=last_block.page_number,
                    is_heading=False,
                )
            ]
        return []

    for block in all_blocks:
        b_tokens = block.token_count

        if block.is_heading and block.heading_title:
            active_section_title = block.heading_title

        # Check if we should split before adding this block:
        # A) Current chunk reached token ceiling:
        #    Normal ceiling is target_max_tokens.
        #    Allow up to 10% headroom (825 tokens for 750 target) only when current_blocks contains
        #    exactly one heading block and the immediately following block is its associated section body.
        ceiling = target_max_tokens
        if (
            len(current_blocks) == 1
            and current_blocks[0].is_heading
            and not block.is_heading
        ):
            ceiling = int(target_max_tokens * 1.10)

        reached_limit = (current_tokens + b_tokens) > ceiling
        is_natural_split = (current_tokens >= target_min_tokens) and block.is_heading

        if (reached_limit or is_natural_split) and current_blocks:
            emit_chunk(current_blocks, active_section_title)

            # Compute overlap blocks for continuity
            if not block.is_heading:
                current_blocks = compute_overlap_blocks(current_blocks)
                current_tokens = sum(b.token_count for b in current_blocks)
            else:
                # Heading boundary: start fresh without cross-section overlap
                current_blocks = []
                current_tokens = 0

        current_blocks.append(block)
        current_tokens += b_tokens

    # Flush final chunk
    if current_blocks:
        emit_chunk(current_blocks, active_section_title)

    return chunks
