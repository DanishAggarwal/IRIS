"""Conservative text cleaning and normalisation for IRIS.

Preserves institutional provenance, dates, codes, tables, bullet points,
headings, and clause numbers while eliminating anomalous whitespace, broken
hyphenation, and repetitive running headers/footers where safe.

Design rules:
- Non-destructive: raw extracted text is never overwritten.
- Conservative: when in doubt, keep text rather than risk removing meaning.
- Tables and structured markdown are strictly preserved.
"""

import re
from typing import Optional

CLEANING_VERSION = "clean-v1"

# Anomalous unicode spaces and invisible characters to standardise
_UNICODE_SPACE_TRANSLATION = str.maketrans({
    "\u00a0": " ",      # non-breaking space
    "\u2000": " ",      # en quad
    "\u2001": " ",      # em quad
    "\u2002": " ",      # en space
    "\u2003": " ",      # em space
    "\u2004": " ",      # three-per-em space
    "\u2005": " ",      # four-per-em space
    "\u2006": " ",      # six-per-em space
    "\u2007": " ",      # figure space
    "\u2008": " ",      # punctuation space
    "\u2009": " ",      # thin space
    "\u200a": " ",      # hair space
    "\u202f": " ",      # narrow no-break space
    "\u205f": " ",      # medium mathematical space
    "\u3000": " ",      # ideographic space
    "\u200b": "",       # zero-width space
    "\u200c": "",       # zero-width non-joiner
    "\u200d": "",       # zero-width joiner
    "\ufeff": "",       # zero-width no-break space (BOM)
    "\xad": "",         # soft hyphen
    "\r": "",           # carriage return (normalise to \n)
})

# Standardise fancy quote marks to standard quotes
_QUOTE_TRANSLATION = str.maketrans({
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "‚": "'",
    "„": '"',
    "′": "'",
    "″": '"',
})

# Bullet point normalisation (keep list structure readable)
_BULLET_RE = re.compile(r"^[\t ]*[\u2022\u2023\u25e6\u2043\u2219\u25cf\u25aa\u25ab\u25b8\u25c6]\s*", re.MULTILINE)

# De-hyphenation across line breaks: only join word-characters of at least 3 letters
# e.g., "implemen-\ntation" -> "implementation"
# Does NOT match dates/ranges like "2023-\n2024" or code prefixes like "PEC-\nCSE"
_DEHYPHEN_RE = re.compile(r"([a-zA-Z]{3,})-\n([a-zA-Z]{3,})")

# Pattern for running page number footers/headers:
# "Page 12", "Page 12 of 55", "- 12 -", "12 / 55"
_PAGE_NUM_ONLY_RE = re.compile(
    r"^[\t ]*(?:page[\t ]+\d+(?:[\t ]*(?:of|/|–|-)[\t ]*\d+)?|[-–—]\s*\d+\s*[-–—]|\d+[\t ]*/[\t ]*\d+)[\t ]*$",
    re.IGNORECASE,
)


def normalise_unicode(text: str) -> str:
    """Normalise invisible characters, anomalous spaces, and fancy quotes."""
    if not text:
        return ""
    text = text.translate(_UNICODE_SPACE_TRANSLATION)
    text = text.translate(_QUOTE_TRANSLATION)
    return text


def repair_line_break_hyphenation(text: str) -> str:
    """Repair words broken across line breaks by hyphens.

    Preserves code tokens, date ranges, and clause numbers.
    """
    return _DEHYPHEN_RE.sub(r"\1\2", text)


def normalise_bullets(text: str) -> str:
    """Standardise assorted unicode bullet glyphs to markdown bullet '-'."""
    return _BULLET_RE.sub("- ", text)


def is_table_row(line: str) -> bool:
    """Check if a line is part of a markdown table."""
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def normalise_horizontal_whitespace(line: str) -> str:
    """Collapse excess spaces within a line while preserving markdown tables."""
    if is_table_row(line):
        # In table rows, preserve column delimiters; trim outer padding only
        return line.strip()
    # Otherwise collapse multiple horizontal spaces to single space
    # (preserve leading whitespace up to 4 spaces for indented lists)
    indent_match = re.match(r"^([ ]{1,4})", line)
    indent = indent_match.group(1) if indent_match else ""
    collapsed = re.sub(r"[ \t]+", " ", line.strip())
    return (indent + collapsed) if collapsed else ""


def strip_running_page_numbers(lines: list[str], page_number: Optional[int] = None) -> list[str]:
    """Strip standalone page number lines at the extreme top or bottom only."""
    if not lines:
        return lines

    result = list(lines)

    # Check first 2 lines
    for i in range(min(2, len(result))):
        if _PAGE_NUM_ONLY_RE.match(result[i]):
            result[i] = ""
            break

    # Check last 2 lines
    for i in range(len(result) - 1, max(-1, len(result) - 3), -1):
        if _PAGE_NUM_ONLY_RE.match(result[i]):
            result[i] = ""
            break

    return result


def clean_text(raw_text: str, page_number: Optional[int] = None) -> str:
    """Clean and normalise extracted page text conservatively.

    Preserves:
    - Markdown tables
    - Heading hierarchy and blank lines between paragraphs
    - Clause numbers (e.g. 1.1, PEC/CSE/25/836)
    - Dates, percentages, course credits, marks
    - Exception and qualifier clauses

    Args:
        raw_text:    The verbatim text from PyMuPDF or Gemini OCR.
        page_number: 1-indexed page number (optional, for footer verification).

    Returns:
        Cleaned, standardised text string.
    """
    if not raw_text or not raw_text.strip():
        return ""

    # 1. Unicode & invisible character normalisation
    text = normalise_unicode(raw_text)

    # 2. De-hyphenate broken words across line breaks
    text = repair_line_break_hyphenation(text)

    # 3. Standardise bullets
    text = normalise_bullets(text)

    # 4. Process line-by-line: whitespace normalisation and running page numbers
    raw_lines = text.split("\n")
    cleaned_lines = [normalise_horizontal_whitespace(line) for line in raw_lines]

    # Strip standalone page number headers/footers
    cleaned_lines = strip_running_page_numbers(cleaned_lines, page_number=page_number)

    # 5. Rejoin and normalise vertical whitespace
    # Join lines back
    text = "\n".join(cleaned_lines)

    # Collapse 3 or more consecutive newlines into 2 (standard paragraph break)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
