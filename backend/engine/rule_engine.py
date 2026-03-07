"""
engine/rule_engine.py — Rule Engine for Agent Paperpal

Handles three rule-sourcing modes before passing to the CrewAI pipeline:
  standard — load from rules/{journal}.json (existing behaviour)
  semi      — load base journal + merge user overrides + apply defaults
  full      — LLM-extract from guideline PDF (or accept custom_rules JSON) + apply defaults

The pipeline (crew.py) receives a validated rules dict in all cases.
"""

from __future__ import annotations

import copy
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import fitz  # PyMuPDF

from tools.logger import get_logger
from tools.rule_loader import JOURNAL_MAP, load_rules
from tools.tool_errors import RuleLoadError, RuleValidationError

logger = get_logger(__name__)

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# ---------------------------------------------------------------------------
# Default rules template — full schema-compliant, used to fill any gaps
# ---------------------------------------------------------------------------
DEFAULT_RULES: dict[str, Any] = {
    "style_name": "Custom",
    "document": {
        "font": "Times New Roman",
        "font_size": 12,
        "line_spacing": 1.5,
        "alignment": "justify",
        "columns": 1,
        "margins": {
            "top": "1in",
            "bottom": "1in",
            "left": "1in",
            "right": "1in",
        },
    },
    "title_page": {
        "title_case": "Title Case",
        "title_bold": True,
        "title_centered": True,
        "title_font_size": 14,
    },
    "abstract": {
        "label": "Abstract",
        "label_bold": True,
        "label_centered": True,
        "label_italic": False,
        "max_words": 250,
        "indent_first_line": False,
        "keywords_present": True,
        "keywords_label": "Keywords:",
        "keywords_italic": False,
    },
    "headings": {
        "H1": {
            "bold": True,
            "italic": False,
            "centered": True,
            "underline": False,
            "font_size": 14,
            "case": "Title Case",
            "numbering": "numeric",
        },
        "H2": {
            "bold": True,
            "italic": False,
            "centered": False,
            "underline": False,
            "font_size": 12,
            "case": "Title Case",
            "numbering": "numeric",
        },
        "H3": {
            "bold": False,
            "italic": True,
            "centered": False,
            "underline": False,
            "font_size": 12,
            "case": "Sentence case",
            "numbering": "numeric",
        },
    },
    "citations": {
        "style": "author-date",
        "brackets": "parentheses",
        "format_one_author": "(Author, Year)",
        "format_two_authors": "(Author & Author, Year)",
        "format_three_plus": "(Author et al., Year)",
        "format_numbered": "[N]",
        "include_page_for_quotes": False,
        "page_format": "p. {page}",
    },
    "references": {
        "section_label": "References",
        "label_bold": True,
        "label_centered": True,
        "label_italic": False,
        "ordering": "alphabetical",
        "hanging_indent": True,
        "indent_size": "0.5in",
        "line_spacing": 2.0,
        "space_between_entries": False,
        "formats": {
            "journal_article": "Author, A. (Year). Title. Journal, vol(issue), pages.",
            "book": "Author, A. (Year). Title. Publisher.",
            "book_chapter": "Author, A. (Year). Chapter. In Editor (Ed.), Book. Publisher.",
            "website": "Author, A. (Year). Title. Retrieved from URL",
            "conference_paper": "Author, A. (Year). Title. In Proceedings. Publisher.",
        },
    },
    "figures": {
        "label_prefix": "Figure",
        "label_bold": True,
        "label_italic": False,
        "caption_position": "below",
        "caption_italic": False,
        "caption_alignment": "center",
        "numbering": "arabic",
        "note_label": "Note.",
    },
    "tables": {
        "label_prefix": "Table",
        "label_bold": True,
        "label_italic": False,
        "caption_position": "above",
        "caption_italic": False,
        "caption_alignment": "center",
        "numbering": "arabic",
        "border_style": "top_bottom_only",
        "note_label": "Note.",
    },
    "equations": {
        "numbering": "right_aligned",
        "numbering_format": "(1)",
    },
    "general_rules": {
        "doi_format": "https://doi.org/xxxxx",
        "url_format": "Available: URL",
        "date_format": "Month Year",
        "et_al_threshold": 3,
        "use_ampersand_in_citations": False,
        "use_ampersand_in_references": False,
        "oxford_comma": True,
    },
}

