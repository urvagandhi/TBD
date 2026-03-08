"""
Agent 1: PARSE — Extract complete structured metadata from paper text.

Receives raw or pre-labeled paper text and returns a strict paper_structure
JSON consumed by the Transform and Validate agents.

Schema matches APA_Pipeline_Complete_Prompts.md §3 exactly.
"""
import time
from typing import Any

from crewai import Agent

from tools.logger import get_logger
from tools.tool_errors import LLMResponseError, ParseError  # noqa: F401

logger = get_logger(__name__)

# Required top-level keys in paper_structure output
REQUIRED_FIELDS = [
    "metadata", "title", "authors", "affiliations", "abstract",
    "keywords", "sections", "figures", "tables", "citations",
    "references",
]


def _validate_parse_output(data: dict) -> None:
    """
    Validate that parse output contains all required top-level fields.

    Performs cross-agent sanity checks:
      - All REQUIRED_FIELDS present
      - sections is non-empty
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

    refs = data.get("references", [])
    logger.info(
        "[PARSE] Validation passed — sections=%d refs=%d figures=%d tables=%d",
        len(sections),
        len(refs),
        len(data.get("figures", [])),
        len(data.get("tables", [])),
    )


def _safe_context(context: dict, key: str) -> Any:
    if key not in context:
        raise ValueError(f"Pipeline context missing required key: '{key}'")
    return context[key]


# ── System prompt from APA_Pipeline_Complete_Prompts.md §3 ──────────────────
PARSE_SYSTEM_PROMPT = """You are a structured data extractor. You receive an academic paper (raw or pre-labeled with [SECTION: ...] markers) and extract a structured JSON object containing every paper element.

## YOUR TASK

1. Identify every structural element: title, authors, abstract, keywords, sections, figures, tables, citations, references, acknowledgments.
2. Detect the citation style used in the paper — this is CRITICAL for downstream formatting:
   - Scan in-text citations: if they use (Author, Year) patterns → "author-date"
   - If they use [1], (1), superscript numbers, or [1-3] → "numbered"
3. Detect the source format:
   - Papers from PNAS, Nature, Science, Cell, Lancet use NLM/Vancouver numbered style → "NLM"
   - Papers using (Author, Year) with APA-style references → "APA"
   - Otherwise → "other"
4. Merge partial paragraphs split by PDF extraction:
   - Lines ending without sentence-end punctuation (. ? ! :) AND next line starts lowercase → merge into one paragraph
   - Hyphenated line breaks like "entero-\\nhemorrhagic" → merge to "enterohemorrhagic"
5. Parse the text into the following JSON schema.

## OUTPUT JSON SCHEMA

{
  "metadata": {
    "citation_style": "numbered | author-date",
    "source_format": "NLM | APA | other",
    "paper_type": "research | review | meta-analysis | case-study | other"
  },
  "title": "Full paper title as single string",
  "authors": [
    {
      "name": "Full Name",
      "affiliations": ["a", "b"],
      "is_corresponding": true/false,
      "email": "if available"
    }
  ],
  "affiliations": [
    {"key": "a", "institution": "...", "address": "..."}
  ],
  "abstract": {
    "text": "Full abstract text as single paragraph",
    "word_count": 150,
    "has_explicit_label": true/false
  },
  "keywords": ["keyword1", "keyword2"],
  "significance": "Significance paragraph text if present, else null",
  "sections": [
    {
      "heading": "Introduction",
      "level": 1,
      "content": "Full section body text. Merge all paragraphs belonging to this section.",
      "subsections": [
        {
          "heading": "Subsection Title",
          "level": 2,
          "content": "Subsection body text"
        }
      ]
    }
  ],
  "figures": [
    {
      "number": 1,
      "caption": "Full caption text starting from Fig. 1..."
    }
  ],
  "tables": [
    {
      "number": 1,
      "caption": "Full table caption"
    }
  ],
  "citations": [
    {
      "id": "1",
      "original_text": "(1)",
      "context": "5 words before and after the citation",
      "in_text_format": "numbered"
    }
  ],
  "references": [
    {
      "id": "1",
      "original_text": "Full reference as written in paper",
      "parsed": {
        "authors": [{"last": "Nataro", "initials": "JP"}],
        "year": 1998,
        "title": "Article title",
        "journal": "Clin Microbiol Rev",
        "volume": "11",
        "issue": "1",
        "pages": "142-201",
        "doi": "if available"
      }
    }
  ],
  "acknowledgments": "Acknowledgments text if present",
  "author_contributions": "Author contributions text if present",
  "journal_metadata": {
    "journal": "PNAS",
    "volume": "112",
    "issue": "17",
    "pages": "5503-5508",
    "doi": "10.1073/pnas.1422986112",
    "received_date": "December 2, 2014",
    "accepted_date": "March 25, 2015"
  }
}

