"""
Unified exception hierarchy for all Agent Paperpal tools.

Agents and the pipeline catch these specific types to produce
meaningful error messages instead of generic Python exceptions.
"""


class ToolError(Exception):
    """Base exception for all tool-related errors."""


class FileProcessingError(ToolError):
    """Raised when a file cannot be read, opened, or is otherwise inaccessible."""


class ExtractionError(ToolError):
    """Raised when text extraction from a PDF or DOCX fails."""


class RuleValidationError(ToolError):
    """Raised when journal formatting rules fail validation or cannot be loaded."""


class DocumentWriteError(ToolError):
    """Raised when DOCX generation or writing to disk fails."""


# ── Agent-specific exceptions ────────────────────────────────────────────────

class LLMResponseError(ToolError):
    """Raised when an LLM returns output that cannot be parsed as expected JSON."""


class ParseError(ToolError):
    """Raised by Agent 2 (PARSE) when paper structure cannot be extracted."""


class RuleLoadError(ToolError):
    """Raised by Agent 3 (INTERPRET) when journal rules cannot be loaded."""


class TransformError(ToolError):
    """Raised by Agent 4 (TRANSFORM) when docx_instructions cannot be produced."""


class ValidationError(ToolError):
    """Raised by Agent 5 (VALIDATE) when compliance report cannot be generated."""
