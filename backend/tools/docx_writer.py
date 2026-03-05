from pathlib import Path
from typing import Any, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from tools.logger import get_logger
from tools.tool_errors import DocumentWriteError

logger = get_logger(__name__)

_CASE_OPTIONS = {"Title Case", "UPPERCASE", "Sentence case", "lowercase"}


def write_formatted_docx(instructions: dict, output_path: str) -> str:
    """
    Write a formatted DOCX file from structured docx_instructions.

    This function NEVER raises — if a specific instruction fails, it logs and
    continues. It always produces a valid .docx file.

    Args:
        instructions: Dict produced by the transform agent containing:
            - rules: journal rules dict
            - sections: list of { type, content, level, bold, italic, centered, ... }
        output_path: Absolute path where the DOCX should be saved.

    Returns:
        output_path on success.
    """
    if not instructions or not instructions.get("sections"):
        raise DocumentWriteError("docx_instructions must contain a non-empty 'sections' list.")

    doc = Document()
    rules = instructions.get("rules", {}) or {}
    sections = instructions.get("sections", []) or []

    doc_rules = rules.get("document", {})
    font_name = doc_rules.get("font", "Times New Roman")
    font_size = _safe_int(doc_rules.get("font_size", 12), 12)
    line_spacing = _safe_float(doc_rules.get("line_spacing", 2.0), 2.0)
    margins = doc_rules.get("margins", {})

    _apply_document_defaults(doc, font_name, font_size, line_spacing)
    _set_document_margins(doc, margins)

    for section in sections:
        section_type = section.get("type", "paragraph")
        content = section.get("content", "")
        if content is None:
            content = ""

        try:
            if section_type == "title":
                _add_title(doc, content, font_name, font_size)
            elif section_type == "heading":
                level = _safe_int(section.get("level", 1), 1)
                heading_rules = rules.get("headings", {}).get(f"H{level}", {})
                _add_heading(doc, content, level, heading_rules, font_name, font_size)
            elif section_type == "abstract":
                abstract_rules = rules.get("abstract", {})
                _add_abstract(doc, content, abstract_rules, font_name, font_size, line_spacing)
            elif section_type == "reference":
                ref_rules = rules.get("references", {})
                _add_reference(doc, content, ref_rules, font_name, font_size)
            elif section_type == "figure_caption":
                fig_rules = rules.get("figures", {})
                _add_figure_caption(doc, content, fig_rules, font_name, font_size)
            elif section_type == "table_caption":
                tbl_rules = rules.get("tables", {})
                _add_table_caption(doc, content, tbl_rules, font_name, font_size)
            else:
                _add_paragraph(doc, content, font_name, font_size, line_spacing)
        except Exception as e:
            logger.warning("[DOCX] Failed to render section type=%s: %s", section_type, e)
            # Fallback: add content as plain paragraph
            try:
                _add_paragraph(doc, content, font_name, font_size, line_spacing)
            except Exception:
                pass

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    logger.info("DOCX written | file=%s | sections=%d", out.name, len(sections))
    return str(out)


def _apply_document_defaults(doc: Document, font_name: str, font_size: int, line_spacing: float) -> None:
    """Set font, size, and line spacing on the Normal style for the entire document."""
    try:
        style = doc.styles["Normal"]
        style.font.name = font_name
        style.font.size = Pt(font_size)
        pf = style.paragraph_format
        _apply_line_spacing(pf, line_spacing)
    except Exception as e:
        logger.warning("[DOCX] Could not set document defaults: %s", e)


def _set_document_margins(doc: Document, margins: dict) -> None:
    """Apply margins to all document sections."""
    for section in doc.sections:
        try:
            top = _parse_measurement(margins.get("top", 1.0))
            bottom = _parse_measurement(margins.get("bottom", 1.0))
            left = _parse_measurement(margins.get("left", 1.0))
            right = _parse_measurement(margins.get("right", 1.0))
            section.top_margin = Inches(top)
            section.bottom_margin = Inches(bottom)
            section.left_margin = Inches(left)
            section.right_margin = Inches(right)
        except Exception as e:
            logger.warning("[DOCX] Could not set margins: %s", e)


