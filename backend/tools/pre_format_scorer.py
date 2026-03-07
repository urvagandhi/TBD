"""
Pre-format compliance scorer — runs BEFORE the CrewAI pipeline.

Analyzes raw paper text against the selected journal's rules JSON and produces
a pre_format_score (0-100) with per-category breakdown. This gives users
immediate feedback on how far their manuscript is from compliance, before
the (slower) agentic formatting pipeline runs.

Standalone module — no coupling to the formatter or CrewAI agents.
"""
import re
from typing import Optional

from tools.logger import get_logger
from agents.validate_agent import SECTION_WEIGHTS, _clamp_score

logger = get_logger(__name__)

# Expected academic paper sections (case-insensitive matching)
_STANDARD_SECTIONS = [
    "abstract", "introduction", "methods", "methodology", "materials and methods",
    "results", "discussion", "conclusion", "conclusions", "references",
    "acknowledgments", "acknowledgements",
]

# IEEE-style roman-numeral headings
_ROMAN_HEADING_RE = re.compile(
    r"^(?:(?:[IVX]+)\.\s+)(.+)", re.MULTILINE
)

# Generic heading patterns: numbered (1. Introduction) or standalone capitalized lines
_NUMBERED_HEADING_RE = re.compile(
    r"^(?:\d+\.?\s+)([A-Z][A-Za-z\s]+)", re.MULTILINE
)
_ALLCAPS_HEADING_RE = re.compile(
    r"^([A-Z][A-Z\s]{3,})$", re.MULTILINE
)

# Citation patterns
_NUMBERED_CITATION_RE = re.compile(r"\[(\d+(?:[,\s\-\u2013]+\d+)*)\]")
_AUTHOR_DATE_CITATION_RE = re.compile(
    r"\(([A-Z][a-z]+(?:\s(?:&|and)\s[A-Z][a-z]+)?(?:\s+et\s+al\.?)?,?\s*\d{4}[a-z]?)\)"
)

# Reference list patterns
_NUMBERED_REF_RE = re.compile(r"^\s*\[?\d+\]?\s+\S", re.MULTILINE)
_AUTHOR_DATE_REF_RE = re.compile(
    r"^[A-Z][a-z]+,\s+[A-Z]", re.MULTILINE
)


def score_pre_format(paper_text: str, rules: dict) -> dict:
    """
    Score raw paper text against journal rules BEFORE formatting.

    Args:
        paper_text: Raw extracted text from PDF/DOCX.
        rules: Normalized journal rules dict (from rules/*.json or custom extraction).

    Returns:
        {
            "total_score": int (0-100),
            "breakdown": {
                "abstract":   {"score": int, "issue": str | None},
                "headings":   {"score": int, "issue": str | None},
                "citations":  {"score": int, "issue": str | None},
                "references": {"score": int, "issue": str | None},
                "document_format":   {"score": int, "issue": str | None},
            }
        }
    """
    breakdown = {
        "abstract": _score_abstract(paper_text, rules),
        "headings": _score_headings(paper_text, rules),
        "citations": _score_citations(paper_text, rules),
        "references": _score_references(paper_text, rules),
        "document_format": _score_document(paper_text, rules),
        # Pre-format scorer doesn't evaluate Figures/Tables well from raw text natively
        # So we baseline them at 100 to not ruin the weighted score.
        "figures": {"score": 100, "issue": None},
        "tables": {"score": 100, "issue": None},
    }

    # Calculate weighted score using shared SECTION_WEIGHTS
    total_score = 0.0
    for section, weight in SECTION_WEIGHTS.items():
        section_data = breakdown.get(section, {})
        raw_score = section_data.get("score", 100) if isinstance(section_data, dict) else 100
        total_score += _clamp_score(raw_score) * weight
    
    total_score = _clamp_score(round(total_score))

    logger.info(
        "[PRE-SCORE] total=%d | abstract=%d headings=%d citations=%d references=%d document_format=%d",
        total_score,
        breakdown["abstract"]["score"],
        breakdown["headings"]["score"],
        breakdown["citations"]["score"],
        breakdown["references"]["score"],
        breakdown["document_format"]["score"],
    )

    return {"total_score": total_score, "breakdown": breakdown}


