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

    def get_font(self) -> str:
        """Return the document font name."""
        return self._rules["document"].get("font", "Times New Roman")

    def get_font_size(self) -> int:
        """Return the document font size in points."""
        return int(self._rules["document"].get("font_size", 12))

    def get_line_spacing(self) -> float:
        """Return the line spacing multiplier (1.0, 1.5, 2.0)."""
        return float(self._rules["document"].get("line_spacing", 2.0))

    def get_margins(self) -> dict:
        """Return margins dict with top/bottom/left/right keys."""
        return self._rules["document"].get("margins", {
            "top": "1in", "bottom": "1in", "left": "1in", "right": "1in",
        })

    def get_alignment(self) -> str:
        """Return body text alignment: 'left' or 'justify'."""
        return self._rules["document"].get("alignment", "left")

    def get_columns(self) -> int:
        """Return number of columns (1 or 2)."""
        return int(self._rules["document"].get("columns", 1))

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

    def get_heading_style(self, level: int) -> dict:
        """
        Return heading style dict for the given numeric level (1, 2, or 3).

        Returns:
            dict with bold (bool), italic (bool), centered (bool),
            case (str), numbering (str), font_size (int).
        """
        key = f"H{level}"
        headings = self._rules.get("headings", {})
        rules = headings.get(key, {})
        return {
            "bold": rules.get("bold", True),
            "italic": rules.get("italic", False),
            "centered": rules.get("centered", False),
            "case": rules.get("case", "Title Case"),
            "numbering": rules.get("numbering", "none"),
            "font_size": int(rules.get("font_size", self.get_font_size())),
        }

    # ------------------------------------------------------------------
    # Abstract rules
    # ------------------------------------------------------------------

    def get_abstract_rules(self) -> dict:
        """Return the full abstract section rules."""
        return self._rules.get("abstract", {})

    def get_abstract_word_limit(self) -> int:
        """Return the maximum word count for the abstract."""
        return int(self._rules.get("abstract", {}).get("max_words", 250))

    def is_abstract_label_centered(self) -> bool:
        """Return True if the abstract label should be centered."""
        return bool(self._rules.get("abstract", {}).get("label_centered", True))

    def is_abstract_label_bold(self) -> bool:
        """Return True if the abstract label should be bold."""
        return bool(self._rules.get("abstract", {}).get("label_bold", False))

    # ------------------------------------------------------------------
    # Figure / Table rules
    # ------------------------------------------------------------------

    def get_figure_rules(self) -> dict:
        """Return figure formatting rules."""
        return self._rules["figures"]

    def get_figure_label_prefix(self) -> str:
        """Return the figure label prefix, e.g. 'Figure' or 'Fig.'."""
        return self._rules.get("figures", {}).get("label_prefix", "Figure")

    def get_figure_caption_position(self) -> str:
        """Return figure caption position: 'above' or 'below'."""
        return self._rules.get("figures", {}).get("caption_position", "below")

    def is_figure_label_bold(self) -> bool:
        """Return True if the figure label should be bold."""
        return bool(self._rules.get("figures", {}).get("label_bold", True))

    def get_table_rules(self) -> dict:
        """Return table formatting rules."""
        return self._rules["tables"]

    def get_table_label_prefix(self) -> str:
        """Return the table label prefix, e.g. 'Table' or 'TABLE'."""
        return self._rules.get("tables", {}).get("label_prefix", "Table")

    def get_table_caption_position(self) -> str:
        """Return table caption position: 'above' or 'below'."""
        return self._rules.get("tables", {}).get("caption_position", "above")

    def is_table_label_bold(self) -> bool:
        """Return True if the table label should be bold."""
        return bool(self._rules.get("tables", {}).get("label_bold", True))

    def get_table_border_style(self) -> str:
        """Return table border style string."""
        return self._rules.get("tables", {}).get("border_style", "top_bottom_only")

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

    def get_reference_ordering(self) -> str:
        """Return reference ordering: 'alphabetical' or 'appearance'."""
        return self._rules.get("references", {}).get("ordering", "alphabetical")

    def has_hanging_indent(self) -> bool:
        """Return True if references use hanging indent."""
        return bool(self._rules.get("references", {}).get("hanging_indent", True))

    # ------------------------------------------------------------------
    # Citation generation
    # ------------------------------------------------------------------

    def get_citation_style(self) -> str:
        """Return citation style: 'author-date' or 'numbered'."""
        return self._rules.get("citations", {}).get("style", "author-date")

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
            all_but_last = ", ".join(authors[:-1])
            author_part = f"{all_but_last}{separator}{authors[-1]}"
        else:
            author_part = f"{authors[0]} et al."

        brackets = citations.get("brackets", "parentheses")
        open_b = "(" if brackets == "parentheses" else "["
        close_b = ")" if brackets == "parentheses" else "]"

        sample = citations.get("format_one_author", "(Smith, 2020)")
        author_year_sep = ", " if ", " in (sample or "") else " "

        if page is not None and citations.get("include_page_for_quotes", False):
            page_str = page_format_template.replace("{page}", str(page))
            if str(page) not in page_str:
                page_str = f"p. {page}"
            return f"{open_b}{author_part}{author_year_sep}{year}, {page_str}{close_b}"

        return f"{open_b}{author_part}{author_year_sep}{year}{close_b}"

    # ------------------------------------------------------------------
    # General rules
    # ------------------------------------------------------------------

    def get_et_al_threshold(self) -> int:
        """Return the number of authors at which 'et al.' is used."""
        return int(self._rules.get("general_rules", {}).get("et_al_threshold", 3))

    def uses_ampersand(self) -> bool:
        """Return True if ampersand (&) is used instead of 'and' in citations."""
        return bool(self._rules.get("general_rules", {}).get("use_ampersand_in_citations", False))

    def get_doi_format(self) -> str:
        """Return the DOI format string."""
        return self._rules.get("general_rules", {}).get("doi_format", "https://doi.org/xxxxx")

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

        print(f"  Font:          {engine.get_font()} {engine.get_font_size()}pt")
        print(f"  Line spacing:  {engine.get_line_spacing()}")
        print(f"  Alignment:     {engine.get_alignment()}")
        print(f"  Columns:       {engine.get_columns()}")
        print(f"  Citation:      {engine.get_citation_style()}")
        print(f"  Et al at:      {engine.get_et_al_threshold()}")
        print(f"  Ampersand:     {engine.uses_ampersand()}")
        print(f"  DOI format:    {engine.get_doi_format()}")
        print(f"  Ref ordering:  {engine.get_reference_ordering()}")
        print(f"  Hanging indent:{engine.has_hanging_indent()}")
        print(f"  Fig prefix:    {engine.get_figure_label_prefix()}")
        print(f"  Fig position:  {engine.get_figure_caption_position()}")
        print(f"  Tbl prefix:    {engine.get_table_label_prefix()}")
        print(f"  Tbl position:  {engine.get_table_caption_position()}")
        print(f"  Abstract limit:{engine.get_abstract_word_limit()} words")
        print(f"  H1 style:      {engine.get_heading_style(1)}")
        print(f"  Citation 1 author: {engine.format_citation(['Smith'], 2020)}")
        print(f"  Citation 2 authors:{engine.format_citation(['Smith', 'Jones'], 2020)}")
        print(f"  Citation 3+ authors:{engine.format_citation(['Smith', 'Jones', 'Brown'], 2020)}")
