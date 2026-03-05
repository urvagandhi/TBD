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
