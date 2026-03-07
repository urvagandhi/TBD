"""
Agent 1: INGEST — Label and structure raw research paper text.

Receives raw extracted text from PDF/DOCX and annotates every content block
with structural markers. Downstream agents depend entirely on these labels.

Labels match APA_Pipeline_Complete_Prompts.md exactly.
"""
import re
import time
from typing import Any

from crewai import Agent

from tools.logger import get_logger
from tools.tool_errors import LLMResponseError, ParseError  # noqa: F401

logger = get_logger(__name__)

# Labels used by this agent — matches APA Pipeline spec
STRUCTURAL_LABELS = [
    "[TITLE_START]", "[TITLE_END]",
    "[AUTHORS_START]", "[AUTHORS_END]",
    "[ABSTRACT_START]", "[ABSTRACT_END]",
    "[KEYWORDS_START]", "[KEYWORDS_END]",
    "[SIGNIFICANCE_START]", "[SIGNIFICANCE_END]",
    "[HEADING_H1:<text>]",
    "[HEADING_H2:<text>]",
    "[HEADING_H3:<text>]",
    "[FIGURE_CAPTION_START:<N>]", "[FIGURE_CAPTION_END:<N>]",
    "[TABLE_CAPTION_START:<N>]", "[TABLE_CAPTION_END:<N>]",
    "[REFERENCE_START]", "[REFERENCE_END]",
    "[CITATION:<text>]",
    "[METADATA_START]", "[METADATA_END]",
    "[ACKNOWLEDGMENTS_START]", "[ACKNOWLEDGMENTS_END]",
    "[AUTHOR_CONTRIBUTIONS_START]", "[AUTHOR_CONTRIBUTIONS_END]",
    "[CITATION_STYLE:<style>]",
    "[SOURCE_FORMAT:<format>]",
]

# Compiled pattern for validating ingest output
_LABEL_PATTERN = re.compile(
    r"\[(?:TITLE_START|TITLE_END|AUTHORS_START|AUTHORS_END"
    r"|ABSTRACT_START|ABSTRACT_END|KEYWORDS_START|KEYWORDS_END"
    r"|SIGNIFICANCE_START|SIGNIFICANCE_END"
    r"|HEADING_H[123]:[^\]]+|FIGURE_CAPTION_(?:START|END):[^\]]+"
    r"|TABLE_CAPTION_(?:START|END):[^\]]+"
    r"|REFERENCE_START|REFERENCE_END|CITATION:[^\]]+"
    r"|METADATA_START|METADATA_END"
    r"|ACKNOWLEDGMENTS_START|ACKNOWLEDGMENTS_END"
    r"|AUTHOR_CONTRIBUTIONS_START|AUTHOR_CONTRIBUTIONS_END"
    r"|CITATION_STYLE:[^\]]+|SOURCE_FORMAT:[^\]]+)\]"
)


def _validate_ingest_output(labelled_text: str) -> None:
    """Validate that ingest output contains at least one structural label."""
    matches = _LABEL_PATTERN.findall(labelled_text)
    if not matches:
        raise LLMResponseError(
            "Ingest output contains no structural labels. "
            "Expected at least one of: [TITLE_START], [ABSTRACT_START], [HEADING_H1:...], etc."
        )
    logger.info("[INGEST] Output validated — %d structural labels detected", len(matches))


def _safe_context(context: dict, key: str) -> Any:
    if key not in context:
        raise ValueError(f"Pipeline context missing required key: '{key}'")
    return context[key]