# Allowed enum values for strict schema fields — used to sanitise LLM output
_ENUM_CONSTRAINTS: dict[str, list] = {
    "document.alignment":          ["left", "justify", "center", "right"],
    "citations.style":             ["author-date", "numbered", "footnote"],
    "citations.brackets":          ["parentheses", "square", "none"],
    "references.ordering":         ["alphabetical", "appearance"],
    "figures.caption_position":    ["above", "below"],
    "figures.caption_alignment":   ["left", "center", "right"],
    "figures.numbering":           ["arabic", "roman"],
    "tables.caption_position":     ["above", "below"],
    "tables.caption_alignment":    ["left", "center", "right"],
    "tables.numbering":            ["arabic", "roman"],
    "tables.border_style":         ["full", "full_grid", "top_bottom_only", "header_only", "none"],
}


# ---------------------------------------------------------------------------
# merge_rules — recursive deep merge
# ---------------------------------------------------------------------------

def merge_rules(base: dict, override: dict) -> dict:
    """
    Recursively merge `override` into `base`.

    For nested dicts, merges recursively so only the overridden leaf-values
    are replaced. Scalar values in `override` always win.

    Returns a new dict (neither input is mutated).
    """
    result = copy.deepcopy(base)
    gaps_filled = 0

    def _merge(dst: dict, src: dict, path: str = "") -> None:
        nonlocal gaps_filled
        for key, val in src.items():
            full_path = f"{path}.{key}" if path else key
            if key in dst and isinstance(dst[key], dict) and isinstance(val, dict):
                _merge(dst[key], val, full_path)
            else:
                dst[key] = copy.deepcopy(val)
                gaps_filled += 1

    _merge(result, override)
    logger.info("[RULE] Overrides applied: %d keys merged", gaps_filled)
    return result


# ---------------------------------------------------------------------------
# apply_defaults — fill missing fields from DEFAULT_RULES
# ---------------------------------------------------------------------------

def apply_defaults(rules: dict) -> dict:
    """
    Fill any missing fields in `rules` using DEFAULT_RULES as a fallback.

    Uses the same recursive merge strategy — DEFAULT_RULES values are only
    applied where the key is completely absent in `rules`.

    Returns a new dict.
    """
    result = copy.deepcopy(rules)
    gaps_filled = [0]

    def _fill(dst: dict, src: dict, path: str = "") -> None:
        for key, val in src.items():
            full_path = f"{path}.{key}" if path else key
            if key not in dst:
                dst[key] = copy.deepcopy(val)
                gaps_filled[0] += 1
                logger.debug("[RULE] Default applied: %s = %r", full_path, val)
            elif isinstance(val, dict) and isinstance(dst.get(key), dict):
                _fill(dst[key], val, full_path)

    _fill(result, DEFAULT_RULES)
    logger.info("[RULE] Defaults applied: %d gaps filled", gaps_filled[0])
    return result


# ---------------------------------------------------------------------------
# _sanitise_llm_rules — strip invalid enum values, remove unknown keys
# ---------------------------------------------------------------------------

def _sanitise_llm_rules(rules: dict) -> dict:
    """
    Post-process LLM-extracted rules dict to:
    - Remove top-level keys not present in DEFAULT_RULES (schema rejects extras)
    - Replace invalid enum values with their DEFAULT_RULES fallback
    """
    known_keys = set(DEFAULT_RULES.keys())
    sanitised = {k: v for k, v in rules.items() if k in known_keys}

    def _get_nested(d: dict, path: str):
        keys = path.split(".")
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    def _set_nested(d: dict, path: str, val) -> None:
        keys = path.split(".")
        cur = d
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        cur[keys[-1]] = val

    for field_path, allowed in _ENUM_CONSTRAINTS.items():
        val = _get_nested(sanitised, field_path)
        if val is not None and val not in allowed:
            default_val = _get_nested(DEFAULT_RULES, field_path)
            logger.warning(
                "[RULE] LLM enum mismatch at %s: %r not in %s — using default %r",
                field_path, val, allowed, default_val,
            )
            _set_nested(sanitised, field_path, default_val)

    # Replace None values with defaults — LLM often returns null for fields
    # it can't extract, but the schema requires concrete types (e.g. string).
    def _replace_nulls(dst: dict, src: dict, path: str = "") -> None:
        for key, val in dst.items():
            full_path = f"{path}.{key}" if path else key
            if val is None:
                default_val = _get_nested(src, full_path)
                if default_val is not None:
                    dst[key] = copy.deepcopy(default_val)
                    logger.warning(
                        "[RULE] LLM returned null at %s — using default %r",
                        full_path, default_val,
                    )
            elif isinstance(val, dict):
                _replace_nulls(val, src, full_path)

    _replace_nulls(sanitised, DEFAULT_RULES)

    return sanitised


