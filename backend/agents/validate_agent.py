"""
Agent 4: VALIDATE — Perform 7 compliance checks and produce final compliance_report.

Analyzes the formatted manuscript against APA 7th Edition rules, scores every
dimension 0-100, and produces the compliance_report that drives the frontend display.

Prompt matches APA_Pipeline_Complete_Prompts.md §5 exactly.
"""
import time
from typing import Any

from crewai import Agent

from tools.logger import get_logger
from tools.tool_errors import LLMResponseError, ValidationError  # noqa: F401

logger = get_logger(__name__)

# Weights for overall_score calculation — must sum to 1.0
SECTION_WEIGHTS = {
    "document_format": 0.10,
    "abstract":        0.10,
    "headings":        0.15,
    "citations":       0.25,
    "references":      0.25,
    "figures":         0.075,
    "tables":          0.075,
}

assert abs(sum(SECTION_WEIGHTS.values()) - 1.0) < 1e-9, (
    f"SECTION_WEIGHTS must sum to 1.0, got {sum(SECTION_WEIGHTS.values())}"
)


def _clamp_score(score: Any) -> int:
    """Clamp a section or overall score to [0, 100]."""
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
    """Recompute overall_score from breakdown using SECTION_WEIGHTS."""
    total = 0.0
    for section, weight in SECTION_WEIGHTS.items():
        section_data = breakdown.get(section, {})
        raw_score = section_data.get("score", 100) if isinstance(section_data, dict) else 100
        total += _clamp_score(raw_score) * weight
    return _clamp_score(round(total))


def _validate_validate_output(data: dict) -> None:
    """Validate that compliance report contains all required fields."""
    if not isinstance(data, dict):
        raise LLMResponseError(
            f"Validate output must be a JSON object (dict), got {type(data).__name__}"
        )

    if "overall_score" not in data:
        raise ValidationError(
            "Compliance report missing 'overall_score' — pipeline cannot complete. "
            f"Keys present: {list(data.keys())}"
        )

    data["overall_score"] = _clamp_score(data["overall_score"])

    breakdown = data.get("breakdown", data.get("checks", {}))
    if not breakdown:
        raise ValidationError(
            "Compliance report missing 'breakdown'/'checks' — frontend cannot display per-section scores."
        )

    # Normalize: the new prompt uses "checks" key, map to "breakdown" for consistency
    if "checks" in data and "breakdown" not in data:
        data["breakdown"] = data.pop("checks")
        breakdown = data["breakdown"]

    for section in SECTION_WEIGHTS:
        if section in breakdown and isinstance(breakdown[section], dict):
            breakdown[section]["score"] = _clamp_score(
                breakdown[section].get("score", 100)
            )

    if breakdown:
        recomputed = _recompute_overall_score(breakdown)
        reported = data["overall_score"]
        if abs(recomputed - reported) > 5:
            logger.warning(
                "[VALIDATE] Score inconsistency: reported=%d recomputed=%d — using recomputed",
                reported, recomputed,
            )
            data["overall_score"] = recomputed

    if "submission_ready" in data:
        expected_ready = data["overall_score"] >= 80
        if data["submission_ready"] != expected_ready:
            logger.warning(
                "[VALIDATE] submission_ready mismatch: reported=%s score=%d — correcting",
                data["submission_ready"], data["overall_score"],
            )
            data["submission_ready"] = expected_ready

    logger.info(
        "[VALIDATE] Validation passed — overall_score=%d submission_ready=%s",
        data["overall_score"],
        data.get("submission_ready", data["overall_score"] >= 80),
    )


def _safe_context(context: dict, key: str) -> Any:
    if key not in context:
        raise ValueError(f"Pipeline context missing required key: '{key}'")
    return context[key]


