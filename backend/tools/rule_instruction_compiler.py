"""Compile normalized journal rules into explainable formatter actions."""
from __future__ import annotations

from typing import Any


def _action(action_id: str, title: str, status: str, paths: list[str], detail: str) -> dict[str, Any]:
    return {"id": action_id, "title": title, "status": status, "rule_paths": paths, "detail": detail}


def compile_rule_instructions(rules: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic author guidance and the formatter's execution contract."""
    document = rules.get("document", {})
    abstract = rules.get("abstract", {})
    citations = rules.get("citations", {})
    references = rules.get("references", {})
    headings = rules.get("headings", {})
    figures = rules.get("figures", {})
    tables = rules.get("tables", {})
    margins = document.get("margins", {})

    checklist = [
        {"category": "Document", "text": f"Use {document.get('font', 'the selected')} {document.get('font_size', '')}pt font with {document.get('line_spacing', '')} line spacing.".strip(), "rule_paths": ["document.font", "document.font_size", "document.line_spacing"]},
        {"category": "Document", "text": f"Use {document.get('columns', 1)} column(s) and margins of top {margins.get('top', 'not specified')}, bottom {margins.get('bottom', 'not specified')}, left {margins.get('left', 'not specified')}, right {margins.get('right', 'not specified')}.", "rule_paths": ["document.columns", "document.margins"]},
        {"category": "Abstract", "text": f"Keep the abstract at or below {abstract.get('max_words', 'the journal limit')} words.", "rule_paths": ["abstract.max_words"]},
        {"category": "Headings", "text": "Use the approved heading hierarchy and casing for each heading level.", "rule_paths": ["headings"]},
        {"category": "References", "text": f"Use {citations.get('style', 'the required')} citations and order references by {references.get('ordering', 'the journal requirement')}.", "rule_paths": ["citations.style", "references.ordering"]},
    ]
    actions = [
        _action("set_document_layout", "Set page layout", "applied_automatically", ["document.margins", "document.columns", "document.alignment"], "The DOCX writer applies margins, columns, and body alignment."),
        _action("set_body_font", "Set body typography", "applied_automatically", ["document.font", "document.font_size", "document.line_spacing"], "The DOCX writer applies body font and line spacing."),
        _action("apply_heading_style", "Apply heading styles", "applied_automatically", ["headings"], "The DOCX writer applies level-specific heading rules."),
        _action("format_references", "Format reference section", "applied_automatically", ["references"], "The DOCX writer applies reference heading, ordering layout, indentation, and spacing."),
        _action("format_figures_tables", "Format figures and tables", "applied_automatically", ["figures", "tables"], "The DOCX writer applies supported label and caption rules."),
        _action("validate_abstract_limit", "Check abstract limit", "validated_not_transformed", ["abstract.max_words"], "The scorer checks the word limit; it does not rewrite abstract content."),
        _action("validate_citation_style", "Check citation style", "validated_not_transformed", ["citations"], "The validator reports citation issues; it does not guarantee bibliographic correctness."),
        _action("author_metadata", "Confirm journal submission metadata", "requires_author_action", ["general_rules"], "Authors must confirm journal forms, declarations, identifiers, and submission-only requirements."),
    ]
    unsupported = [
        _action("journal_template", "Journal-specific template or LaTeX package", "unsupported", ["general_rules"], "Upload or apply the publisher template manually when the journal requires one."),
        _action("editorial_policy", "Editorial and ethical policy compliance", "unsupported", ["general_rules"], "Review ethics, data availability, conflicts, fees, and policy requirements manually."),
    ]
    return {
        "author_checklist": checklist,
        "formatter_actions": actions,
        "unsupported_rules": unsupported,
        "summary": {
            "applied_automatically": sum(action["status"] == "applied_automatically" for action in actions),
            "validated_not_transformed": sum(action["status"] == "validated_not_transformed" for action in actions),
            "requires_author_action": sum(action["status"] == "requires_author_action" for action in actions),
            "unsupported": len(unsupported),
        },
    }
