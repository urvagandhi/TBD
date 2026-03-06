"""
Agent 2: PARSE — Extract complete structured metadata from labelled paper text.

Consumes the labelled_text produced by the Ingest agent and returns a strict
paper_structure JSON consumed by the Transform and Validate agents.

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
PARSE_SYSTEM_PROMPT = """You are a structured data extractor. You receive a labeled academic paper (output from the INGEST agent) and extract a structured JSON object containing every paper element.

## YOUR TASK

Parse the labeled text and produce a JSON object with the following schema.

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
      "content": "Full section body text as a single string (for backward compatibility).",
      "paragraphs": [
        {"index": 1, "text": "First paragraph text.", "type": "body"},
        {"index": 2, "text": "Second paragraph text.", "type": "body"},
        {"index": 3, "text": "Long quoted passage...", "type": "block_quote"}
      ],
      "subsections": [
        {
          "heading": "Subsection Title",
          "level": 2,
          "content": "Subsection body text",
          "paragraphs": [
            {"index": 1, "text": "Paragraph text.", "type": "body"}
          ]
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
      "section_heading": "Introduction",
      "paragraph_index": 1,
      "citation_type": "parenthetical",
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
9. When building sections[].content, strip all [CITATION:] labels but leave the original citation text in place. Example: 'colonized by [CITATION:(1)] trillions' → 'colonized by (1) trillions'. The citations array captures the mapping separately.
10. For each section, split the content into separate paragraphs in the "paragraphs" array. Each paragraph boundary is indicated by a blank line, [PARA_START]/[PARA_END] labels, or indentation change in the source text. Also provide "content" as a flat string for backward compatibility.
11. For each citation, record "citation_type": "parenthetical" or "narrative". Parenthetical = citation inside parentheses. Narrative = author name is part of the sentence with year in parentheses.
12. Group/organizational authors: set parsed.authors[0].is_group=true, last='CDC'. No-date references: parsed.year='n.d.'. In-press references: parsed.year='in press'.

## OUTPUT

Return ONLY valid JSON. No markdown, no explanation, no backticks."""


def create_parse_agent(llm: Any) -> Agent:
    """
    Agent 2: PARSE — Produce paper_structure JSON from labelled text.

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
            "PLOS, and Wiley. "
            "You produce deterministic, schema-compliant JSON every single time — your output is "
            "consumed directly by the Transform and Validate agents with no human review. "
            "You parse EVERY reference into its component parts: authors, year, title, journal, "
            "volume, issue, pages, DOI. You detect citation styles by scanning inline patterns. "
            "You count words with mathematical precision. "
            "You never hallucinate content — every value is grounded in the actual document text. "
            "Before returning, you self-check: all required keys present, sections non-empty, "
            "references fully parsed."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=3,
        max_tokens=16384,
    )
