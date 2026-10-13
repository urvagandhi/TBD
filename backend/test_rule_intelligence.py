import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import journal_intelligence as intelligence
from tools.rule_instruction_compiler import compile_rule_instructions


def sample_rules():
    return {
        "style_name": "Example Journal",
        "document": {"font": "Arial", "font_size": 11, "line_spacing": 1.5, "alignment": "left", "columns": 1, "margins": {"top": "1in", "bottom": "1in", "left": "1in", "right": "1in"}},
        "title_page": {"title_case": "Title Case", "title_bold": True, "title_centered": True, "title_font_size": 14},
        "abstract": {"label": "Abstract", "label_bold": True, "label_centered": False, "label_italic": False, "max_words": 250, "indent_first_line": False, "keywords_present": True, "keywords_label": "Keywords:", "keywords_italic": False},
        "headings": {"H1": {"bold": True, "italic": False, "centered": False, "underline": False, "case": "Title Case", "numbering": "none", "font_size": 14}},
        "citations": {"style": "numbered", "brackets": "square", "format_one_author": "", "format_two_authors": "", "format_three_plus": "", "format_numbered": "[N]", "include_page_for_quotes": False, "page_format": "p. {page}"},
        "references": {"section_label": "References", "label_bold": True, "label_centered": False, "label_italic": False, "ordering": "appearance", "hanging_indent": True, "indent_size": "0.5in", "line_spacing": 1.0, "space_between_entries": False, "formats": {}},
        "figures": {"label_prefix": "Figure", "label_bold": True, "label_italic": False, "caption_position": "below", "caption_italic": False, "caption_alignment": "left", "numbering": "arabic", "note_label": "Note:"},
        "tables": {"label_prefix": "Table", "label_bold": True, "label_italic": False, "caption_position": "above", "caption_italic": False, "caption_alignment": "left", "numbering": "arabic", "border_style": "full", "note_label": "Note:"},
        "equations": {"numbering": "right_aligned", "numbering_format": "(1)"},
        "general_rules": {"doi_format": "doi", "url_format": "url", "date_format": "year", "et_al_threshold": 3, "use_ampersand_in_citations": False, "use_ampersand_in_references": False, "oxford_comma": True},
    }


class JournalIntelligenceTests(unittest.TestCase):
    def test_compiler_is_deterministic_and_exposes_manual_work(self):
        plan = compile_rule_instructions(sample_rules())
        self.assertTrue(plan["author_checklist"])
        self.assertTrue(any(item["id"] == "set_body_font" for item in plan["formatter_actions"]))
        self.assertTrue(plan["unsupported_rules"])

    def test_source_rank_explains_official_trust(self):
        ranked = intelligence.rank_sources("Example Journal", [{"title": "Example Journal author guidelines", "url": "https://journals.plos.org/example", "snippet": "submission instructions"}])
        self.assertEqual(ranked[0]["official_likelihood"], "high")
        self.assertTrue(ranked[0]["trust_reasons"])

    def test_other_journal_page_cannot_be_high_confidence(self):
        ranked = intelligence.rank_sources("PeerJ", [{"title": "Journal of Animal Ecology author guidelines", "url": "https://besjournals.onlinelibrary.wiley.com/guidelines", "snippet": "author instructions"}])
        self.assertNotEqual(ranked[0]["official_likelihood"], "high")

    def test_reviewer_edit_records_override_and_approval_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            drafts, approved = Path(directory) / "drafts", Path(directory) / "approved"
            drafts.mkdir(); approved.mkdir()
            source_text = ("Manuscript font and margin requirements. Abstract word limit. Heading and section rules. "
                           "Citation and reference requirements. " * 8)
            search_result = [{"title": "Example Journal author guidelines", "url": "https://journals.plos.org/example", "snippet": "submission guidelines"}]
            with patch.object(intelligence, "DRAFTS_DIR", drafts), patch.object(intelligence, "APPROVED_DIR", approved), patch.object(intelligence, "search_journal", return_value=search_result), patch.object(intelligence, "fetch_journal_page", return_value=source_text), patch.object(intelligence, "extract_rules_from_text", return_value=sample_rules()), patch.object(intelligence, "_validate_rules", return_value=[]):
                draft = intelligence.discover_journal("Example Journal")
                self.assertTrue(draft["quality"]["can_approve"])
                updated = intelligence.update_draft_rules(draft["draft_id"], [{"path": "document.font_size", "value": 12}])
                fact = next(item for item in updated["field_facts"] if item["path"] == "document.font_size")
                self.assertEqual(fact["provenance"], "user_override")
                result = intelligence.approve_draft(draft["draft_id"])
                self.assertIn("rule_set_id", result)
                self.assertTrue((approved).glob("*.json"))

    def test_rejects_invalid_typed_edit(self):
        with self.assertRaises(ValueError):
            intelligence._coerce_edit("document.font_size", 11, "eleven")


if __name__ == "__main__":
    unittest.main()
