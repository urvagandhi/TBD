import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from tools.text_chunker import split_into_sections
from tools.pdf_reader import extract_pdf_text

from crewai import Agent, Crew, Process, Task, LLM
from dotenv import load_dotenv

from agents import (
    create_ingest_agent,
    create_parse_agent,
    create_transform_agent,
    create_validate_agent,
)
from agents.validate_agent import SECTION_WEIGHTS
from tools.compliance_checker import apply_deterministic_checks, run_deterministic_checks
from tools.docx_reader import extract_docx_text
from tools.docx_writer import build_apa_docx, build_ieee_docx, transform_docx_in_place, write_formatted_docx
from tools.logger import get_logger
from tools.media_extractor import extract_all_media, map_figures_to_images, map_tables_to_captions
from tools.pre_format_scorer import score_pre_format
from tools.rule_loader import load_rules
from tools.tool_errors import (
    DocumentWriteError,
    LLMResponseError,
    ParseError,
    TransformError,
    ValidationError,
)

load_dotenv(override=True)

# Override litellm default max_tokens (4096) — far too low for our pipeline.
# The TRANSFORM agent outputs full paper content as structured JSON which
# easily exceeds 4096 tokens. Gemini 2.5 Flash supports up to 65535 output tokens.
import litellm
litellm.max_tokens = int(os.getenv("GEMINI_MAX_TOKENS", "65536"))
# Set global litellm request timeout so httpx doesn't use its own (low) default.
litellm.request_timeout = int(os.getenv("LLM_TIMEOUT", "300"))
# Retry on transient failures (429, 500, timeout)
litellm.num_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))

logger = get_logger(__name__)


def merge_broken_lines(raw_text: str) -> str:
    """
    PDF-extracted text has hard line breaks mid-sentence.
    This merges them into proper paragraphs BEFORE the LLM sees the text.

    Rules:
    - If a line ends WITHOUT sentence-ending punctuation (. ? ! :)
      AND the next line starts with a lowercase letter or continues a word,
      merge them with a space.
    - If a line ends with a hyphen (word break like "entero-\\nhemorrhagic"),
      merge WITHOUT space and remove hyphen.
    - Preserve blank lines as paragraph breaks.
    - Preserve lines that start numbered references (e.g., "1. Author...")
    """
    lines = raw_text.split('\n')
    merged = []
    buffer = ""

    for line in lines:
        stripped = line.strip()

        # Blank line = paragraph break
        if not stripped:
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append("")
            continue

        # If buffer is empty, start new buffer
        if not buffer:
            buffer = stripped
            continue

        # Check if previous buffer line ends with hyphenated word break
        if buffer.endswith('-') and stripped and stripped[0].islower():
            buffer = buffer[:-1] + stripped  # merge without space, remove hyphen
        # Check if this looks like a continuation (no sentence-end + lowercase start)
        elif (buffer and
              buffer[-1] not in '.?!:' and
              stripped and
              (stripped[0].islower() or stripped[0] in '(,;')):
            buffer = buffer + " " + stripped
        else:
            merged.append(buffer)
            buffer = stripped

    if buffer:
        merged.append(buffer)

    return '\n'.join(merged)

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


# In-memory pipeline cache: identical (paper, journal) pairs return instantly
PIPELINE_CACHE: dict = {}

_STEP_NAMES = ["INGEST", "PARSE", "TRANSFORM", "VALIDATE"]

# Rule reference lookup — keyed by journal (first word, lowercase) → topic → section ref
# Used to enrich changes_made entries with authoritative rule citations for judge visibility.
RULE_REFERENCES: dict[str, dict[str, str]] = {
    "apa": {
        "abstract":           "APA 7th §2.9",
        "abstract_word":      "APA 7th §2.9",
        "heading":            "APA 7th §2.27",
        "headings":           "APA 7th §2.27",
        "citation":           "APA 7th §8.11",
        "citations":          "APA 7th §8.11",
        "in_text_citation":   "APA 7th §8.11",
        "et_al":              "APA 7th §8.17",
        "reference":          "APA 7th §9.4",
        "references":         "APA 7th §9.4",
        "hanging_indent":     "APA 7th §9.43",
        "doi":                "APA 7th §9.34",
        "title_page":         "APA 7th §2.3",
        "font":               "APA 7th §2.19",
        "document_format":    "APA 7th §2.19",
        "line_spacing":       "APA 7th §2.21",
        "margins":            "APA 7th §2.22",
        "figures":            "APA 7th §7.22",
        "tables":             "APA 7th §7.4",
        "keywords":           "APA 7th §2.13",
    },
    "ieee": {
        "abstract":           "IEEE Style §II",
        "heading":            "IEEE Style §II-A",
        "headings":           "IEEE Style §II-A",
        "citation":           "IEEE Ref Guide §III",
        "citations":          "IEEE Ref Guide §III",
        "in_text_citation":   "IEEE Ref Guide §III",
        "et_al":              "IEEE Ref Guide §II",
        "reference":          "IEEE Ref Guide §V",
        "references":         "IEEE Ref Guide §V",
        "figures":            "IEEE Style §IV",
        "tables":             "IEEE Style §III-B",
        "font":               "IEEE Style §I",
        "document_format":    "IEEE Style §I",
        "line_spacing":       "IEEE Style §I",
        "margins":            "IEEE Style §I",
        "keywords":           "IEEE Style §II",
    },
    "vancouver": {
        "abstract":           "Vancouver §2",
        "heading":            "Vancouver §3",
        "headings":           "Vancouver §3",
        "citation":           "Vancouver §6",
        "citations":          "Vancouver §6",
        "in_text_citation":   "Vancouver §6",
        "et_al":              "Vancouver §6.2",
        "reference":          "Vancouver §7",
        "references":         "Vancouver §7",
        "figures":            "Vancouver §4",
        "tables":             "Vancouver §5",
        "font":               "Vancouver §1",
        "document_format":    "Vancouver §1",
        "line_spacing":       "Vancouver §1",
        "margins":            "Vancouver §1",
        "keywords":           "Vancouver §2",
    },
    "springer": {
        "abstract":           "Springer §2.1",
        "heading":            "Springer §2.3",
        "headings":           "Springer §2.3",
        "citation":           "Springer §3.1",
        "citations":          "Springer §3.1",
        "in_text_citation":   "Springer §3.1",
        "et_al":              "Springer §3.1",
        "reference":          "Springer §3.2",
        "references":         "Springer §3.2",
        "figures":            "Springer §4.1",
        "tables":             "Springer §4.2",
        "font":               "Springer §2.6",
        "document_format":    "Springer §2.6",
        "line_spacing":       "Springer §2.6",
        "margins":            "Springer §2.6",
        "keywords":           "Springer §2.2",
    },
    "chicago": {
        "abstract":           "Chicago 17th §A.2",
        "heading":            "Chicago 17th §A.1",
        "headings":           "Chicago 17th §A.1",
        "citation":           "Chicago 17th §15.2",
        "citations":          "Chicago 17th §15.2",
        "in_text_citation":   "Chicago 17th §15.2",
        "et_al":              "Chicago 17th §15.28",
        "reference":          "Chicago 17th §14.1",
        "references":         "Chicago 17th §14.1",
        "hanging_indent":     "Chicago 17th §14.22",
        "figures":            "Chicago 17th §3.14",
        "tables":             "Chicago 17th §3.51",
        "font":               "Chicago 17th §A.1",
        "document_format":    "Chicago 17th §A.1",
        "line_spacing":       "Chicago 17th §A.1",
        "margins":            "Chicago 17th §A.1",
        "keywords":           "Chicago 17th §A.2",
    },
}

# Keyword → rule topic mapping for enriching plain-string changes_made entries
_CHANGE_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["abstract", "word count", "word limit", "words over"], "abstract"),
    (["heading", "h1", "h2", "h3", "title case", "uppercase", "sentence case", "bold"], "headings"),
    (["citation", "in-text", "in_text", "author-date", "numbered citation", "cite"], "citations"),
    (["et al"], "et_al"),
    (["reference", "bibliography", "hanging indent", "alphabetical", "sorted ref"], "references"),
    (["doi", "url", "link", "https"], "doi"),
    (["figure", "fig.", "caption below", "caption above"], "figures"),
    (["table", "tbl."], "tables"),
    (["font", "times new roman", "arial", "calibri", "typeface", "serif"], "font"),
    (["line spacing", "double space", "single space", "spacing"], "line_spacing"),
    (["margin", "page size", "page layout"], "margins"),
    (["keyword", "key word", "index term"], "keywords"),
]


def _enrich_changes_made(changes: list, journal_style: str) -> list[dict]:
    """
    Enrich changes_made entries with authoritative rule references.

    Accepts either:
      - Structured dicts {what, rule_reference, why} — LLM returned structured output
      - Plain strings — keyword-matched to assign rule_reference from RULE_REFERENCES

    Returns a list of {what, rule_reference, why} dicts, always.
    Empty or non-list input returns an empty list.
    """
    if not isinstance(changes, list):
        return []

    # Extract journal key: "APA 7th Edition" → "apa", "Chicago 17th Edition" → "chicago"
    journal_key = journal_style.lower().split()[0]
    refs = RULE_REFERENCES.get(journal_key, {})

    enriched: list[dict] = []
    for change in changes:
        if isinstance(change, dict):
            # Already structured — fill in any missing fields
            what = change.get("what") or change.get("description") or str(change)
            ref  = change.get("rule_reference") or ""
            if not ref:
                # Try keyword match on the 'what' field
                ref = _keyword_match_ref(what, refs)
            why = change.get("why") or f"Required by {ref}"
            enriched.append({"what": what, "rule_reference": ref, "why": why})
        elif isinstance(change, str) and change.strip():
            ref = _keyword_match_ref(change, refs)
            enriched.append({
                "what": change,
                "rule_reference": ref,
                "why": f"Required by {ref}",
            })

    return enriched


def _keyword_match_ref(text: str, refs: dict) -> str:
    """Return a rule reference string by keyword-matching against a journal's refs dict."""
    lower = text.lower()
    for keywords, topic in _CHANGE_KEYWORD_MAP:
        if any(kw in lower for kw in keywords):
            if topic in refs:
                return refs[topic]
    return "Journal guidelines"


# ── 8B: Response schema validation ────────────────────────────────────────────
DOCX_INSTRUCTIONS_SCHEMA = {
    "type": "object",
    "required": ["sections"],
    "properties": {
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["type", "content"],
                "properties": {
                    "type": {"type": "string"},
                    "content": {"type": ["string", "null"]},
                },
            },
        },
    },
}


def _validate_docx_instructions(docx_instructions: dict) -> None:
    """
    Validate docx_instructions schema using jsonschema before DOCX write.

    Raises TransformError with a human-readable message on violation.
    Non-blocking if jsonschema is unavailable.
    """
    try:
        import jsonschema
        jsonschema.validate(instance=docx_instructions, schema=DOCX_INSTRUCTIONS_SCHEMA)
        logger.debug("[DOCX_VALID] docx_instructions schema OK — %d sections",
                     len(docx_instructions.get("sections", [])))
    except ImportError:
        logger.warning("[DOCX_VALID] jsonschema not installed — skipping schema validation")
    except Exception as e:
        # Extract the section index if the error occurred within the sections list
        path_msg = ""
        if hasattr(e, "path") and len(e.path) >= 2 and e.path[0] == "sections":
            idx = e.path[1]
            path_msg = f" at sections[{idx}]"
        
        msg = e.message if hasattr(e, "message") else str(e)
        logger.error("[TRANSFORM] Schema validation failed%s: %s", path_msg, msg)
        raise TransformError(
            f"docx_instructions failed schema validation{path_msg}: {msg}. "
            "Transform agent returned malformed output."
        )


# ── 8A: Verbatim content guard ─────────────────────────────────────────────────
def _guard_section_contents(sections: list, paper_content: Optional[str]) -> list:
    """
    Verbatim content guard for the PDF/TXT DOCX rebuild path.

    Pass 1 — filters empty/null content sections (prevents blank paragraphs).
    Pass 2 — restores abstract from original paper text if LLM truncated it.

    Never raises — all failures are logged as warnings.
    """
    # Pass 1: Remove empty sections
    cleaned = [s for s in sections if s.get("content") and str(s["content"]).strip()]
    removed = len(sections) - len(cleaned)
    if removed:
        logger.info("[DOCX_GUARD] Filtered %d empty/null sections", removed)

    if not paper_content:
        return cleaned

    # Pass 2: Restore truncated abstract from original text
    try:
        orig_sections = split_into_sections(paper_content)
        orig_map = {sec.name.lower(): sec.text for sec in orig_sections}

        for section in cleaned:
            sec_type = str(section.get("type", "")).lower()
            content = str(section.get("content", ""))
            if sec_type == "abstract" and len(content.strip()) < 100:
                original_abstract = orig_map.get("abstract", "")
                if len(original_abstract) > len(content):
                    section["content"] = original_abstract
                    logger.info(
                        "[DOCX_GUARD] Abstract restored from original (%d → %d chars)",
                        len(content), len(original_abstract),
                    )
    except Exception as _e:
        logger.warning("[DOCX_GUARD] Content guard pass 2 failed (non-fatal): %s", _e)

    return cleaned


def _hash_content(paper_text: str, journal: str) -> str:
    """SHA-256 fingerprint of (paper_text + journal) for cache keying."""
    payload = f"{journal}::{paper_text}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _build_structured_paper(paper_content: str) -> tuple[str, dict]:
    """
    Pre-label the paper with IMRAD section delimiters so agents understand
    document structure without guessing.

    Uses text_chunker.split_into_sections() to detect boundaries in Python,
    then injects clear section header markers. No content is removed or
    truncated — structure is ADDED, not subtracted.

    Returns:
        (structured_text, section_stats) where section_stats maps section
        name → {word_count, char_count} for injecting into agent prompts.
    """
    sections = split_into_sections(paper_content)
    if len(sections) <= 1:
        # No section headers detected — return as-is (short papers, abstracts only, etc.)
        return paper_content, {}

    parts: list[str] = []
    stats: dict = {}

    for sec in sections:
        stats[sec.name] = {
            "word_count": len(sec.text.split()),
            "char_count":  sec.chars,
        }
        if sec.name == "preamble":
            parts.append(sec.text)
        else:
            label = f"\n{'=' * 60}\n[SECTION: {sec.raw_name.upper()}]\n{'=' * 60}"
            parts.append(f"{label}\n{sec.text}")

    structured = "\n\n".join(parts)
    logger.debug(
        "[PIPELINE] Paper pre-structured — %d sections: %s | total chars: %d",
        len(sections), list(stats.keys()), len(structured),
    )
    return structured, stats


def _build_section_rules_guide(rules: dict, section_stats: dict) -> str:
    """
    Build a compact, section-by-section formatting guide for the transform agent.

    Maps each IMRAD section type to its specific journal rules + detected stats.
    This gives the transform agent precise, actionable instructions per section
    instead of a flat rules blob, dramatically improving per-section accuracy.

    Returns a human-readable multi-line string injected into the transform task.
    """
    lines: list[str] = ["=== SECTION-BY-SECTION FORMATTING GUIDE ===", ""]

    # ── Abstract ──────────────────────────────────────────────────────────────
    abs_rules = rules.get("abstract", {})
    abs_stat  = section_stats.get("abstract", {})
    abs_words = abs_stat.get("word_count", "?")
    abs_limit = abs_rules.get("max_words")
    if isinstance(abs_words, int) and isinstance(abs_limit, int) and abs_words > abs_limit:
        abs_status = f"⚠ OVER LIMIT BY {abs_words - abs_limit} WORDS — TRIM REQUIRED"
    else:
        abs_status = f"✓ within limit ({abs_words}/{abs_limit or '?'} words)"
    lines += [
        f"[ABSTRACT]  {abs_status}",
        f"  limit: {abs_limit or 'not specified'} words",
    ]
    if abs_rules.get("structured"):
        lines.append("  structured abstract required: Background / Objective / Methods / Results / Conclusion")
    if abs_rules.get("keywords_required"):
        lines.append(f"  keywords: required — max {abs_rules.get('max_keywords', '?')} terms")
    lines.append("")

    # ── Headings ──────────────────────────────────────────────────────────────
    h_rules = rules.get("headings", {})
    lines.append("[HEADINGS]  — apply case/style to EVERY heading in the document")
    for level in ["H1", "H2", "H3"]:
        h = h_rules.get(level, {})
        if h:
            lines.append(
                f"  {level}: case={h.get('case', '?')!r}  "
                f"bold={h.get('bold', '?')}  "
                f"italic={h.get('italic', False)}  "
                f"centered={h.get('centered', False)}  "
                f"font_size={h.get('font_size', 'inherit')}pt"
            )
    lines.append("")

    # ── In-text citations ─────────────────────────────────────────────────────
    cit_rules = rules.get("citations", {})
    lines += [
        "[IN-TEXT CITATIONS]",
        f"  format: {cit_rules.get('style', cit_rules.get('format', '?'))}  "
        f"(numbered = [1], [2] style  |  author-date = (Smith, 2020) style)",
        f"  et_al_threshold: {cit_rules.get('et_al_threshold', '?')} authors",
    ]
    if cit_rules.get("ibid_allowed") is not None:
        lines.append(f"  ibid allowed: {cit_rules.get('ibid_allowed')}")
    lines.append("")

    # ── References list ───────────────────────────────────────────────────────
    ref_rules = rules.get("references", {})
    ref_stat  = section_stats.get("references", section_stats.get("bibliography", {}))
    lines += [
        "[REFERENCES LIST]",
        f"  ordering: {ref_rules.get('ordering', 'alphabetical')}",
        f"  style: {ref_rules.get('style', '?')}",
        f"  detected section size: {ref_stat.get('word_count', '?')} words",
    ]
    lines.append("")

    # ── Document / page format ────────────────────────────────────────────────
    doc_rules = rules.get("document", {})
    margins   = doc_rules.get("margins", {})
    lines += [
        "[DOCUMENT FORMAT  — apply to ALL body paragraphs]",
        f"  font: {doc_rules.get('font', '?')}",
        f"  font_size: {doc_rules.get('font_size', '?')}pt",
        f"  line_spacing: {doc_rules.get('line_spacing', '?')}",
        f"  margins (inches):  "
        f"top={margins.get('top', '?')}  "
        f"bottom={margins.get('bottom', '?')}  "
        f"left={margins.get('left', '?')}  "
        f"right={margins.get('right', '?')}",
    ]
    lines.append("")

    # ── Figures & Tables ──────────────────────────────────────────────────────
    fig_rules = rules.get("figures", {})
    tbl_rules = rules.get("tables", {})
    lines.append("[FIGURES & TABLES]")
    if fig_rules.get("caption_position"):
        lines.append(
            f"  figure caption: {fig_rules['caption_position']} figure  |  "
            f"format: {fig_rules.get('caption_format', '?')}"
        )
    if tbl_rules.get("caption_position"):
        lines.append(
            f"  table caption: {tbl_rules['caption_position']} table  |  "
            f"format: {tbl_rules.get('caption_format', '?')}"
        )
    lines.append("")
    lines.append("=== END OF SECTION GUIDE — apply each section's rules precisely ===")

    return "\n".join(lines)


def _extract_first_json_block(text: str) -> str | None:
    """
    Balanced-bracket extraction of the LARGEST complete JSON object from text.

    LLMs (especially Gemini 2.5 Flash with thinking) often output reasoning
    text containing small JSON snippets BEFORE the actual large JSON output.
    This function finds ALL complete JSON blocks and returns the largest one,
    which is almost always the intended output.

    Returns the JSON substring on success, None if no valid block found.
    """
    blocks = []
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        search_start = 0
        while search_start < len(text):
            start = text.find(open_ch, search_start)
            if start == -1:
                break
            depth = 0
            in_string = False
            escape_next = False
            found_end = -1
            for i, ch in enumerate(text[start:], start=start):
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        found_end = i
                        break
            if found_end > start:
                block = text[start:found_end + 1]
                blocks.append(block)
                search_start = found_end + 1
            else:
                search_start = start + 1

    if not blocks:
        return None

    # Return the largest block — the actual output, not reasoning snippets
    return max(blocks, key=len)


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

    # Step 0: Strip Gemini thinking prefix and CrewAI markers
    # Gemini 2.5 Flash outputs "Thought: ..." before the actual answer.
    # CrewAI wraps with "Final Answer: ..." marker.
    if text.startswith("Thought:"):
        # Find "Final Answer:" marker — everything after it is the actual output
        fa_match = re.search(r"Final Answer:\s*", text)
        if fa_match:
            text = text[fa_match.end():].strip()

    # Step 1: Remove markdown code fences (```json...```, ```...```, ~~~...~~~)
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^~~~(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?~~~\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Step 2: Balanced bracket extraction — handles preamble and trailing text
    extracted = _extract_first_json_block(text)
    if extracted:
        text = extracted

    # Step 3: Fix trailing commas before } or ]
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    
    # NEW Step: Fix missing commas between objects in a list
    # This matches } { and replaces with }, { (allowing for whitespace)
    text = re.sub(r'}\s*\n*\s*{', '}, {', text)
    # Also fix missing commas between key-value pairs where the next key starts on a new line
    # Match "value" \n "key":
    text = re.sub(r'("\s*:\s*(?:"[^"]*"|[\dtruefalsenull\.]+))\s*\n+\s*"', r'\1, \n"', text)

    # NEW Step: Fix unescaped newlines inside strings (common in LLM output)
    def fix_newlines(m):
        return m.group(0).replace('\n', '\\n').replace('\r', '')
    text = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_newlines, text, flags=re.DOTALL)

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
        # Improved single-quote to double-quote conversion
        # This replaces single quotes that look like they are delimiting strings
        fixed = re.sub(r"(^|[\{\s,\[])'([^']*)'([\s,\}\]]|$)", r'\1"\2"\3', text)
        # If that didn't help, try the old hammer
        if fixed == text:
            fixed = text.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        snippet = raw[:300] + ("..." if len(raw) > 300 else "")
        raise LLMResponseError(
            f"Could not extract valid JSON from LLM output.\n"
            f"Parse error: {e}\n"
            f"Note: This often happens if the LLM output was truncated or contained unescaped characters.\n"
            f"Raw output (first 300 chars): {snippet}"
        )




class _StepTimer:
    """Logs wall-clock duration of each CrewAI task, updates progress callback."""

    # Progress percentages after each step completes
    _STEP_PROGRESS = [20, 40, 75, 95]

    def __init__(self, progress_callback=None) -> None:
        self._step_index = 0
        self._step_start = time.time()
        self._pipeline_start = time.time()
        self.stage_times: dict = {}
        self._progress_callback = progress_callback

    def on_task_complete(self, output) -> None:
        elapsed = round(time.time() - self._step_start, 2)
        total_elapsed = round(time.time() - self._pipeline_start, 1)
        name = (
            _STEP_NAMES[self._step_index]
            if self._step_index < len(_STEP_NAMES)
            else f"Step {self._step_index + 1}"
        )
        self.stage_times[name.lower()] = elapsed

        progress = (
            self._STEP_PROGRESS[self._step_index]
            if self._step_index < len(self._STEP_PROGRESS)
            else 95
        )

        logger.info(
            "[PIPELINE] Step %d/4 — %-10s completed in %.2fs (total: %.1fs, progress: %d%%)",
            self._step_index + 1, name, elapsed, total_elapsed, progress,
        )

        # Notify caller (main.py) to update JOB_STORE
        if self._progress_callback:
            self._progress_callback(
                step_index=self._step_index + 1,  # completed step (1-indexed)
                progress=progress,
                step_name=name,
                step_elapsed=elapsed,
                total_elapsed=total_elapsed,
            )

        self._step_index += 1
        self._step_start = time.time()


def _validate_task_outputs(crew: Crew) -> str:
    """
    Central pipeline guard — validate all task outputs after crew.kickoff().

    For JSON steps (parse, transform, validate), uses extract_json_from_llm()
    to properly strip chain-of-thought preamble before checking required keys.
    Raises TransformError immediately on any failure.

    Returns:
        run_id (str): Unique 6-char hex identifier for this pipeline run.
    """
    import uuid
    from pathlib import Path

    # Save intermediate outputs to a per-run subfolder for clean organization
    run_id = uuid.uuid4().hex[:6]
    run_dir = Path(__file__).parent / "outputs" / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Step 0: ingest — just needs non-empty text output
    # Steps 1-3: need valid JSON with specific keys
    json_validations = [
        (1, "parse",     "sections"),
        (2, "transform", "docx_instructions"),
        (3, "validate",  "overall_score"),
    ]

    for idx in range(4):
        name = ["ingest", "parse", "transform", "validate"][idx]
        try:
            raw = _get_task_output(crew, idx)
            debug_path = run_dir / f"{idx+1}_{name}.txt"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(raw)
        except TransformError as e:
            raise TransformError(f"Pipeline task '{name}' (step {idx + 1}) produced no output: {e}")

        if idx == 0:
            # Ingest: just check non-empty
            if not raw or not raw.strip():
                raise TransformError(
                    f"Pipeline task 'ingest' (step 1) produced empty output."
                )
        else:
            # JSON steps: extract JSON properly (strips Thought: preamble)
            _, _, required_key = next(v for v in json_validations if v[0] == idx)
            try:
                parsed = extract_json_from_llm(raw)
            except LLMResponseError as e:
                snippet = (raw[:200] + "...") if len(raw) > 200 else raw
                raise TransformError(
                    f"Pipeline task '{name}' (step {idx + 1}) failed JSON extraction: {e}. "
                    f"Output snippet: {snippet!r}"
                )
            if required_key not in parsed:
                raise TransformError(
                    f"Pipeline task '{name}' (step {idx + 1}) missing required key "
                    f"'{required_key}'. Keys found: {list(parsed.keys())}"
                )

        logger.debug("[PIPELINE] Task '%s' output validated OK (%d chars)", name, len(raw))

    return run_id


def run_pipeline(paper_content: str, journal_style: str, source_docx_path: Optional[str] = None, rules_override: Optional[dict] = None, progress_callback=None, source_file_path: Optional[str] = None) -> dict:
    """
    Execute the 5-agent CrewAI sequential pipeline.

    Pipeline: INGEST → PARSE → INTERPRET → TRANSFORM → VALIDATE

    Args:
        paper_content: Full extracted text from uploaded PDF/DOCX.
        journal_style: One of "APA 7th Edition", "IEEE", "Vancouver",
                       "Springer", "Chicago".
        rules_override: Pre-merged rules dict (with overrides applied).
                        If provided, skips load_rules() and uses this directly.

    Returns:
        dict with keys:
            - compliance_report: Full compliance report with scores
            - docx_filename: Filename of the generated DOCX in outputs/
            - output_metadata: {filename, size_bytes, size_kb}
            - pipeline_metrics: {stage_times, total_runtime}

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

    # ── Improvement 7: Cache check — return instantly for identical submissions ──
    cache_key = _hash_content(paper_content, journal_style)
    if cache_key in PIPELINE_CACHE:
        logger.info(
            "[PIPELINE] Cache HIT — journal=%s hash=%s (returning cached result)",
            journal_style, cache_key[:12],
        )
        return PIPELINE_CACHE[cache_key]

    logger.info(
        "[PIPELINE] Starting — journal=%s chars=%d cache_miss=%s",
        journal_style, len(paper_content), cache_key[:12],
    )
    pipeline_start = time.time()

    # LiteLLM (used internally by CrewAI) reads GOOGLE_API_KEY for Google AI Studio
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    llm_timeout = int(os.getenv("LLM_TIMEOUT", "300"))

    # Use high max_tokens to prevent truncation — Gemini Flash uses
    # chain-of-thought "Thought:" tokens that consume output budget.
    max_tokens = int(os.getenv("GEMINI_MAX_TOKENS", "65536"))
    llm = LLM(
        model=f"gemini/{model_name}",
        timeout=llm_timeout,
        temperature=0,
        max_tokens=max_tokens,
    )
    logger.info("[PIPELINE] LLM = %s (max_tokens=%d)", model_name, max_tokens)

    if rules_override:
        logger.info("[PIPELINE] Using pre-merged rules (with overrides) — %d sections", len(rules_override))
        rules = rules_override
    else:
        logger.info("[PIPELINE] Loading rules for '%s'...", journal_style)
        rules = load_rules(journal_style)
        logger.info("[PIPELINE] Rules loaded — %d sections", len(rules))

    # ── Pre-pipeline: merge broken PDF lines ─────────────────────────────────
    paper_content = merge_broken_lines(paper_content)
    logger.info("[PIPELINE] Broken lines merged — %d chars after merge", len(paper_content))

    # ── Section-aware context building ───────────────────────────────────────
    # Pre-label the paper with IMRAD section delimiters (no truncation — only adds structure).
    # This gives INGEST a structurally clear document, dramatically improving
    # per-section label accuracy and downstream agent precision.
    structured_paper, section_stats = _build_structured_paper(paper_content)
    section_rules_guide = _build_section_rules_guide(rules, section_stats)
    logger.info(
        "[PIPELINE] Section-aware context built — %d sections detected: %s",
        len(section_stats), list(section_stats.keys()),
    )

    # ── Media extraction — side-channel for images & tables (bypasses LLM) ──
    # Determine source file path: prefer explicit param, fall back to source_docx_path
    _media_source = source_file_path or source_docx_path
    media_data: dict = {"source_type": "unknown", "raw_images": [], "raw_tables": []}
    if _media_source and Path(_media_source).exists():
        try:
            media_data = extract_all_media(_media_source)
            logger.info(
                "[PIPELINE] Media extracted — %d images, %d tables from %s (%s)",
                len(media_data["raw_images"]), len(media_data["raw_tables"]),
                Path(_media_source).name, media_data["source_type"],
            )
        except Exception as _media_err:
            logger.warning("[PIPELINE] Media extraction failed (non-fatal): %s", _media_err)
    else:
        logger.info("[PIPELINE] No source file for media extraction — figures/tables will use placeholders")

    from agents.transform_agent import detect_style
    style_key = detect_style(journal_style)  # "apa" | "ieee" | "generic"
    is_apa = style_key == "apa"
    logger.info("[PIPELINE] Initialising 4 agents — journal=%s style_key=%s", journal_style, style_key)
    ingest_agent = create_ingest_agent(llm)
    parse_agent = create_parse_agent(llm)
    transform_agent = create_transform_agent(llm, journal_style=journal_style)
    validate_agent = create_validate_agent(llm, journal_style=journal_style)
    logger.info("[PIPELINE] Agents ready")

    ingest_task = Task(
        description=(
            f"Label the following paper with structural markers. Follow ALL rules exactly.\n\n"
            f"<paper>\n{structured_paper}\n</paper>"
        ),
        expected_output=(
            "The complete paper text with all structural labels inserted. "
            "Must start with [CITATION_STYLE:...] and [SOURCE_FORMAT:...] lines. "
            "Then the full paper text with [TITLE_START]...[TITLE_END], "
            "[AUTHORS_START]...[AUTHORS_END], [ABSTRACT_START]...[ABSTRACT_END], "
            "[HEADING_H1:text], [HEADING_H2:text], [CITATION:text], "
            "[REFERENCE_START]...[REFERENCE_END] labels inserted."
        ),
        agent=ingest_agent,
    )

    parse_task = Task(
        description=(
            "Parse this labeled paper into structured JSON:\n\n"
            "<labeled_paper>\n"
            "The labeled paper text from the previous INGEST step.\n"
            "</labeled_paper>\n\n"
            "Extract ALL elements: metadata (citation_style, source_format, paper_type), "
            "title, authors (with affiliations), abstract (text + word_count), keywords, "
            "sections (with heading, level, content, subsections), figures, tables, "
            "citations (with id, original_text, context), "
            "references (with id, original_text, parsed components: authors, year, title, journal, volume, issue, pages, doi). "
            "Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        expected_output=(
            "Valid JSON object with keys: metadata, title, authors, affiliations, abstract, "
            "keywords, sections, figures, tables, citations, references. "
            "Each reference must be parsed into component parts (authors, year, title, journal, etc.)."
        ),
        agent=parse_agent,
        context=[ingest_task],
    )

    # ── Section stats summary for inject into transform task ──────────────────
    _section_stats_text = (
        "".join(
            f"   {name}: {stat['word_count']} words\n"
            for name, stat in section_stats.items()
        ) or "   (no sections detected — paper may lack standard headers)\n"
    )

    # ── Build transform task description — APA-specific vs generic ──────────
    _transform_common_prefix = (
        f"Transform this parsed paper to {journal_style} format. "
        f"Apply ALL formatting rules. Convert ALL citations and references.\n\n"
        f"<parsed_paper>\n"
        f"The parsed paper JSON from the previous PARSE step.\n"
        f"</parsed_paper>\n\n"
        f"<journal_rules>\n{json.dumps(rules, indent=2)}\n</journal_rules>\n\n"
        f"<formatting_guide>\n{section_rules_guide}\n</formatting_guide>\n\n"
        f"Pre-computed section word counts:\n{_section_stats_text}\n\n"
    )

    if is_apa:
        _transform_specifics = (
            f"CRITICAL REQUIREMENTS FOR APA 7th Edition:\n"
            f"1. Convert ALL numbered citations (1), [1], superscript¹ → (Author, Year) format\n"
            f"   Map each numbered citation to its reference entry. Use & in parenthetical, 'and' in narrative.\n"
            f"   3+ authors → first author et al. (with period after 'al')\n"
            f"2. Convert ALL references from NLM/Vancouver to APA format:\n"
            f"   - Author, F. M. (Year). Title. *Journal*, *Vol*(Issue), pages–pages.\n"
            f"   - Alphabetical order by first author surname\n"
            f"   - Hanging indent on all reference entries\n"
            f"   - Use *asterisks* for italic (journal names, volume numbers)\n"
            f"   - Use en-dash (–) for page ranges, not hyphen\n"
            f"3. STRIP all source journal metadata (page numbers, journal headers, footer URLs)\n"
            f"4. Generate docx_instructions with format_id='apa7' and these exact field names:\n"
            f"   - font_size_halfpoints: 24 (= 12pt)\n"
            f"   - line_spacing_twips: 480 (= double-spaced)\n"
            f"   - body_first_line_indent_dxa: 720 (= 0.5 inch)\n"
            f"5. sections array MUST contain (in order):\n"
            f"   - title_page: spacing(3 blank lines), title(bold,centered), spacing(1), authors, affiliation\n"
            f"   - abstract_page: abstract_label(bold,centered), abstract_body(no indent), keywords(items=[...], label_italic=true)\n"
            f"   - body: title_repeat(bold,centered), body_paragraphs(0.5\" indent), headings H1/H2/H3, figure/table captions\n"
            f"   - references_page: references_label(bold,centered), reference_entry(hanging_indent=true)\n"
            f"6. ALL citation replacements must be applied INLINE in body text\n"
            f"7. Include format_applied='APA 7th Edition' in top-level output\n\n"
        )
        _transform_expected = (
            "Valid JSON with: format_applied, violations, changes_made, citation_replacements, "
            "reference_conversions, reference_order, docx_instructions "
            "(with format_id='apa7', font_size_halfpoints=24, line_spacing_twips=480, "
            "body_first_line_indent_dxa=720, sections: [title_page, abstract_page, body, references_page])."
        )
    elif style_key == "springer":
        _cit_rules = rules.get("citations", {})
        _ref_rules = rules.get("references", {})
        _doc_rules = rules.get("document", {})
        _transform_specifics = (
            f"CRITICAL REQUIREMENTS FOR Springer Nature (sn-mathphys-ay):\n"
            f"1. Citation format: {_cit_rules.get('style', 'author-date')} "
            f"— brackets: {_cit_rules.get('brackets', 'parentheses')}\n"
            f"   Apply to ALL inline citations. Use 'and' for two authors, 'et al.' for 3+.\n"
            f"2. Reference ordering: {_ref_rules.get('ordering', 'alphabetical')}\n"
            f"3. Reference style: follow the format templates in the rules JSON exactly.\n"
            f"4. Hanging indent: {_ref_rules.get('hanging_indent', True)}\n"
            f"5. Document: font={_doc_rules.get('font', 'Times New Roman')}, "
            f"size={_doc_rules.get('font_size', 10)}pt, "
            f"spacing={_doc_rules.get('line_spacing', 1.0)}, "
            f"alignment={_doc_rules.get('alignment', 'justify')}\n"
            f"6. Headings MUST be hierarchically numbered (1, 1.1, 1.1.1).\n"
            f"7. Generate docx_instructions with a FLAT sections array containing:\n"
            f"   types: title, authors, affiliations, abstract, keywords, heading, "
            f"paragraph, reference, figure_caption, table_caption\n"
            f"   Each section has: type, content, and relevant formatting flags\n"
            f"8. ALL citation/reference changes must be applied INLINE in body text. "
            f"ZERO numbered citations should remain.\n\n"
        )
        _transform_expected = (
            "Valid JSON with: format_applied, violations, changes_made, citation_replacements, "
            "reference_conversions, reference_order, docx_instructions "
            "(with flat sections array: [title, authors, affiliations, abstract, keywords, heading, paragraph, reference...])."
        )
    elif style_key == "chicago":
        _transform_specifics = (
            f"CRITICAL REQUIREMENTS FOR Chicago Manual of Style (17th Edition, Author-Date):\n"
            f"1. Citation format: (Author Year) format. Use 'and' for two authors, italic 'et al.' for 3+.\n"
            f"   Apply to ALL inline citations. Multiple citations separated by semicolons.\n"
            f"2. Reference ordering: alphabetical by author surname.\n"
            f"3. Reference style: follow the format exactly (Author. Year. Title. etc).\n"
            f"4. Hanging indent: True (0.5 inch).\n"
            f"5. Document: font=Times New Roman, size=12pt, spacing=2.0 (Double), alignment=left.\n"
            f"6. Headings MUST be un-numbered. H1 Center/Bold/Title Case. H2 Left/Title Case. H3 Left/Italic.\n"
            f"7. Generate docx_instructions with a FLAT sections array containing:\n"
            f"   types: title, authors, affiliations, abstract, keywords, heading, "
            f"paragraph, reference, figure_caption, table_caption\n"
            f"   Each section has: type, content, and relevant formatting flags\n"
            f"8. ALL citation/reference changes must be applied INLINE in body text. "
            f"ZERO numbered citations should remain.\n\n"
        )
        _transform_expected = (
            "Valid JSON with: format_applied, violations, changes_made, citation_replacements, "
            "reference_conversions, reference_order, docx_instructions "
            "(with flat sections array: [title, authors, affiliations, abstract, keywords, heading, paragraph, reference...])."
        )
    elif style_key == "vancouver":
        _transform_specifics = (
            f"CRITICAL REQUIREMENTS FOR Vancouver (ICMJE / Biomedical):\n"
            f"1. Citation format: Numbered style [1]. Ordered by first appearance in text.\n"
            f"   Apply to ALL inline citations. Multiple citations separated by commas [1,3,5]. Ranges [2-4].\n"
            f"2. Reference ordering: Numerically by citation appearance.\n"
            f"3. Reference style: follow the format exactly (Author AA. Title. Journal. Year;Vol(Iss):Pages.).\n"
            f"4. Hanging indent: True (0.5 inch).\n"
            f"5. Document: font=Times New Roman, size=12pt, spacing=2.0 (Double), alignment=left.\n"
            f"6. Headings MUST be structured (Introduction, Methods, Results, Discussion). H1 Bold/Upper. H2 Title Case/Bold. H3 Title Case/Italic.\n"
            f"7. Generate docx_instructions with a FLAT sections array containing:\n"
            f"   types: title, authors, affiliations, abstract, keywords, heading, "
            f"paragraph, reference, figure_caption, table_caption\n"
            f"   Each section has: type, content, and relevant formatting flags\n"
            f"8. ALL citation/reference changes must be applied INLINE in body text. "
            f"Author formatting must be Surname Initials.\n\n"
        )
        _transform_expected = (
            "Valid JSON with: format_applied, violations, changes_made, citation_replacements, "
            "reference_conversions, reference_order, docx_instructions "
            "(with flat sections array: [title, authors, affiliations, abstract, keywords, heading, paragraph, reference...])."
        )
    else:
        _cit_rules = rules.get("citations", {})
        _ref_rules = rules.get("references", {})
        _doc_rules = rules.get("document", {})
        _transform_specifics = (
            f"CRITICAL REQUIREMENTS FOR {journal_style}:\n"
            f"1. Citation format: {_cit_rules.get('style', _cit_rules.get('format', 'see rules'))} "
            f"— brackets: {_cit_rules.get('brackets', 'see rules')}\n"
            f"2. Reference ordering: {_ref_rules.get('ordering', 'see rules')}\n"
            f"3. Reference style: follow the format templates in the rules JSON exactly\n"
            f"4. Hanging indent: {_ref_rules.get('hanging_indent', False)}\n"
            f"5. Document: font={_doc_rules.get('font', '?')}, "
            f"size={_doc_rules.get('font_size', '?')}pt, "
            f"spacing={_doc_rules.get('line_spacing', '?')}, "
            f"alignment={_doc_rules.get('alignment', '?')}\n"
            f"6. Generate docx_instructions with a FLAT sections array containing:\n"
            f"   types: title, abstract, heading (with level), paragraph, reference, "
            f"figure_caption, table_caption\n"
            f"   Each section has: type, content, and relevant formatting flags\n"
            f"7. ALL citation/reference changes must be applied INLINE in body text\n\n"
        )
        _transform_expected = (
            "Valid JSON with: violations, changes_made, citation_replacements, "
            "reference_conversions, reference_order, docx_instructions "
            "(with flat sections array: [title, abstract, heading, paragraph, reference, ...])."
        )

    transform_task = Task(
        description=(
            _transform_common_prefix + _transform_specifics
            + "Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        expected_output=_transform_expected,
        agent=transform_agent,
        context=[parse_task],
    )

    # --- Deterministic abstract word count (P4) ---
    # Use section_stats (from text_chunker, Python-exact) as primary source.
    # Falls back to regex on raw paper_content if section detection missed the abstract.
    abstract_word_limit: int = rules.get("abstract", {}).get("max_words", 250)
    abstract_word_count: int = section_stats.get("abstract", {}).get("word_count", 0)
    abstract_over_limit: bool = False

    if abstract_word_count:
        abstract_over_limit = abstract_word_count > abstract_word_limit
        logger.info(
            "[PIPELINE] Abstract word count (from section_stats): %d / %d — over_limit=%s",
            abstract_word_count, abstract_word_limit, abstract_over_limit,
        )
    else:
        # Fallback: regex scan of raw paper text
        try:
            _abstract_match = re.search(
                r"(?i)abstract[\s\n:]+(.+?)(?=\n\s*(?:keywords?|introduction|1\.|background))",
                paper_content,
                re.DOTALL,
            )
            if _abstract_match:
                abstract_word_count = len(_abstract_match.group(1).split())
                abstract_over_limit = abstract_word_count > abstract_word_limit
                logger.info(
                    "[PIPELINE] Abstract word count (regex fallback): %d / %d — over_limit=%s",
                    abstract_word_count, abstract_word_limit, abstract_over_limit,
                )
        except Exception as _e:
            logger.warning("[PIPELINE] Abstract word count extraction failed: %s", _e)

    # ── Build validate task description — APA-specific vs generic ───────────
    _validate_common = (
        f"Validate this transformed paper against {journal_style}:\n\n"
        f"<transform_output>\n"
        f"The transform output from the previous TRANSFORM step.\n"
        f"</transform_output>\n\n"
        f"<journal_rules>\n{json.dumps(rules, indent=2)}\n</journal_rules>\n\n"
        f"SYSTEM-VERIFIED FACTS (use these exact values):\n"
        f"- Abstract word count: {abstract_word_count} words\n"
        f"- Abstract word limit: {abstract_word_limit} words\n"
        f"- Over limit: {abstract_over_limit}\n"
        f"{'- Apply -15 to abstract score.' if abstract_over_limit else '- Abstract within limit — no deduction.'}\n\n"
    )

    if is_apa:
        _validate_checks = (
            f"Perform ALL 7 compliance checks (APA 7th Edition):\n"
            f"1. Citations (25%): ALL must be author-date (Author, Year). & in parenthetical, 'and' in narrative.\n"
            f"   3+ authors: et al. with period. ZERO numbered citations remain. -10 per remaining numbered.\n"
            f"2. References (25%): ALL in APA format: Author, F. M. (Year). Title. *Journal*, *Vol*(Issue), pages.\n"
            f"   Alphabetical order, hanging indent, & before last author, en-dash page ranges.\n"
            f"3. Citation ↔ Reference consistency: every citation has a reference, every reference is cited.\n"
            f"4. Headings (15%): H1 bold+centered+NOT italic, H2 bold+left+NOT italic, H3 bold+italic+left.\n"
            f"   IMRAD complete (Intro/Method/Results/Discussion). -25 per missing IMRAD section.\n"
            f"5. Document format (10%): font_size_halfpoints=24, line_spacing_twips=480, margins=1440 DXA,\n"
            f"   body_first_line_indent_dxa=720, alignment=left. -15 per wrong setting.\n"
            f"6. Abstract (10%): ≤250 words, bold centered label, no first-line indent, keywords with italic label.\n"
            f"7. Figures (7.5%) & Tables (7.5%): 'Figure N' not 'Fig.', sequential numbering, label bold, caption italic.\n\n"
        )
    elif style_key == "springer":
        _validate_checks = (
            f"Perform ALL 7 compliance checks against Springer Nature (sn-mathphys-ay) rules:\n"
            f"1. Citations (25%): ALL must be (Author Year) format. -10 per numbered citation remaining.\n"
            f"2. References (25%): Alphabetical order. Surname Initials (Year). Hanging indent. -10 per missing field.\n"
            f"3. Citation ↔ Reference consistency: every citation has a reference, every reference is cited.\n"
            f"4. Headings (15%): Numeric hierarchy required (1, 1.1, 1.1.1). H1/H2 bold, H3 italic.\n"
            f"5. Front Matter (10%): Check for structured affiliations (Department, Organization...) and author initials.\n"
            f"6. Abstract & Keywords (10%): Abstract label bold, justified body. Keywords label bold.\n"
            f"7. Figures & Tables (15%): 'Fig. N' below (Bold). 'Table N' above (Bold).\n\n"
        )
    elif style_key == "chicago":
        _validate_checks = (
            f"Perform ALL 7 compliance checks against Chicago Manual of Style (Author-Date):\n"
            f"1. Citations (25%): ALL must be (Author Year) format without commas between author & year. -10 per error.\n"
            f"2. References (25%): Alphabetical order. Correct punctuation (periods). Hanging indent 0.5in.\n"
            f"3. Citation ↔ Reference consistency: every citation has a reference, every reference is cited.\n"
            f"4. Headings (15%): Un-numbered hierarchy. H1 Centered/Bold. H2 Left. H3 Left/Italic.\n"
            f"5. Document format (10%): Times New Roman 12pt. Double spaced (2.0). Left aligned. First line indent 0.5in.\n"
            f"6. Abstract (10%): Label Centered/Not bold. Paragraph indented.\n"
            f"7. Figures & Tables (15%): Figures below, left aligned. Tables above, minimal borders.\n\n"
        )
    else:
        _cit_rules = rules.get("citations", {})
        _ref_rules = rules.get("references", {})
        _doc_rules = rules.get("document", {})
        _h_rules = rules.get("headings", {})
        _abs_rules = rules.get("abstract", {})
        _validate_checks = (
            f"Perform ALL 7 compliance checks against {journal_style} rules:\n"
            f"1. Citations (25%): Must use {_cit_rules.get('style', _cit_rules.get('format', 'journal'))} format. "
            f"Brackets: {_cit_rules.get('brackets', 'per rules')}.\n"
            f"2. References (25%): {_ref_rules.get('ordering', 'per rules')} order. "
            f"Hanging indent: {_ref_rules.get('hanging_indent', 'per rules')}.\n"
            f"3. Citation ↔ Reference consistency: every citation has a reference, every reference is cited.\n"
            f"4. Headings (15%): Check H1/H2/H3 styles match rules "
            f"(bold, italic, centered, case, numbering per journal).\n"
            f"5. Document format (10%): {_doc_rules.get('font', '?')} {_doc_rules.get('font_size', '?')}pt, "
            f"spacing={_doc_rules.get('line_spacing', '?')}, alignment={_doc_rules.get('alignment', '?')}.\n"
            f"6. Abstract (10%): ≤{_abs_rules.get('max_words', 250)} words, "
            f"label bold={_abs_rules.get('label_bold', '?')}, keywords={_abs_rules.get('keywords_present', '?')}.\n"
            f"7. Figures & Tables (15%): sequential numbering, correct caption position/style per rules.\n\n"
        )

    validate_task = Task(
        description=(
            _validate_common + _validate_checks
            + "Compute: overall_score = weighted sum. submission_ready = (score >= 80).\n"
            + "Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        expected_output=(
            "Valid JSON with: overall_score (0-100), checks/breakdown (7 sections each with "
            "score, issues, details), submission_ready, warnings, summary."
        ),
        agent=validate_agent,
        context=[transform_task],
    )

    step_timer = _StepTimer(progress_callback=progress_callback)

    crew = Crew(
        agents=[ingest_agent, parse_agent, transform_agent, validate_agent],
        tasks=[ingest_task, parse_task, transform_task, validate_task],
        process=Process.sequential,
        verbose=True,
        task_callback=step_timer.on_task_complete,
    )

    # Allow one retry on validation failures (e.g. LLM chain-of-thought issues)
    max_retries = 1
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            logger.info("[PIPELINE] Kicking off CrewAI (Attempt %d/%d)...",
                        attempt + 1, max_retries + 1)
            result = crew.kickoff()
            raw_output = str(result)

            # Validate all task outputs before proceeding
            logger.info("[PIPELINE] Validating task outputs...")
            run_id = _validate_task_outputs(crew)
            
            # Additional validation for transform output specifically
            transform_raw = _get_task_output(crew, task_index=2)
            transform_data = extract_json_from_llm(transform_raw)
            if "docx_instructions" in transform_data:
                _normalize_docx_instructions(transform_data["docx_instructions"])
                _validate_docx_instructions(transform_data["docx_instructions"])

            logger.info("[PIPELINE] All outputs validated OK on attempt %d", attempt + 1)
            break
        except (TransformError, LLMResponseError, ValidationError) as e:
            last_error = e
            if attempt < max_retries:
                logger.warning("[PIPELINE] Attempt %d failed: %s. Retrying...", attempt + 1, e)
                # Small delay before retry
                time.sleep(2)
                continue
            else:
                logger.error("[PIPELINE] All %d attempts failed. Final error: %s", max_retries + 1, e)
                raise

    logger.info("[PIPELINE] All steps complete — parsing outputs...")
    parse_raw = _get_task_output(crew, task_index=1)
    transform_raw = _get_task_output(crew, task_index=2)
    transform_data = extract_json_from_llm(transform_raw)

    compliance_report = _parse_compliance_report(raw_output)
    overall_score = compliance_report.get("overall_score", "N/A")
    logger.info("[PIPELINE] Compliance report parsed — overall_score=%s", overall_score)

    # ── Map extracted media to figure/table captions from PARSE output ─────────
    image_store: dict = {}
    table_store: dict = {}
    try:
        _parse_data = extract_json_from_llm(parse_raw)
        figure_captions = _parse_data.get("figures", [])
        table_captions = _parse_data.get("tables", [])
        if media_data["raw_images"] or media_data["raw_tables"]:
            image_store = map_figures_to_images(
                media_data["raw_images"], figure_captions, media_data["source_type"],
            )
            table_store = map_tables_to_captions(
                media_data["raw_tables"], table_captions, media_data["source_type"],
            )
            logger.info(
                "[PIPELINE] Media mapped — %d figures, %d tables",
                len(image_store), len(table_store),
            )
    except Exception as _map_err:
        logger.warning("[PIPELINE] Media mapping failed (non-fatal): %s", _map_err)

    # ── Deterministic overrides — replace LLM scores with Python-computed facts ──
    try:
        paper_structure = extract_json_from_llm(parse_raw)
        det_checks = run_deterministic_checks(paper_structure, rules)
        if det_checks:
            compliance_report = apply_deterministic_checks(
                compliance_report, det_checks, SECTION_WEIGHTS
            )
            overall_score = compliance_report.get("overall_score", overall_score)
            logger.info(
                "[PIPELINE] Deterministic checks applied (%d) — final_score=%s",
                len(det_checks), overall_score,
            )
    except Exception as _det_err:
        logger.warning(
            "[PIPELINE] Deterministic checks failed (non-fatal — LLM scores kept): %s",
            _det_err,
        )

    # ── Extract interpretation results (PHASE A violations) + enriched changes_made ──
    interpretation_results: dict = {"violations": [], "total_violations": 0}
    enriched_changes: list[dict] = []
    try:
        _transform_data_preview = transform_data

        # Violations (PHASE A)
        _violations = _transform_data_preview.get("violations", [])
        if isinstance(_violations, list):
            structured_violations = []
            for i, v in enumerate(_violations):
                if not isinstance(v, dict):
                    v = {"text": str(v), "message": str(v)}
                
                v_text = v.get("text", v.get("current", ""))
                start_char = paper_content.find(v_text) if v_text else -1
                end_char = start_char + len(v_text) if start_char != -1 else -1

                structured_violations.append({
                    "id": f"v{i+1}",
                    "element": v.get("element", ""),
                    "text": v_text,
                    "start_char": start_char,
                    "end_char": end_char,
                    "message": v.get("message", "Formatting violation"),
                    "expected": v.get("expected", v.get("required", "")),
                    "rule_reference": v.get("rule_reference", v.get("apa_ref", "")),
                    "severity": v.get("severity", "medium")
                })
            
            interpretation_results = {
                "violations": structured_violations,
                "total_violations": len(structured_violations),
                "journal": journal_style,
            }
            logger.info(
                "[PIPELINE] Interpretation results extracted — %d violations surfaced",
                len(structured_violations),
            )

        # Changes made (PHASE B) — enrich with rule references
        _changes_raw = _transform_data_preview.get("changes_made", [])
        if isinstance(_changes_raw, list) and _changes_raw:
            enriched_changes = _enrich_changes_made(_changes_raw, journal_style)
            logger.info(
                "[PIPELINE] Enriched %d changes_made entries with rule references",
                len(enriched_changes),
            )
    except Exception as _ie:
        logger.warning("[PIPELINE] Could not extract transform results (non-fatal): %s", _ie)

    logger.info("[PIPELINE] Writing formatted DOCX (source_docx=%s)...",
                "in-place" if source_docx_path else "from-text")
    t0 = time.time()
    docx_filename = _write_docx_from_transform(
        transform_raw, rules, source_docx_path, paper_content, style_key,
        run_id=run_id, image_store=image_store, table_store=table_store,
    )
    logger.info("[PIPELINE] DOCX written — file=%s in %.2fs", docx_filename, time.time() - t0)

    total_elapsed = round(time.time() - pipeline_start, 1)

    # Improvement 4: Stage timing metrics for demo visibility
    pipeline_metrics = {
        "stage_times": step_timer.stage_times,
        "total_runtime": total_elapsed,
    }

    # Improvement 6: Output file metadata for frontend display
    output_path = OUTPUT_DIR / docx_filename
    file_size = output_path.stat().st_size if output_path.exists() else 0
    output_metadata = {
        "filename": docx_filename,
        "size_bytes": file_size,
        "size_kb": round(file_size / 1024, 1),
    }

    # ── Post-format scoring — re-score the output DOCX against same rules ──
    post_format_score: dict = {}
    try:
        output_text = extract_docx_text(str(output_path))
        post_format_score = score_pre_format(output_text, rules)
        logger.info(
            "[PIPELINE] Post-format score: %d (from output DOCX)",
            post_format_score.get("total_score", -1),
        )
    except Exception as _pfs_err:
        logger.warning("[PIPELINE] Post-format scoring failed (non-fatal): %s", _pfs_err)

    # ── Formatting report — what was done, skipped, needs attention ──────────
    formatting_report = _build_formatting_report(
        enriched_changes, interpretation_results, compliance_report,
    )

    logger.info(
        "[PIPELINE] Done — score=%s docx=%s size=%sKB total=%.1fs",
        overall_score, docx_filename, output_metadata["size_kb"], total_elapsed,
    )

    # ── Extract parsed structure for the Live Document Editor  ───────────────
    document_structure = {}
    try:
        parse_raw = _get_task_output(crew, task_index=1)
        document_structure = extract_json_from_llm(parse_raw)
        logger.info("[PIPELINE] Extracted parsed document structure from Agent 2")
    except Exception as e:
        logger.warning("[PIPELINE] Could not extract parsed document structure: %s", e)

    pipeline_result = {
        "compliance_report": compliance_report,
        "docx_filename": docx_filename,
        "output_metadata": output_metadata,
        "pipeline_metrics": pipeline_metrics,
        "interpretation_results": interpretation_results,
        "changes_made": enriched_changes,  # Rule-referenced, from transform PHASE B
        "post_format_score": post_format_score,
        "formatting_report": formatting_report,
        "document_structure": document_structure,
    }

    # Improvement 7: Cache for instant re-runs of identical submissions
    PIPELINE_CACHE[cache_key] = pipeline_result
    return pipeline_result


def _build_formatting_report(
    changes_made: list,
    interpretation_results: dict,
    compliance_report: dict,
) -> dict:
    """
    Build a structured formatting report from pipeline artifacts.

    Returns:
        {
            "done": [...],                     # auto-applied by formatter
            "not_done_by_user_choice": [...],   # user override kept
            "needs_manual_attention": [...]      # system can't touch (images, tables, etc.)
        }
    """
    done: list[str] = []
    not_done_by_user_choice: list[str] = []
    needs_manual_attention: list[str] = []

    # ── "done" — from enriched changes_made (transform PHASE B) ──────────
    for change in changes_made:
        if isinstance(change, str):
            done.append(change)
        elif isinstance(change, dict):
            desc = change.get("description", change.get("change", str(change)))
            done.append(str(desc))

    # ── "needs_manual_attention" — from violations that remain unresolved ──
    # Violations the transform couldn't fix (figures, tables, equations, images)
    _manual_keywords = {"figure", "table", "image", "equation", "caption", "graph", "chart"}
    violations = interpretation_results.get("violations", [])
    for v in violations:
        text = v if isinstance(v, str) else v.get("description", v.get("issue", str(v)))
        text_lower = str(text).lower()
        if any(kw in text_lower for kw in _manual_keywords):
            needs_manual_attention.append(str(text))

    # Also check compliance_report breakdown for low-scoring visual sections
    breakdown = compliance_report.get("breakdown", {})
    for section_key in ("figures", "tables"):
        section = breakdown.get(section_key, {})
        if isinstance(section, dict):
            score = section.get("score", 100)
            issues = section.get("issues", [])
            if isinstance(score, (int, float)) and score < 80:
                for issue in issues:
                    issue_str = str(issue)
                    if issue_str not in needs_manual_attention:
                        needs_manual_attention.append(issue_str)

    logger.info(
        "[PIPELINE] Formatting report: done=%d skipped=%d manual=%d",
        len(done), len(not_done_by_user_choice), len(needs_manual_attention),
    )

    return {
        "done": done,
        "not_done_by_user_choice": not_done_by_user_choice,
        "needs_manual_attention": needs_manual_attention,
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
        logger.debug("[PIPELINE] Task[%d] output type: %s", task_index, type(output).__name__)
        if output is None:
            raise TransformError(
                f"Task at index {task_index} produced no output. "
                "Pipeline may have failed silently at this step."
            )

        # Prefer json_dict if available — CrewAI may have pre-parsed the JSON
        if hasattr(output, "json_dict") and output.json_dict:
            logger.debug("[PIPELINE] Task[%d] using json_dict (pre-parsed)", task_index)
            return json.dumps(output.json_dict)

        if hasattr(output, "raw"):
            return output.raw
        if hasattr(output, "result"):
            return output.result
        if hasattr(output, "output"):
            return output.output
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
    # The new APA validate prompt uses "checks" key; normalize to "breakdown"
    required_sections = [
        "document_format", "abstract", "headings",
        "citations", "references", "figures", "tables",
    ]
    breakdown = report.get("breakdown", report.get("checks", {}))
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


_SECTION_TYPE_MAP: dict[str, dict] = {
    # LLM-returned types (from transform prompt) → docx_writer internal types
    "title":            {"type": "title"},
    "authors":          {"type": "paragraph", "centered": True}, # Writers apply styling via 'rules' when type is passed or mapped
    "abstract_label":   {"type": "abstract"}, # Merges the label styling
    "abstract_body":    {"type": "paragraph"},
    "keywords":         {"type": "paragraph"},
    
    "heading_h1":       {"type": "heading", "level": 1},
    "heading_h2":       {"type": "heading", "level": 2},
    "heading_h3":       {"type": "heading", "level": 3},
    "heading":          {"type": "heading"},
    
    "body":             {"type": "paragraph"},
    "body_paragraph":   {"type": "paragraph"},
    
    "figure_caption":   {"type": "figure_caption"},
    "table_caption":    {"type": "table_caption"},
    
    "reference_label":  {"type": "heading", "level": 1},
    "reference_entry":  {"type": "reference"},
    
    # Already-normalised passthrough (identity mappings)
    "abstract":         {"type": "abstract"},
    "paragraph":        {"type": "paragraph"},
    "reference":        {"type": "reference"},
}


def _normalize_docx_instructions(docx: dict) -> dict:
    """
    User-suggested normalization layer (Improvement 11).
    Ensures every section has a 'content' key, mapping 'text' -> 'content' if needed.
    Also handles cases where LLM returns a list instead of a string.
    """
    sections = docx.get("sections", [])
    if not isinstance(sections, list):
        return docx

    for s in sections:
        if not isinstance(s, dict):
            continue
        # convert text → content
        if "content" not in s:
            if "text" in s:
                s["content"] = s.pop("text")
            else:
                s["content"] = ""

        # Recovery for list-type content (e.g., authors or references)
        if isinstance(s.get("content"), list):
            s["content"] = ", ".join([str(item) for item in s["content"]])

    return docx


def _normalize_section_types(sections: list) -> list:
    """
    Normalize LLM-returned section type strings to docx_writer-compatible values.
    """
    normalized = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        raw_type = str(sec.get("type", "paragraph")).lower()
        mapping = _SECTION_TYPE_MAP.get(raw_type)

        if mapping:
            merged = {**sec, **mapping}
            if "level" not in mapping and "level" in sec:
                merged["level"] = sec["level"]
            normalized.append(merged)
        else:
            logger.warning(
                "[DOCX] Unknown section type '%s' — falling back to 'paragraph'", raw_type
            )
            normalized.append({**sec, "type": "paragraph"})
    return normalized


def _write_docx_from_transform(
    transform_raw: str,
    rules: dict,
    source_docx_path: Optional[str] = None,
    paper_content: Optional[str] = None,
    style_key: str = "generic",
    run_id: Optional[str] = None,
    image_store: Optional[dict] = None,
    table_store: Optional[dict] = None,
) -> str:
    """
    Extract transform output and write the formatted DOCX file.

    Routes to the appropriate builder based on style_key:
      - "apa"     → build_apa_docx()    (page-based sections)
      - "ieee"    → build_ieee_docx()   (flat sections, 2-column, 10pt)
      - "generic" → write_formatted_docx() (rules-driven fallback)

    For DOCX source files with non-APA styles, may use transform_docx_in_place()
    to preserve figures, tables, and embedded objects.
    """
    transform_data = extract_json_from_llm(transform_raw)

    if "docx_instructions" not in transform_data:
        raise TransformError(
            "Transform result is missing 'docx_instructions' key. "
            "Agent 4 (transform_agent) did not produce valid output. "
            f"Keys found: {list(transform_data.keys())}"
        )

    docx_instructions = transform_data["docx_instructions"]
    docx_basename = f"formatted_{run_id or uuid.uuid4().hex[:8]}.docx"
    if run_id:
        run_dir = OUTPUT_DIR / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(run_dir / docx_basename)
        # Return path relative to OUTPUT_DIR so download/preview endpoints can find it
        output_filename = f"run_{run_id}/{docx_basename}"
    else:
        output_path = str(OUTPUT_DIR / docx_basename)
        output_filename = docx_basename

    sections = docx_instructions.get("sections") if isinstance(docx_instructions, dict) else None

    # ── Path A: APA → build_apa_docx (page-based sections) ──
    if style_key == "apa":
        if not isinstance(sections, list) or not sections:
            raise TransformError(
                "APA docx_instructions missing 'sections' list. "
                f"Keys: {list(docx_instructions.keys()) if isinstance(docx_instructions, dict) else '(not a dict)'}"
            )
        logger.info("[DOCX] APA format — using build_apa_docx — %d sections → %s",
                    len(sections), output_filename)
        build_apa_docx(transform_data, output_path, image_store=image_store, table_store=table_store)
        return output_filename

    # ── Path B: IEEE → build_ieee_docx (flat sections, 2-column, 10pt) ──
    # IEEE always rebuilds from extracted text (even for DOCX uploads) to apply
    # 2-column layout, 10pt font, and IEEE-specific heading/caption formatting.
    if style_key == "ieee":
        if not isinstance(sections, list) or not sections:
            raise TransformError(
                "IEEE docx_instructions missing 'sections' list. "
                f"Keys: {list(docx_instructions.keys()) if isinstance(docx_instructions, dict) else '(not a dict)'}"
            )
        docx_instructions = _normalize_docx_instructions(docx_instructions)
        _validate_docx_instructions(docx_instructions)
        sections = _guard_section_contents(sections, paper_content)
        if not sections:
            raise TransformError(
                "All sections were empty after content guard — transform agent produced no usable content."
            )
        docx_instructions["sections"] = _normalize_section_types(sections)
        docx_instructions["rules"] = rules
        logger.info("[DOCX] IEEE format — using build_ieee_docx — %d sections → %s",
                    len(docx_instructions["sections"]), output_filename)
        build_ieee_docx(docx_instructions, output_path, image_store=image_store, table_store=table_store)
        return output_filename

    # ── Path C: DOCX source with in-place transformation (preserves figures/tables) ──
    # Only used for generic styles where preserving original DOCX structure matters.
    if source_docx_path and Path(source_docx_path).exists():
        logger.info("[DOCX] In-place transformation (style=%s) — source=%s → %s",
                    style_key, Path(source_docx_path).name, output_filename)
        transform_docx_in_place(source_docx_path, transform_data, rules, output_path)
        return output_filename

    # ── Path D: Generic PDF/TXT source — rebuild from extracted text ──
    if not isinstance(sections, list) or len(sections) == 0:
        raise TransformError(
            "docx_instructions is missing a non-empty 'sections' list. "
            f"Keys: {list(docx_instructions.keys()) if isinstance(docx_instructions, dict) else '(not a dict)'}"
        )

    docx_instructions = _normalize_docx_instructions(docx_instructions)
    _validate_docx_instructions(docx_instructions)

    sections = _guard_section_contents(sections, paper_content)
    if not sections:
        raise TransformError(
            "All sections were empty after content guard — transform agent produced no usable content."
        )

    docx_instructions["sections"] = _normalize_section_types(sections)
    docx_instructions["rules"] = rules
    logger.info("[DOCX] Generic format — using write_formatted_docx — %d sections → %s",
                len(docx_instructions["sections"]), output_filename)
    write_formatted_docx(docx_instructions, output_path, image_store=image_store, table_store=table_store)
    return output_filename
