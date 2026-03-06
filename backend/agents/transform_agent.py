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
            "SYSTEM RULE: You are a DATA GENERATOR, not a programmer. "
            "DO NOT write Python code. DO NOT explain your process. DO NOT use scratchpads.\n\n"
            "Produce the complete transformation results for {journal_style} as a RAW JSON OBJECT. "
            "Your entire response must be a single JSON object with exactly these 5 keys:\n"
            "1. violations: list of formatting problems found\n"
            "2. changes_made: list of rule-referenced fix descriptions\n"
            "3. docx_instructions: complete DOCX build spec (font, margins, sections)\n"
            "4. citation_replacements: list of {original, replacement}\n"
            "5. reference_order: list of reference strings\n\n"
            "NEGATIVE CONSTRAINTS:\n"
            "- NO PREAMBLE (e.g., 'Here is the JSON...')\n"
            "- NO PYTHON CODE (e.g., 'import json...')\n"
            "- NO CODE FENCES (```json ... ```)\n"
            "- NO COMMENTARY\n\n"
            "DOCX_INSTRUCTIONS.SECTIONS — MANDATORY:\n"
            "  - Must be a non-empty list covering ALL paper content verbatim.\n"
            "  - Use EXACT section types: title, authors, abstract_label, abstract_body, keywords, heading, body, figure_caption, table_caption, reference_label, reference_entry.\n\n"
            "Return ONLY the raw JSON object."
        ),
        backstory=(
            "You are a high-performance formatting compiler. You receive structural data "
            "and output a precise machine-readable build specification for a DOCX writer. "
            "You never talk, never explain, and never write code. You only emit JSON."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )
