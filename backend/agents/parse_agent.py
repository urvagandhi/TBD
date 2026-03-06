"""
Agent 2: PARSE — Extract complete structured metadata from labelled paper text.

Consumes the labelled_text produced by the Ingest agent and returns a strict
paper_structure JSON consumed by the Transform and Validate agents.
"""
import time
from typing import Any

from crewai import Agent

from tools.logger import get_logger
from tools.tool_errors import LLMResponseError, ParseError  # noqa: F401 — available for callers

logger = get_logger(__name__)

# Required top-level keys in paper_structure output (Improvement 3)
REQUIRED_FIELDS = [
    "title", "authors", "abstract", "keywords",
    "imrad", "sections", "figures", "tables", "references", "metadata",
]

def _validate_parse_output(data: dict) -> None:
    """
    Validate that parse output contains all required top-level fields.

    Performs cross-agent sanity checks:
      - All 10 REQUIRED_FIELDS present
      - sections is non-empty
      - metadata.total_references == len(references)

    Args:
        data: Parsed paper_structure dict.

    Raises:
        ParseError: If required fields are missing or sections is empty.
        LLMResponseError: If data is not a dict.
    """
    if not isinstance(data, dict):
        raise LLMResponseError(
            f"Parse output must be a JSON object (dict), got {type(data).__name__}"
        )

    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ParseError(f"Parse output missing required fields: {missing}")

    sections = data.get("sections", [])
    if not sections:
        raise ParseError(
            "Parse output has empty sections list — downstream agents cannot "
            "transform a paper with no detected sections."
        )

    # Cross-agent sanity: total_references must match actual list (Improvement 10)
    refs = data.get("references", [])
    meta = data.get("metadata", {})
    meta_total = meta.get("total_references", -1)
    if meta_total != -1 and meta_total != len(refs):
        logger.warning(
            "[PARSE] Sanity check failed: metadata.total_references=%d != "
            "len(references)=%d — downstream agents will use len(references)",
            meta_total, len(refs),
        )

    logger.info(
        "[PARSE] Validation passed — sections=%d refs=%d figures=%d tables=%d",
        len(sections),
        len(refs),
        len(data.get("figures", [])),
        len(data.get("tables", [])),
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


def create_parse_agent(llm: Any) -> Agent:
    """
    Agent 2: PARSE — Produce paper_structure JSON from labelled text.

    Output schema (all 10 top-level keys REQUIRED):
      title          : str
      authors        : list[str]
      abstract       : {text: str, word_count: int}
      keywords       : list[str]
      imrad          : {introduction: bool, methods: bool, results: bool, discussion: bool}
      sections       : list[{heading: str, level: int(1/2/3), content_preview: str,
                             in_text_citations: list[str], word_count: int}]
      figures        : list[{id: str, caption: str}]
      tables         : list[{id: str, caption: str}]
      references     : list[str]  — each complete reference as one string
      metadata       : {total_words: int, total_sections: int, total_figures: int,
                        total_tables: int, total_references: int,
                        citation_style_detected: str (author-date|numbered|mixed|unknown),
                        has_doi: bool}

    Validation rules enforced post-parse:
      - sections must NOT be empty (raises ParseError)
      - abstract.word_count recalculated if 0 but text is not empty
      - metadata.total_references overridden with len(references) if mismatched
      - All list fields default to [] if content is absent
      - All boolean fields default to false if absent

    Args:
        llm: Shared LLM string at temperature=0.

    Returns:
        CrewAI Agent configured for structural parsing.
    """
    logger.info("[PARSE] Agent created")

    return Agent(
        role="Academic Paper Structure Extractor",
        goal=(
            "Extract the complete structural metadata from the labelled paper text "
            "and return it as a single valid JSON object.\n\n"
            "OUTPUT SCHEMA — all 10 top-level keys are REQUIRED:\n"
            "  title (str) — full paper title\n"
            "  authors (list[str]) — one entry per author\n"
            "  abstract: {text: str, word_count: int} — full abstract text, accurate word count\n"
            "  keywords (list[str]) — individual keywords/phrases\n"
            "  imrad: {introduction: bool, methods: bool, results: bool, discussion: bool}\n"
            "  sections: list of {heading: str, level: int (1/2/3), "
            "    content_preview: str (first 200 chars of section body), "
            "    in_text_citations: list[str] (unique citations in this section), "
            "    word_count: int (words in section body)}\n"
            "  figures: list of {id: str (e.g. 'Figure 1'), caption: str}\n"
            "  tables:  list of {id: str (e.g. 'Table 1'),  caption: str}\n"
            "  references: list[str] — each complete reference as one string\n"
            "  metadata: {total_words: int, total_sections: int, total_figures: int,\n"
            "             total_tables: int, total_references: int,\n"
            "             citation_style_detected: str (author-date|numbered|mixed|unknown),\n"
            "             has_doi: bool}\n\n"
            "STRICT RULES:\n"
            "  1. Return ONLY valid JSON — no markdown fences, no prose, no explanation\n"
            "  2. sections MUST NOT be empty — if no sections found, raise ParseError\n"
            "  3. Use [] for any list field where content is absent in the paper\n"
            "  4. Use false for any boolean field where the element is absent\n"
            "  5. word_count: count space-separated tokens accurately\n"
            "  6. citation_style_detected: 'numbered' if citations are [1] or (1);\n"
            "     'author-date' if (Smith, 2020) or (Smith et al., 2020);\n"
            "     'mixed' if both styles appear; 'unknown' if none detected\n"
            "  7. has_doi: true if any reference contains 'doi' or 'https://doi.org'\n"
            "  8. metadata.total_references MUST equal len(references)\n"
            "  9. If abstract.word_count is 0 but abstract.text is non-empty, recalculate\n"
            " 10. Preserve Unicode and special characters in reference strings exactly\n\n"
            "VALIDATION SELF-CHECK (before returning):\n"
            "  - Confirm all 10 top-level keys are present\n"
            "  - Confirm sections list has at least 1 entry\n"
            "  - Confirm metadata.total_references == len(references)\n"
            "  - Confirm your JSON is parseable (no trailing commas, no single quotes)\n"
            "  If any check fails, fix your output before returning."
        ),
        backstory=(
            "You are a precision data extraction specialist trained on academic publishing "
            "metadata standards. You have extracted structured data from over 100,000 research "
            "papers across all major scientific publishers: Elsevier, Springer, IEEE, Nature, "
            "PLOS, and Wiley. "
            "You produce deterministic, schema-compliant JSON every single time — your output is "
            "consumed directly by the Transform and Validate agents with no human review or "
            "correction. You count words with mathematical precision, detect citation styles by "
            "scanning inline patterns systematically, and always include every required field "
            "even when the corresponding content is absent (using empty defaults). "
            "You never hallucinate content — every value you output is grounded in the actual "
            "document text. You never omit a field or change the schema structure. "
            "Before returning, you mentally run a self-check: all 10 keys present, sections "
            "non-empty, total_references matches references list length. Only then do you output."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )
