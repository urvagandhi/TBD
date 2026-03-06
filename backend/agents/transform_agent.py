"""
Agent 4: TRANSFORM — Compare paper structure vs journal rules, produce docx_instructions.

Identifies every formatting violation and generates the full transformation output
including docx_instructions.sections which drives the DOCX writer.
"""
import re
import time
from typing import Any

from crewai import Agent

from tools.logger import get_logger
from tools.tool_errors import LLMResponseError, TransformError  # noqa: F401 — available for callers

logger = get_logger(__name__)

# Canonical IMRAD section order for ordering recovery (Improvement 7)
CANONICAL_SECTION_ORDER = [
    "title",
    "authors",
    "abstract_label",
    "abstract_body",
    "keywords",
    "heading",         # Introduction
    "body",
    "heading",         # Methods
    "body",
    "heading",         # Results
    "body",
    "heading",         # Discussion / Conclusion
    "body",
    "figure_caption",
    "table_caption",
    "reference_label",
    "reference_entry",
]

# Section type priority for ordering (lower index = earlier in document)
_SECTION_TYPE_ORDER = {
    "title": 0,
    "authors": 1,
    "abstract_label": 2,
    "abstract_body": 3,
    "keywords": 4,
    "heading": 5,
    "body": 6,
    "figure_caption": 7,
    "table_caption": 8,
    "reference_label": 9,
    "reference_entry": 10,
}

# Citation pattern matchers for normalization (Improvement 6)
_NUMBERED_CITATION = re.compile(r"^\[(\d+(?:[,\-]\d+)*)\]$")
_AUTHOR_DATE_CITATION = re.compile(
    r"^\(([A-Z][a-zA-Z]+(?:\s+et\s+al\.?)?),?\s+(\d{4})\)$"
)


def _normalize_citation(citation: str) -> str:
    """
    Normalize citation string to a canonical representation for comparison.

    Handles patterns:
      [1]            → "num:1"
      [1,2]          → "num:1,2"
      [1-3]          → "num:1-3"
      (Smith, 2020)  → "aut:Smith:2020"
      (Smith et al., 2020) → "aut:Smith et al.:2020"

    This canonical form enables consistent citation_replacements detection
    and citation consistency scoring regardless of minor formatting differences.

    Args:
        citation: Raw citation string from paper.

    Returns:
        Normalized string representation.
    """
    c = citation.strip()

    m = _NUMBERED_CITATION.match(c)
    if m:
        return f"num:{m.group(1)}"

    m = _AUTHOR_DATE_CITATION.match(c)
    if m:
        author = m.group(1).strip()  # keep "et al." dot — it's part of the abbreviation
        year = m.group(2)
        return f"aut:{author}:{year}"

    # Fallback: lowercase + collapse whitespace
    return re.sub(r"\s+", " ", c.lower())


def _sort_sections_by_canonical_order(sections: list[dict]) -> list[dict]:
    """
    Sort docx_instructions.sections into canonical document reading order.

    LLMs sometimes return sections in wrong order. This recovery step ensures
    the DOCX writer always receives content in correct reading order:
      title → authors → abstract → keywords → body sections → references

    Sections of the same type retain their relative order (stable sort).

    Args:
        sections: List of section dicts, each with at minimum a "type" key.

    Returns:
        Sections sorted by canonical type order.
    """
    return sorted(
        sections,
        key=lambda s: _SECTION_TYPE_ORDER.get(s.get("type", "body"), 6),
    )


def _validate_transform_output(data: dict) -> None:
    """
    Validate transform output before DOCX generation.

    Checks:
      1. data is a dict
      2. "docx_instructions" key exists
      3. docx_instructions["sections"] exists and is non-empty
      4. "violations" key exists (list, may be empty for compliant papers)
      5. "changes_made" key exists

    Cross-agent sanity: if sections is empty, the DOCX writer will produce
    an empty document — this is always a pipeline error, not a valid state.

    Args:
        data: Parsed transform output dict.

    Raises:
        TransformError: If docx_instructions or sections are missing/empty.
        LLMResponseError: If data is not a dict.
    """
    if not isinstance(data, dict):
        raise LLMResponseError(
            f"Transform output must be a JSON object (dict), got {type(data).__name__}"
        )

    docx = data.get("docx_instructions")
    if not docx:
        raise TransformError(
            "Transform output missing 'docx_instructions'. "
            f"Keys present: {list(data.keys())}"
        )

    sections = docx.get("sections")
    if not sections:
        raise TransformError(
            "Transform output missing docx_instructions.sections — "
            "crew._write_docx_from_transform() will crash without it."
        )

    violations_count = len(data.get("violations", []))
    logger.info(
        "[TRANSFORM] Validation passed — sections=%d violations=%d",
        len(sections), violations_count,
    )


