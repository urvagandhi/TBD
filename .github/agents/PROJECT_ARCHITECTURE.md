---
name: project-architecture
description: Agent Paperpal — Autonomous Manuscript Formatting System. HackaMined 2026 | Cactus Communications | Paperpal Track. Full project domain context for all agents.
---

# PROJECT_ARCHITECTURE.md — Agent Paperpal

> **Purpose**: Define WHAT to build and WHY. All HOW-to-build rules live in `UNIVERSAL_AGENT.md` and domain agents.
>
> **Reading order**: `UNIVERSAL_AGENT.md` (1st) → This file (2nd) → Domain agents (3rd).
>
> **This file governs ALL agents**. Technical standards never override domain context.

---

## 1. Project Overview

**Project Name**: `Agent Paperpal`

**Hackathon**: HackaMined 2026 | Track: "Fix My Format, Agent Paperpal" | Sponsor: Cactus Communications (Paperpal by Editage)

**Problem Statement**:
> Academic publishing demands strict adherence to journal-specific formatting styles (APA, IEEE, Vancouver, Springer, Chicago). Researchers spend countless hours manually reformatting manuscripts. Formatting errors are among the most common reasons for manuscript rejection. Build an **agentic AI system** that can autonomously interpret journal guidelines and dynamically transform manuscripts to meet required standards.

**Core Objective**: Accept a research paper (PDF or DOCX), detect its structure, load target journal rules, fix every formatting violation autonomously, and output a publication-ready `.docx` file with a compliance score dashboard.

**Critical Distinction**: This is NOT a grammar checker. NOT a plagiarism detector. This is an **autonomous formatting agent** — the first of its kind.

**Target Users**:
- Academic researchers preparing manuscripts for journal submission
- Graduate students formatting thesis/dissertations
- Academic editors doing pre-submission checks

**Evaluation Criteria**:
| Criteria | Weight | How We Score High |
|----------|--------|-------------------|
| Style guide accuracy | 30% | Precise rules JSON + LLM verification |
| Working demo | 30% | Live upload → format → download in ~45s |
| Presentation + Mentor engagement | 20% | Show Paperpal product knowledge + internship pitch |
| Tech scalability | 20% | Modular agents, new journal = new JSON file only |

**Internship Pitch to Mentors**:
> "Paperpal currently checks and suggests fixes. Our agent auto-transforms the entire document and outputs a submission-ready .docx. This could be a new 'Auto-Format' feature inside Paperpal — one click, fully formatted paper. We noticed the gap: the tool tells you what's wrong but doesn't fix it automatically. That's exactly what Agent Paperpal solves."

---

## 2. Tech Stack (HARDCODED — Do NOT deviate)

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | React 18 + Vite | 18.x |
| Frontend Styling | TailwindCSS (dark theme: gray-950 background) | 3.x |
| Frontend HTTP | Axios | latest |
| Backend | FastAPI + Uvicorn | 0.111.0 / 0.29.0 |
| Backend Language | Python 3.11+ | 3.11+ |
| AI Brain | Gemini 2.0 Flash via Google AI Studio | gemini-2.0-flash |
| Agent Framework | CrewAI (sequential pipeline) | 0.36.0+ |
| LLM Client | LiteLLM (built into CrewAI) — string format "gemini/gemini-2.0-flash" | built-in |
| PDF Reading | PyMuPDF (fitz) | 1.24.0 |
| DOCX Read/Write | python-docx | 1.1.0 |
| File Upload | python-multipart | 0.0.9 |
| Validation | Pydantic v2 | 2.7.0 |
| Config | python-dotenv | 1.0.1 |
| Testing | pytest + httpx | latest |

**CRITICAL**: Backend is Python/FastAPI — NOT Node.js/Express. All api-agent.md patterns MUST use Python/FastAPI idioms, NOT TypeScript/Prisma.

---

## 3. Folder Structure (CANONICAL — Must match exactly)

