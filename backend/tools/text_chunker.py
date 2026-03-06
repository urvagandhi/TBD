"""
Section-aware text chunker for manuscript processing.

Replaces naive head+tail truncation with intelligent section-aware splitting.
Priority order ensures Abstract and References are ALWAYS fully preserved —
the two sections most critical for compliance scoring.

Preservation priority:
  1. Preamble / title block  (always — contains journal/author metadata)
  2. Abstract                (always — word count check, structured keywords)
  3. References              (always — citation consistency, ordering check)
  4. Introduction            (high — IMRAD structure check)
  5. Methods / Materials     (medium — IMRAD structure check)
  6. Results                 (medium — IMRAD structure check)
  7. Discussion / Conclusion (medium — IMRAD structure check)
  8. Keywords / Other        (low — included only if budget allows)
"""
import re
from dataclasses import dataclass, field

from tools.logger import get_logger

logger = get_logger(__name__)

# Maximum characters sent to the LLM pipeline (safe under typical 32K token windows)
MAX_CHARS = 1000000

# Characters to include per section when truncating a large section
_SECTION_PREVIEW_CHARS = 600

_TRUNCATION_NOTE = "[... SECTION TRUNCATED — content continues in original document ...]"

# Known section header strings — matched case-insensitively
# Ordered to define IMRAD priority (index 0 = highest priority after preamble)
_SECTION_ORDER: list[str] = [
    "abstract",
    "introduction",
    "background",
    "literature review",
    "related work",
    "methodology",
    "methods",
    "materials and methods",
    "experimental",
    "results",
    "results and discussion",
    "discussion",
    "conclusion",
    "conclusions",
    "acknowledgements",
    "acknowledgments",
    "keywords",
    "references",
    "bibliography",
    "appendix",
]

# Sections that must be fully preserved regardless of budget
_ALWAYS_FULL = {"abstract", "references", "bibliography", "preamble"}

# Build a single regex that detects section header lines
# Matches: a line that is ONLY a section header word (possibly with numbering like "1. Introduction")
_HEADER_PATTERN = re.compile(
    r"^\s*(?:\d+[\.\s]+)?("
    + "|".join(re.escape(h) for h in _SECTION_ORDER)
    + r")s?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class _Section:
    name: str        # normalized lowercase section name
    raw_name: str    # original text as it appeared in document
    text: str        # full text content (excluding the header line)
    chars: int = field(init=False)

    def __post_init__(self) -> None:
        self.chars = len(self.text)

    def priority(self) -> int:
        """Lower = higher priority. Preamble = 0, unknown = 999."""
        if self.name == "preamble":
            return 0
        try:
            return _SECTION_ORDER.index(self.name) + 1
        except ValueError:
            return 999


def split_into_sections(text: str) -> list[_Section]:
    """
    Split manuscript text into labeled sections.

    Uses HEADER_PATTERN to detect section boundaries. Everything before the
    first recognized header is labeled "preamble" (title, authors, affiliations).

    Returns:
        List of _Section objects in document order.
    """
    sections: list[_Section] = []
    last_end = 0
    current_label = "preamble"
    current_raw = "preamble"

    for match in _HEADER_PATTERN.finditer(text):
        # Save the text before this header
        segment = text[last_end:match.start()].strip()
        if segment:
            sections.append(_Section(
                name=current_label,
                raw_name=current_raw,
                text=segment,
            ))

        current_label = match.group(1).lower().strip()
        current_raw   = match.group(0).strip()
        last_end      = match.end()

    # Save the final section
    final_segment = text[last_end:].strip()
    if final_segment:
        sections.append(_Section(
            name=current_label,
            raw_name=current_raw,
            text=final_segment,
        ))

    # If no headers were found at all, return the whole text as preamble
    if not sections:
        sections = [_Section(name="preamble", raw_name="preamble", text=text.strip())]

    logger.debug(
        "[CHUNKER] Detected %d sections: %s",
        len(sections),
        [s.name for s in sections],
    )
    return sections


def smart_truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    """
    Intelligently truncate a manuscript to fit within max_chars.

    If the text already fits, returns it unchanged.

    Otherwise:
      1. Split into sections
      2. Always include preamble, abstract, references in full
      3. Fill remaining budget with IMRAD sections in priority order
      4. Sections that don't fit are included as header + preview + truncation note
      5. Always ends with the references section (critical for compliance)

    Args:
        text: Full extracted manuscript text.
        max_chars: Maximum characters to return (default 32 000).

    Returns:
        String of at most max_chars characters with [TRUNCATED] markers where needed.
    """
    if len(text) <= max_chars:
        return text

    sections = split_into_sections(text)
    total_original = len(text)

    # Separate into: must-have (always full) vs optional (fill if budget allows)
    must_have: list[_Section] = []
    optional:  list[_Section] = []

    for sec in sections:
        if sec.name in _ALWAYS_FULL:
            must_have.append(sec)
        else:
            optional.append(sec)

    # Sort optional sections by priority (IMRAD order)
    optional.sort(key=lambda s: s.priority())

    # Budget tracking
    used = sum(s.chars for s in must_have)
    remaining = max_chars - used

    # Assign budget to optional sections
    included:  list[_Section] = list(must_have)
    truncated: list[_Section] = []

    for sec in optional:
        if remaining >= sec.chars:
            included.append(sec)
            remaining -= sec.chars
        elif remaining >= _SECTION_PREVIEW_CHARS + 50:
            # Include a preview — better than nothing
            preview_text = (
                sec.text[:_SECTION_PREVIEW_CHARS].rstrip()
                + f"\n{_TRUNCATION_NOTE}"
            )
            truncated_sec = _Section(
                name=sec.name,
                raw_name=sec.raw_name,
                text=preview_text,
            )
            truncated.append(truncated_sec)
            included.append(truncated_sec)
            remaining = 0
            break
        else:
            # No budget left — add a stub so the LLM knows the section exists
            stub = _Section(
                name=sec.name,
                raw_name=sec.raw_name,
                text=f"{_TRUNCATION_NOTE}",
            )
            included.append(stub)

    # Re-sort to document order (by original index)
    name_order = {s.name: i for i, s in enumerate(sections)}
    included.sort(key=lambda s: name_order.get(s.name, 999))

    # Build the output string
    parts: list[str] = []
    for sec in included:
        header = sec.raw_name if sec.raw_name != "preamble" else ""
        if header:
            parts.append(f"{header}\n{sec.text}")
        else:
            parts.append(sec.text)

    result = "\n\n".join(parts)

    truncated_names = [s.name for s in truncated]
    dropped_names   = [
        s.name for s in optional
        if s.name not in {i.name for i in included}
    ]

    logger.warning(
        "[CHUNKER] Paper truncated: %d → %d chars | "
        "preserved=%s | truncated=%s | dropped=%s",
        total_original, len(result),
        [s.name for s in must_have] + [s.name for s in optional if s in included],
        truncated_names,
        dropped_names,
    )

    return result
