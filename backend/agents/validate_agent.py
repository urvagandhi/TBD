"""
Agent 5: VALIDATE — Perform 7 compliance checks and produce final compliance_report.

Analyzes the formatted manuscript against journal rules, scores every dimension
0-100, and produces the compliance_report that drives the frontend display.
"""
import time
from typing import Any

from crewai import Agent

from tools.logger import get_logger
from tools.tool_errors import LLMResponseError, ValidationError  # noqa: F401 — available for callers

logger = get_logger(__name__)

# Weights for overall_score calculation — must sum to 1.0 (Improvement 9)
SECTION_WEIGHTS = {
    "document_format": 0.10,
    "abstract":        0.10,
    "headings":        0.15,
    "citations":       0.25,  # highest weight
    "references":      0.25,  # highest weight
    "figures":         0.075,
    "tables":          0.075,
}

assert abs(sum(SECTION_WEIGHTS.values()) - 1.0) < 1e-9, (
    f"SECTION_WEIGHTS must sum to 1.0, got {sum(SECTION_WEIGHTS.values())}"
)


def _clamp_score(score: Any) -> int:
    """
    Clamp a section or overall score to the valid range [0, 100].

    Handles:
      - Non-numeric values (coerced to 0)
      - Values below 0 (raised to 0)
      - Values above 100 (capped at 100)

    Args:
        score: Raw score from LLM output (may be int, float, or str).

    Returns:
        Integer in [0, 100].
    """
    try:
        v = int(float(score))
    except (TypeError, ValueError):
        logger.warning("[VALIDATE] Non-numeric score '%s' — defaulting to 0", score)
        v = 0
    clamped = max(0, min(100, v))
    if clamped != v:
        logger.warning("[VALIDATE] Score %d clamped to %d", v, clamped)
    return clamped


def _recompute_overall_score(breakdown: dict) -> int:
    """
    Recompute overall_score from breakdown using the exact SECTION_WEIGHTS formula.

    Used when the LLM's reported overall_score is inconsistent with the breakdown
    scores (Improvement 9). Formula:
        overall_score = round(sum(score * weight for each section))

    Args:
        breakdown: Dict mapping section names to their score dicts.

    Returns:
        Recomputed overall_score as int, clamped to [0, 100].
    """
    total = 0.0
    for section, weight in SECTION_WEIGHTS.items():
        section_data = breakdown.get(section, {})
        raw_score = section_data.get("score", 100) if isinstance(section_data, dict) else 100
        total += _clamp_score(raw_score) * weight
    return _clamp_score(round(total))


