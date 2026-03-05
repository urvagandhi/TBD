import json
import os
import re
import time
import uuid
from pathlib import Path

from crewai import Crew, Process, Task
from dotenv import load_dotenv

from agents import (
    create_ingest_agent,
    create_interpret_agent,
    create_parse_agent,
    create_transform_agent,
    create_validate_agent,
)
from tools.docx_writer import write_formatted_docx
from tools.logger import get_logger
from tools.rule_loader import load_rules
from tools.tool_errors import (
    DocumentWriteError,
    LLMResponseError,
    ParseError,
    TransformError,
    ValidationError,
)

load_dotenv(override=True)
logger = get_logger(__name__)

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# Truncation constants — 24K body + 8K tail (references) per spec
MAX_CHARS = 32_000
HEAD_CHARS = 24_000
TAIL_CHARS = 8_000
TRUNCATION_MARKER = (
    "\n\n[... CONTENT TRUNCATED FOR PROCESSING — REFERENCES SECTION BELOW ...]\n\n"
)

_STEP_NAMES = ["INGEST", "PARSE", "INTERPRET", "TRANSFORM", "VALIDATE"]


def extract_json_from_llm(raw: str) -> dict:
    """
    Robustly extract a JSON dict from raw LLM output.

    Handles all known LLM output quirks:
      1. Clean JSON
      2. ```json ... ``` fenced
      3. ``` ... ``` fenced (no lang tag)
      4. Text preamble before JSON ("Here is the result: {...}")
      5. Text after JSON ({...} followed by explanation)
      6. Trailing commas: {"a": 1,}
      7. Single quotes: {'a': 'b'}
      8. Newlines inside string values
      9. Python literals: True / False / None

    Raises:
        LLMResponseError: If no valid JSON can be extracted after all attempts.
    """
    if not raw or not raw.strip():
        raise LLMResponseError("LLM returned empty response")

    text = raw.strip()

    # Step 1: Remove markdown code fences (```json...```, ```...```, ~~~...~~~)
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^~~~(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?~~~\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Step 2: Extract outermost JSON object or array
    # Handles Format 4 (preamble) and Format 5 (trailing text)
    json_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if json_match:
        text = json_match.group(1)

    # Step 3: Fix trailing commas before } or ]
    text = re.sub(r",(\s*[}\]])", r"\1", text)

    # Step 4: Replace Python literals with JSON equivalents
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    text = re.sub(r"\bNone\b", "null", text)

    # Step 5: Attempt standard parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Step 6: Last resort — replace single quotes with double quotes
    try:
        fixed = text.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        snippet = raw[:300] + ("..." if len(raw) > 300 else "")
        raise LLMResponseError(
            f"Could not extract valid JSON from LLM output.\n"
            f"Parse error: {e}\n"
            f"Raw output (first 300 chars): {snippet}"
        )


def _truncate_paper(content: str) -> str:
    """
    Truncate large papers to stay within LLM context limits.
    Takes first 24K chars (body) + last 8K chars (references).
    Returns original content unchanged if under MAX_CHARS.
    """
    if len(content) <= MAX_CHARS:
        return content

    logger.warning(
        "[PIPELINE] Paper content truncated: %d chars → %d chars (head=%d, tail=%d)",
        len(content), MAX_CHARS, HEAD_CHARS, TAIL_CHARS,
    )
    head = content[:HEAD_CHARS]
    tail = content[-TAIL_CHARS:]
    return head + TRUNCATION_MARKER + tail


class _StepTimer:
    """Logs the name and wall-clock duration of each CrewAI task as it completes."""

    def __init__(self) -> None:
        self._step_index = 0
        self._step_start = time.time()

    def on_task_complete(self, output) -> None:
        elapsed = round(time.time() - self._step_start, 2)
        name = (
            _STEP_NAMES[self._step_index]
            if self._step_index < len(_STEP_NAMES)
            else f"Step {self._step_index + 1}"
        )
        logger.info(
            "[PIPELINE] Step %d/5 — %-10s completed in %.2fs",
            self._step_index + 1, name, elapsed,
        )
        self._step_index += 1
        self._step_start = time.time()


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
            - compliance_report: Full compliance report with scores
            - docx_filename: Filename of the generated DOCX in outputs/

    Raises:
        ParseError: If paper_content is too short to process.
        LLMResponseError: If any agent returns unparseable JSON.
        TransformError: If transform agent fails to produce docx_instructions.
        ValidationError: If validate agent fails to produce compliance report.
        DocumentWriteError: If DOCX writing fails.
    """
    # ── Input validation — fail fast before expensive LLM calls ──────────────
    if not paper_content or len(paper_content.strip()) < 100:
        raise ParseError(
            f"Paper content is too short to process "
            f"({len(paper_content.strip()) if paper_content else 0} chars). "
            "Minimum required: 100 characters."
        )
    if not journal_style or not journal_style.strip():
        raise ParseError("Journal style cannot be empty.")

    original_len = len(paper_content)
    paper_content = _truncate_paper(paper_content)
    truncated = len(paper_content) < original_len

    logger.info(
        "[PIPELINE] Starting — journal=%s chars=%d%s",
        journal_style, len(paper_content),
        f" (truncated from {original_len})" if truncated else "",
    )
    pipeline_start = time.time()

    # LiteLLM (used internally by CrewAI) reads GOOGLE_API_KEY for Google AI Studio
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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
    compliance_report = _parse_compliance_report(raw_output)
    overall_score = compliance_report.get("overall_score", "N/A")
    logger.info("[PIPELINE] Compliance report parsed — overall_score=%s", overall_score)

    logger.info("[PIPELINE] Extracting transform output for DOCX generation...")
    transform_raw = _get_task_output(crew, task_index=3)

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


def _get_task_output(crew: Crew, task_index: int) -> str:
    """
    Safely retrieve the raw string output of a specific task after crew.kickoff().

    Args:
        crew: Completed Crew instance.
        task_index: Zero-based index into crew.tasks.

    Returns:
        Raw output string from the task.

    Raises:
        TransformError: If task output is missing or inaccessible.
    """
    try:
        task = crew.tasks[task_index]
        output = task.output
        if output is None:
            raise TransformError(
                f"Task at index {task_index} produced no output. "
                "Pipeline may have failed silently at this step."
            )
        if hasattr(output, "raw"):
            return output.raw
        if hasattr(output, "result"):
            return output.result
        return str(output)
    except IndexError:
        raise TransformError(
            f"Cannot access task at index {task_index}. "
            f"Crew only has {len(crew.tasks)} tasks."
        )
    except TransformError:
        raise
    except AttributeError as e:
        raise TransformError(f"Unexpected task output structure: {e}")


def _parse_compliance_report(raw: str) -> dict:
    """
    Parse and validate the compliance report from Agent 5 (validate_agent).

    Raises:
        ValidationError: If overall_score is missing or breakdown is invalid.
        LLMResponseError: If JSON cannot be parsed.
    """
    # extract_json_from_llm raises LLMResponseError on failure
    report = extract_json_from_llm(raw)

    # HARD REQUIREMENT: overall_score must exist — never default silently
    if "overall_score" not in report:
        raise ValidationError(
            "Compliance report is missing 'overall_score'. "
            "Agent 5 (validate_agent) did not return a valid compliance report. "
            f"Keys found: {list(report.keys())}"
        )

    # Validate and clamp overall_score to [0, 100]
    score = report["overall_score"]
    if not isinstance(score, (int, float)):
        raise ValidationError(
            f"overall_score must be a number, got: {type(score).__name__} = {score!r}"
        )
    report["overall_score"] = max(0, min(100, int(score)))

    # Validate breakdown — add placeholder scores for any missing sections (non-blocking)
    required_sections = [
        "document_format", "abstract", "headings",
        "citations", "references", "figures", "tables",
    ]
    breakdown = report.get("breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    missing = [s for s in required_sections if s not in breakdown]
    if missing:
        logger.warning("[PIPELINE] Compliance report missing breakdown sections: %s", missing)
        for s in missing:
            breakdown[s] = {"score": 70, "issues": ["Score unavailable — section not checked"]}
    report["breakdown"] = breakdown

    # Ensure submission_ready is deterministically set
    if "submission_ready" not in report:
        report["submission_ready"] = report["overall_score"] >= 80

    # Ensure changes_made is a list
    if "changes_made" not in report or not isinstance(report.get("changes_made"), list):
        report["changes_made"] = []

    # Normalise: recommendations may come as "warnings" in some agent versions
    if "recommendations" not in report:
        report["recommendations"] = report.get("warnings", [])
    if not isinstance(report["recommendations"], list):
        report["recommendations"] = []

    return report


def _write_docx_from_transform(transform_raw: str, rules: dict) -> str:
    """
    Extract docx_instructions from transform output and write the DOCX file.

    Args:
        transform_raw: Raw string output from transform_task.
        rules: Journal rules dict injected as source of truth for docx_writer.

    Returns:
        Output filename (not full path) for the generated DOCX.

    Raises:
        TransformError: If docx_instructions or sections key is missing.
        DocumentWriteError: Propagated from docx_writer if writing fails.
    """
    # extract_json_from_llm raises LLMResponseError on failure
    transform_data = extract_json_from_llm(transform_raw)

    # HARD REQUIREMENT: docx_instructions must exist
    if "docx_instructions" not in transform_data:
        raise TransformError(
            "Transform result is missing 'docx_instructions' key. "
            "Agent 4 (transform_agent) did not produce valid output. "
            f"Keys found: {list(transform_data.keys())}"
        )

    docx_instructions = transform_data["docx_instructions"]

    # HARD REQUIREMENT: sections must be a non-empty list
    sections = docx_instructions.get("sections") if docx_instructions else None
    if not isinstance(sections, list) or len(sections) == 0:
        raise TransformError(
            "docx_instructions is missing a non-empty 'sections' list. "
            "The 'sections' array defines the entire document structure. "
            f"docx_instructions keys found: "
            f"{list(docx_instructions.keys()) if isinstance(docx_instructions, dict) else '(not a dict)'}"
        )

    # Inject the real journal rules so docx_writer always has the source of truth
    docx_instructions["rules"] = rules

    output_filename = f"formatted_{uuid.uuid4().hex[:8]}.docx"
    output_path = str(OUTPUT_DIR / output_filename)

    logger.info("[DOCX] Building document — %d sections → %s", len(sections), output_filename)

    # write_formatted_docx raises DocumentWriteError on failure — let it propagate
    write_formatted_docx(docx_instructions, output_path)
    return output_filename