```
paperpal-agent/
├── backend/
│   ├── main.py                  ← FastAPI routing ONLY — zero business logic
│   ├── crew.py                  ← CrewAI assembly + kickoff + run_pipeline()
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── ingest_agent.py      ← Agent 1: Read + extract file content
│   │   ├── parse_agent.py       ← Agent 2: Detect paper structure via LLM
│   │   ├── interpret_agent.py   ← Agent 3: Load journal rules from JSON
│   │   ├── transform_agent.py   ← Agent 4: Fix violations via LLM + docx_writer
│   │   └── validate_agent.py    ← Agent 5: Score compliance 0-100
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── pdf_reader.py        ← PyMuPDF text extraction
│   │   ├── docx_reader.py       ← python-docx text extraction
│   │   ├── docx_writer.py       ← python-docx formatted output generation
│   │   └── rule_loader.py       ← JSON rules loading + JOURNAL_MAP lookup
│   ├── rules/
│   │   ├── apa7.json            ← APA 7th Edition rules
│   │   ├── ieee.json            ← IEEE rules
│   │   ├── vancouver.json       ← Vancouver rules
│   │   ├── springer.json        ← Springer rules
│   │   └── chicago.json         ← Chicago rules
│   ├── schemas/
│   │   └── rules_schema.json    ← JSON Schema to validate rules/*.json
│   ├── engine/
│   │   ├── __init__.py
│   │   └── format_engine.py     ← FormatEngine class + load_format_engine()
│   ├── uploads/                 ← Temp uploaded files (git-ignored)
│   ├── outputs/                 ← Formatted output DOCX files (git-ignored)
│   ├── .env                     ← GEMINI_API_KEY + GOOGLE_API_KEY (never commit)
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx              ← Root component + state machine
│   │   ├── components/
│   │   │   ├── Upload.jsx       ← File drag/drop + journal selector + submit
│   │   │   ├── BeforeAfter.jsx  ← Side-by-side document comparison
│   │   │   ├── ComplianceScore.jsx ← Score dashboard with per-section bars
│   │   │   └── ChangesList.jsx  ← Explainable list of all corrections made
│   │   └── index.css            ← Tailwind + dark theme tokens
│   ├── package.json
│   └── vite.config.js
│
├── tasks/
│   ├── todo.md                  ← Active task tracking
│   └── lessons.md               ← Accumulated lessons
└── README.md
```

---

## 4. Core Concepts / Domain Model

### 4.1 Processing Pipeline — Sequential CrewAI Agents

```
INGEST → PARSE → INTERPRET → TRANSFORM → VALIDATE
  ↓        ↓         ↓            ↓           ↓
Raw      Paper     Journal    Formatted    Compliance
Content  Structure  Rules     DOCX         Report
```

Each agent has ONE job. Never combine responsibilities. Context flows automatically via CrewAI task output chaining.

### 4.2 Journal Styles Supported

| Style Name (User-facing) | File | Key Characteristics |
|--------------------------|------|---------------------|
| APA 7th Edition | apa7.json | Times New Roman 12pt, 2.0 spacing, author-date citations, alphabetical refs |
| IEEE | ieee.json | Times New Roman 10pt, 1.0 spacing, numbered [N] citations, appearance-order refs |
| Vancouver | vancouver.json | Times New Roman 12pt, 2.0 spacing, numbered [N] citations, appearance-order refs |
| Springer | springer.json | Times New Roman 12pt, 1.5 spacing, author-date citations, alphabetical refs |
| Chicago | chicago.json | Times New Roman 12pt, 2.0 spacing, author-date or footnote, alphabetical refs |

### 4.3 Paper Structure Elements (What PARSE Agent Detects)