## CRITICAL RULES

1. Preserve ALL text verbatim in content fields — never summarize or truncate.
2. Parse EVERY reference into its component parts (authors, year, title, journal, etc.).
3. For author names: separate last name and initials. "Nataro JP" → last: "Nataro", initials: "JP"
4. For "et al." references: include the named authors and mark has_et_al: true.
5. Count abstract words accurately.
6. Map each citation in the text to its corresponding reference ID.
7. The sections array must follow the paper's actual order.
8. Merge partial paragraphs that were split by PDF extraction into complete paragraphs.

## CITATION STYLE DETECTION (MANDATORY)

You MUST correctly set metadata.citation_style and metadata.source_format:

- **Numbered citations**: Look for [1], (1), superscript ¹, [1,2], [1-5], (1-3) patterns in body text.
  References section will have numbered entries: "1. Author..." or "[1] Author..."
  → citation_style: "numbered"

- **Author-date citations**: Look for (Smith, 2020), (Smith & Jones, 2020), (Smith et al., 2020) patterns.
  References section will list entries alphabetically by author last name.
  → citation_style: "author-date"

- **Source format detection**:
  - PNAS, Nature, Science, Cell, Lancet, BMJ, NEJM → source_format: "NLM" (these use Vancouver/NLM numbered style)
  - APA-style journals with (Author, Year) → source_format: "APA"
  - If unclear → source_format: "other"

Getting this wrong causes the entire downstream formatting to apply incorrect citation/reference rules.

## OUTPUT

Return ONLY valid JSON. No markdown, no explanation, no backticks."""


def create_parse_agent(llm: Any) -> Agent:
    """
    Agent 1: PARSE — Produce paper_structure JSON from paper text.

    Handles both structural detection and data extraction in a single pass.
    Uses the comprehensive schema from APA Pipeline spec.
    """
    logger.info("[PARSE] Agent created")

    return Agent(
        role="Academic Paper Structure Extractor",
        goal=PARSE_SYSTEM_PROMPT,
        backstory=(
            "You are a precision data extraction specialist trained on academic publishing "
            "metadata standards. You have extracted structured data from over 100,000 research "
            "papers across all major scientific publishers: Elsevier, Springer, IEEE, Nature, "
            "PNAS, PLOS, and Wiley. "
            "You produce deterministic, schema-compliant JSON every single time — your output is "
            "consumed directly by the Transform and Validate agents with no human review. "
            "You parse EVERY reference into its component parts: authors, year, title, journal, "
            "volume, issue, pages, DOI. "
            "You are an expert at detecting citation styles: you distinguish numbered citations "
            "([1], (1), superscripts) from author-date citations ((Smith, 2020)) by scanning "
            "the actual in-text patterns. You recognize that PNAS, Nature, Science, Cell papers "
            "use NLM/Vancouver numbered citations which must be flagged as source_format 'NLM' "
            "for downstream conversion. Getting citation_style wrong breaks the entire pipeline. "
            "You count words with mathematical precision. "
            "You never hallucinate content — every value is grounded in the actual document text. "
            "Before returning, you self-check: all required keys present, metadata.citation_style "
            "and metadata.source_format set correctly, sections non-empty, references fully parsed."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=1,
        max_tokens=65536,
    )