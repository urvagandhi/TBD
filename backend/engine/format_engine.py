"""
FormatEngine — Rule interpretation layer for Agent Paperpal.

Wraps a loaded rules dict and exposes formatting utilities used by agents.
Agents call this instead of directly accessing raw rule dicts, providing
a stable interface that abstracts rule schema internals.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running standalone: python engine/format_engine.py
sys.path.insert(0, str(Path(__file__).parent.parent))


class FormatEngine:
    """Interprets journal rule JSON and provides formatting utilities."""

    def __init__(self, rules: dict) -> None:
        self._rules = rules

    # ------------------------------------------------------------------
    # Document settings
    # ------------------------------------------------------------------

    def get_document_settings(self) -> dict:
        """Return core document formatting parameters."""
        doc = self._rules["document"]
        return {
            "font": doc["font"],
            "font_size": doc["font_size"],
            "line_spacing": doc["line_spacing"],
            "margins": doc["margins"],
            "alignment": doc["alignment"],
            "columns": doc["columns"],
        }

    # ------------------------------------------------------------------
    # Heading rules
    # ------------------------------------------------------------------

    def get_heading_rules(self, level: str) -> dict:
        """
        Return formatting rules for the given heading level.

        Args:
            level: "H1", "H2", or "H3"

        Returns:
            dict with bold, italic, centered, underline, font_size, case, etc.

        Raises:
            KeyError: If level is not H1/H2/H3.
        """
        level = level.upper()
        headings = self._rules["headings"]
        if level not in headings:
            raise KeyError(f"Heading level '{level}' not found. Available: {list(headings.keys())}")
        return headings[level]

    # ------------------------------------------------------------------
    # Figure / Table rules
    # ------------------------------------------------------------------

    def get_figure_rules(self) -> dict:
        """Return figure formatting rules."""
        return self._rules["figures"]

    def get_table_rules(self) -> dict:
        """Return table formatting rules."""
        return self._rules["tables"]

    # ------------------------------------------------------------------
    # Reference templates
    # ------------------------------------------------------------------

    def get_reference_template(self, reference_type: str) -> str:
        """
        Return the format template string for a given reference type.

        Args:
            reference_type: One of journal_article, book, book_chapter,
                            website, conference_paper.

        Returns:
            Template string with placeholders.

        Raises:
            KeyError: If reference_type is not in the rules.
        """
        formats = self._rules["references"]["formats"]
        if reference_type not in formats:
            raise KeyError(
                f"Reference type '{reference_type}' not found. "
                f"Available: {list(formats.keys())}"
            )
        return formats[reference_type]

    # ------------------------------------------------------------------
    # Citation generation
    # ------------------------------------------------------------------

    def format_citation(
        self,
        authors: list[str],
        year: int | str,
        page: int | str | None = None,
    ) -> str:
        """
        Generate an in-text citation string using the journal's citation rules.

        Supports both author-date and numbered citation styles.

        Args:
            authors: List of author last names, e.g. ["Smith"], ["Smith", "Jones"].
            year: Publication year, e.g. 2020.
            page: Optional page number for direct quotes.

        Returns:
            Formatted citation string, e.g. "(Smith, 2020)" or "[1]".

        Examples:
            >>> engine.format_citation(["Smith"], 2020)
            "(Smith, 2020)"
            >>> engine.format_citation(["Smith", "Jones"], 2020)
            "(Smith & Jones, 2020)"
            >>> engine.format_citation(["Smith", "Jones", "Brown"], 2020)
            "(Smith et al., 2020)"
            >>> engine.format_citation(["Smith"], 2020, page=45)
            "(Smith, 2020, p. 45)"
        """
        citations = self._rules["citations"]
        general = self._rules["general_rules"]

        style = citations.get("style", "author-date")
        et_al_threshold = int(general.get("et_al_threshold", 3))
        use_ampersand = bool(general.get("use_ampersand_in_citations", False))
        page_format_template = citations.get("page_format", "p. {page}")

        # --- Numbered citation (IEEE, Vancouver) ---
        if style == "numbered":
            # The actual number is assigned by document context;
            # return a placeholder token the transform agent can replace.
            fmt = citations.get("format_numbered") or "[N]"
            return fmt.replace("N", "?")

        # --- Author-date citation (APA, Springer, Chicago) ---
        n = len(authors)
        separator = " & " if use_ampersand else " and "

        if n == 0:
            author_part = "Unknown"
        elif n == 1:
            author_part = authors[0]
        elif n == 2:
            author_part = f"{authors[0]}{separator}{authors[1]}"
        elif n < et_al_threshold:
            # e.g. et_al_threshold=4 → 3 authors listed individually
            all_but_last = ", ".join(authors[:-1])
            author_part = f"{all_but_last}{separator}{authors[-1]}"
        else:
            author_part = f"{authors[0]} et al."

        brackets = citations.get("brackets", "parentheses")
        open_b = "(" if brackets == "parentheses" else "["
        close_b = ")" if brackets == "parentheses" else "]"

        # Determine separator between author and year (APA uses comma, Chicago/Springer use space)
        # Detect from format_one_author template if available
        sample = citations.get("format_one_author", "(Smith, 2020)")
        author_year_sep = ", " if ", " in (sample or "") else " "

        if page is not None and citations.get("include_page_for_quotes", False):
            page_str = page_format_template.replace("{page}", str(page))
            # page_format may be literal like "p. 45" or "45" — normalise
            if str(page) not in page_str:
                page_str = f"p. {page}"
            return f"{open_b}{author_part}{author_year_sep}{year}, {page_str}{close_b}"

        return f"{open_b}{author_part}{author_year_sep}{year}{close_b}"

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get_citations_rules(self) -> dict:
        """Return the full citations section."""
        return self._rules["citations"]

    def get_references_rules(self) -> dict:
        """Return the full references section (excluding formats)."""
        r = dict(self._rules["references"])
        r.pop("formats", None)
        return r

    def get_general_rules(self) -> dict:
        """Return the general_rules section."""
        return self._rules["general_rules"]

    def get_style_name(self) -> str:
        """Return the journal style display name."""
        return self._rules["style_name"]


# ---------------------------------------------------------------------------
# Helper loader
# ---------------------------------------------------------------------------

def load_format_engine(style_name: str) -> FormatEngine:
    """
    Load journal rules and return a configured FormatEngine.

    Args:
        style_name: Journal name accepted by rule_loader.load_rules(),
                    e.g. "APA 7th Edition", "IEEE", "Vancouver".

    Returns:
        FormatEngine instance ready to use.
    """
    from tools.rule_loader import load_rules
    rules = load_rules(style_name)
    return FormatEngine(rules)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    journals = [
        "APA 7th Edition",
        "IEEE",
        "Vancouver",
        "Springer",
        "Chicago 17th Edition",
    ]

    for journal in journals:
        print(f"\n{'='*60}")
        print(f"  {journal}")
        print("="*60)
        engine = load_format_engine(journal)

        print("Document settings:")
        print(f"  {engine.get_document_settings()}")

        print("H1 heading rules:")
        print(f"  {engine.get_heading_rules('H1')}")

        print("Citation — 1 author:")
        print(f"  {engine.format_citation(['Smith'], 2020)}")

        print("Citation — 2 authors:")
        print(f"  {engine.format_citation(['Smith', 'Jones'], 2020)}")

        print("Citation — 3+ authors:")
        print(f"  {engine.format_citation(['Smith', 'Jones', 'Brown'], 2020)}")

        print("Citation — with page:")
        print(f"  {engine.format_citation(['Smith'], 2020, page=45)}")

        print("journal_article template:")
        print(f"  {engine.get_reference_template('journal_article')}")