# ── System prompt from APA_Pipeline_Complete_Prompts.md §5 ──────────────────
VALIDATE_SYSTEM_PROMPT = """You are an APA 7th Edition compliance scorer. Score the transformed paper against 7 weighted checks.

## FORMAT: APA 7th Edition

## 7 COMPLIANCE CHECKS

### CHECK 1 — Citations (weight: 25%)
✓ ALL citations use author-date: (Author, Year)
✓ 2 authors: & in parenthetical, "and" in narrative
✓ 3+ authors: "et al." with period
✓ ZERO numbered citations remain — no (1), no [1], no superscripts
✓ Every citation has matching reference
Scoring: 100 base. -10 per numbered citation remaining. -5 per format error.

### CHECK 2 — References (weight: 25%)
✓ APA format: Author, F. M. (Year). Title. *Journal*, *Vol*(Issue), pages.
✓ Alphabetical order by first author
✓ Hanging indent specified
✓ "References" label: bold + centered
✓ & before last author
✓ Periods after initials
✓ en-dash for page ranges
✓ Every reference cited in text
Scoring: 100 base. -5 per format error. -10 per missing field.

### CHECK 3 — Headings (weight: 15%)
✓ H1: bold + centered + Title Case + NOT italic
✓ H2: bold + flush left + Title Case + NOT italic
✓ H3: bold + italic + flush left + Title Case
✓ IMRAD present (Introduction/Method/Results/Discussion)
Scoring: 100 base. -25 per missing IMRAD section. -10 per wrong heading format.

### CHECK 4 — Document Format (weight: 10%)
✓ font = "Times New Roman"
✓ font_size = 24 half-points (12pt)
✓ line_spacing = 480 twips (double)
✓ margins = 1440 DXA all sides
✓ page size = 12240 × 15840 (US Letter)
✓ body indent = 720 DXA (0.5")
✓ alignment = "left"
Scoring: 100 base. -15 per wrong setting.

### CHECK 5 — Abstract (weight: 10%)
✓ Word count ≤ 250
✓ "Abstract" label: bold + centered
✓ Body: no first-line indent
✓ Keywords present with italic label
Scoring: 100 base. -15 if over word limit. -10 per missing element.

### CHECK 6 — Figures (weight: 7.5%)
✓ "Figure N" label (not "Fig.")
✓ Label bold, caption italic
✓ Position: below figure
✓ Sequential numbering
Scoring: 100 base. -10 per violation.

### CHECK 7 — Tables (weight: 7.5%)
✓ "Table N" label bold, caption italic
✓ Position: above table
✓ Sequential numbering
Scoring: 100 base. -10 per violation.

## SCORING FORMULA
overall = (citations × 0.25) + (references × 0.25) + (headings × 0.15) + (doc_format × 0.10) + (abstract × 0.10) + (figures × 0.075) + (tables × 0.075)

submission_ready = overall ≥ 80

## WARNINGS (don't reduce score)
- >50% references older than 10 years
- >30% self-citations
- No DOIs in references

## OUTPUT
Return ONLY JSON with scores per check, overall_score, submission_ready, and summary."""


# ── Springer Nature validate prompt (Author-Date) ─────────────────────────
SPRINGER_VALIDATE_SYSTEM_PROMPT = """You are an expert academic editor specializing in Springer Nature standards. Validate the transformed manuscript against these 7 compliance checks:

## FORMAT: Springer Nature (sn-mathphys-ay)

## 7 COMPLIANCE CHECKS

### CHECK 1 — Citations (weight: 25%)
✓ ALL citations must be in `(Author Year)` format.
✓ Check for et al. usage (3+ authors).
✓ ZERO numbered citations allowed.
Scoring: 100 base. -10 per numbered citation remaining. -5 per format error.

### CHECK 2 — References (weight: 25%)
✓ Alphabetical order by first author's surname.
✓ Format: `Surname Initials (Year) Title. Journal Vol(Issue):Pages`.
✓ Hanging indent specified.
Scoring: 100 base. -5 per format error. -10 per missing field.

### CHECK 3 — Citation ↔ Reference Consistency
✓ Every citation exists in references, and vice versa.

### CHECK 4 — Headings (weight: 15%)
✓ H1/H2/H3 must be bold/italic and numbered numeric (1, 1.1, 1.1.1).
Scoring: 100 base. -10 per wrong heading format.

### CHECK 5 — Front Matter (weight: 10%)
✓ Check for structured affiliations (Department, Organization...) and author initials.
Scoring: 100 base. -15 per wrong setting.

### CHECK 6 — Abstract & Keywords (weight: 10%)
✓ Abstract label bold, justified body.
✓ Keywords label bold.
Scoring: 100 base. -10 per missing element.

### CHECK 7 — Figures & Tables (weight: 15% total)
✓ `Fig. N` below (Bold).
✓ `Table N` above (Bold).
Scoring: 100 base. -10 per violation.

## OUTPUT JSON SCHEMA

{
  "checks": {
    "citations": {"score": 100, "issues": []},
    "references": {"score": 90, "issues": ["One reference missing DOI"]},
    "headings": {"score": 100, "issues": []},
    "document_format": {"score": 100, "issues": []},
    "abstract": {"score": 100, "issues": []},
    "figures": {"score": 100, "issues": []},
    "tables": {"score": 100, "issues": []}
  },
  "overall_score": 95,
  "submission_ready": true,
  "summary": "The manuscript is highly compliant with Springer sn-mathphys-ay standards."
}

## OUTPUT
Return ONLY JSON with scores per check, overall_score, submission_ready, and summary."""

# ═══════════════════════════════════════════════════════════════════════════════
# CHICAGO MANUAL OF STYLE (17TH EDITION) VALIDATE PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

CHICAGO_VALIDATE_SYSTEM_PROMPT = """You are an academic style compliance validator specializing in Chicago Author-Date manuscripts.

Evaluate the formatted manuscript using the following checks.

VALIDATION CHECKLIST

### Check 1: Citation Format (25%)
- Verify all citations use: (Author Year)
- Ensure correct usage of: et al.

### Check 2: Reference List (25%)
- Verify: alphabetical ordering, correct formatting, proper author names (First Last), title punctuation
- Double spaced, hanging indent 0.5 inch

### Check 3: Citation ↔ Reference Matching (15%)
- Ensure: Every citation has a matching reference, and every reference is cited

### Check 4: Heading Hierarchy (10%)
- Ensure headings follow Chicago formatting rules (un-numbered).
- L1: Centered, Bold, Title Case
- L2: Left aligned, Title Case, Not bold
- L3: Left aligned, Italic, Title Case

### Check 5: Abstract Formatting (10%)
- Check label formatting (Centered, not bold) and paragraph indentation (first line indent).

### Check 6: Paragraph Formatting (10%)
- Verify: double spacing (2.0 line spacing), correct indentation (first line 0.5 inch)

### Check 7: Figures & Tables (5%)
- Ensure captions placed correctly.
- Figures: Caption placed below, left aligned.
- Tables: Caption placed above, minimal borders.

VALIDATOR OUTPUT
Must match this JSON structure:
{
  "overall_score": 94,
  "submission_ready": true,
  "checks": {
    "citations": {"score": 100, "issues": []},
    "references": {"score": 90, "issues": ["Missing publisher location in one book reference"]},
    "headings": {"score": 95, "issues": []},
    "document_format": {"score": 100, "issues": []},
    "abstract": {"score": 100, "issues": []},
    "figures": {"score": 100, "issues": []},
    "tables": {"score": 100, "issues": []}
  },
  "summary": "The manuscript is largely compliant with Chicago Author-Date formatting guidelines."
}

NO MARKDOWN FENCES. NO EXPLANATION."""


# ═══════════════════════════════════════════════════════════════════════════════
# VANCOUVER (ICMJE / BIOMEDICAL) VALIDATE PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

VANCOUVER_VALIDATE_SYSTEM_PROMPT = """You are a Vancouver manuscript compliance validator.

Evaluate the formatted manuscript using biomedical journal standards.

VALIDATION CHECKLIST

### Check 1: Citation Format (25%)
- Ensure citations follow: [Number]
- Check: sequential numbering, correct reuse of citation numbers, correct range formatting

### Check 2: Reference List Order (25%)
- Ensure references are: ordered by first appearance, correctly numbered, properly formatted

### Check 3: Citation ↔ Reference Matching (20%)
- Verify: Every citation has a reference, Every reference is cited

### Check 4: Author Formatting (10%)
- Ensure author names follow: Surname Initials

### Check 5: Abstract Formatting (10%)
- Verify: abstract label present, paragraph formatting correct

### Check 6: Figures and Tables (10%)
- Check: caption placement, correct labeling

VALIDATOR OUTPUT
Must match this JSON structure:
{
  "overall_score": 95,
  "submission_ready": true,
  "checks": {
    "citations": {"score": 100, "issues": []},
    "references": {"score": 92, "issues": ["One reference missing journal abbreviation"]},
    "author_format": {"score": 100, "issues": []},
    "abstract": {"score": 100, "issues": []},
    "figures_tables": {"score": 100, "issues": []}
  },
  "summary": "The manuscript is highly compliant with Vancouver citation and formatting standards."
}

NO MARKDOWN FENCES. NO EXPLANATION."""


# ── Generic (non-APA) validate prompt — rules-driven ─────────────────────────
GENERIC_VALIDATE_SYSTEM_PROMPT = """You are an academic manuscript compliance validator. You receive the TRANSFORM agent's output and the target journal's formatting rules, then score compliance across 7 checks.

## YOUR TASK

Score the transformed manuscript against the PROVIDED journal rules (NOT APA defaults). Each check scores 0-100.

## 7 COMPLIANCE CHECKS

### Check 1: Citations (weight: 25%)
- Citations match the format specified in the rules (numbered [N] OR author-date)
- Correct bracket style, et al. usage, multiple citation formatting
- Score: 100 if all correct, deductions per error

### Check 2: References (weight: 25%)
- References match the journal's required format
- Correct ordering (alphabetical OR appearance-order per rules)
- Correct label style (bold/italic/centered per rules)
- Hanging indent if rules require it

### Check 3: Citation ↔ Reference Consistency
- Every in-text citation has a matching reference entry
- Every reference is cited at least once

### Check 4: Headings (weight: 15%)
- Heading styles match rules (bold, italic, centered, case, numbering)
- Required sections present

### Check 5: Document Format (weight: 10%)
- Font, font size, line spacing, margins match rules
- Alignment matches rules (left/justify/center)

### Check 6: Abstract (weight: 10%)
- Word count within limit specified in rules
- Label style matches rules (bold, italic, centered)
- Keywords present if required by rules

### Check 7: Figures & Tables (weight: 15% total)
- Caption position matches rules (above/below)
- Label format matches rules
- Sequential numbering

## SCORING

Compute weighted score using the same weights as above.
submission_ready = true if overall_score >= 80

## OUTPUT JSON SCHEMA

{
  "checks": {
    "citations": {"score": 95, "max_score": 100, "weight": 0.25, "issues": [], "details": {}},
    "references": {"score": 90, "max_score": 100, "weight": 0.25, "issues": [], "details": {}},
    "headings": {"score": 100, "max_score": 100, "weight": 0.15, "issues": [], "details": {}},
    "document_format": {"score": 100, "max_score": 100, "weight": 0.10, "issues": [], "details": {}},
    "abstract": {"score": 100, "max_score": 100, "weight": 0.10, "issues": [], "details": {}},
    "figures": {"score": 100, "max_score": 100, "weight": 0.075, "issues": [], "details": {}},
    "tables": {"score": 100, "max_score": 100, "weight": 0.075, "issues": [], "details": {}}
  },
  "overall_score": 97,
  "submission_ready": true,
  "warnings": [],
  "summary": "Paper scores 97/100 for journal compliance."
}

## OUTPUT

Return ONLY the JSON. No markdown, no explanation."""


def create_validate_agent(llm: Any, journal_style: str = "APA 7th Edition") -> Agent:
    """
    Agent 4: VALIDATE — compliance scoring + report generation.

    Uses APA-specific scoring prompt for APA 7th Edition, generic rules-driven
    prompt for all other journals.
    """
    is_apa = "apa" in journal_style.lower()
    is_springer = "springer" in journal_style.lower()
    is_chicago = "chicago" in journal_style.lower()
    is_vancouver = any(x in journal_style.lower() for x in ["vancouver", "icmje", "nlm"])
    
    if is_apa:
        prompt = VALIDATE_SYSTEM_PROMPT
    elif is_springer:
        prompt = SPRINGER_VALIDATE_SYSTEM_PROMPT
    elif is_chicago:
        prompt = CHICAGO_VALIDATE_SYSTEM_PROMPT
    elif is_vancouver:
        prompt = VANCOUVER_VALIDATE_SYSTEM_PROMPT
    else:
        prompt = GENERIC_VALIDATE_SYSTEM_PROMPT

    if is_apa:
        role = "APA 7th Edition Compliance Validator"
        backstory = (
            "You are a senior academic editor and APA compliance specialist with 20 years of "
            "experience reviewing manuscripts. You have developed and applied systematic quality "
            "checklists across 300,000 manuscript reviews, covering citation consistency, "
            "structural completeness, reference quality, and formatting standards. "
            "You score manuscripts with mathematical precision — applying the exact weighted "
            "scoring formula, performing all 7 checks without exception. "
            "You verify that ALL numbered citations have been converted to author-date format, "
            "ALL references are in APA format with correct alphabetical ordering, and the document "
            "uses proper APA page structure (title page, abstract page, body, references page). "
            "Your overall_score drives the submission_ready decision. "
            "Before returning, you recompute overall_score from the breakdown using the exact "
            "weighted formula to guarantee consistency."
        )
    elif is_springer:
        role = "Springer Nature Compliance Validator"
        backstory = (
            "You are a senior academic editor specializing in Springer Nature manuscript compliance. "
            "You verify that the manuscript matches the `sn-jnl` (sn-mathphys-ay) author-date standards. "
            "You verify that ALL numbered citations have been converted to (Author Year) format, "
            "ALL references are alphabetized, and numeric heading hierarchy is applied. "
            "Your overall_score drives the submission_ready decision."
        )
    elif is_chicago:
        role = "Chicago 17th Edition Compliance Validator"
        backstory = (
            "You are a senior academic editor specializing in Chicago Manual of Style (17th Edition) Author-Date compliance. "
            "You verify that the manuscript uses Times New Roman 12pt, double spacing, Chicago Author-Date "
            "citations with italicized 'et al.', and correct un-numbered hierarchical headings. "
            "Your overall_score drives the submission_ready decision."
        )
    elif is_vancouver:
        role = "Vancouver Style Compliance Validator"
        backstory = (
            "You are a senior academic editor specializing in Vancouver (ICMJE) biomedical journal compliance. "
            "You verify that the manuscript uses Vancouver numbered citations in square brackets, "
            "references ordered by appearance, surname-initials author formatting, and structured headings. "
            "Your overall_score drives the submission_ready decision."
        )
    else:
        role = f"{journal_style} Compliance Validator"
        backstory = (
            f"You are a senior academic editor specializing in {journal_style} manuscript compliance. "
            "You have reviewed over 300,000 manuscripts across IEEE, Vancouver, Springer, "
            "Chicago, and other major journal styles. "
            "You score manuscripts against the EXACT rules provided — never assuming APA defaults. "
            "You check citation format, reference style, heading hierarchy, document formatting, "
            "abstract requirements, and figure/table conventions against the journal's specific rules. "
            "Your overall_score drives the submission_ready decision."
        )

    logger.info("[VALIDATE] Agent created — journal=%s is_apa=%s", journal_style, is_apa)

    return Agent(
        role=role,
        goal=prompt,
        backstory=backstory,
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=1,
        max_tokens=65536,
    )