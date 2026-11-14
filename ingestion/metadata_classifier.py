"""Document metadata extraction and non-blocking categorization for IRIS.

Infers document category, subcategory, academic session, version, and labels
from document filenames and introductory page text.

Design rules:
- Non-blocking: failures never block ingestion; defaults to 'unclassified'.
- Multi-label support: returns primary category and list of subcategory tags.
- Explainable: heuristic and rule-based, fully deterministic.
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

METADATA_VERSION = "meta-v1"


def classify_document(
    filename: str, first_pages_text: list[str] = None
) -> dict[str, Any]:
    """Infer metadata and classification for a document.

    Args:
        filename:         The document filename (e.g. 'CSE_syllabus_24.pdf').
        first_pages_text: Optional list of text from the first 1-3 pages.

    Returns:
        Dictionary of inferred metadata:
        {
            "category": str,
            "subcategories": list[str],
            "labels": list[str],
            "department": Optional[str],
            "academic_year": Optional[str],
            "version": Optional[str],
            "effective_date": Optional[str],
            "metadata_version": str,
        }
    """
    try:
        return _infer_metadata(filename, first_pages_text or [])
    except Exception as exc:
        logger.warning(
            "Classification failed for %s (non-blocking): %s. Marking unclassified.",
            filename,
            exc,
        )
        return {
            "category": "unclassified",
            "subcategories": [],
            "labels": ["unclassified"],
            "department": None,
            "academic_year": None,
            "version": None,
            "effective_date": None,
            "metadata_version": METADATA_VERSION,
        }


def _infer_metadata(filename: str, pages_text: list[str]) -> dict[str, Any]:
    combined_sample = " ".join(pages_text[:3]).lower() if pages_text else ""
    fn_lower = filename.lower()

    category = "unclassified"
    subcategories: list[str] = []
    department: Optional[str] = None
    academic_year: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[str] = None

    # 1. Determine category
    if "syllabus" in fn_lower or "syllabi" in combined_sample or "curriculum" in fn_lower:
        category = "syllabus"
        subcategories.append("curriculum")
    elif "handout" in fn_lower or "course handout" in combined_sample:
        category = "course_handout"
        subcategories.append("course_pack")
    elif "scheme" in fn_lower or "teaching scheme" in combined_sample:
        category = "teaching_scheme"
        subcategories.append("curriculum")
    elif "circular" in fn_lower or "notice" in fn_lower:
        category = "circular"
    elif "ordinance" in fn_lower or "regulation" in fn_lower:
        category = "regulations"

    # 2. Department detection
    if "cse" in fn_lower or "computer science" in combined_sample:
        department = "Computer Science & Engineering"
        subcategories.append("cse")
    elif "ece" in fn_lower or "electronics" in combined_sample:
        department = "Electronics & Communication Engineering"
        subcategories.append("ece")
    elif "mech" in fn_lower or "mechanical" in combined_sample:
        department = "Mechanical Engineering"
        subcategories.append("me")
    elif "civil" in fn_lower:
        department = "Civil Engineering"
        subcategories.append("ce")

    # 3. Programme / Degree level
    if "b.tech" in combined_sample or "b. tech" in combined_sample or "btech" in fn_lower:
        subcategories.append("btech")
        subcategories.append("undergraduate")
    elif "m.tech" in combined_sample or "mtech" in fn_lower:
        subcategories.append("mtech")
        subcategories.append("postgraduate")
    elif "ph.d" in combined_sample or "phd" in fn_lower:
        subcategories.append("phd")

    # 4. Version detection (e.g. Ver 1_0, Ver 2.0, v1, v2)
    ver_match = re.search(r"ver[_\s]?(\d+[._]\d+)", fn_lower)
    if ver_match:
        version = ver_match.group(1).replace("_", ".")
    elif "version" in combined_sample:
        doc_ver = re.search(r"version[\s:]+(\d+\.\d+)", combined_sample)
        if doc_ver:
            version = doc_ver.group(1)

    # 5. Date detection in filename or header (e.g. 04082025 -> 04/08/2025, or 4/8/2025)
    date_match = re.search(r"(\d{2})(\d{2})(\d{4})", filename)
    if date_match:
        day, month, yr = date_match.groups()
        if int(month) <= 12 and int(day) <= 31:
            effective_date = f"{day}/{month}/{yr}"
    if not effective_date:
        doc_date = re.search(r"dated[\s:]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", combined_sample)
        if doc_date:
            effective_date = doc_date.group(1)

    # 6. Academic Year / Batch detection (e.g. "2023 batch onwards", "25-26-1", "2024")
    year_match = re.search(r"(20\d{2}[-–]\d{2,4})", combined_sample)
    if year_match:
        academic_year = year_match.group(1)
    elif "25261" in filename or "25-26-1" in combined_sample:
        academic_year = "2025-26 (Sem 1)"
    elif "batch" in combined_sample:
        batch_m = re.search(r"(\d{4})\s+batch", combined_sample)
        if batch_m:
            academic_year = f"{batch_m.group(1)} batch onwards"

    # 7. Labels list (all unique tags)
    labels = [category] + [s for s in subcategories if s != category]
    if not labels or labels == ["unclassified"]:
        labels = ["unclassified"]

    return {
        "category": category,
        "subcategories": list(dict.fromkeys(subcategories)),
        "labels": list(dict.fromkeys(labels)),
        "department": department,
        "academic_year": academic_year,
        "version": version,
        "effective_date": effective_date,
        "metadata_version": METADATA_VERSION,
    }