# ---------------------------------------------------------------------------
# Category scorers
# ---------------------------------------------------------------------------

def _score_abstract(paper_text: str, rules: dict) -> dict:
    """Check abstract presence and word count against rules.abstract.max_words."""
    max_words = rules.get("abstract", {}).get("max_words")

    # Try to extract abstract text between "Abstract" label and next section heading
    abstract_text = _extract_abstract(paper_text)

    if not abstract_text:
        return {"score": 0, "issue": "No abstract detected in the document"}

    word_count = len(abstract_text.split())

    if not max_words:
        # Rules don't specify a limit — give full marks for presence
        return {"score": 100, "issue": None}

    if word_count <= max_words:
        return {"score": 100, "issue": None}

    over_by = word_count - max_words
    penalty = min(1.0, over_by / max_words)
    score = max(0, round(100 * (1.0 - penalty)))
    return {
        "score": score,
        "issue": f"Abstract has {word_count} words, exceeds {max_words}-word limit by {over_by}",
    }


def _score_headings(paper_text: str, rules: dict) -> dict:
    """Check whether expected heading structure is present."""
    expected_headings = rules.get("headings", {})
    if not expected_headings:
        return {"score": 50, "issue": "No heading rules defined — cannot assess"}

    # Detect headings from raw text
    detected = set()
    text_lower = paper_text.lower()

    for section_name in _STANDARD_SECTIONS:
        if section_name in text_lower:
            detected.add(section_name)

    # Also detect via regex patterns
    for m in _ROMAN_HEADING_RE.finditer(paper_text):
        detected.add(m.group(1).strip().lower())
    for m in _NUMBERED_HEADING_RE.finditer(paper_text):
        detected.add(m.group(1).strip().lower())
    for m in _ALLCAPS_HEADING_RE.finditer(paper_text):
        detected.add(m.group(1).strip().lower())

    # Core sections every academic paper should have
    core_sections = {"abstract", "introduction", "conclusion", "conclusions", "references"}
    core_found = detected & core_sections
    # Treat conclusion/conclusions as one
    has_conclusion = "conclusion" in detected or "conclusions" in detected
    core_expected = 4  # abstract, introduction, conclusion, references
    core_count = len(core_found - {"conclusions"})  # deduplicate
    if has_conclusion and "conclusion" not in core_found:
        core_count += 1

    if core_count >= core_expected:
        score = 100
        issue = None
    elif core_count >= 2:
        score = round(core_count / core_expected * 100)
        missing = core_sections - detected
        # Clean up alias
        if "conclusions" in missing and has_conclusion:
            missing.discard("conclusions")
        issue = f"Missing expected sections: {', '.join(sorted(missing))}" if missing else None
    else:
        score = max(20, round(core_count / core_expected * 100))
        issue = "Paper structure is incomplete — most expected sections are missing"

    # Check heading level depth matches rules
    expected_levels = len(expected_headings)  # H1, H2, H3 etc.
    has_subsections = bool(_NUMBERED_HEADING_RE.findall(paper_text)) or any(
        "." in m for m in re.findall(r"^\d+\.\d+", paper_text, re.MULTILINE)
    )
    if expected_levels >= 2 and not has_subsections and len(detected) > 3:
        score = max(0, score - 10)
        sub_issue = "No subsection hierarchy detected (rules expect multi-level headings)"
        issue = f"{issue}; {sub_issue}" if issue else sub_issue

    return {"score": score, "issue": issue}


