import json
import os
import re
import uuid
from pathlib import Path

from crewai import Crew, Process, Task

from agents import (
    create_ingest_agent,
    create_interpret_agent,
    create_parse_agent,
    create_transform_agent,
    create_validate_agent,
)
from tools.docx_writer import write_formatted_docx
from tools.rule_loader import load_rules

OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

MAX_PAPER_CHARS = 32_000


def _truncate_paper_content(text: str) -> str:
    """Preserve head + tail of large documents to stay within token limits."""
    if len(text) <= MAX_PAPER_CHARS:
        return text
    head = text[: MAX_PAPER_CHARS // 2]
    tail = text[-(MAX_PAPER_CHARS // 2) :]
    return f"{head}\n\n[... content truncated for length ...]\n\n{tail}"


def extract_json_from_llm(text: str) -> dict:
    """
    Robustly parse JSON from LLM output that may contain markdown fences.

    Args:
        text: Raw LLM output string.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If JSON cannot be parsed after cleanup.
    """
    # Strip markdown code fences
    clean = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    clean = clean.strip().rstrip("`").strip()
    # Fix trailing commas before closing brackets
    clean = re.sub(r",(\s*[}\]])", r"\1", clean)

    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from LLM output: {e}\nRaw text:\n{text[:500]}") from e


PARSE_FALLBACK: dict = {
    "title": "Unknown Title",
    "authors": [],
    "abstract": {"text": "", "word_count": 0},
    "keywords": [],
    "imrad": {
        "introduction": False,
        "methods": False,
        "results": False,
        "discussion": False,
    },
    "sections": [],
    "figures": [],
    "tables": [],
    "references": [],
}

VALIDATE_FALLBACK: dict = {
    "overall_score": 50,
    "breakdown": {
        "document_format": {"score": 50, "issues": ["Unable to fully validate"]},
        "abstract": {"score": 50, "issues": []},
        "headings": {"score": 50, "issues": []},
        "citations": {"score": 50, "issues": []},
        "references": {"score": 50, "issues": []},
        "figures": {"score": 50, "issues": []},
        "tables": {"score": 50, "issues": []},
    },
    "changes_made": [],
    "imrad_check": {
        "introduction": False,
        "methods": False,
        "results": False,
        "discussion": False,
    },
    "citation_consistency": {"orphan_citations": [], "uncited_references": []},
    "warnings": ["Validation completed with partial data"],
}


def run_pipeline(paper_content: str, journal_style: str) -> dict:
    """
    Execute the 5-agent CrewAI sequential pipeline.

    Pipeline: INGEST → PARSE → INTERPRET → TRANSFORM → VALIDATE

    Args:
        paper_content: Full extracted text from uploaded PDF/DOCX.
        journal_style: One of "APA 7th Edition", "IEEE", "Vancouver",
                       "Springer", "Chicago".

    Returns:
        dict with keys:
            - compliance_report: ComplianceReport dict (overall_score, breakdown,
              changes_made, imrad_check, citation_consistency, warnings)
            - docx_filename: filename of the generated DOCX in outputs/
    """
    paper_content = _truncate_paper_content(paper_content)

    # LiteLLM (used internally by CrewAI) reads GOOGLE_API_KEY for Google AI Studio
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    llm = f"gemini/{model_name}"

    rules = load_rules(journal_style)

    ingest_agent = create_ingest_agent(llm)
    parse_agent = create_parse_agent(llm)
    interpret_agent = create_interpret_agent(llm)
    transform_agent = create_transform_agent(llm)
    validate_agent = create_validate_agent(llm)

    ingest_task = Task(
        description=(
            f"You have received the raw text of a research paper. "
            f"Label every content block with its type marker "
            f"(TITLE, ABSTRACT, KEYWORD, HEADING_H1, HEADING_H2, HEADING_H3, "
            f"BODY_PARAGRAPH, IN_TEXT_CITATION, FIGURE_CAPTION, TABLE_CAPTION, "
            f"REFERENCE_ENTRY). Return the labelled content.\n\n"
            f"--- RAW PAPER CONTENT ---\n{paper_content}"
        ),
        expected_output=(
            "Labelled document content with each block prefixed by its type marker. "
            "Example: [TITLE] Machine Learning in Healthcare\n[ABSTRACT] This paper..."
        ),
        agent=ingest_agent,
    )

    parse_task = Task(
        description=(
            "Parse the labelled document content from the previous step and extract "
            "the complete paper structure. "
            "Return ONLY valid JSON matching the paper_structure schema with keys: "
            "title, authors, abstract (text + word_count), keywords, "
            "imrad (introduction/methods/results/discussion booleans), "
            "sections (list of heading/level/content_preview/in_text_citations), "
            "figures (list of id/caption), tables (list of id/caption), "
            "references (list of full reference strings). "
            "Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        expected_output=(
            "Valid JSON object matching the paper_structure schema. "
            "Must be parseable by json.loads() without any post-processing."
        ),
        agent=parse_agent,
        context=[ingest_task],
    )

    interpret_task = Task(
        description=(
            f"The target journal is: {journal_style}\n\n"
            f"Load and return the complete formatting rules for this journal. "
            f"The rules are already loaded — return the following JSON exactly:\n"
            f"{json.dumps(rules, indent=2)}\n\n"
            f"Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        expected_output=(
            "Valid JSON object containing the complete journal formatting rules. "
            "Must include: document, abstract, headings, citations, references, "
            "figures, tables sections."
        ),
        agent=interpret_agent,
    )

    transform_task = Task(
        description=(
            "You have the paper_structure (from parse step) and the journal rules "
            "(from interpret step). "
            "Compare every paper element against the journal rules. "
            "Identify all formatting violations. "
            "Produce the transformation output as JSON with keys: "
            "violations (list of violation descriptions), "
            "changes_made (list of human-readable fix descriptions), "
            "docx_instructions (object with: rules dict, sections list where each "
            "section has: type, content, and optionally level for headings), "
            "output_filename (string). "
            "The sections list must contain ALL paper content in document order. "
            "Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        expected_output=(
            "Valid JSON with violations, changes_made, docx_instructions "
            "(containing rules and sections list), and output_filename."
        ),
        agent=transform_agent,
        context=[parse_task, interpret_task],
    )

    validate_task = Task(
        description=(
            "You have the transform output (violations, changes_made, docx_instructions) "
            "and the journal rules. "
            "Perform all 7 mandatory compliance checks:\n"
            "1. Citation ↔ Reference 1:1 consistency\n"
            "2. IMRAD structure completeness\n"
            "3. Reference age (>50% older than 10 years → warning)\n"
            "4. Self-citation rate (>30% same author → warning)\n"
            "5. Figure sequential numbering (no gaps)\n"
            "6. Table sequential numbering (no gaps)\n"
            "7. Abstract word count vs journal limit\n\n"
            "Return the compliance_report as JSON with keys: "
            "overall_score (0-100), breakdown (7 section scores + issues), "
            "changes_made, imrad_check, citation_consistency, warnings. "
            "Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        expected_output=(
            "Valid JSON compliance_report with overall_score, breakdown (7 sections "
            "each with score and issues list), changes_made, imrad_check, "
            "citation_consistency, and warnings."
        ),
        agent=validate_agent,
        context=[transform_task, interpret_task],
    )

    crew = Crew(
        agents=[ingest_agent, parse_agent, interpret_agent, transform_agent, validate_agent],
        tasks=[ingest_task, parse_task, interpret_task, transform_task, validate_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()
    raw_output = str(result)

    compliance_report = _safe_parse_compliance(raw_output)

    transform_raw = str(transform_task.output) if transform_task.output else "{}"
    docx_filename = _write_docx_from_transform(transform_raw, rules)

    return {
        "compliance_report": compliance_report,
        "docx_filename": docx_filename,
    }


def _safe_parse_compliance(raw: str) -> dict:
    """Parse compliance_report from final agent output with fallback."""
    try:
        return extract_json_from_llm(raw)
    except (ValueError, KeyError):
        return VALIDATE_FALLBACK.copy()


def _write_docx_from_transform(transform_raw: str, rules: dict) -> str:
    """
    Extract docx_instructions from transform output and write the DOCX file.
    Falls back to a minimal document on parse failure.
    """
    output_filename = f"formatted_{uuid.uuid4().hex[:8]}.docx"
    output_path = str(OUTPUTS_DIR / output_filename)

    try:
        transform_data = extract_json_from_llm(transform_raw)
        docx_instructions = transform_data.get("docx_instructions", {})
        if not docx_instructions:
            docx_instructions = {"rules": rules, "sections": []}
        write_formatted_docx(docx_instructions, output_path)
    except Exception:
        fallback_instructions = {
            "rules": rules,
            "sections": [
                {"type": "paragraph", "content": "Formatted document — see compliance report for details."}
            ],
        }
        write_formatted_docx(fallback_instructions, output_path)

    return output_filename