```
- title: Full paper title
- authors: List of author names
- abstract: { text, word_count }
- keywords: List of keyword strings
- imrad: { introduction: bool, methods: bool, results: bool, discussion: bool }
- sections: [{ heading, level (H1/H2/H3), content_preview, in_text_citations }]
- figures: [{ id, caption }]
- tables: [{ id, caption }]
- references: ["full reference string", ...]
```

### 4.4 Journal Rules Schema (rules/*.json)

```json
{
  "style_name": "string",
  "document": { "font": "string", "font_size": number, "line_spacing": number, "margins": {...} },
  "abstract": { "label": "string", "label_bold": bool, "label_centered": bool, "max_words": number },
  "headings": {
    "H1": { "bold": bool, "centered": bool, "italic": bool, "case": "Title Case|UPPERCASE|Sentence case" },
    "H2": { "bold": bool, "centered": bool, "italic": bool, "case": "string" },
    "H3": { "bold": bool, "centered": bool, "italic": bool, "indent": bool }
  },
  "citations": { "style": "author-date|numbered", "format": "string", "two_authors": "string", "three_plus": "string" },
  "references": { "section_label": "string", "label_bold": bool, "label_centered": bool, "ordering": "alphabetical|appearance", "hanging_indent": bool, "journal_article_format": "string" },
  "figures": { "label_format": "string", "label_bold": bool, "caption_position": "above|below", "caption_italic": bool },
  "tables": { "label_format": "string", "label_bold": bool, "caption_position": "above|below", "borders": "string" }
}
```

### 4.5 Compliance Report Schema (What VALIDATE Agent Produces)

```json
{
  "overall_score": 0-100,
  "breakdown": {
    "document_format": { "score": 0-100, "issues": ["string"] },
    "abstract": { "score": 0-100, "issues": ["string"] },
    "headings": { "score": 0-100, "issues": ["string"] },
    "citations": { "score": 0-100, "issues": ["string"] },
    "references": { "score": 0-100, "issues": ["string"] },
    "figures": { "score": 0-100, "issues": ["string"] },
    "tables": { "score": 0-100, "issues": ["string"] }
  },
  "changes_made": ["Human-readable string describing each correction"],
  "imrad_check": { "introduction": bool, "methods": bool, "results": bool, "discussion": bool },
  "citation_consistency": { "orphan_citations": ["string"], "uncited_references": ["string"] },
  "warnings": ["string"]
}
```

---

## 5. API Surface

**Base URL**: `http://localhost:8000`

**Endpoints**:

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/health` | Health check | None |
| POST | `/format` | Upload + format document | None |
| GET | `/download/{filename}` | Download formatted DOCX | None |

### POST /format — Request

```
Content-Type: multipart/form-data
Fields:
  - file: UploadFile (PDF or DOCX, max 10MB)
  - journal: string (one of: "APA 7th Edition", "IEEE", "Vancouver", "Springer", "Chicago")
```

### POST /format — Response (Success)

```json
{
  "success": true,
  "download_url": "/download/formatted_abc12345.docx",
  "compliance_report": { ... ComplianceReport schema ... },
  "processing_time_seconds": 42.3
}
```

### POST /format — Response (Error)

```json
{
  "success": false,
  "error": "Could not extract text from document",
  "step": "pipeline_execution"
}
```

**Validation Rules**:
- File extension MUST be `pdf` or `docx`
- File size MUST be ≤ 10MB (10 * 1024 * 1024 bytes)
- Extracted text MUST be ≥ 100 characters
- Journal MUST be one of the 5 supported styles

---

## 6. Agent Responsibilities (ONE JOB PER AGENT — NEVER COMBINE)

### Agent 1: INGEST
- **Input**: Raw file path + paper content text
- **Job**: Structure and label all content elements with type markers
- **Output**: Structured raw content with element markers
- **Tools used**: pdf_reader.py, docx_reader.py
- **LLM used**: YES (minimal — to label elements)
- **NEVER**: Parse structure, apply rules, create output files

### Agent 2: PARSE
- **Input**: Raw content from Agent 1
- **Job**: Call GPT-4o-mini to identify ALL structural elements
- **Output**: Valid JSON matching paper_structure schema (temperature=0)
- **Tools used**: None (pure LLM task)
- **LLM used**: YES (primary reasoning task)
- **NEVER**: Load rules, fix violations, score compliance

### Agent 3: INTERPRET
- **Input**: Journal name string from inputs
- **Job**: Load the correct rules JSON file via JOURNAL_MAP lookup
- **Output**: Complete journal rules JSON
- **Tools used**: rule_loader.py
- **LLM used**: ONLY as fallback for unsupported journals (generate rules dynamically)
- **NEVER**: Parse paper structure, fix violations, score

### Agent 4: TRANSFORM
- **Input**: paper_structure (from Agent 2) + rules (from Agent 3)
- **Job**: Compare every element → identify violations → generate docx_instructions → call docx_writer → save formatted DOCX
- **Output**: JSON with violations list, changes_made list, docx_path
- **Tools used**: docx_writer.py
- **LLM used**: YES (comparison + instruction generation, temperature=0)
- **NEVER**: Re-parse structure, load rules again, score compliance

### Agent 5: VALIDATE
- **Input**: Formatted document content + journal rules
- **Job**: Perform 7 compliance checks, score each 0-100
- **Output**: Complete compliance_report JSON
- **Tools used**: None (pure LLM analysis)
- **LLM used**: YES (validation logic, temperature=0)
- **NEVER**: Make further edits, re-run transformation

### 7 Validation Checks Agent 5 MUST Perform:
1. Citation ↔ Reference 1:1 consistency (orphan citations + uncited references)
2. IMRAD structure completeness (all 4 sections present)
3. Reference age (flag if >50% older than 10 years)
4. Self-citation rate (flag if same author >30% of references)
5. Figure sequential numbering (no gaps: 1, 2, 3...)
6. Table sequential numbering (no gaps: 1, 2, 3...)
7. Abstract word count vs journal limit

---

## 7. Business Rules (MUST ENFORCE)

| Rule | Where Enforced |
|------|----------------|
| Only PDF and DOCX accepted | main.py — before pipeline starts |
| File size ≤ 10MB | main.py — after reading content bytes |
| Extracted text ≥ 100 chars | main.py — after extraction |
| Journal must be in JOURNAL_MAP | rule_loader.py + main.py validation |
| Output ALWAYS a .docx file | transform_agent.py — never return plain text only |
| All journal rules live in rules/*.json | NEVER hardcode rules inside agent code |
| API keys NEVER hardcoded | .env + os.getenv() always |
| Every tool function has try/except | tools/*.py — meaningful error messages |
| Unique filename per upload | uuid4()[:8] prefix |

---

## 8. State Machine — Processing Job

```
IDLE → UPLOADING → EXTRACTING → PIPELINE_RUNNING → FORMATTING → VALIDATING → COMPLETE
Any → ERROR (terminal — user must retry)
```

**Frontend shows these states** via PIPELINE_STEPS progress indicator:
1. "Reading document..."
2. "Detecting structure..."
3. "Loading journal rules..."
4. "Formatting document..."
5. "Validating output..."

Progress simulated on frontend (9s per step interval) since backend is synchronous ~45s pipeline.

---

## 9. File Handling

| Directory | Purpose | Lifecycle |
|-----------|---------|-----------|
| `uploads/` | Temp uploaded files | Created at startup, never committed |
| `outputs/` | Formatted DOCX files | Created at startup, never committed |
| Filename pattern | `{uuid8}_{original_filename}` | Upload path |
| Output pattern | `formatted_{uuid8}.docx` | Output path |

Both directories created with `os.makedirs(..., exist_ok=True)` at server startup.

---

## 10. DOCX Writer Responsibilities (tools/docx_writer.py)

The docx_writer MUST apply these transformations based on docx_instructions from Agent 4:

| Transformation | Implementation |
|---------------|----------------|
| Font name + size | `paragraph.runs[i].font.name/size` |
| Line spacing | `paragraph.paragraph_format.line_spacing` |
| Heading bold/center | `run.bold`, `paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER` |
| Heading case (Title Case / UPPERCASE) | `text.title()` / `text.upper()` |
| Citation replacement | String replacement in paragraph runs |
| Reference reordering | Sort alphabetically or by appearance order |
| Figure caption position | Move paragraphs above/below figure marker |
| Table caption position | Move paragraphs above/below table |
| Abstract label bold | `run.bold = True` on "Abstract" run |
| Margins | `doc.sections[0].top_margin = Inches(1.0)` |

---

## 11. JOURNAL_MAP (tools/rule_loader.py)

```python
JOURNAL_MAP = {
    "APA 7th Edition": "apa7.json",
    "APA": "apa7.json",
    "IEEE": "ieee.json",
    "Vancouver": "vancouver.json",
    "Springer": "springer.json",
    "Chicago": "chicago.json",
}
```

Any journal name NOT in this map falls back to LLM-generated rules via interpret_agent.

---

## 12. Frontend UI States

| State | Component Shown |
|-------|----------------|
| `idle` | Upload component (drag/drop + journal select + submit button) |
| `loading` | Pipeline steps progress with animated spinner + step dots |
| `success` | ComplianceScore + ChangesList + Download button + "Format Another" |
| `error` | Error message + "Try Again" button |

**UI Theme**: Dark (bg-gray-950 background, white text, blue-400 accents)

---

## 13. Edge Cases and Handling

| Edge Case | Handling Strategy |
|-----------|------------------|
| PDF with no extractable text (scanned) | Return 400: "Could not extract text from document" |
| DOCX with only images | Return 400: extracted text < 100 chars threshold |
| Unknown journal name | rule_loader falls back to LLM-generated rules |
| LLM returns malformed JSON | Agent retries with explicit "return ONLY valid JSON" instruction |
| Pipeline takes > 120s | Frontend axios timeout 120000ms returns timeout error |
| Large paper (>10MB) | Return 400 before pipeline starts |
| Empty violation list (perfect paper) | Still generate compliance report with score ~95-100 |
| File not found on download | Return 404 |
| OpenAI API rate limit hit | CrewAI handles retry internally; log error if exhausted |

---

## 14. Scale and Performance

| Concern | Expectation |
|---------|-------------|
| Processing time | 40-60 seconds per paper (GPT-4o-mini is fast) |
| Concurrent requests | 1-2 (hackathon demo — not production scale) |
| Max file size | 10MB |
| Output file | ~50-200KB DOCX |
| Journal support | 5 (extensible via new JSON file only) |
| API cost per paper | ~$0.01-0.05 (GPT-4o-mini pricing) |

Adding a new journal: Create `rules/newjournal.json` + add entry to `JOURNAL_MAP`. Zero code changes required.

---

## 15. Demo Script (Hackathon Presentation Order)

1. Upload a real academic paper PDF (bring one pre-prepared)
2. Select "APA 7th Edition" from dropdown
3. Click "Format My Paper"
4. Show pipeline steps animating (~45 seconds)
5. Show compliance score dashboard (highlight per-section scores)
6. Show changes list (explainable corrections)
7. Download the formatted DOCX
8. Open DOCX and show "before vs after" formatting side-by-side
9. Switch journal to "IEEE" — show new rules apply differently
10. Pitch: "One click. Fully formatted. Submission-ready."

---

## END OF PROJECT ARCHITECTURE

> All agents derive their work from this document:
> - **AI Agent / LLM Agent** → Pipeline design from Sections 6, 7, 13
> - **API Agent** → Endpoints from Section 5, validation from Section 7
> - **UI/UX Agent** → States from Section 12, components from Section 3
> - **Test Agent** → Test cases from Sections 7, 13