def _score_citations(paper_text: str, rules: dict) -> dict:
    """Check citation style matches rules (numbered vs author-date)."""
    citation_rules = rules.get("citations", {})
    expected_style = citation_rules.get("style", "")

    numbered_matches = _NUMBERED_CITATION_RE.findall(paper_text)
    author_date_matches = _AUTHOR_DATE_CITATION_RE.findall(paper_text)

    total_detected = len(numbered_matches) + len(author_date_matches)

    if total_detected == 0:
        return {"score": 20, "issue": "No in-text citations detected"}

    if expected_style == "numbered":
        correct = len(numbered_matches)
        wrong = len(author_date_matches)
    elif expected_style in ("author-date", "author_date", "author_year"):
        correct = len(author_date_matches)
        wrong = len(numbered_matches)
    else:
        # Unknown style — score based on consistency
        dominant = max(len(numbered_matches), len(author_date_matches))
        ratio = dominant / total_detected
        score = round(ratio * 100)
        issue = None if ratio >= 0.9 else "Mixed citation styles detected"
        return {"score": score, "issue": issue}

    if total_detected == 0:
        return {"score": 20, "issue": "No in-text citations detected"}

    ratio = correct / total_detected
    score = round(ratio * 100)

    if ratio >= 0.9:
        return {"score": score, "issue": None}

    style_label = "numbered [N]" if expected_style == "numbered" else "author-date (Author, Year)"
    return {
        "score": score,
        "issue": f"{wrong} citations use wrong style — expected {style_label}",
    }


def _score_references(paper_text: str, rules: dict) -> dict:
    """Check reference list presence and style consistency."""
    ref_rules = rules.get("references", {})
    expected_ordering = ref_rules.get("ordering", "")
    expected_style = rules.get("citations", {}).get("style", "")

    # Find the references section
    ref_section = _extract_references_section(paper_text)

    if not ref_section:
        return {"score": 0, "issue": "No references section detected"}

    # Count reference entries
    numbered_refs = _NUMBERED_REF_RE.findall(ref_section)
    author_date_refs = _AUTHOR_DATE_REF_RE.findall(ref_section)

    ref_count = max(len(numbered_refs), len(author_date_refs))
    if ref_count == 0:
        return {"score": 20, "issue": "References section found but no entries detected"}

    score = 100
    issues = []

    # Check format consistency with citation style
    if expected_style == "numbered" and len(numbered_refs) < len(author_date_refs):
        score -= 30
        issues.append("Reference format doesn't match numbered citation style")
    elif expected_style in ("author-date", "author_date", "author_year"):
        if len(author_date_refs) < len(numbered_refs):
            score -= 30
            issues.append("Reference format doesn't match author-date citation style")

    # Check alphabetical ordering for styles that require it
    if expected_ordering == "alphabetical":
        lines = [l.strip() for l in ref_section.split("\n") if l.strip() and len(l.strip()) > 10]
        if len(lines) >= 2:
            # Extract first word (approximate surname) from each reference line
            first_words = [l.lstrip("[0123456789] ").split(",")[0].split(".")[0].strip().lower()
                           for l in lines if l.lstrip("[0123456789] ")]
            first_words = [w for w in first_words if w]
            if first_words and first_words != sorted(first_words):
                score -= 25
                issues.append("References are not alphabetically ordered")

    score = max(0, score)
    issue = "; ".join(issues) if issues else None
    return {"score": score, "issue": issue}


def _score_document(paper_text: str, rules: dict) -> dict:
    """
    Score document-level formatting hints detectable from raw text.

    Raw text has limited formatting info, so this checks what's inferrable:
    - Line spacing patterns (single vs double)
    - Presence of page numbers
    - Column indicators
    """
    doc_rules = rules.get("document", {})
    if not doc_rules:
        return {"score": 50, "issue": "No document-level rules defined — cannot assess"}

    score = 70  # Base score — raw text can't fully verify formatting
    issues = []

    expected_spacing = doc_rules.get("line_spacing")
    expected_columns = doc_rules.get("columns")

    # Heuristic: double-spaced text tends to have many blank lines between paragraphs
    lines = paper_text.split("\n")
    if len(lines) > 20:
        blank_ratio = sum(1 for l in lines if not l.strip()) / len(lines)

        if expected_spacing and expected_spacing >= 2.0:
            # Expect lots of blank lines for double spacing
            if blank_ratio < 0.15:
                score -= 15
                issues.append("Text appears single-spaced; double spacing expected")
        elif expected_spacing and expected_spacing <= 1.0:
            if blank_ratio > 0.4:
                score -= 10
                issues.append("Excessive blank lines detected; single spacing expected")

    # Two-column detection heuristic: short average line length
    if expected_columns and expected_columns == 2:
        non_blank = [l for l in lines if l.strip()]
        if non_blank:
            avg_len = sum(len(l) for l in non_blank) / len(non_blank)
            if avg_len > 100:
                # Long lines suggest single-column input
                score -= 10
                issues.append("Text appears single-column; two-column layout expected")

    score = max(0, min(100, score))
    issue = "; ".join(issues) if issues else None
    return {"score": score, "issue": issue}


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_abstract(paper_text: str) -> Optional[str]:
    """Extract abstract text from raw paper using multiple strategies."""

    # Strategy 1: Explicit "Abstract" label followed by text
    m = re.search(
        r"(?:^|\n)\s*(?:abstract|ABSTRACT|Abstract)\s*[:\-—.]?\s*\n?(.*?)(?=\n\s*(?:"
        r"introduction|keywords|index\s+terms|1[\.\s]|I[\.\s]|INTRODUCTION"
        r")|\Z)",
        paper_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        text = m.group(1).strip()
        if len(text.split()) >= 20:
            return text

    # Strategy 2: "Significance" or "Summary" section (PNAS-style)
    m = re.search(
        r"(?:^|\n)\s*(?:Significance|SIGNIFICANCE|Summary|SUMMARY)\s*[:\-—.]?\s*\n?(.*?)(?=\n\s*(?:"
        r"introduction|results|keywords|1[\.\s]|I[\.\s]|INTRODUCTION|RESULTS"
        r")|\Z)",
        paper_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        text = m.group(1).strip()
        if len(text.split()) >= 20:
            return text

    # Strategy 3: Implicit abstract — text block between author/metadata and first
    # section heading. Common in papers without explicit "Abstract" label.
    # Look for the first major section heading and take the paragraph block before it.
    first_section = re.search(
        r"\n\s*(?:(?:1\.?\s+)?(?:Introduction|INTRODUCTION|Background|BACKGROUND)"
        r"|(?:I\.\s+\S))",
        paper_text,
    )
    if first_section:
        preamble = paper_text[:first_section.start()]
        # Find the last substantial paragraph block in the preamble.
        # Skip title, authors, affiliations (short lines) — look for a dense text block.
        paragraphs = re.split(r"\n\s*\n", preamble)
        # Find paragraphs with 20+ words (likely the abstract)
        candidates = [p.strip() for p in paragraphs if len(p.split()) >= 20]
        if candidates:
            # Take the longest candidate (most likely the abstract)
            best = max(candidates, key=lambda p: len(p.split()))
            return best

    # Strategy 4: Keyword-delimited — text between keywords like "received for review"
    # and keyword line (common in journal-formatted papers)
    m = re.search(
        r"(?:received\s+for\s+review|accepted\s|approved\s)[^\n]*\n\s*\n?(.*?)(?=\n\s*(?:"
        r"[a-z]+\s*\|\s*[a-z]|keywords|introduction|significance|1[\.\s]"
        r"))",
        paper_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        text = m.group(1).strip()
        if len(text.split()) >= 20:
            return text

    return None


def _extract_references_section(paper_text: str) -> Optional[str]:
    """Extract the references section from raw paper text using multiple strategies."""

    _POST_REF_CUTOFFS = [
        "Appendix", "APPENDIX", "Supplementary", "Author Contributions",
        "Acknowledgment", "ACKNOWLEDGMENT", "Supporting Information",
    ]

    def _trim_post_ref(text: str) -> str:
        for cutoff in _POST_REF_CUTOFFS:
            idx = text.find(cutoff)
            if idx > 0:
                text = text[:idx]
        return text.strip()

    # Strategy 1: Explicit "References" / "Bibliography" header
    m = re.search(
        r"(?:^|\n)\s*(?:REFERENCES|References|BIBLIOGRAPHY|Bibliography|WORKS\s+CITED|Works\s+Cited"
        r"|LITERATURE\s+CITED|Literature\s+Cited)\s*\n(.*)",
        paper_text,
        re.DOTALL,
    )
    if m:
        text = _trim_post_ref(m.group(1))
        if len(text) > 50:
            return text

    # Strategy 2: Detect a block of numbered references (1. Author..., 2. Author...)
    # without a header — common in PNAS, Nature, Science formatted papers
    numbered_ref_pattern = re.compile(
        r"^\s*(\d+)\.\s+[A-Z][a-z]+[\s,]", re.MULTILINE
    )
    matches = list(numbered_ref_pattern.finditer(paper_text))
    if len(matches) >= 3:
        # Check if there's a consecutive run of numbered entries
        # Find the first entry where numbers are sequential
        for i in range(len(matches) - 2):
            try:
                n1 = int(matches[i].group(1))
                n2 = int(matches[i + 1].group(1))
                n3 = int(matches[i + 2].group(1))
            except ValueError:
                continue
            if n1 == 1 and n2 == 2 and n3 == 3:
                # Found start of numbered reference list
                ref_start = matches[i].start()
                text = _trim_post_ref(paper_text[ref_start:])
                if len(text) > 50:
                    return text
                break
            elif n2 == n1 + 1 and n3 == n2 + 1:
                # Consecutive block even if not starting at 1
                ref_start = matches[i].start()
                text = _trim_post_ref(paper_text[ref_start:])
                if len(text) > 50:
                    return text
                break

    # Strategy 3: Detect bracketed numbered references ([1] Author...)
    bracketed_ref_pattern = re.compile(
        r"^\s*\[(\d+)\]\s+[A-Z]", re.MULTILINE
    )
    bracket_matches = list(bracketed_ref_pattern.finditer(paper_text))
    if len(bracket_matches) >= 3:
        for i in range(len(bracket_matches) - 2):
            try:
                n1 = int(bracket_matches[i].group(1))
                n2 = int(bracket_matches[i + 1].group(1))
            except ValueError:
                continue
            if n2 == n1 + 1:
                ref_start = bracket_matches[i].start()
                text = _trim_post_ref(paper_text[ref_start:])
                if len(text) > 50:
                    return text
                break

    # Strategy 4: Detect author-date reference blocks (Author, A. A. (Year)...)
    # Look for a dense cluster of lines matching "Surname, Initial." near end of doc
    lines = paper_text.split("\n")
    total_lines = len(lines)
    if total_lines > 20:
        # Check the last 40% of the document for author-date ref patterns
        search_start = int(total_lines * 0.6)
        ref_line_re = re.compile(r"^[A-Z][a-z]+,?\s+[A-Z]\.?\s")
        consecutive = 0
        ref_block_start = None
        for i in range(search_start, total_lines):
            if ref_line_re.match(lines[i].strip()):
                if consecutive == 0:
                    ref_block_start = i
                consecutive += 1
            else:
                if consecutive >= 3 and ref_block_start is not None:
                    break
                consecutive = 0
                ref_block_start = None

        if consecutive >= 3 and ref_block_start is not None:
            text = _trim_post_ref("\n".join(lines[ref_block_start:]))
            if len(text) > 50:
                return text

    return None