# ── System prompt from APA_Pipeline_Complete_Prompts.md §2 ──────────────────
INGEST_SYSTEM_PROMPT = """You are a scientific paper structure labeler. Your ONLY job is to read raw academic paper text and add structural labels. You must NOT change, rewrite, rephrase, summarize, or delete ANY text.

## YOUR TASK

Read the paper text and insert structural marker labels at the correct positions. Return the ENTIRE paper text with labels inserted.

## STRUCTURAL LABELS TO INSERT

You must identify and label ALL of the following elements using these exact markers:

[TITLE_START]...[TITLE_END]
  - The main title of the paper. Usually the first major text block.
  - Join multi-line titles into a single line between the markers.

[AUTHORS_START]...[AUTHORS_END]
  - Author names and affiliations block. Includes superscript affiliation markers.
  - Include institution names and addresses within this block.

[ABSTRACT_START]...[ABSTRACT_END]
  - The abstract paragraph. May or may not have an explicit "Abstract" label.
  - Look for: a summary paragraph before the Introduction, often after author info.
  - Significance statements are NOT part of the abstract — label them separately.

[KEYWORDS_START]...[KEYWORDS_END]
  - Keywords line. May use | or , or ; as separators.

[SIGNIFICANCE_START]...[SIGNIFICANCE_END]
  - "Significance" section if present (common in PNAS papers).

[HEADING_H1:Exact Heading Text]
  - Major section headings: Introduction, Results, Discussion, Methods, Materials and Methods, Conclusion, Acknowledgments.
  - These are Level 1 headings (centered, bold in APA).

[HEADING_H2:Exact Heading Text]
  - Subsection headings within a major section.
  - Often italicized or bold in the source.

[HEADING_H3:Exact Heading Text]
  - Sub-subsection headings (rare). Usually run-in with the paragraph text.

[FIGURE_CAPTION_START:N]...[FIGURE_CAPTION_END:N]
  - Figure caption text. N = figure number (1, 2, 3...).
  - Starts with "Fig. N." or "Figure N." in the source text.

[TABLE_CAPTION_START:N]...[TABLE_CAPTION_END:N]
  - Table caption text. N = table number.

[REFERENCE_START]...[REFERENCE_END]
  - The entire references / bibliography section.
  - Each individual reference entry should be preserved exactly as-is within this block.

[CITATION:original_text]
  - In-text citations. Mark EVERY citation occurrence.
  - Numbered: (1), (2, 3), (1-5), superscript numbers, [1], [2-4]
  - Author-date: (Smith, 2020), (Smith & Jones, 2020), (Smith et al., 2020)

[METADATA_START]...[METADATA_END]
  - Journal metadata: DOI, received/accepted dates, editor info, page numbers.

[ACKNOWLEDGMENTS_START]...[ACKNOWLEDGMENTS_END]
  - Acknowledgments section.

[AUTHOR_CONTRIBUTIONS_START]...[AUTHOR_CONTRIBUTIONS_END]
  - "Author contributions:" block if present.

## CRITICAL RULES

1. NEVER modify any text content. Only INSERT labels around existing text.
2. Every label that is opened MUST be closed.
3. If a heading appears to span what would be H1 and H2, use H2 for the more specific sub-topic.
4. Detect the citation STYLE used in the paper:
   - If references are numbered (1, 2, 3...) and citations use numbers → [CITATION_STYLE:numbered]
   - If citations use (Author, Year) → [CITATION_STYLE:author-date]
   Insert this once at the top of your output.
5. If the paper is from a journal (PNAS, Nature, Cell, etc.), note the source style:
   [SOURCE_FORMAT:NLM] or [SOURCE_FORMAT:APA] or [SOURCE_FORMAT:other]
6. Papers from PNAS, Nature, Science, Cell use NLM/Vancouver numbered style — this is NOT APA and must be converted.

## PARAGRAPH MERGING RULE

If the input has hard line breaks in the middle of sentences (common from PDF extraction):
- Lines ending without period AND next line starts lowercase → these are ONE paragraph
- Merge them into a single continuous paragraph between labels
- Hyphenated line breaks like "entero-\\nhemorrhagic" → merge to "enterohemorrhagic"

## OUTPUT FORMAT

Return the complete paper text with all labels inserted. Start with:
[CITATION_STYLE:numbered|author-date]
[SOURCE_FORMAT:NLM|APA|other]

Then the labeled paper text."""


def create_ingest_agent(llm: Any) -> Agent:
    """
    Agent 1: INGEST — Label raw paper text with structural markers.

    Uses comprehensive structural labels from APA Pipeline spec.
    """
    logger.info("[INGEST] Agent created")

    return Agent(
        role="Scientific Paper Structure Labeler",
        goal=INGEST_SYSTEM_PROMPT,
        backstory=(
            "You are an expert academic document parser with 15 years of experience "
            "processing research manuscripts across all disciplines. You have labelled over "
            "50,000 papers using structural annotation systems for major publishers including "
            "Elsevier, Springer, IEEE, Nature, PNAS, and PLoS. "
            "Your labels are precise and conservative: you annotate what you are certain about "
            "and leave ambiguous content unlabelled rather than guess incorrectly. "
            "You never alter a single word of the original text — your job is to add structural "
            "markers that guide the downstream Parse agent in extracting the paper's metadata. "
            "You detect citation styles (numbered vs author-date) and source formats (NLM vs APA) "
            "automatically. You recognize that PNAS, Nature, Science, Cell papers use NLM/Vancouver "
            "numbered citations which must be flagged for downstream conversion to APA author-date format. "
            "When input is very large, you ensure that you label EVERY section "
            "and block without skipping or truncating content."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=1,
        max_tokens=65536,
    )