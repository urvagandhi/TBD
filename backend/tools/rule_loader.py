import json
import os
from pathlib import Path

# Map of accepted journal name variations (all lowercase) → filename
JOURNAL_MAP = {
    # APA variations
    "apa": "apa7.json",
    "apa 7": "apa7.json",
    "apa7": "apa7.json",
    "apa 7th": "apa7.json",
    "apa 7th edition": "apa7.json",
    "american psychological association": "apa7.json",

    # IEEE variations
    "ieee": "ieee.json",
    "institute of electrical and electronics engineers": "ieee.json",

    # Vancouver variations
    "vancouver": "vancouver.json",
    "icmje": "vancouver.json",
    "vancouver style": "vancouver.json",

    # Springer variations
    "springer": "springer.json",
    "springer basic": "springer.json",
    "springer nature": "springer.json",

    # Chicago variations
    "chicago": "chicago.json",
    "chicago 17": "chicago.json",
    "chicago 17th": "chicago.json",
    "chicago 17th edition": "chicago.json",
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

# In-memory cache: filename → parsed rules dict
_RULE_CACHE: dict = {}


def _load_schema() -> dict | None:
    """Load rules_schema.json once. Returns None if jsonschema not installed."""
    schema_path = SCHEMAS_DIR / "rules_schema.json"
    if not schema_path.exists():
        return None
    try:
        import jsonschema  # noqa: F401 — confirm it's available
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except ImportError:
        return None


_RULES_SCHEMA: dict | None = None
_SCHEMA_LOADED: bool = False


def _get_schema() -> dict | None:
    """Lazy-load schema once per process."""
    global _RULES_SCHEMA, _SCHEMA_LOADED
    if not _SCHEMA_LOADED:
        _RULES_SCHEMA = _load_schema()
        _SCHEMA_LOADED = True
    return _RULES_SCHEMA


def load_rules(journal_style: str) -> dict:
    """
    Load formatting rules for the given journal style.

    Uses in-memory cache to avoid repeated disk reads.
    Validates against rules_schema.json if jsonschema is installed.

    Args:
        journal_style: Name of journal style (e.g. "APA 7th Edition")

    Returns:
        dict: Complete formatting rules

    Raises:
        ValueError: If journal not found in JOURNAL_MAP.
        FileNotFoundError: If rules JSON file is missing.
        jsonschema.ValidationError: If loaded rules fail schema validation.
    """
    key = journal_style.lower().strip()
    filename = JOURNAL_MAP.get(key)

    if not filename:
        raise ValueError(
            f"Journal '{journal_style}' not found.\n"
            f"Supported journals: {', '.join(_DISPLAY_NAMES)}"
        )

    # Return from cache if already loaded
    if filename in _RULE_CACHE:
        return _RULE_CACHE[filename]

    rules_path = RULES_DIR / filename

    if not rules_path.exists():
        raise FileNotFoundError(
            f"Rules file not found: {rules_path}\n"
            f"Make sure {filename} exists in backend/rules/"
        )

    with open(rules_path, "r", encoding="utf-8") as f:
        rules = json.load(f)

    # Schema validation (non-blocking — warns if jsonschema unavailable)
    schema = _get_schema()
    if schema is not None:
        try:
            import jsonschema
            jsonschema.validate(instance=rules, schema=schema)
        except jsonschema.ValidationError as e:
            raise jsonschema.ValidationError(
                f"Rules file '{filename}' failed schema validation: {e.message}"
            ) from e

    # Store in cache before returning
    _RULE_CACHE[filename] = rules
    return rules


def get_supported_journals() -> list:
    """Return list of supported journal display names."""
    return list(_DISPLAY_NAMES)


def validate_rules(rules: dict) -> bool:
    """
    Validate that rules dict has all required fields.
    Returns True if valid, raises ValueError if not.
    """
    required_keys = [
        "style_name", "document", "abstract",
        "headings", "citations", "references",
        "figures", "tables", "general_rules",
    ]
    for key in required_keys:
        if key not in rules:
            raise ValueError(f"Rules missing required field: '{key}'")
    return True


def clear_cache() -> None:
    """Clear the in-memory rules cache (useful for testing)."""
    _RULE_CACHE.clear()


# Quick test when run directly
if __name__ == "__main__":
    for journal in get_supported_journals():
        try:
            rules = load_rules(journal)
            validate_rules(rules)
            print(f"OK {journal} -- loaded successfully (sections: {len(rules)})")
        except Exception as e:
            print(f"FAIL {journal} -- ERROR: {e}")

    # Confirm cache is working
    print("\nCache hit test:")
    rules_a = load_rules("APA 7th Edition")
    rules_b = load_rules("apa")
    assert rules_a is rules_b, "Cache miss — same file loaded twice!"
    print("  Cache hit confirmed: load_rules('APA 7th Edition') is load_rules('apa')")