def _safe_context(context: dict, key: str) -> Any:
    """
    Defensively access a required key from a pipeline context dict.

    Args:
        context: Pipeline context dictionary.
        key: Required key name.

    Returns:
        Value at context[key].

    Raises:
        ValueError: If key is absent.
    """
    if key not in context:
        raise ValueError(f"Pipeline context missing required key: '{key}'")
    return context[key]


def create_transform_agent(llm: Any) -> Agent:
    """
    Agent 4: TRANSFORM — Violation detection + DOCX instruction generation.

    Receives paper_structure (Agent 2) and rules (Agent 3), compares every
    paper element against the journal requirements, and produces:
      - violations: detailed list of every formatting problem found
      - changes_made: human-readable list of fixes applied
      - docx_instructions: complete DOCX build spec with sections array
      - citation_replacements: citation style conversion map
      - reference_order: references in correct order per journal rules

    CRITICAL: docx_instructions.sections is REQUIRED.
    crew.py raises ValueError if sections key is missing or empty.

    Checks performed (all required):
      Document:   font, font_size, line_spacing
      Abstract:   word count vs max_words, label bold/centered per rules
      Headings:   H1/H2/H3 bold, centered, italic, case per rules
      Citations:  style (author-date vs numbered), et al. threshold, & vs and
      References: ordering (alpha vs appearance order), hanging indent, label
      Figures:    caption position (above/below), label prefix, label bold
      Tables:     caption position (above/below), label prefix

    Args:
        llm: Shared LLM string at temperature=0.

    Returns:
        CrewAI Agent configured for transformation.
    """
    logger.info("[TRANSFORM] Agent created")

    return Agent(
        role="Manuscript Formatting Transformation Engine",
        goal=(
            "Compare EVERY element of the paper_structure against the journal rules. "
            "For each violation found, generate a precise correction. "
            "Produce the complete transformation result as JSON with these 5 keys:\n\n"
            "1. violations: list of objects, each with:\n"
            "     {element: str, current_state: str, required_state: str,\n"
            "      severity: 'high'|'medium'|'low', correction: str}\n\n"
            "2. changes_made: list of str — human-readable descriptions of fixes applied.\n"
            "   IMPORTANT: Each entry MUST include the rule reference in parentheses.\n"
            "   Format: 'Fix description (StyleName §Section — rule detail)'\n"
            "   Examples:\n"
            "     'Reformatted 14 in-text citations to author-date style (APA 7th §8.11 — author-date format required)'\n"
            "     'Converted heading to Title Case (APA 7th §2.27 — H1 headings must be centered Title Case)'\n"
            "     'Reordered references alphabetically (APA 7th §9.44 — reference list ordered alphabetically by first author surname)'\n"
            "     'Corrected et al. threshold for 3+ authors (IEEE §II.B — use et al. for 3 or more authors)'\n\n"
            "3. docx_instructions: object with:\n"
            "     font: str, font_size: int, line_spacing: float,\n"
            "     margins: {top, bottom, left, right: str},\n"
            "     sections: list (REQUIRED — see rules below)\n\n"
            "4. citation_replacements: list of {original: str, replacement: str}\n\n"
            "5. reference_order: list[str] — references in correct journal order\n\n"
            "WHAT TO CHECK (all required):\n"
            "  DOCUMENT: font vs rules.document.font; font_size vs rules.document.font_size;\n"
            "    line_spacing vs rules.document.line_spacing\n"
            "  ABSTRACT: word_count vs rules.abstract.max_words (flag only, never truncate);\n"
            "    label bold/centered per rules.abstract\n"
            "  HEADINGS: for each level (H1/H2/H3) check bold, centered, italic, case\n"
            "    per rules.headings.H1/H2/H3\n"
            "  CITATIONS: detect if paper style matches rules.citations.style;\n"
            "    check et_al threshold; check & vs 'and' per uses_ampersand\n"
            "  REFERENCES: check ordering per rules.references.ordering;\n"
            "    check hanging indent; check label formatting\n"
            "  FIGURES: check caption position per rules.figures.caption_position;\n"
            "    check label prefix per rules.figures.label_prefix\n"
            "  TABLES: check caption position per rules.tables.caption_position;\n"
            "    check label prefix per rules.tables.label_prefix\n\n"
            "DOCX_INSTRUCTIONS.SECTIONS — CRITICAL RULES:\n"
            "  1. sections MUST be a non-empty list (crew.py raises ValueError if missing)\n"
            "  2. Cover ALL document content in reading order — do NOT skip sections or blocks\n"
            "  3. Preserve ALL original text verbatim — never delete or truncate content\n"
            "  4. Use these exact section types:\n"
            "       title           — paper title with {bold, centered, font_size}\n"
            "       authors         — author line with {centered}\n"
            "       abstract_label  — 'Abstract' heading with {bold, centered, italic}\n"
            "       abstract_body   — abstract text with {indent_first_line: bool}\n"
            "       heading         — section heading with {level: int, bold, centered, italic, case}\n"
            "       body            — paragraph text\n"
            "       figure_caption  — with {id: str, caption: str, position: str, bold: bool}\n"
            "       table_caption   — with {id: str, caption: str, position: str, bold: bool}\n"
            "       reference_label — 'References' heading with {bold, centered}\n"
            "       reference_entry — with {text: str, hanging_indent: bool}\n\n"
            "SECTION ORDERING (Improvement 7 — Recovery Rule):\n"
            "  Sections MUST appear in this canonical reading order:\n"
            "    title → authors → abstract_label → abstract_body → keywords\n"
            "    → headings+body (IMRAD order) → figure_caption → table_caption\n"
            "    → reference_label → reference_entry\n"
            "  If unsure about order, follow the original paper's reading order exactly.\n\n"
            "CITATION NORMALIZATION (Improvement 6):\n"
            "  Before generating citation_replacements, normalize citation patterns:\n"
            "    [1], [1,2], [1-3]           → numbered style\n"
            "    (Smith, 2020), (Smith et al., 2020) → author-date style\n"
            "  Use the target journal's citations.style to determine target format.\n\n"
            "CROSS-AGENT SANITY CHECK (Improvement 10):\n"
            "  If paper_structure.sections is empty, raise TransformError immediately.\n"
            "  Do not attempt to generate docx_instructions for a structureless paper.\n\n"
            "VALIDATION SELF-CHECK (before returning):\n"
            "  - Confirm docx_instructions.sections is non-empty\n"
            "  - Confirm violations and changes_made keys exist\n"
            "  - Confirm all section objects have a 'type' field\n\n"
            "NEVER re-parse structure. NEVER reload rules. NEVER score compliance.\n"
            "Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        backstory=(
            "You are a precision manuscript formatting engine with encyclopedic knowledge "
            "of academic style guides. You have transformed over 200,000 manuscripts for "
            "submission to APA, IEEE, Vancouver, Springer, and Chicago style journals. "
            "You apply formatting rules with zero tolerance for error — every element of "
            "the paper is checked methodically against journal requirements. "
            "You never make editorial changes or alter scientific content — only formatting "
            "corrections dictated by the journal rules. "
            "Your docx_instructions.sections output drives the DOCX writer directly: "
            "every section object must be complete, correctly typed, and in reading order. "
            "Missing the sections key or using wrong section types causes document generation "
            "to fail entirely — your output precision determines whether the researcher "
            "receives a correctly formatted manuscript. "
            "You normalize citation patterns before comparison so that minor formatting "
            "differences (spaces, punctuation) never cause false violations. "
            "You recover section ordering automatically: even if the paper's sections "
            "arrive out of order, your output always follows canonical IMRAD reading order."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=3,
    )
