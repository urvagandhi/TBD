"""
Agent 1: INGEST — Label and structure raw research paper text.

Receives raw extracted text from PDF/DOCX and annotates every content block
with structural markers. Downstream agents depend entirely on these labels.
"""
import re
import time
from typing import Any

from crewai import Agent

from tools.logger import get_logger
from tools.tool_errors import LLMResponseError, ParseError  # noqa: F401 — available for callers

logger = get_logger(__name__)

# Labels used by this agent — must match STEP4 spec exactly
STRUCTURAL_LABELS = [
    "[TITLE]",
    "[AUTHORS]",
    "[ABSTRACT_START]",
    "[ABSTRACT_END]",
    "[KEYWORDS]",
    "[HEADING_H1:<text>]",
    "[HEADING_H2:<text>]",
    "[HEADING_H3:<text>]",
    "[FIGURE_CAPTION:<text>]",
    "[TABLE_CAPTION:<text>]",
    "[REFERENCE_START]",
    "[REFERENCE_END]",
    "[CITATION:<text>]",
]

# Compiled pattern for validating ingest output (Improvement 3)
_LABEL_PATTERN = re.compile(
    r"\[(?:TITLE|AUTHORS|ABSTRACT_START|ABSTRACT_END|KEYWORDS"
    r"|HEADING_H[123]:[^\]]+|FIGURE_CAPTION:[^\]]+|TABLE_CAPTION:[^\]]+"
    r"|REFERENCE_START|REFERENCE_END|CITATION:[^\]]+)\]"
)


def _validate_ingest_output(labelled_text: str) -> None:
    """
    Validate that ingest output contains at least one structural label.

    Raises:
        LLMResponseError: If no structural labels are found.
    """
    matches = _LABEL_PATTERN.findall(labelled_text)
    if not matches:
        raise LLMResponseError(
            "Ingest output contains no structural labels. "
            "Expected at least one of: [TITLE], [AUTHORS], [HEADING_H1:...], etc."
        )
    logger.info("[INGEST] Output validated — %d structural labels detected", len(matches))


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


def create_ingest_agent(llm: Any) -> Agent:
    """
    Agent 1: INGEST — Label raw paper text with structural markers.

    Receives raw paper_content and produces labelled_text that the Parse agent
    uses to extract the full paper_structure JSON. This agent ONLY adds labels —
    it never interprets formatting rules, modifies content, or scores compliance.

    Labelling rules (13 structural markers):
      [TITLE]          → First prominent short line (< 200 chars), before authors
      [AUTHORS]        → Name/affiliation lines immediately after title
      [ABSTRACT_START] → Beginning of abstract block
      [ABSTRACT_END]   → End of abstract block
      [KEYWORDS]       → Line starting with Keywords/Key words/Index Terms
      [HEADING_H1:x]   → Major sections (Introduction, Methods, Results, etc.)
      [HEADING_H2:x]   → Subsections (1.1, 2.3, or indented short lines)
      [HEADING_H3:x]   → Sub-subsections (1.1.1)
      [FIGURE_CAPTION] → Lines starting with Figure/Fig/FIGURE + number
      [TABLE_CAPTION]  → Lines starting with Table/TABLE + number
      [REFERENCE_START]→ Start of References/Bibliography section
      [REFERENCE_END]  → End of document
      [CITATION:x]     → Inline citations: (Author, Year), [1], [1-3]

    Edge cases:
      - paper_content < 100 chars → raises ParseError
      - paper_content > 50,000 chars → truncates: first 40,000 + last 5,000

    Args:
        llm: Shared LLM string (e.g., "gemini/gemini-2.0-flash") at temperature=0.

    Returns:
        CrewAI Agent configured for structural labelling.
    """
    logger.info("[INGEST] Agent created")

    return Agent(
        role="Academic Document Structure Analyst",
        goal=(
            "Read raw research paper text and annotate EVERY content block with "
            "its structural role using exactly these 13 label types:\n"
            "  [TITLE]          — First prominent short line before author names\n"
            "  [AUTHORS]        — Author name/affiliation block after title\n"
            "  [ABSTRACT_START] — Opening marker of abstract section\n"
            "  [ABSTRACT_END]   — Closing marker of abstract section\n"
            "  [KEYWORDS]       — Line starting with Keywords/Key words/Index Terms\n"
            "  [HEADING_H1:text]— Major section headings (Introduction, Methods, etc.)\n"
            "  [HEADING_H2:text]— Subsection headings (1.1, 2.3, or indented short lines)\n"
            "  [HEADING_H3:text]— Sub-subsection headings (1.1.1)\n"
            "  [FIGURE_CAPTION:text] — Caption lines starting with Figure/Fig + number\n"
            "  [TABLE_CAPTION:text]  — Caption lines starting with Table + number\n"
            "  [REFERENCE_START]— Opening marker of References/Bibliography section\n"
            "  [REFERENCE_END]  — Closing marker at end of references\n"
            "  [CITATION:text]  — Inline citations: (Author, Year), [1], [1,2], [1-3]\n\n"
            "LABELLING RULES (non-negotiable):\n"
            "  1. Each label appears on its OWN LINE immediately before the content it marks\n"
            "  2. Preserve ALL original text verbatim — never delete, reorder, or paraphrase\n"
            "  3. Only add labels you are confident about — skip ambiguous content\n"
            "  4. [HEADING_H1] for: Introduction, Methodology/Methods, Results/Findings, "
            "     Discussion, Conclusion, Acknowledgements, Appendix — and numbered equivalents\n"
            "  5. [HEADING_H2] for: numbered subsections (1.1, 2.3) or short indented lines\n"
            "  6. [HEADING_H3] for: numbered sub-subsections (1.1.1) only\n"
            "  7. [CITATION] inline within paragraph text — keep citation inline, "
            "     add [CITATION:text] immediately before the citation marker\n"
            "  8. Process the entire paper_content regardless of length\n"
            "  9. Non-English papers: attempt labelling using section names in that language\n"
            " 10. Return ONLY the labelled text — no JSON, no explanation, no commentary\n\n"
            "TOKEN SAFETY: If input is very large, focus on Title, Authors, Abstract, "
            "first 3 sections, Figures, Tables, and References — these carry the most "
            "structural information for downstream agents.\n\n"
            "VALIDATION: Your output MUST contain at least one structural label. "
            "If you produce output with no labels at all, the pipeline will reject it "
            "and retry. Ensure every response has at minimum [TITLE] and [ABSTRACT_START]."
        ),
        backstory=(
            "You are an expert academic document parser with 15 years of experience "
            "processing research manuscripts across all disciplines — biomedical sciences, "
            "engineering, physics, social sciences, and humanities. You have labelled over "
            "50,000 papers using structural annotation systems for major publishers including "
            "Elsevier, Springer, IEEE, Nature, and PLoS. "
            "Your labels are precise and conservative: you annotate what you are certain about "
            "and leave ambiguous content unlabelled rather than guess incorrectly. "
            "You never alter a single word of the original text — your job is to add structural "
            "markers that guide the downstream Parse agent in extracting the paper's metadata. "
            "Wrong labels produce wrong structure, which causes incorrect formatting — your "
            "accuracy directly determines the quality of the final formatted manuscript. "
            "When input is very large, you ensure that you label EVERY section "
            "and block without skipping or truncating content."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )
