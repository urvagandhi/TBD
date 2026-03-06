"""
Agent 3: INTERPRET — Analyze journal formatting rules and surface critical constraints.

This agent receives the pre-loaded rules JSON and enriches it by identifying
the most critical formatting requirements that are commonly violated, adding
a 'critical_checks' list per section and a 'style_summary' at the top level.
"""
import json
import time
from typing import Any

from crewai import Agent
from crewai.tools import tool

from tools.logger import get_logger
from tools.rule_extractor import extract_journal_rules_from_url
from tools.rule_loader import load_rules as _load_rules
from tools.tool_errors import LLMResponseError, RuleLoadError  # noqa: F401 — available for callers

logger = get_logger(__name__)

# All 11 top-level keys that a valid rules JSON must contain (Improvement 3)
REQUIRED_INTERPRET_KEYS = [
    "style_name", "document", "title_page", "abstract", "headings",
    "citations", "references", "figures", "tables", "equations", "general_rules",
]

# In-memory cache so repeated runs don't re-read disk (Improvement 12)
_RULE_ENGINE_CACHE: dict[str, dict] = {}


@tool("Journal Rules Loader")
def load_journal_rules(journal_style: str) -> str:
    """
    Load the complete formatting rules for a specific journal style.

    Supported journals: APA 7th Edition, IEEE, Vancouver, Springer, Chicago.
    Returns exact JSON content from the rules file — no interpretation.
    Results are cached in-memory so repeated calls for the same journal
    avoid redundant disk reads (Improvement 12).

    Args:
        journal_style: Journal name (e.g., 'APA 7th Edition', 'IEEE', 'Vancouver').

    Returns:
        JSON string of the complete formatting rules.

    Raises:
        RuleLoadError: If journal is not supported or rules file is corrupted.
    """
    # Cache hit — skip disk read (Improvement 12)
    if journal_style in _RULE_ENGINE_CACHE:
        logger.info(
            "[INTERPRET] Cache hit — journal=%s (skipping disk read)", journal_style
        )
        return json.dumps(_RULE_ENGINE_CACHE[journal_style], indent=2)

    try:
        t0 = time.time()
        rules = _load_rules(journal_style)
        elapsed = time.time() - t0

        # Validate required keys (Improvement 3)
        _validate_interpret_output(rules)

        # Populate cache
        _RULE_ENGINE_CACHE[journal_style] = rules

        logger.info(
            "[INTERPRET] Rules loaded — journal=%s keys=%d elapsed=%.3fs",
            journal_style, len(rules), elapsed,
        )
        return json.dumps(rules, indent=2)
    except RuleLoadError:
        raise
    except Exception as e:
        raise RuleLoadError(str(e)) from e


def _validate_interpret_output(data: dict) -> None:
    """
    Validate that loaded rules contain all 11 required top-level keys.

    Args:
        data: Parsed rules dict.

    Raises:
        RuleLoadError: If required keys are missing.
        LLMResponseError: If data is not a dict.
    """
    if not isinstance(data, dict):
        raise LLMResponseError(
            f"Interpret output must be a JSON object (dict), got {type(data).__name__}"
        )
    missing = [k for k in REQUIRED_INTERPRET_KEYS if k not in data]
    if missing:
        raise RuleLoadError(
            f"Rules JSON missing required top-level keys: {missing}. "
            f"All 11 keys required: {REQUIRED_INTERPRET_KEYS}"
        )
    logger.info(
        "[INTERPRET] Rules validation passed — all %d required keys present",
        len(REQUIRED_INTERPRET_KEYS),
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


def create_interpret_agent(llm: Any) -> Agent:
    """
    Agent 3: INTERPRET — Analyze journal rules and surface critical constraints.

    Receives the pre-loaded rules JSON from crew.py, analyzes it to identify
    the most commonly violated formatting requirements, and returns the enriched
    rules with 'critical_checks' per section and a 'style_summary'.

    Required output keys (all original 11 must be present + enrichment):
      style_name, document, title_page, abstract, headings,
      citations, references, figures, tables, equations, general_rules,
      style_summary (new), critical_checks per section (new)

    Args:
        llm: Shared LLM string at temperature=0.

    Returns:
        CrewAI Agent configured for rule analysis.
    """
    logger.info("[INTERPRET] Agent created")

    return Agent(
        role="Journal Formatting Violation Scanner",
        goal=(
            "Scan a parsed manuscript against a journal's formatting rules and "
            "identify the top violations that would cause desk rejection.\n\n"
            "YOUR TASK:\n"
            "  1. Receive the parsed paper_structure JSON from the parse step\n"
            "  2. Cross-reference every paper element against the provided journal rules\n"
            "  3. For each rule category (abstract, headings, citations, references, "
            "figures, tables, font/margins), determine if a violation exists in the manuscript\n"
            "  4. Rank the top 5 violations by desk rejection risk\n"
            "  5. For each violation, provide an exact fix_instruction the Transform agent "
            "can execute directly\n\n"
            "OUTPUT must be a JSON object with these keys:\n"
            "  journal: name of the journal\n"
            "  total_violations_found: integer count\n"
            "  critical_violations: list of up to 5 objects, each with:\n"
            "    rule_category: e.g. 'abstract', 'headings', 'citations'\n"
            "    rule_description: exact rule text from the journal rules\n"
            "    rule_reference: e.g. 'APA 7th §8.11'\n"
            "    violation_found: what is wrong in this specific manuscript\n"
            "    fix_instruction: precise, actionable transformation instruction\n"
            "  rule_summary: 2-sentence plain-English summary of what needs to change\n\n"
            "Return ONLY valid JSON — no markdown fences, no explanation."
        ),
        backstory=(
            "You are a senior academic editor with 20 years of experience reviewing "
            "manuscripts for APA, IEEE, Vancouver, Springer, and Chicago style journals. "
            "You have reviewed over 300,000 manuscripts and know exactly which formatting "
            "rules authors violate most often. "
            "When given a manuscript and its target journal's rules, you immediately spot "
            "the violations that cause desk rejections: abstract word limit exceeded, "
            "wrong citation style, heading case violations, reference ordering errors, "
            "missing figure caption format. "
            "You don't just list rules — you compare the actual manuscript content against "
            "the rules and produce specific, actionable fix instructions that the Transform "
            "agent can execute without any ambiguity."
        ),
        llm=llm,
        tools=[load_journal_rules, extract_journal_rules_from_url],
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )
