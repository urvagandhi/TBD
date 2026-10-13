import json
import re
from pathlib import Path
from typing import Any, Optional

from tools.logger import get_logger
from tools.tool_errors import RuleValidationError

logger = get_logger(__name__)

# Import discovery module lazily to avoid circular imports
_discovery = None


def _get_discovery():
    global _discovery
    if _discovery is None:
        from tools import journal_discovery
        _discovery = journal_discovery
    return _discovery

# Map of accepted journal name variations (all lowercase) → filename
JOURNAL_MAP = {
    # APA variations
    "apa": "apa7.json",
    "apa 7": "apa7.json",
    "apa7": "apa7.json",
    "apa 7th": "apa7.json",
    "apa 7th edition": "apa7.json",
    "apa seventh edition": "apa7.json",
    "american psychological association": "apa7.json",

    # IEEE variations
    "ieee": "ieee.json",
    "ieee style": "ieee.json",
    "institute of electrical and electronics engineers": "ieee.json",

    # Vancouver variations
    "vancouver": "vancouver.json",
    "vancouver style": "vancouver.json",
    "icmje": "vancouver.json",
    "nlm": "vancouver.json",
    "national library of medicine": "vancouver.json",

    # Springer variations
    "springer": "springer.json",
    "springer basic": "springer.json",
    "springer nature": "springer.json",
    "springer basic (author-date)": "springer.json",

    # Chicago variations
    "chicago": "chicago.json",
    "chicago 17": "chicago.json",
    "chicago 17th": "chicago.json",
    "chicago 17th edition": "chicago.json",
    "chicago manual of style": "chicago.json",
    "cms": "chicago.json",
}

RULES_DIR = Path(__file__).parent.parent / "rules"
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# Display names for UI / error messages
_DISPLAY_NAMES = [
    "APA 7th Edition",
    "IEEE",
    "Vancouver",
    "Springer",
    "Chicago 17th Edition",
]


def get_builtin_journals() -> list[str]:
    """Return only the five maintained local rule profiles.

    These are the only journals that can be selected without the discovery and
    human-approval workflow.  Cached or approved discoveries deliberately do
    not belong in this list because they are versioned research results, not
    product-maintained defaults.
    """
    return list(_DISPLAY_NAMES)

# In-memory cache: filename → parsed rules dict
_RULE_CACHE: dict = {}

_RULES_SCHEMA: dict | None = None
_SCHEMA_LOADED: bool = False


def _load_schema() -> dict | None:
    """Load rules_schema.json once. Returns None if jsonschema not installed."""
    schema_path = SCHEMAS_DIR / "rules_schema.json"
    if not schema_path.exists():
        logger.warning("[RULES] Schema file not found at %s — skipping validation", schema_path)
        return None
    try:
        import jsonschema  # noqa: F401
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except ImportError:
        logger.warning("[RULES] jsonschema not installed — skipping schema validation")
        return None
    except Exception as e:
        logger.warning("[RULES] Could not load schema: %s", e)
        return None


def _get_schema() -> dict | None:
    """Lazy-load schema once per process."""
    global _RULES_SCHEMA, _SCHEMA_LOADED
    if not _SCHEMA_LOADED:
        _RULES_SCHEMA = _load_schema()
        _SCHEMA_LOADED = True
    return _RULES_SCHEMA


def _find_extracted_rules(journal_style: str) -> dict | None:
    """
    Search the extracted/ folder for a cached rules file matching this journal.
    Returns parsed rules dict or None.
    """
    extracted_dir = RULES_DIR / "extracted"
    if not extracted_dir.exists():
        return None

    slug = re.sub(r"[^a-z0-9]+", "-", journal_style.lower()).strip("-")[:60]
    cache_file = extracted_dir / f"{slug}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "style_name" in data:
                logger.info("[RULES] Found extracted rules: %s", cache_file.name)
                return data
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    for f in extracted_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("style_name", "").lower() == journal_style.lower():
                logger.info("[RULES] Found extracted rules by style_name: %s", f.name)
                return data
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return None


def _find_approved_rules(journal_style: str) -> dict | None:
    """Return the newest explicitly approved discovery result for a journal."""
    approved_dir = RULES_DIR / "approved"
    if not approved_dir.exists():
        return None
    matches = []
    for path in approved_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("journal_name", "").lower() == journal_style.lower() and payload.get("status") == "approved":
                matches.append((payload.get("approved_at", 0), payload))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    if matches:
        latest = max(matches, key=lambda item: item[0])[1]
        logger.info("[RULES] Found approved evidence-backed rule set: %s", latest.get("rule_set_id", "unknown"))
        return latest.get("rules")
    return None


def load_rules(journal_style: str) -> dict:
    """
    Load formatting rules for the given journal style.

    Fallback chain:
    1. Built-in JOURNAL_MAP (instant)
    2. Explicitly approved discovery results in rules/approved/ (fast)
    3. Legacy extracted rules in rules/extracted/ (backward compatibility)

    Uses in-memory cache to avoid repeated disk reads.
    Validates against rules_schema.json if jsonschema is installed.

    Args:
        journal_style: Name of journal style (e.g. "APA 7th Edition")

    Returns:
        dict: Complete formatting rules

    Raises:
        RuleValidationError: If journal not found, rules JSON is corrupted, or schema fails.
        FileNotFoundError: If rules JSON file is missing from disk.
    """
    key = journal_style.lower().strip()
    filename = JOURNAL_MAP.get(key)

    if filename:
        cache_key = f"builtin:{filename}"
    else:
        cache_key = f"dynamic:{key}"

    if cache_key in _RULE_CACHE:
        logger.debug("[RULES] Cache hit for %s", cache_key)
        return _RULE_CACHE[cache_key]

    rules = None

    # Path 1: Built-in journal
    if filename:
        rules_path = RULES_DIR / filename
        if not rules_path.exists():
            raise FileNotFoundError(
                f"Rules file not found: {rules_path}\n"
                f"Make sure {filename} exists in backend/rules/"
            )
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                rules = json.load(f)
        except json.JSONDecodeError as e:
            raise RuleValidationError(
                f"Rules file '{filename}' is corrupted or invalid JSON: {e}"
            ) from e

    # Path 2: Reuse evidence-backed rules only after explicit approval.
    if rules is None:
        rules = _find_approved_rules(journal_style)

    # Path 3: legacy extracted cache. New discovery must go through the
    # approval endpoints; this remains only so older locally-created files work.
    if rules is None:
        rules = _find_extracted_rules(journal_style)

    # Do not silently discover and trust an arbitrary web result here. The API
    # exposes /journals/discover for research and user approval first.
    if rules is None:
        raise RuleValidationError(
            f"No approved rules are available for '{journal_style}'. "
            "Use journal discovery, review the evidence, and approve a source first."
        )

    # Schema validation (non-blocking)
    schema = _get_schema()
    if schema is not None:
        try:
            import jsonschema
            jsonschema.validate(instance=rules, schema=schema)
        except jsonschema.ValidationError as e:
            logger.warning("[RULES] Schema validation warning for '%s': %s", journal_style, e.message)
        except Exception as e:
            logger.warning("[RULES] Schema validation error for '%s': %s", journal_style, e)

    _RULE_CACHE[cache_key] = rules
    logger.info("[RULES] Loaded rules for '%s' (%d top-level sections)", journal_style, len(rules))
    return rules


def get_supported_journals() -> list:
    """Return list of supported journal display names (built-in + extracted)."""
    journals = get_builtin_journals()
    extracted_dir = RULES_DIR / "extracted"
    if extracted_dir.exists():
        for f in sorted(extracted_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                name = data.get("style_name", f.stem)
                if name not in journals:
                    journals.append(name)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return journals


def validate_rules(rules: dict) -> bool:
    """
    Validate that a rules dict has all required top-level fields.

    Returns:
        True if valid.

    Raises:
        ValueError: If any required field is missing.
    """
    required_keys = [
        "style_name", "document", "abstract",
        "headings", "citations", "references",
        "figures", "tables", "general_rules",
    ]
    for key in required_keys:
        if key not in rules:
            raise RuleValidationError(f"Rules missing required field: '{key}'")
    return True


def clear_cache() -> None:
    """Clear the in-memory rules cache (useful for testing)."""
    _RULE_CACHE.clear()
    logger.debug("[RULES] Cache cleared")


def get_rule_value(rules: dict, key_path: str, default=None):
    """
    Safe nested dict accessor using dot notation.

    Args:
        rules: The rules dict.
        key_path: Dot-separated key path, e.g. "citations.format_one_author".
        default: Value to return if path is not found.

    Returns:
        The value at key_path, or default if any key in the path is missing.

    Example:
        get_rule_value(rules, "abstract.max_words", 250) → 250
    """
    keys = key_path.split(".")
    current = rules
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


if __name__ == "__main__":
    for journal in get_supported_journals():
        try:
            rules = load_rules(journal)
            validate_rules(rules)
            print(f"OK {journal} — loaded ({len(rules)} sections)")
        except Exception as e:
            print(f"FAIL {journal} — {e}")

    # Test name variations
    rules_a = load_rules("APA 7th Edition")
    rules_b = load_rules("apa")
    assert rules_a is rules_b, "Cache miss — same file loaded twice!"
    print("\nOK cache: load_rules('APA 7th Edition') is load_rules('apa')")

    # Test get_rule_value
    assert get_rule_value(rules_a, "abstract.max_words") == 250
    assert get_rule_value(rules_a, "nonexistent.key", "fallback") == "fallback"
    print("OK get_rule_value: nested access and fallback work")