# ---------------------------------------------------------------------------
# _translate_ui_overrides — convert frontend UI fields to schema-compliant keys
# ---------------------------------------------------------------------------

def _translate_ui_overrides(overrides: dict) -> dict:
    """
    The frontend SemiCustomPanel sends conceptual override keys that don't
    exist in the JSON schema (e.g. references.style, headings.numbering_style).
    This function translates them into real schema-compliant fields and strips
    any remaining non-schema keys from sections with additionalProperties=false.
    """
    result = copy.deepcopy(overrides)

    # ── headings.numbering_style → H1/H2/H3 .numbering ──────────────────
    if "headings" in result and "numbering_style" in result["headings"]:
        ns = result["headings"].pop("numbering_style")
        for level in ("H1", "H2", "H3"):
            result["headings"].setdefault(level, {})["numbering"] = ns
        logger.info("[RULE] Translated headings.numbering_style=%s → H1/H2/H3", ns)

    # ── references.style → strip (UI-only concept, not a schema field) ───
    if "references" in result and "style" in result["references"]:
        removed = result["references"].pop("style")
        logger.info("[RULE] Stripped non-schema field references.style=%s", removed)
        if not result["references"]:
            del result["references"]

    return result


# ---------------------------------------------------------------------------
# extract_guidelines_text — PyMuPDF text extraction
# ---------------------------------------------------------------------------

def extract_guidelines_text(pdf_bytes: bytes) -> str:
    """
    Extract plain text from a journal author guidelines PDF using PyMuPDF.

    Args:
        pdf_bytes: Raw bytes of the uploaded PDF.

    Returns:
        Extracted text string.

    Raises:
        RuleLoadError: If PDF is empty, corrupt, or yields no text.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise RuleLoadError(f"Could not open guideline PDF: {e}") from e

    pages = []
    for page in doc:
        text = page.get_text("text")
        if text:
            pages.append(text)
    doc.close()

    full_text = "\n".join(pages).strip()
    if not full_text or len(full_text) < 50:
        raise RuleLoadError(
            "Guideline PDF appears to be empty or scanned (no extractable text). "
            "Please upload a text-based PDF."
        )
    logger.info(
        "[RULE] Guideline PDF extracted — %d pages, %d chars",
        len(pages), len(full_text),
    )
    return full_text


# ---------------------------------------------------------------------------
# extract_rules_llm — Gemini extraction with retries
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """\
You are a journal formatting rule extraction system.

Extract formatting rules from the following journal author guidelines.

Return ONLY valid JSON — no markdown fences, no explanation, no preamble.

The JSON must have these top-level keys (omit any you cannot find evidence for):
  document, abstract, headings, citations, references, figures, tables

Rules to detect and extract:

document:
  font (string, e.g. "Times New Roman")
  font_size (number, in points)
  line_spacing (number, e.g. 1.0, 1.5, 2.0)
  alignment ("left", "justify", "center", or "right")
  columns (number, 1 or 2)
  margins: top, bottom, left, right (strings with units, e.g. "1in")

abstract:
  max_words (number)
  label_bold (boolean)
  label_centered (boolean)

headings (H1, H2, H3 — each with):
  bold (boolean), italic (boolean), centered (boolean),
  underline (boolean), font_size (number), case (string), numbering (string)

citations:
  style ("author-date", "numbered", or "footnote")
  brackets ("parentheses", "square", or "none")

references:
  ordering ("alphabetical" or "appearance")
  hanging_indent (boolean)
  line_spacing (number)

figures:
  caption_position ("above" or "below")
  caption_alignment ("left", "center", or "right")
  label_prefix (string, e.g. "Figure" or "Fig.")
  numbering ("arabic" or "roman")

tables:
  caption_position ("above" or "below")
  caption_alignment ("left", "center", or "right")
  label_prefix (string, e.g. "Table")
  numbering ("arabic" or "roman")
  border_style ("full", "full_grid", "top_bottom_only", "header_only", or "none")

headings:
  numbering_style ("roman", "numeric", "alpha")

IMPORTANT:
- If a rule is not explicitly mentioned, omit that key entirely.
- Only use the allowed enum values listed above.
- Return ONLY the JSON object. No other text.

Journal Author Guidelines:
\"\"\"
{guidelines_text}
\"\"\"
"""


def extract_rules_llm(guidelines_text: str, max_retries: int = 3) -> dict:
    """
    Call Gemini to extract formatting rules from guideline text.

    Retries up to `max_retries` times on JSON parse failure.
    Returns a (possibly partial) rules dict — caller must apply_defaults().

    Raises:
        RuleLoadError: If extraction fails after all retries.
    """
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuleLoadError(
            "GEMINI_API_KEY not set — cannot extract rules from guideline PDF."
        )

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    # Truncate to avoid token limits — first 12 000 chars is plenty for rules
    truncated = guidelines_text[:12_000]
    prompt = _EXTRACTION_PROMPT.replace("{guidelines_text}", truncated)

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        logger.info("[RULE] LLM extraction attempt %d/%d", attempt, max_retries)
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0},
            )
            raw = response.text.strip()

            # Strip markdown fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            raw = raw.strip()

            extracted: dict = json.loads(raw)
            if not isinstance(extracted, dict):
                raise ValueError("LLM returned non-dict JSON")

            logger.info(
                "[RULE] LLM extraction success on attempt %d — %d top-level keys",
                attempt, len(extracted),
            )
            return extracted

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning(
                "[RULE] LLM extraction attempt %d/%d failed — JSON parse error: %s",
                attempt, max_retries, e,
            )
            if attempt < max_retries:
                time.sleep(1)

        except Exception as e:
            last_error = e
            logger.warning(
                "[RULE] LLM extraction attempt %d/%d failed — %s: %s",
                attempt, max_retries, type(e).__name__, e,
            )
            if attempt < max_retries:
                time.sleep(2)

    raise RuleLoadError(
        f"Failed to extract formatting rules from guideline PDF after "
        f"{max_retries} attempts. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# convert_prompt_to_overrides — Natural language prompt → JSON overrides
# ---------------------------------------------------------------------------

_PROMPT_TO_JSON_PROMPT = """\
You are a formatting rule assistant.

Convert the following user request into a JSON formatting override object.
The request might be natural language like "use double columns" or "font size 10".

Return ONLY valid JSON — no markdown fences, no explanation.

Target schema fields:
  document: font, font_size (number), line_spacing (number), alignment, columns (number), margins (top, bottom, left, right)
  abstract: max_words (number), label_bold (bool), label_centered (bool)
  headings: H1, H2, H3 (bold, italic, centered, font_size, numbering)
  citations: style, brackets
  references: ordering, hanging_indent (bool)

Example: "Double column, 11pt Times font"
Output: {{"document": {{"columns": 2, "font_size": 11, "font": "Times New Roman"}}}}