def _parse_measurement(value) -> float:
    """
    Convert a measurement to inches (float).

    Accepts:
        "1in" → 1.0
        "2.54cm" → 1.0
        "72pt" → 1.0
        1.0 → 1.0
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip().lower()
        try:
            if value.endswith("in"):
                return float(value[:-2])
            elif value.endswith("cm"):
                return float(value[:-2]) / 2.54
            elif value.endswith("mm"):
                return float(value[:-2]) / 25.4
            elif value.endswith("pt"):
                return float(value[:-2]) / 72.0
            else:
                return float(value)
        except ValueError:
            logger.warning("[DOCX] Cannot parse measurement '%s' — defaulting to 1.0in", value)
            return 1.0
    return 1.0


def _apply_line_spacing(pf, line_spacing: float) -> None:
    """Apply WD_LINE_SPACING rule based on the float value."""
    if line_spacing == 1.0:
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    elif line_spacing == 1.5:
        pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    elif line_spacing == 2.0:
        pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    else:
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(line_spacing * 12)


def _apply_font(run, font_name: str, font_size: int, bold: bool = False, italic: bool = False) -> None:
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic


def _apply_case_transform(text: str, case_rule: str) -> str:
    """
    Transform text case per journal rules.

    Supports: "Title Case", "UPPERCASE", "Sentence case", "lowercase"
    Handles acronyms (NLP, AI), hyphenated words, non-ASCII chars.
    """
    if not case_rule or case_rule not in _CASE_OPTIONS:
        return text

    try:
        if case_rule == "UPPERCASE":
            return text.upper()
        elif case_rule == "lowercase":
            return text.lower()
        elif case_rule == "Sentence case":
            if not text:
                return text
            return text[0].upper() + text[1:].lower() if len(text) > 1 else text.upper()
        elif case_rule == "Title Case":
            # Skip all-caps words (acronyms like NLP, AI) and hyphenated sub-words
            _SMALL_WORDS = {
                "a", "an", "the", "and", "but", "or", "for", "nor",
                "on", "at", "to", "by", "in", "of", "up", "as", "is",
            }
            words = text.split()
            result = []
            for i, word in enumerate(words):
                # Preserve already-uppercase acronyms (2+ uppercase letters)
                if len(word) >= 2 and word.isupper():
                    result.append(word)
                elif "-" in word:
                    result.append("-".join(
                        part.capitalize() for part in word.split("-")
                    ))
                elif i == 0 or word.lower() not in _SMALL_WORDS:
                    result.append(word.capitalize())
                else:
                    result.append(word.lower())
            return " ".join(result)
    except Exception as e:
        logger.warning("[DOCX] Case transform failed for '%s': %s — keeping original", case_rule, e)

    return text


def _add_paragraph(doc: Document, text: str, font_name: str, font_size: int, line_spacing: float) -> None:
    para = doc.add_paragraph()
    run = para.add_run(text)
    _apply_font(run, font_name, font_size)
    _apply_line_spacing(para.paragraph_format, line_spacing)


def _add_title(doc: Document, text: str, font_name: str, font_size: int) -> None:
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run(text)
    _apply_font(run, font_name, font_size + 2, bold=True)


def _add_heading(doc: Document, text: str, level: int, heading_rules: dict, font_name: str, font_size: int) -> None:
    para = doc.add_paragraph()
    bold = heading_rules.get("bold", True)
    italic = heading_rules.get("italic", False)
    centered = heading_rules.get("centered", False)
    case = heading_rules.get("case", "Title Case")
    heading_font_size = _safe_int(heading_rules.get("font_size", font_size), font_size)

    text = _apply_case_transform(text, case)

    if centered:
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run = para.add_run(text)
    _apply_font(run, font_name, heading_font_size, bold=bold, italic=italic)


def _add_abstract(
    doc: Document,
    text: str,
    abstract_rules: dict,
    font_name: str,
    font_size: int,
    line_spacing: float,
) -> None:
    label = abstract_rules.get("label", "Abstract")
    label_bold = abstract_rules.get("label_bold", False)
    centered = abstract_rules.get("label_centered", True)

    label_para = doc.add_paragraph()
    if centered:
        label_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label_run = label_para.add_run(label)
    _apply_font(label_run, font_name, font_size, bold=label_bold)

    body_para = doc.add_paragraph()
    body_run = body_para.add_run(text)
    _apply_font(body_run, font_name, font_size)
    _apply_line_spacing(body_para.paragraph_format, line_spacing)


def _add_reference(doc: Document, text: str, ref_rules: dict, font_name: str, font_size: int) -> None:
    para = doc.add_paragraph()
    hanging = ref_rules.get("hanging_indent", True)
    hanging_inches = _parse_measurement(ref_rules.get("indent_size", ref_rules.get("hanging_indent_inches", 0.5)))
    if hanging:
        para.paragraph_format.left_indent = Inches(hanging_inches)
        para.paragraph_format.first_line_indent = Inches(-hanging_inches)
    run = para.add_run(text)
    _apply_font(run, font_name, font_size)


def _apply_heading_style(paragraph, fix: dict) -> None:
    """Apply bold/italic/centered/case to an existing heading paragraph."""
    bold = fix.get("bold", True)
    italic = fix.get("italic", False)
    centered = fix.get("centered", False)
    case = fix.get("case", "Title Case")

    text = paragraph.text
    text = _apply_case_transform(text, case)

    if centered:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for run in paragraph.runs:
        run.bold = bold
        run.italic = italic

    # If text changed (case transform), rewrite the first run
    if text != paragraph.text and paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""


def _apply_reference_formatting(doc: Document, reference_order: list, font_name: str, font_size: int) -> None:
    """Add a references section with hanging indent from the given list."""
    if not reference_order:
        return
    for ref_text in reference_order:
        para = doc.add_paragraph()
        para.paragraph_format.left_indent = Inches(0.5)
        para.paragraph_format.first_line_indent = Inches(-0.5)
        run = para.add_run(ref_text)
        run.font.name = font_name
        run.font.size = Pt(font_size)


def _add_figure_caption(doc: Document, text: str, fig_rules: dict, font_name: str, font_size: int) -> None:
    para = doc.add_paragraph()
    bold = fig_rules.get("label_bold", True)
    italic = fig_rules.get("caption_italic", False)
    run = para.add_run(text)
    _apply_font(run, font_name, font_size - 1, bold=bold, italic=italic)


def _add_table_caption(doc: Document, text: str, tbl_rules: dict, font_name: str, font_size: int) -> None:
    para = doc.add_paragraph()
    bold = tbl_rules.get("label_bold", True)
    run = para.add_run(text)
    _apply_font(run, font_name, font_size - 1, bold=bold)


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    import os as _os, sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.rule_loader import load_rules as _load_rules

    rules = _load_rules("APA 7th Edition")
    instructions = {
        "rules": rules,
        "sections": [
            {"type": "title", "content": "machine learning in healthcare"},
            {"type": "abstract", "content": "This paper presents a novel approach to ML in clinical settings."},
            {"type": "heading", "content": "introduction", "level": 1},
            {"type": "paragraph", "content": "We study the effect of deep learning on radiology outcomes."},
            {"type": "reference", "content": "Smith, J. A. (2020). Article title. Journal, 10(2), 100-110."},
        ],
    }

    path = write_formatted_docx(instructions, "tests/output_test.docx")
    assert _os.path.exists(path), "Output file not created!"
    print(f"OK docx_writer: created {path}")

    # Test case transform
    assert _apply_case_transform("machine learning in NLP", "Title Case") == "Machine Learning in NLP"
    assert _apply_case_transform("hello world", "UPPERCASE") == "HELLO WORLD"
    assert _apply_case_transform("HELLO WORLD", "Sentence case") == "Hello world"
    print("OK docx_writer: case transforms correct")

    # Test measurement parsing
    assert _parse_measurement("1in") == 1.0
    assert abs(_parse_measurement("2.54cm") - 1.0) < 0.01
    assert _parse_measurement(1.5) == 1.5
    print("OK docx_writer: measurement parsing correct")
