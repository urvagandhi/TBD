import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

from crewai import Crew, Process, Task

logger = logging.getLogger(__name__)

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


_STEP_NAMES = ["INGEST", "PARSE", "INTERPRET", "TRANSFORM", "VALIDATE"]


class _StepTimer:
    """Logs the name and wall-clock duration of each CrewAI task as it completes."""

    def __init__(self) -> None:
        self._step_index = 0
        self._step_start = time.time()

    def on_task_complete(self, output) -> None:
        elapsed = round(time.time() - self._step_start, 2)
        name = _STEP_NAMES[self._step_index] if self._step_index < len(_STEP_NAMES) else f"Step {self._step_index + 1}"
        logger.info(
            "[PIPELINE] Step %d/5 — %-10s completed in %.2fs",
            self._step_index + 1, name, elapsed,
        )
        self._step_index += 1
        self._step_start = time.time()


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
    original_len = len(paper_content)
    paper_content = _truncate_paper_content(paper_content)
    truncated = len(paper_content) < original_len

    logger.info(
        "[PIPELINE] Starting — journal=%s chars=%d%s",
        journal_style, len(paper_content),
        f" (truncated from {original_len})" if truncated else "",
    )
    pipeline_start = time.time()

    # LiteLLM (used internally by CrewAI) reads GOOGLE_API_KEY for Google AI Studio
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    llm = f"gemini/{model_name}"
    logger.info("[PIPELINE] LLM = %s", llm)

    logger.info("[PIPELINE] Loading rules for '%s'...", journal_style)
    rules = load_rules(journal_style)
    logger.info("[PIPELINE] Rules loaded — %d sections", len(rules))

    logger.info("[PIPELINE] Initialising 5 agents...")
    ingest_agent = create_ingest_agent(llm)
    parse_agent = create_parse_agent(llm)
    interpret_agent = create_interpret_agent(llm)
    transform_agent = create_transform_agent(llm)
    validate_agent = create_validate_agent(llm)
    logger.info("[PIPELINE] Agents ready")

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

    step_timer = _StepTimer()

    crew = Crew(
        agents=[ingest_agent, parse_agent, interpret_agent, transform_agent, validate_agent],
        tasks=[ingest_task, parse_task, interpret_task, transform_task, validate_task],
        process=Process.sequential,
        verbose=True,
        task_callback=step_timer.on_task_complete,
    )

    logger.info("[PIPELINE] Kicking off CrewAI — 5 steps: %s", " → ".join(_STEP_NAMES))
    result = crew.kickoff()
    raw_output = str(result)

    logger.info("[PIPELINE] All steps complete — parsing compliance report...")
    compliance_report = _safe_parse_compliance(raw_output)
    overall_score = compliance_report.get("overall_score", "N/A")
    logger.info("[PIPELINE] Compliance report parsed — overall_score=%s", overall_score)

    transform_raw = str(transform_task.output) if transform_task.output else "{}"

    logger.info("[PIPELINE] Writing formatted DOCX...")
    t0 = time.time()
    docx_filename = _write_docx_from_transform(transform_raw, rules)
    logger.info("[PIPELINE] DOCX written — file=%s in %.2fs", docx_filename, time.time() - t0)

    total_elapsed = round(time.time() - pipeline_start, 1)
    logger.info(
        "[PIPELINE] Done — score=%s docx=%s total=%.1fs",
        overall_score, docx_filename, total_elapsed,
    )

    return {
        "compliance_report": compliance_report,
        "docx_filename": docx_filename,
    }


def _safe_parse_compliance(raw: str) -> dict:
    """Parse compliance_report from final agent output with fallback."""
    try:
        return extract_json_from_llm(raw)
    except (ValueError, KeyError) as e:
        logger.warning("[PIPELINE] Compliance JSON parse failed (%s) — using fallback", e)
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
            logger.warning("[DOCX] docx_instructions missing from transform output — using empty sections")
            docx_instructions = {"rules": rules, "sections": []}
        sections_count = len(docx_instructions.get("sections", []))
        logger.info("[DOCX] Building document — %d sections", sections_count)
        write_formatted_docx(docx_instructions, output_path)
    except Exception as e:
        logger.warning("[DOCX] Transform parse failed (%s) — writing fallback document", e)
        fallback_instructions = {
            "rules": rules,
            "sections": [
                {"type": "paragraph", "content": "Formatted document — see compliance report for details."}
            ],
        }
        write_formatted_docx(fallback_instructions, output_path)

    return output_filename