User Request: "{prompt}"
Output JSON:
"""

def convert_prompt_to_overrides(prompt: str, max_retries: int = 2) -> dict:
    """
    Use Gemini to convert a natural language prompt into a JSON overrides dict.
    """
    import google.generativeai as genai
    
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("[RULE] LLM API key not set — skipping prompt-to-JSON conversion")
        return {}

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    
    for attempt in range(1, max_retries + 1):
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                _PROMPT_TO_JSON_PROMPT.format(prompt=prompt),
                generation_config={"temperature": 0},
            )
            raw = response.text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            
            extracted = json.loads(raw)
            if isinstance(extracted, dict):
                logger.info("[RULE] Prompt converted to JSON overrides: %s", list(extracted.keys()))
                return extracted
        except Exception as e:
            logger.warning("[RULE] Prompt-to-JSON failed (attempt %d): %s", attempt, e)
    
    return {}



# ---------------------------------------------------------------------------
# validate_rules — jsonschema validation
# ---------------------------------------------------------------------------

def validate_rules(rules: dict) -> None:
    """
    Validate a rules dict against rules_schema.json.

    Raises:
        RuleValidationError: If validation fails.
    """
    schema_path = SCHEMAS_DIR / "rules_schema.json"
    if not schema_path.exists():
        logger.warning("[RULE] rules_schema.json not found — skipping schema validation")
        return

    try:
        import jsonschema
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(instance=rules, schema=schema)
        logger.info("[RULE] Rules validated OK against schema")
    except ImportError:
        logger.warning("[RULE] jsonschema not installed — skipping validation")
    except jsonschema.ValidationError as e:
        raise RuleValidationError(
            f"Rules failed schema validation: {e.message} "
            f"(at path: {' > '.join(str(p) for p in e.absolute_path)})"
        ) from e
    except Exception as e:
        logger.warning("[RULE] Schema validation error (non-fatal): %s", e)


# ---------------------------------------------------------------------------
# generate_rules — top-level dispatcher
# ---------------------------------------------------------------------------

def generate_rules(
    mode: str,
    journal: Optional[str] = None,
    overrides: Optional[dict | str] = None,
    guideline_pdf_bytes: Optional[bytes] = None,
    custom_rules: Optional[dict | str] = None,
) -> dict:
    """
    Prepare a validated rules dict for the formatting pipeline.

    Args:
        mode:                 "standard" | "semi" | "full"
        journal:              Journal name (required for standard/semi)
        overrides:            Override fields dict (semi mode only)
        guideline_pdf_bytes:  Raw PDF bytes of author guidelines (full mode)
        custom_rules:         Pre-built full rules dict (full mode shortcut)

    Returns:
        Validated rules dict ready for run_pipeline().

    Raises:
        RuleLoadError:       Journal not found, PDF unreadable, LLM failure.
        RuleValidationError: Final rules fail schema validation.
        ValueError:          Invalid mode or missing required arguments.
    """
    mode = mode.strip().lower()
    if mode not in {"standard", "semi", "full"}:
        raise ValueError(
            f"Invalid mode '{mode}'. Must be one of: standard, semi, full."
        )

    logger.info("[RULE] Mode selected: %s", mode)

    # ── STANDARD ─────────────────────────────────────────────────────────────
    if mode == "standard":
        if not journal:
            raise ValueError("'journal' is required for standard mode.")
        rules = load_rules(journal)
        logger.info("[RULE] Journal loaded: %s", journal)
        validate_rules(rules)
        return rules

    # ── SEMI ──────────────────────────────────────────────────────────────────
    if mode == "semi":
        if not journal:
            raise ValueError("'journal' is required for semi mode.")
        base = load_rules(journal)
        logger.info("[RULE] Journal loaded: %s", journal)

        if overrides:
            overrides_dict = _translate_ui_overrides(overrides)
            merged = merge_rules(base, overrides_dict)
            logger.info("[RULE] Applied %d top-level overrides", len(overrides_dict))
        else:
            merged = copy.deepcopy(base)
            logger.info("[RULE] No overrides provided — using base journal rules")

        final = apply_defaults(merged)
        validate_rules(final)
        return final

    # ── FULL ──────────────────────────────────────────────────────────────────
    if mode == "full":
        if custom_rules:
            logger.info("[RULE] Full mode — preparing custom_rules")
            raw = copy.deepcopy(custom_rules)
        elif guideline_pdf_bytes:
            logger.info("[RULE] Full mode — extracting rules from guideline PDF")
            guidelines_text = extract_guidelines_text(guideline_pdf_bytes)
            extracted = extract_rules_llm(guidelines_text)
            raw = _sanitise_llm_rules(extracted)
        elif journal:
            # Convenience: full mode with a base journal — start from journal, no overrides
            raw = copy.deepcopy(load_rules(journal))
            logger.info("[RULE] Full mode — using journal '%s' as base", journal)
        else:
            raise ValueError(
                "Full mode requires one of: custom_rules, guideline_pdf, or journal."
            )

        # Always set style_name for full mode
        if "style_name" not in raw:
            raw["style_name"] = "Custom"

        final = apply_defaults(raw)
        validate_rules(final)
        return final

    # Should never reach here due to mode check above
    raise ValueError(f"Unhandled mode: {mode}")
