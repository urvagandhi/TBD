# APA 7th Edition Pipeline — Complete Technical Deep Dive

This document traces the **entire APA formatting pipeline** from raw paper upload to final DOCX generation. It covers: rules, prompts (generic vs APA-specific), JSON schemas, agent flow, and DOCX rendering.

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [APA Rules (apa7.json)](#2-apa-rules-apa7json)
3. [Agent 1: INGEST (Generic)](#3-agent-1-ingest-generic)
4. [Agent 2: PARSE (Generic)](#4-agent-2-parse-generic)
5. [Agent 3: TRANSFORM (APA-Specific)](#5-agent-3-transform-apa-specific)
6. [Agent 4: VALIDATE (APA-Specific)](#6-agent-4-validate-apa-specific)
7. [DOCX Generation (build_apa_docx)](#7-docx-generation-build_apa_docx)
8. [Post-Pipeline Processing](#8-post-pipeline-processing)
9. [End-to-End Data Flow Diagram](#9-end-to-end-data-flow-diagram)

---

## 1. Pipeline Overview

```
USER UPLOADS PDF/DOCX
         |
         v
    [Text Extraction]  (docx_reader.py / pdf_reader.py)
         |
         v
    AGENT 1: INGEST    (Generic prompt — same for all journals)
    Input:  Raw text
    Output: Labelled text with structural markers
         |
         v
    AGENT 2: PARSE     (Generic prompt — same for all journals)
    Input:  Labelled text from INGEST
    Output: paper_structure JSON
         |
         v
    AGENT 3: TRANSFORM (APA-SPECIFIC prompt + APA rules JSON)
    Input:  paper_structure JSON + apa7.json rules
    Output: docx_instructions JSON (page-based sections)
         |
         v
    AGENT 4: VALIDATE  (APA-SPECIFIC prompt + rules)
    Input:  TRANSFORM output + rules
    Output: compliance_report JSON (7 checks, overall_score)
         |
         v
    [DOCX Writer]       build_apa_docx() — APA-specific builder
    Input:  docx_instructions from TRANSFORM
    Output: Formatted .docx file
```

**Key insight**: Agents 1-2 are **journal-agnostic** (same prompt regardless of APA/IEEE/etc). Agents 3-4 use **journal-specific prompts** selected via `detect_style()`.

**Orchestration**: CrewAI `Process.sequential` — each agent runs in order, with `context=` linking each task to its predecessor.

---

## 2. APA Rules (apa7.json)

File: `backend/rules/apa7.json`

This is the deterministic rules file that drives both the TRANSFORM prompt and the VALIDATE scoring. Every rule maps to a specific APA manual section.

### Document-Level Rules
```json
{
  "style_name": "APA 7th Edition",
  "document": {
    "font": "Times New Roman",
    "font_size": 12,
    "line_spacing": 2.0,
    "margins": { "top": "1in", "bottom": "1in", "left": "1in", "right": "1in" },
    "alignment": "left",
    "columns": 1
  }
}
```

### Title Page Rules
```json
{
  "title_page": {
    "title_case": "Title Case",
    "title_bold": true,
    "title_centered": true,
    "title_font_size": 12
  }
}
```

### Abstract Rules
```json
{
  "abstract": {
    "label": "Abstract",
    "label_bold": true,
    "label_centered": true,
    "max_words": 250,
    "indent_first_line": false,
    "keywords_present": true,
    "keywords_label": "Keywords:",
    "keywords_italic": true
  }
}
```

### Heading Rules (APA 5-level hierarchy)
```json
{
  "headings": {
    "H1": { "bold": true, "italic": false, "centered": true, "case": "Title Case", "numbering": "none", "font_size": 12 },
    "H2": { "bold": true, "italic": false, "centered": false, "case": "Title Case", "numbering": "none", "font_size": 12 },
    "H3": { "bold": true, "italic": true, "centered": false, "indent": true, "case": "Title Case", "inline_with_text": true, "font_size": 12 }
  }
}
```

### Citation Rules
```json
{
  "citations": {
    "style": "author-date",
    "brackets": "parentheses",
    "format_one_author": "(Smith, 2020)",
    "format_two_authors": "(Smith & Jones, 2020)",
    "format_three_plus": "(Smith et al., 2020)",
    "include_page_for_quotes": true,
    "page_format": "p. 45"
  }
}
```

### Reference Rules
```json
{
  "references": {
    "section_label": "References",
    "label_bold": true,
    "label_centered": true,
    "ordering": "alphabetical",
    "hanging_indent": true,
    "indent_size": "0.5in",
    "line_spacing": 2.0,
    "formats": {
      "journal_article": "Author, A. A., & Author, B. B. (Year). Title of article. Journal Name, Volume(Issue), Page-Page. https://doi.org/xxxxx",
      "book": "Author, A. A. (Year). Title of work: Capital letter also for subtitle. Publisher.",
      "book_chapter": "Author, A. A., & Author, B. B. (Year). Title of chapter. In E. E. Editor (Ed.), Title of book (pp. page-page). Publisher.",
      "website": "Author, A. A. (Year, Month Day). Title of page. Site Name. URL",
      "conference_paper": "Author, A. A. (Year, Month). Title of paper [Paper presentation]. Conference Name, Location."
    }
  }
}
```

### General Rules
```json
{
  "general_rules": {
    "doi_format": "https://doi.org/xxxxx",
    "et_al_threshold": 3,
    "use_ampersand_in_citations": true,
    "use_ampersand_in_references": true,
    "oxford_comma": true
  }
}
```

---

## 3. Agent 1: INGEST (Generic)

**File**: `backend/agents/ingest_agent.py`
**Purpose**: Read raw text, insert structural labels. **Zero text modification.**
**Prompt type**: GENERIC (same for all journals)

### System Prompt (Summary)
The INGEST agent is told:
- "You are a scientific paper structure labeler. Your ONLY job is to read raw academic paper text and add structural labels."
- "You must NOT change, rewrite, rephrase, summarize, or delete ANY text."

### Structural Labels Inserted
```
[CITATION_STYLE:numbered|author-date]     <-- detected from the paper
[SOURCE_FORMAT:NLM|APA|other]             <-- detected from the paper

[TITLE_START]...[TITLE_END]
[AUTHORS_START]...[AUTHORS_END]
[ABSTRACT_START]...[ABSTRACT_END]
[KEYWORDS_START]...[KEYWORDS_END]
[SIGNIFICANCE_START]...[SIGNIFICANCE_END]
[HEADING_H1:Exact Heading Text]
[HEADING_H2:Subsection Title]
[HEADING_H3:Sub-subsection Title]
[FIGURE_CAPTION_START:N]...[FIGURE_CAPTION_END:N]
[TABLE_CAPTION_START:N]...[TABLE_CAPTION_END:N]
[REFERENCE_START]...[REFERENCE_END]
[CITATION:original_text]                   <-- every in-text citation
[METADATA_START]...[METADATA_END]
[ACKNOWLEDGMENTS_START]...[ACKNOWLEDGMENTS_END]
[AUTHOR_CONTRIBUTIONS_START]...[AUTHOR_CONTRIBUTIONS_END]
```

### Critical Rules in Prompt
1. NEVER modify any text content — only INSERT labels
2. Every opened label MUST be closed
3. Detect citation STYLE (numbered vs author-date) automatically
4. Recognize PNAS/Nature/Science use NLM/Vancouver numbered style (not APA)
5. Merge hard line breaks from PDF extraction into proper paragraphs

### CrewAI Task Description (crew.py:883)
```python
ingest_task = Task(
    description=(
        "Label the following paper with structural markers. Follow ALL rules exactly.\n\n"
        "<paper>\n{structured_paper}\n</paper>"
    ),
    expected_output="The complete paper text with all structural labels inserted...",
    agent=ingest_agent,
)
```

### Example Output
```
[CITATION_STYLE:numbered]
[SOURCE_FORMAT:NLM]

[TITLE_START]Diarrheagenic Escherichia coli Pathotypes[TITLE_END]

[AUTHORS_START]
Alsharif G, Ahmad S, Islam MS...
[AUTHORS_END]

[ABSTRACT_START]
Enterohemorrhagic Escherichia coli (EHEC) O157:H7 is a food-borne pathogen...
[ABSTRACT_END]

[KEYWORDS_START]EHEC | O157:H7 | virulence | pathogenesis[KEYWORDS_END]

[HEADING_H1:Introduction]
The gastrointestinal tract is colonized by [CITATION:(1)] trillions of bacteria...

[HEADING_H2:Virulence Factors]
Several virulence factors have been identified [CITATION:(5, 6)]...

[REFERENCE_START]
1. Nataro JP, Kaper JB (1998) Diarrheagenic Escherichia coli. Clin Microbiol Rev 11(1):142-201.
2. Jerse AE, et al. (1990) A genetic locus of enteropathogenic Escherichia coli...
[REFERENCE_END]
```

---

## 4. Agent 2: PARSE (Generic)

**File**: `backend/agents/parse_agent.py`
**Purpose**: Convert labelled text into structured JSON.
**Prompt type**: GENERIC (same for all journals)

### System Prompt (Summary)
"You are a structured data extractor. You receive a labeled academic paper and extract a structured JSON object containing every paper element."

### Output JSON Schema
```json
{
  "metadata": {
    "citation_style": "numbered | author-date",
    "source_format": "NLM | APA | other",
    "paper_type": "research | review | meta-analysis | case-study | other"
  },
  "title": "Full paper title as single string",
  "authors": [
    {
      "name": "Full Name",
      "affiliations": ["a", "b"],
      "is_corresponding": true,
      "email": "if available"
    }
  ],
  "affiliations": [
    { "key": "a", "institution": "...", "address": "..." }
  ],
  "abstract": {
    "text": "Full abstract text as single paragraph",
    "word_count": 150,
    "has_explicit_label": true
  },
  "keywords": ["keyword1", "keyword2"],
  "significance": "Significance paragraph text if present, else null",
  "sections": [
    {
      "heading": "Introduction",
      "level": 1,
      "content": "Full section body text. Merge all paragraphs belonging to this section.",
      "subsections": [
        {
          "heading": "Subsection Title",
          "level": 2,
          "content": "Subsection body text"
        }
      ]
    }
  ],
  "figures": [
    { "number": 1, "caption": "Full caption text starting from Fig. 1..." }
  ],
  "tables": [
    { "number": 1, "caption": "Full table caption" }
  ],
  "citations": [
    {
      "id": "1",
      "original_text": "(1)",
      "context": "5 words before and after the citation",
      "in_text_format": "numbered"
    }
  ],
  "references": [
    {
      "id": "1",
      "original_text": "Full reference as written in paper",
      "parsed": {
        "authors": [{ "last": "Nataro", "initials": "JP" }],
        "year": 1998,
        "title": "Article title",
        "journal": "Clin Microbiol Rev",
        "volume": "11",
        "issue": "1",
        "pages": "142-201",
        "doi": "if available"
      }
    }
  ],
  "acknowledgments": "text or null",
  "author_contributions": "text or null",
  "journal_metadata": {
    "journal": "PNAS",
    "volume": "112", "issue": "17", "pages": "5503-5508",
    "doi": "10.1073/pnas.1422986112"
  }
}
```

### Critical Rules
1. Preserve ALL text verbatim — never summarize or truncate
2. Parse EVERY reference into component parts (authors, year, title, journal, etc.)
3. Count abstract words accurately
4. Map each citation to its reference ID
5. Sections array must follow the paper's actual order

### Required Top-Level Keys (validated in code)
```python
REQUIRED_FIELDS = [
    "metadata", "title", "authors", "affiliations", "abstract",
    "keywords", "sections", "figures", "tables", "citations", "references",
]
```

### CrewAI Task (crew.py:899)
```python
parse_task = Task(
    description="Parse this labeled paper into structured JSON...",
    expected_output="Valid JSON with keys: metadata, title, authors, ...",
    agent=parse_agent,
    context=[ingest_task],  # <-- receives INGEST output
)
```

---

## 5. Agent 3: TRANSFORM (APA-Specific)

**File**: `backend/agents/transform_agent.py`
**Purpose**: Compare paper_structure vs APA rules, convert citations/references, produce docx_instructions.
**Prompt type**: APA-SPECIFIC (`TRANSFORM_SYSTEM_PROMPT`)

This is the **core formatting engine**. The prompt is the longest and most detailed.

### Style Detection (crew.py routing)
```python
def detect_style(journal_style: str) -> str:
    s = journal_style.lower()
    if "apa" in s: return "apa"
    if "ieee" in s: return "ieee"
    return "generic"
```
APA gets `TRANSFORM_SYSTEM_PROMPT`. IEEE gets `IEEE_TRANSFORM_SYSTEM_PROMPT`. Others get `GENERIC_TRANSFORM_SYSTEM_PROMPT`.

### APA Transform System Prompt — Section by Section

#### Section A: Document Formatting
```
- Font: Times New Roman, 12pt
- Line spacing: 2.0 (double) throughout
- Margins: 1 inch all sides
- Body paragraph indent: 0.5" first-line indent
- Alignment: Left-aligned (ragged right) — NEVER justified
- Page numbers: top-right corner, every page starting from page 1
```

#### Section B: Title Page (APA SS2.3-2.8)
```
Create a SEPARATE first page containing (ALL centered, double-spaced):
1. Page number "1" in top-right header
2. 3-4 blank lines from top margin
3. Paper title -- BOLD, centered, Title Case
4. One blank line
5. Author name(s) -- centered, NOT bold
6. Affiliation -- centered, NOT bold
```

#### Section C: Abstract Page (APA SS2.9, SS2.13)
```
Separate page containing:
1. "Abstract" -- bold, centered, NOT italic
2. Abstract body -- single paragraph, NO first-line indent, left-aligned
3. Word count MUST be <= 250
4. "Keywords:" -- italic, followed by keywords in regular font, comma-separated
```

#### Section D: Body Text (APA SS2.11)
```
1. Paper title repeated -- bold, centered
2. Body text begins with 0.5" first-line indent
3. Do NOT use "Introduction" as a heading
```

#### Section E: Headings (APA SS2.27)
```
Level 1: Bold, Centered, Title Case
Level 2: Bold, Flush Left, Title Case
Level 3: Bold Italic, Flush Left, 0.5" Indented, Title Case
Level 4: Bold, 0.5" Indented, Title Case, Ending With Period. Inline.
Level 5: Bold Italic, 0.5" Indented, Title Case, Ending With Period. Inline.
ALL headings: 12pt (same as body)
```

#### Section F: Citation Conversion (APA SS8.11, SS8.17)

This is the **critical transformation** — converting numbered NLM citations to APA author-date.

**Conversion table in the prompt:**
| Source Citation | APA Replacement | Rule |
|---|---|---|
| (1) | (Nataro & Kaper, 1998) | 2 authors -> both names + & |
| (5) | (Elliott et al., 2000) | 3+ authors -> first + et al. |
| (2, 3) | (Jerse et al., 1990; McDaniel et al., 1997) | multiple -> alphabetical, semicolon |
| (9-12) | (Branchu et al., 2014; Pacheco et al., 2012; ...) | range -> expand, alphabetize |

**Parenthetical vs Narrative:**
- Parenthetical: (Smith & Jones, 2020) — USE &
- Narrative: Smith and Jones (2020) — USE "and" NOT &
- 3+ authors: (Smith et al., 2020) — PERIOD after "al"

#### Section G: Reference Conversion (APA SS9.4, SS9.43)

**Source (NLM):**
```
1. Nataro JP, Kaper JB (1998) Diarrheagenic Escherichia coli. Clin Microbiol Rev 11(1):142-201.
```

**Target (APA):**
```
Nataro, J. P., & Kaper, J. B. (1998). Diarrheagenic Escherichia coli. *Clin Microbiol Rev*, *11*(1), 142-201.
```

**Author format**: Last, F. M. (periods after EACH initial, comma after last name)
**Year**: In parentheses after authors, followed by PERIOD
**Title**: Sentence case
**Journal**: *Title Case*, *italicized*
**Volume**: *italicized*
**Pages**: en-dash (not hyphen)
**Ordering**: Alphabetical by first author's last name
**Hanging indent**: first line flush, subsequent lines indented 0.5"

Uses `*asterisks*` for text that should be italic in the DOCX.

#### Section H: Figures & Tables (APA SS7.4, SS7.22)
```
FIGURES: **Figure N** (bold, flush left) + *Caption text in italic* (below)
TABLES:  **Table N** (bold, flush left) + *Caption text in italic* (above)
```

#### Section I: Metadata Stripping
Remove all source journal metadata (page numbers, journal headers, footer URLs, etc.)

#### Section J: Output JSON Schema

```json
{
  "format_applied": "APA 7th Edition",

  "violations": [
    {"element": "...", "current": "...", "required": "...", "severity": "high|medium|low", "apa_ref": "SS X.XX"}
  ],

  "changes_made": [
    "Converted 29 references from NLM to APA format (APA 7th SS9.4)",
    "Converted 47 citations from numbered to author-date (APA 7th SS8.11)"
  ],

  "citation_replacements": [
    {"original": "(1)", "replacement": "(Nataro & Kaper, 1998)", "ref_id": "1"}
  ],

  "reference_conversions": [
    {"original": "full NLM ref", "converted": "full APA ref with *italic* markers"}
  ],

  "reference_order": ["alphabetically sorted APA references"],

  "docx_instructions": {
    "format_id": "apa7",
    "page_size": {"width": 12240, "height": 15840},
    "margins": {"top": 1440, "bottom": 1440, "left": 1440, "right": 1440},
    "font": "Times New Roman",
    "font_size_halfpoints": 24,
    "line_spacing_twips": 480,
    "body_first_line_indent_dxa": 720,
    "alignment": "left",

    "sections": [
      {
        "type": "title_page",
        "elements": [
          {"type": "spacing", "blank_lines": 3},
          {"type": "title", "text": "...", "bold": true, "centered": true},
          {"type": "spacing", "blank_lines": 1},
          {"type": "authors", "text": "...", "centered": true},
          {"type": "affiliation", "text": "...", "centered": true}
        ]
      },
      {
        "type": "abstract_page",
        "elements": [
          {"type": "abstract_label", "text": "Abstract", "bold": true, "centered": true},
          {"type": "abstract_body", "text": "...", "first_line_indent": false},
          {"type": "keywords", "label_italic": true, "items": ["k1","k2"], "first_line_indent": true}
        ]
      },
      {
        "type": "body",
        "elements": [
          {"type": "title_repeat", "text": "...", "bold": true, "centered": true},
          {"type": "body_paragraph", "text": "text with (Author, Year) citations already replaced"},
          {"type": "heading", "text": "...", "level": 1, "bold": true, "centered": true},
          {"type": "body_paragraph", "text": "..."},
          {"type": "heading", "text": "...", "level": 2, "bold": true, "centered": false},
          {"type": "figure_caption", "number": 1, "label": "Figure 1", "caption": "description"},
          {"type": "table_caption", "number": 1, "label": "Table 1", "caption": "description"}
        ]
      },
      {
        "type": "references_page",
        "elements": [
          {"type": "references_label", "text": "References", "bold": true, "centered": true},
          {"type": "reference_entry", "text": "APA ref with *italic* markers", "hanging_indent": true}
        ]
      }
    ]
  }
}
```

### APA-Specific Task Description Additions (crew.py:941-965)

On top of the system prompt, the task description adds **7 critical requirements**:

```
CRITICAL REQUIREMENTS FOR APA 7th Edition:
1. Convert ALL numbered citations (1), [1], superscript -> (Author, Year) format
2. Convert ALL references from NLM/Vancouver to APA format
3. STRIP all source journal metadata
4. Generate docx_instructions with format_id='apa7' and exact field names:
   - font_size_halfpoints: 24
   - line_spacing_twips: 480
   - body_first_line_indent_dxa: 720
5. sections array MUST contain (in order):
   - title_page, abstract_page, body, references_page
6. ALL citation replacements must be applied INLINE in body text
7. Include format_applied='APA 7th Edition'
```

It also injects:
- The full `apa7.json` rules as `<journal_rules>` XML block
- A `<formatting_guide>` with section-specific rules
- Pre-computed section word counts from text_chunker

---

## 6. Agent 4: VALIDATE (APA-Specific)

**File**: `backend/agents/validate_agent.py`
**Purpose**: Score the formatted paper against 7 weighted checks.
**Prompt type**: APA-SPECIFIC (`VALIDATE_SYSTEM_PROMPT`)

### 7 Compliance Checks with Weights

| # | Check | Weight | Key Criteria |
|---|-------|--------|-------------|
| 1 | Citations | 25% | ALL author-date, zero numbered remaining, & vs "and" correct |
| 2 | References | 25% | APA format, alphabetical, hanging indent, & before last author, en-dash |
| 3 | Headings | 15% | H1 bold+centered, H2 bold+left, H3 bold+italic+left, IMRAD complete |
| 4 | Document Format | 10% | font=24hp, spacing=480tw, margins=1440dxa, indent=720dxa, align=left |
| 5 | Abstract | 10% | <=250 words, bold centered label, no indent, italic keywords label |
| 6 | Figures | 7.5% | "Figure N" not "Fig.", bold label, italic caption, below figure |
| 7 | Tables | 7.5% | "Table N" bold label, italic caption, above table, sequential |

### Scoring Formula
```
overall = (citations x 0.25) + (references x 0.25) + (headings x 0.15)
        + (doc_format x 0.10) + (abstract x 0.10) + (figures x 0.075)
        + (tables x 0.075)

submission_ready = overall >= 80
```

### Score Deductions (from prompt)
- Citations: -10 per numbered citation remaining, -5 per format error
- References: -5 per format error, -10 per missing field
- Headings: -25 per missing IMRAD section, -10 per wrong heading format
- Document Format: -15 per wrong setting
- Abstract: -15 if over word limit, -10 per missing element
- Figures/Tables: -10 per violation

### Python-Side Score Verification (validate_agent.py:48-98)

After the LLM returns scores, Python code:
1. Clamps every section score to [0, 100]
2. **Recomputes** overall_score from breakdown using exact weights
3. If recomputed differs from reported by >5 points, **overrides** with recomputed
4. Verifies submission_ready matches the 80-threshold

```python
SECTION_WEIGHTS = {
    "document_format": 0.10,
    "abstract":        0.10,
    "headings":        0.15,
    "citations":       0.25,
    "references":      0.25,
    "figures":         0.075,
    "tables":          0.075,
}
```

### Deterministic Checks Override (compliance_checker.py)

After the LLM produces scores, `compliance_checker.py` runs **4 deterministic Python checks** that override the LLM scores for verifiable facts:

1. **Abstract Word Count** — exact word count vs max_words (gradual penalty)
2. **Citation Format Match** — regex: do citations match numbered or author-date pattern?
3. **Reference Ordering** — are references sorted alphabetically by first-author surname?
4. **Citation-Reference Consistency** — orphan citations? uncited references?

These scores are **stamped over** the LLM scores with `[Verified]` tags.

### Output JSON Schema
```json
{
  "overall_score": 92,
  "submission_ready": true,
  "breakdown": {
    "citations":       { "score": 95, "issues": [], "details": {} },
    "references":      { "score": 90, "issues": ["..."], "details": {} },
    "headings":        { "score": 100, "issues": [], "details": {} },
    "document_format": { "score": 100, "issues": [], "details": {} },
    "abstract":        { "score": 85, "issues": ["..."], "details": {} },
    "figures":         { "score": 100, "issues": [], "details": {} },
    "tables":          { "score": 100, "issues": [], "details": {} }
  },
  "warnings": ["50%+ references older than 10 years"],
  "summary": "Paper scores 92/100 for APA 7th compliance."
}
```

---

## 7. DOCX Generation (build_apa_docx)

**File**: `backend/tools/docx_writer.py`
**Function**: `build_apa_docx(transform_output, output_path)`

This is the APA-specific DOCX builder. It reads `docx_instructions` from the TRANSFORM agent output and produces a fully formatted Word document using `python-docx`.

### Step 1: Document-Level Defaults
```python
style = doc.styles['Normal']
font.name = "Times New Roman"
font.size = Pt(12)  # from font_size_halfpoints / 2

paragraph_format.space_before = Pt(0)
paragraph_format.space_after = Pt(0)
paragraph_format.line_spacing = 2.0
paragraph_format.alignment = LEFT
```

### Step 2: Configure Heading Styles
```python
# H1: Bold, Centered, 12pt, NOT italic, black, no indent
# H2: Bold, Left-aligned, 12pt, NOT italic, black, no indent
# H3: Bold+Italic, Left-aligned, 12pt, black, 0.5" indent
```

### Step 3: Process Each Section (Page-Based)

The sections array drives page breaks:

#### title_page
- Adds 3 blank lines (top spacing)
- Title: bold, centered, 12pt Times New Roman
- Authors: centered, NOT bold
- Affiliation: centered, NOT bold

#### abstract_page
- `doc.add_section()` — new page
- "Abstract" label: bold, centered, no indent
- Abstract body: left-aligned, NO first-line indent
- Keywords: italic "Keywords:" label + comma-separated items, 0.5" indent

#### body
- `doc.add_section()` — new page
- Title repeat: bold, centered
- Body paragraphs: 0.5" first-line indent, left-aligned, double-spaced
- Headings: use Word Heading 1/2/3 styles (configured in Step 2)
- Figure captions: bold "Figure N" label + italic caption text
- Table captions: bold "Table N" label + italic caption text

#### references_page
- `doc.add_section()` — new page
- "References" label: bold, centered
- Each reference entry: **hanging indent** (left_indent=0.5", first_line_indent=-0.5")
- Italic text parsed from `*asterisk*` markers via `_add_text_with_italics()`

### Step 4: Page Size & Margins
```python
for section in doc.sections:
    section.page_width  = Twips(12240)   # US Letter width
    section.page_height = Twips(15840)   # US Letter height
    section.top_margin    = Twips(1440)  # 1 inch
    section.bottom_margin = Twips(1440)
    section.left_margin   = Twips(1440)
    section.right_margin  = Twips(1440)

    _add_page_number_header(section)     # Right-aligned page numbers
```

### Italic Marker Parsing
The TRANSFORM agent uses `*asterisks*` to mark italic text (journal names, volume numbers in references). The DOCX writer splits on this pattern:
```python
def _add_text_with_italics(paragraph, text):
    parts = re.split(r'(\*[^*]+\*)', text)
    for part in parts:
        if part.startswith('*') and part.endswith('*'):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(part)
```

---

## 8. Post-Pipeline Processing

After all 4 agents complete and the DOCX is written, `crew.py` performs:

### Post-Format Scoring (crew.py:1233-1242)
Re-extracts text from the **output DOCX** and runs the same `score_pre_format()` heuristics used on the input. This gives a before/after comparison on the frontend.

```python
output_text = extract_docx_text(str(output_path))
post_format_score = score_pre_format(output_text, rules)
```

### Formatting Report (crew.py:1245-1247)
Builds a structured report:
- `applied_transformations` — changes that were auto-applied
- `skipped_transformations` — user overrides that prevented changes
- `manual_action_required` — things the system couldn't fix automatically

### Deterministic Check Override (crew.py:1168-1180)
```python
det_checks = run_deterministic_checks(paper_structure, rules)
compliance_report = apply_deterministic_checks(
    compliance_report, det_checks, SECTION_WEIGHTS
)
```

### Final Pipeline Result
```python
pipeline_result = {
    "compliance_report": compliance_report,
    "docx_filename": "run_abc123/formatted_abc123.docx",
    "output_metadata": {"filename": "...", "size_bytes": ..., "size_kb": ...},
    "pipeline_metrics": {"stage_times": {...}, "total_runtime": 45.2},
    "changes_made": [...],
    "post_format_score": {"total_score": 87, ...},
    "formatting_report": {...},
}
```

---

## 9. End-to-End Data Flow Diagram

```
+-------------------+
|   User Upload     |
|   (PDF / DOCX)    |
+--------+----------+
         |
         v
+--------+----------+
| Text Extraction   |  extract_docx_text() / extract_pdf_text()
| (docx_reader.py / |  -> raw string (headings preserved as UPPERCASE
|  pdf_reader.py)   |     with blank line spacing)
+--------+----------+
         |
         | raw text string
         v
+--------+----------+
| AGENT 1: INGEST   |  System: INGEST_SYSTEM_PROMPT (generic)
|                    |  Task: "Label this paper with structural markers"
| GPT-4o-mini       |  Input: raw text
| temp=0            |  Output: labelled text with [TITLE_START]...[TITLE_END] etc.
+--------+----------+
         |
         | labelled text (string)
         v
+--------+----------+
| AGENT 2: PARSE    |  System: PARSE_SYSTEM_PROMPT (generic)
|                    |  Task: "Parse this labeled paper into structured JSON"
| GPT-4o-mini       |  Input: labelled text (via context=[ingest_task])
| temp=0            |  Output: paper_structure JSON
+--------+----------+
         |
         | paper_structure JSON
         v
+--------+----------+
| AGENT 3: TRANSFORM|  System: TRANSFORM_SYSTEM_PROMPT (APA-specific!)
|                    |  Task: "Transform to APA" + rules JSON + formatting guide
| GPT-4o-mini       |  Input: paper_structure (via context=[parse_task])
| temp=0            |  Output: violations + citation_replacements + reference_conversions
|                    |          + docx_instructions (page-based sections)
+--------+----------+
         |
         | transform output JSON (including docx_instructions)
         v
+--------+----------+
| AGENT 4: VALIDATE |  System: VALIDATE_SYSTEM_PROMPT (APA-specific!)
|                    |  Task: "Validate against APA" + rules JSON + facts
| GPT-4o-mini       |  Input: transform output (via context=[transform_task])
| temp=0            |  Output: compliance_report (7 checks, overall_score)
+--------+----------+
         |
         | compliance_report JSON
         v
+--------+----------+
| DETERMINISTIC     |  Python-only — no LLM
| CHECKS            |  Overrides LLM scores for: abstract word count,
| (compliance_      |  citation format, reference ordering, citation consistency
|  checker.py)      |  Stamps [Verified] tags on issues
+--------+----------+
         |
         v
+--------+----------+
| DOCX WRITER       |  build_apa_docx(transform_output, output_path)
| (docx_writer.py)  |
|                    |  Reads docx_instructions.sections:
|                    |    title_page -> abstract_page -> body -> references_page
|                    |
|                    |  Applies:
|                    |    - Times New Roman 12pt, double-spaced
|                    |    - 1" margins, US Letter
|                    |    - Heading styles (H1 centered, H2 left, H3 italic)
|                    |    - 0.5" first-line indent on body paragraphs
|                    |    - Hanging indent on references
|                    |    - *italic* marker parsing
|                    |    - Right-aligned page numbers
+--------+----------+
         |
         | formatted .docx file
         v
+--------+----------+
| POST-PROCESSING   |
|                    |  1. Post-format scoring (extract text from output DOCX,
|                    |     re-run score_pre_format for before/after comparison)
|                    |  2. Build formatting_report (applied/skipped/manual)
|                    |  3. Assemble pipeline_result dict
+--------+----------+
         |
         v
+--------+----------+
| API RESPONSE      |  /format endpoint returns:
|                    |    download_url, preview_url, compliance_report,
|                    |    post_format_score, formatting_report, pipeline_metrics
+-------------------+
```

---

## Key Design Decisions

1. **Generic vs Specific Prompts**: Agents 1-2 are journal-agnostic because structure labeling and JSON extraction don't depend on the target format. Agents 3-4 are journal-specific because formatting rules and scoring criteria differ per journal.

2. **Page-Based vs Flat Sections**: APA uses page-based sections (`title_page`, `abstract_page`, `body`, `references_page`) because APA requires each on a separate page. IEEE uses flat sections (`title`, `heading`, `paragraph`, `reference`) because IEEE has no page-break requirements.

3. **Citation Conversion in TRANSFORM, not DOCX writer**: The LLM performs all citation find-replace INLINE in the body text. The DOCX writer receives already-converted text. This ensures the LLM can use its understanding of context to distinguish parenthetical vs narrative citations.

4. **Deterministic Override Layer**: The compliance_checker.py runs Python-exact checks (word count, regex, sort order) and overrides LLM scores. This prevents the LLM from hallucinating wrong scores for objectively verifiable facts.

5. **Italic Markers**: Rather than passing complex formatting metadata, the TRANSFORM agent marks italic text with `*asterisks*` in the JSON text fields. The DOCX writer parses these into italic runs. Simple and reliable.

6. **Units in docx_instructions**: APA uses Word-native units:
   - `font_size_halfpoints: 24` = 12pt (Word stores font size in half-points)
   - `line_spacing_twips: 480` = double-spaced (1 inch = 1440 twips)
   - `body_first_line_indent_dxa: 720` = 0.5 inch (1440 DXA = 1 inch)
   - `margins: 1440` = 1 inch all sides
   - `page_size: {width: 12240, height: 15840}` = US Letter (8.5" x 11")