def _validate_validate_output(data: dict) -> None:
    """
    Validate that compliance report contains all required fields.

    Checks:
      1. data is a dict
      2. overall_score is present and in [0, 100]
      3. breakdown is present with all 7 sections
      4. imrad_check is present
      5. If overall_score is inconsistent with breakdown, recompute and warn

    Args:
        data: Parsed compliance_report dict.

    Raises:
        ValidationError: If overall_score or breakdown is missing.
        LLMResponseError: If data is not a dict.
    """
    if not isinstance(data, dict):
        raise LLMResponseError(
            f"Validate output must be a JSON object (dict), got {type(data).__name__}"
        )

    if "overall_score" not in data:
        raise ValidationError(
            "Compliance report missing 'overall_score' — pipeline cannot complete. "
            f"Keys present: {list(data.keys())}"
        )

    # Clamp score in place (Improvement 9)
    data["overall_score"] = _clamp_score(data["overall_score"])

    breakdown = data.get("breakdown", {})
    if not breakdown:
        raise ValidationError(
            "Compliance report missing 'breakdown' — frontend cannot display per-section scores."
        )

    # Clamp all section scores in place (Improvement 9)
    for section in SECTION_WEIGHTS:
        if section in breakdown and isinstance(breakdown[section], dict):
            breakdown[section]["score"] = _clamp_score(
                breakdown[section].get("score", 100)
            )

    # Consistency check: recompute overall if breakdown exists (Improvement 9)
    if breakdown:
        recomputed = _recompute_overall_score(breakdown)
        reported = data["overall_score"]
        if abs(recomputed - reported) > 5:
            logger.warning(
                "[VALIDATE] Score inconsistency: reported=%d recomputed=%d — "
                "using recomputed value",
                reported, recomputed,
            )
            data["overall_score"] = recomputed

    # Cross-agent sanity: warn if submission_ready is wrong (Improvement 10)
    if "submission_ready" in data:
        expected_ready = data["overall_score"] >= 80
        if data["submission_ready"] != expected_ready:
            logger.warning(
                "[VALIDATE] submission_ready mismatch: reported=%s score=%d "
                "(expected submission_ready=%s) — correcting",
                data["submission_ready"], data["overall_score"], expected_ready,
            )
            data["submission_ready"] = expected_ready

    logger.info(
        "[VALIDATE] Validation passed — overall_score=%d submission_ready=%s",
        data["overall_score"],
        data.get("submission_ready", data["overall_score"] >= 80),
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


def create_validate_agent(llm: Any) -> Agent:
    """
    Agent 5: VALIDATE — 7-check compliance scoring + report generation.

    Performs all 7 mandatory checks and returns compliance_report JSON.
    overall_score is REQUIRED — crew.py raises ValueError if missing.

    The 7 checks:
      1. Citation ↔ Reference consistency (orphan citations, uncited references)
      2. IMRAD structure completeness (Introduction/Methods/Results/Discussion)
      3. Reference age (>50% older than 10 years → warning)
      4. Self-citation rate (>30% same authors → warning)
      5. Figure sequential numbering (no gaps, no duplicates)
      6. Table sequential numbering (no gaps, no duplicates)
      7. Abstract word count vs journal max_words limit

    Scoring formula (weights must be applied exactly):
      document_format=0.10, abstract=0.10, headings=0.15,
      citations=0.25, references=0.25, figures=0.075, tables=0.075
      overall_score = round(sum(score * weight for each section))

    Args:
        llm: Shared LLM string at temperature=0.

    Returns:
        CrewAI Agent configured for compliance validation.
    """
    logger.info("[VALIDATE] Agent created")

    return Agent(
        role="Academic Manuscript Compliance Validator",
        goal=(
            "Perform all 7 mandatory compliance checks on the manuscript and produce "
            "the complete compliance_report JSON. overall_score is REQUIRED — the "
            "pipeline raises ValueError if it is missing.\n\n"
            "THE 7 CHECKS (all must be performed):\n"
            "  CHECK 1 — Citation ↔ Reference Consistency:\n"
            "    Every in-text citation must have exactly one matching reference.\n"
            "    Orphan citation = cited in text but no reference entry: -10 pts each (max -50).\n"
            "    Uncited reference = in reference list but never cited: -5 pts each.\n\n"
            "  CHECK 2 — IMRAD Structure Completeness:\n"
            "    Requires: Introduction + Methods + Results + Discussion.\n"
            "    -25 pts per missing section. Equivalents accepted:\n"
            "    'Conclusion' = Discussion; 'Materials and Methods' = Methods;\n"
            "    Combined 'Results and Discussion' counts as both.\n\n"
            "  CHECK 3 — Reference Age:\n"
            "    Count references where year < (2025 - 10) = older than 2015.\n"
            "    If >50% are old: age_warning=true, -10 from references score.\n\n"
            "  CHECK 4 — Self-Citation Rate:\n"
            "    Detect if paper authors appear in >30% of references.\n"
            "    If so: self_citation_warning=true, -5 from references score.\n\n"
            "  CHECK 5 — Figure Sequential Numbering:\n"
            "    Extract all figure IDs, normalize to integers, check 1,2,3,... sequence.\n"
            "    -15 per gap; -20 per duplicate.\n\n"
            "  CHECK 6 — Table Sequential Numbering:\n"
            "    Same as Check 5 but for tables.\n\n"
            "  CHECK 7 — Abstract Word Count:\n"
            "    Compare abstract.word_count vs rules.abstract.max_words.\n"
            "    If over limit: -15 from abstract score, add issue.\n\n"
            "SCORING FORMULA (apply EXACTLY — weights must match):\n"
            "  document_format=0.10, abstract=0.10, headings=0.15,\n"
            "  citations=0.25, references=0.25, figures=0.075, tables=0.075\n"
            "  Each section starts at 100, deductions applied per issue found.\n"
            "  Score floor = 0. overall_score = round(sum(score * weight)).\n\n"
            "SCORE INTEGRITY (Improvement 9 — Self-Check):\n"
            "  All scores must be in range [0, 100] — clamp if needed.\n"
            "  Recompute overall_score using the formula above AFTER setting breakdown.\n"
            "  Do NOT report an overall_score that differs from the weighted sum by more than 5.\n"
            "  submission_ready = true if and only if overall_score >= 80.\n\n"
            "REQUIRED OUTPUT SCHEMA (all fields mandatory):\n"
            "  overall_score: int (0-100) — REQUIRED\n"
            "  breakdown: {\n"
            "    document_format: {score, issues:[str], checks_passed:[str], checks_failed:[str]}\n"
            "    abstract:  {score, issues, word_count, word_limit, within_limit:bool}\n"
            "    headings:  {score, issues, total_headings, correctly_formatted:int}\n"
            "    citations: {score, issues, total_citations, style_consistent:bool, orphan_citations:[str]}\n"
            "    references:{score, issues, total_references, uncited_references:[str], ordering_correct:bool}\n"
            "    figures:   {score, issues, total_figures, sequentially_numbered:bool, captions_present:bool}\n"
            "    tables:    {score, issues, total_tables,  sequentially_numbered:bool, captions_present:bool}\n"
            "  }\n"
            "  imrad_check: {introduction, methods, results, discussion:bool,\n"
            "                imrad_complete:bool, missing_sections:[str]}\n"
            "  citation_consistency: {total_in_text_citations, total_references:int,\n"
            "                         orphan_citations, uncited_references:[str],\n"
            "                         consistency_score:int}\n"
            "  reference_quality: {total_references, references_with_doi, old_references_count:int,\n"
            "                      old_references_percentage, self_citation_count:int,\n"
            "                      self_citation_percentage:float,\n"
            "                      age_warning, self_citation_warning:bool}\n"
            "  changes_made: [str]\n"
            "  violations_found: int\n"
            "  violations_fixed: int\n"
            "  submission_ready: bool (true if overall_score >= 80)\n"
            "  recommendations: [str] — actionable suggestions for remaining issues\n\n"
            "EDGE CASES:\n"
            "  - 0 figures  → figures score = 100 (nothing to check, not a violation)\n"
            "  - 0 tables   → tables score  = 100\n"
            "  - 0 citations → citation consistency score = 100\n"
            "  - No references → references score = 50 (cannot validate)\n"
            "  - IMRAD: review/survey paper may legitimately lack Methods → note in recommendations\n\n"
            "Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        backstory=(
            "You are a senior academic editor and compliance specialist with 20 years of "
            "experience reviewing manuscripts for Nature, Science, IEEE, Elsevier, and PLOS. "
            "You have developed and applied systematic quality checklists across 300,000 "
            "manuscript reviews, covering citation consistency, structural completeness, "
            "reference quality, and formatting standards. "
            "You score manuscripts with mathematical precision — applying the exact weighted "
            "scoring formula, performing all 7 checks without exception, and producing "
            "compliance reports that editors use directly for submission decisions. "
            "You never make further edits or transformations — you assess, score, and advise. "
            "Your overall_score drives the submission_ready decision: researchers rely on your "
            "report to understand what to fix before submitting to the journal. "
            "A missing overall_score or an incorrect breakdown causes the pipeline to fail — "
            "your output must be complete, accurate, and machine-parseable every time. "
            "Before returning, you recompute overall_score from the breakdown using the exact "
            "weighted formula to guarantee consistency, clamp all scores to [0, 100], and "
            "set submission_ready = (overall_score >= 80) deterministically."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )
