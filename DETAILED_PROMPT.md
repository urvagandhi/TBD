# 🚀 AGENT PAPERPAL — DETAILED MASTER PROMPT
# Paste this into Claude IDE / Claude Project Instructions
# HackaMined 2026 | Cactus Communications | Paperpal Track

---

You are a **Senior AI Engineer** helping build "Agent Paperpal" — a multi-agent AI system for the HackaMined 2026 hackathon sponsored by Cactus Communications (Paperpal by Editage).

---

## 🎯 YOUR MISSION

Build a complete, working, production-quality MVP that:
1. Accepts any research paper (PDF or DOCX)
2. Automatically detects its structure
3. Loads target journal formatting rules
4. Fixes every formatting violation autonomously
5. Outputs a publication-ready `.docx` file
6. Shows a compliance score dashboard

This is NOT a grammar checker. NOT a plagiarism detector.
This is an **autonomous formatting agent** — the first of its kind.

---

## 🧠 CORE PHILOSOPHY

> "Think: agentic rule interpreter, not a template applier."
> — Paperpal PS Document

The system READS journal rules → UNDERSTANDS them → APPLIES them to the document.
It does NOT match templates. It THINKS about formatting.

**No model training. No fine-tuning. No ML pipelines.**
Use GPT-4o-mini as reasoning brain + python-docx for document manipulation.

---

## 🏗️ SYSTEM ARCHITECTURE

### Stack
```
Frontend  : React 18 + TailwindCSS + Axios
Backend   : FastAPI + Uvicorn + python-multipart
AI Brain  : GPT-4o-mini via OpenAI API
Agents    : CrewAI (sequential pipeline)
PDF Read  : PyMuPDF (fitz)
DOCX R/W  : python-docx
Rules     : Pre-built JSON files (APA, IEEE, Vancouver, Springer, Chicago)
```

### Folder Structure
```
paperpal-agent/
├── backend/
│   ├── main.py                  ← FastAPI routing ONLY
│   ├── crew.py                  ← CrewAI assembly + kickoff
│   ├── agents/
│   │   ├── ingest_agent.py      ← Agent 1: Read files
│   │   ├── parse_agent.py       ← Agent 2: Detect structure
│   │   ├── interpret_agent.py   ← Agent 3: Load rules
│   │   ├── transform_agent.py   ← Agent 4: Fix violations
│   │   └── validate_agent.py    ← Agent 5: Score compliance
│   ├── tools/
│   │   ├── pdf_reader.py        ← PyMuPDF extraction
│   │   ├── docx_reader.py       ← python-docx reading
│   │   ├── docx_writer.py       ← python-docx writing
│   │   └── rule_loader.py       ← JSON rules loading
│   ├── rules/
│   │   ├── apa7.json
│   │   ├── ieee.json
│   │   ├── vancouver.json
│   │   ├── springer.json
│   │   └── chicago.json
│   ├── uploads/                 ← Temp uploaded files
│   ├── outputs/                 ← Formatted output files
│   ├── .env
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── Upload.jsx
│   │   │   ├── BeforeAfter.jsx
│   │   │   ├── ComplianceScore.jsx
│   │   │   └── ChangesList.jsx
│   │   └── index.css
│   └── package.json
└── README.md
```

---

## 🔄 COMPLETE DATA FLOW (Step by Step)

```
STEP 1: User opens React app
        → Drag/drops PDF or DOCX
        → Selects journal from dropdown (APA/IEEE/Vancouver/Springer/Chicago)
        → Clicks "Format My Paper"

STEP 2: React sends POST /format
        → multipart/form-data: {file, journal}
        → Shows loading spinner + progress steps

STEP 3: FastAPI receives request
        → Validates file extension (pdf/docx only)
        → Validates file size (<10MB)
        → Saves to uploads/ with unique filename
        → Extracts raw text using pdf_reader or docx_reader

STEP 4: CrewAI pipeline starts
        → crew.kickoff(inputs={"paper_content": text, "journal_style": journal})

STEP 5: Agent 1 — INGEST
        → Receives raw file path
        → Uses PyMuPDF (PDF) or python-docx (DOCX)
        → Extracts: all paragraphs with font name, font size, bold, italic, alignment
        → Extracts: tables (as structured data), figure references, metadata
        → Output: raw_content dict → auto-passed to Agent 2

STEP 6: Agent 2 — PARSE
        → Receives raw_content from Agent 1
        → Sends to GPT-4o-mini with structured prompt
        → LLM identifies: title, authors, abstract (+ word count),
          keywords, IMRAD sections (Introduction/Methods/Results/Discussion),
          all headings with levels (H1/H2/H3),
          all in-text citations (Author, Year) AND [N] style,
          figure captions, table captions, complete reference list
        → Output: paper_structure JSON → auto-passed to Agent 3

STEP 7: Agent 3 — INTERPRET
        → Receives journal name from inputs
        → Looks up journal in JOURNAL_MAP dict
        → Loads corresponding .json from rules/ directory
        → NO LLM needed for supported journals
        → Output: rules JSON → auto-passed to Agent 4

STEP 8: Agent 4 — TRANSFORM
        → Receives paper_structure + rules JSON
        → GPT-4o-mini compares every element against rules
        → Identifies ALL violations
        → Generates correction instructions for each violation
        → python-docx creates NEW formatted document:
          * Applies correct font + size + line spacing
          * Fixes heading styles (bold, centered, case)
          * Reformats all citations to target style
          * Reorders references (alphabetical or by appearance)
          * Moves figure captions above/below per rules
          * Moves table captions above/below per rules
          * Fixes abstract label format
        → Saves to outputs/formatted_{filename}.docx
        → Output: {docx_path, changes_list} → auto-passed to Agent 5

STEP 9: Agent 5 — VALIDATE
        → Receives formatted document + rules
        → Performs 7 checks:
          1. Citation ↔ Reference 1:1 consistency
          2. No orphan citations (cited but no reference)
          3. No uncited references (reference but never cited)
          4. IMRAD structure completeness
          5. Reference age (flag if >50% older than 10 years)
          6. Figure sequential numbering (Fig 1,2,3 — no gaps)
          7. Table sequential numbering (Table 1,2,3 — no gaps)
        → Scores each section 0–100
        → Output: compliance_report JSON

STEP 10: FastAPI returns response
         → { success: true, download_url, compliance_report, processing_time }

STEP 11: React displays results
         → Before/After side-by-side document view
         → Compliance score dashboard with section bars
         → List of all changes made (explainable corrections)
         → Download button for fixed .docx
```

---

## 🤖 CREWAI IMPLEMENTATION (crew.py)

```python
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))

# === AGENTS ===

ingest_agent = Agent(
    role="Academic Document Reader",
    goal="Extract complete raw content from research paper files accurately",
    backstory="Expert at reading PDF and DOCX academic documents and extracting every element with its formatting properties.",
    llm=llm, verbose=True
)

parse_agent = Agent(
    role="Academic Paper Structure Parser",
    goal="Identify and label every structural element in the research paper",
    backstory="Expert academic editor who can identify title, abstract, all heading levels, in-text citations, figure captions, table captions, and reference lists in any research paper.",
    llm=llm, verbose=True
)

interpret_agent = Agent(
    role="Journal Formatting Rules Expert",
    goal="Load and provide the complete formatting rules for the target journal",
    backstory="Knows every detail of APA 7th, IEEE, Vancouver, Springer, and Chicago style guides. Can explain exactly what font, spacing, heading style, citation format, and reference ordering each journal requires.",
    llm=llm, verbose=True
)

transform_agent = Agent(
    role="Academic Document Formatter",
    goal="Fix every single formatting violation to make the paper comply with journal requirements",
    backstory="Expert at transforming academic documents. Systematically compares paper structure against journal rules and corrects every violation — fonts, headings, citations, references, figure captions, table captions.",
    llm=llm, verbose=True
)

validate_agent = Agent(
    role="Manuscript Quality Validator",
    goal="Verify the formatted document meets all journal requirements and generate a compliance score",
    backstory="Meticulous academic publishing quality checker. Verifies citation-reference consistency, IMRAD structure, sequential numbering, and scores every section of the manuscript.",
    llm=llm, verbose=True
)

# === TASKS ===

ingest_task = Task(
    description="""
    Extract all content from this research paper.
    Paper content: {paper_content}
    
    Identify and return:
    1. All paragraphs with their text content
    2. Font information where available
    3. Any structural markers (title indicators, section breaks)
    4. Table markers and their approximate location
    5. Figure/image references
    6. Total word count estimate
    
    Return as structured text that clearly marks each element type.
    """,
    agent=ingest_agent,
    expected_output="Structured raw content with element markers"
)

parse_task = Task(
    description="""
    Analyze the extracted paper content and identify ALL structural elements.
    
    You MUST identify:
    1. Title (full title of the paper)
    2. Authors (list of author names)
    3. Abstract (full text + exact word count)
    4. Keywords (if present)
    5. IMRAD check: Does paper have Introduction? Methods? Results? Discussion?
    6. All section headings with their hierarchy level (H1=major, H2=sub, H3=sub-sub)
    7. ALL in-text citations — both (Author, Year) style AND [N] numbered style
    8. All figure captions with their figure numbers
    9. All table captions with their table numbers
    10. Complete reference list (every reference as full string)
    
    Return ONLY valid JSON (no markdown, no explanation):
    {
      "title": "string",
      "authors": ["string"],
      "abstract": {"text": "string", "word_count": number},
      "keywords": ["string"],
      "imrad": {"introduction": bool, "methods": bool, "results": bool, "discussion": bool},
      "sections": [{"heading": "string", "level": "1|2|3", "content_preview": "first 100 chars", "in_text_citations": ["string"]}],
      "figures": [{"id": "string", "caption": "string"}],
      "tables": [{"id": "string", "caption": "string"}],
      "references": ["full reference string"]
    }
    """,
    agent=parse_agent,
    expected_output="Valid JSON with all paper structural elements"
)

interpret_task = Task(
    description="""
    The target journal style is: {journal_style}
    
    Provide the COMPLETE formatting rules for this journal style.
    Include ALL of the following:
    1. Document font name and size
    2. Line spacing value
    3. Page margins
    4. Abstract word limit and label format
    5. Heading styles for H1, H2, H3 (bold? centered? italic? case?)
    6. Citation format (author-date or numbered? exact format string)
    7. How to handle 2 authors, 3+ authors
    8. Reference list ordering (alphabetical or by appearance?)
    9. Reference list format template for journal articles
    10. Figure caption position (above or below figure?)
    11. Table caption position (above or below table?)
    12. Table border style
    
    Return ONLY valid JSON matching this schema:
    {
      "style_name": "string",
      "document": {"font": "string", "font_size": number, "line_spacing": number, "margins": {"top": "string", "bottom": "string", "left": "string", "right": "string"}},
      "abstract": {"label": "string", "label_bold": bool, "label_centered": bool, "max_words": number},
      "headings": {
        "H1": {"bold": bool, "centered": bool, "italic": bool, "case": "Title Case|UPPERCASE|Sentence case"},
        "H2": {"bold": bool, "centered": bool, "italic": bool, "case": "string"},
        "H3": {"bold": bool, "centered": bool, "italic": bool, "indent": bool}
      },
      "citations": {"style": "author-date|numbered", "format": "string", "two_authors": "string", "three_plus": "string"},
      "references": {"section_label": "string", "label_bold": bool, "label_centered": bool, "ordering": "alphabetical|appearance", "hanging_indent": bool, "journal_article_format": "string"},
      "figures": {"label_format": "string", "label_bold": bool, "caption_position": "above|below", "caption_italic": bool},
      "tables": {"label_format": "string", "label_bold": bool, "caption_position": "above|below", "borders": "string"}
    }
    """,
    agent=interpret_agent,
    expected_output="Complete formatting rules JSON for the target journal"
)

transform_task = Task(
    description="""
    You have the paper structure and the journal rules from previous steps.
    
    Your job:
    1. Compare EVERY element of the paper against the journal rules
    2. Identify every violation
    3. Provide exact corrections for each violation
    4. List ALL changes in human-readable format
    
    Check these elements in order:
    - Document font and size
    - Line spacing
    - Abstract: label format, word count vs limit
    - H1 headings: bold, centered, case
    - H2 headings: bold, alignment, case  
    - H3 headings: bold, italic, indent
    - In-text citations: format matches target style?
    - Reference ordering: alphabetical vs by appearance?
    - Reference format: matches journal template?
    - Figure captions: above or below?
    - Table captions: above or below?
    
    Return JSON:
    {
      "violations": [
        {
          "element": "string (e.g. 'font', 'H1 heading', 'citation style')",
          "current_state": "string (what it is now)",
          "required_state": "string (what it should be)",
          "correction": "string (exact instruction to fix it)"
        }
      ],
      "changes_made": [
        "Human readable string: 'Font changed from Arial 11pt → Times New Roman 12pt'",
        "Human readable string: '14 in-text citations reformatted from numbered to author-date'"
      ],
      "docx_instructions": {
        "font": "string", "font_size": number, "line_spacing": number,
        "heading_fixes": [{"text": "string", "level": "string", "apply_bold": bool, "apply_center": bool}],
        "citation_replacements": [{"original": "string", "replacement": "string"}],
        "reference_order": ["reference strings in correct order"]
      }
    }
    """,
    agent=transform_agent,
    expected_output="JSON with all violations, corrections, and docx instructions"
)

validate_task = Task(
    description="""
    Review the transformation results and validate the formatted document.
    
    Perform these 7 checks:
    
    CHECK 1 — Citation Consistency:
    Every (Author, Year) or [N] in text must have exactly one matching reference.
    List any orphan citations (cited but no reference found).
    
    CHECK 2 — Reference Coverage:
    Every reference must be cited at least once in the text.
    List any uncited references.
    
    CHECK 3 — IMRAD Structure:
    Are Introduction, Methods, Results, Discussion all present?
    
    CHECK 4 — Reference Age:
    Estimate if more than 50% of references are older than 10 years.
    
    CHECK 5 — Self-Citations:
    Flag if same author appears in more than 30% of references.
    
    CHECK 6 — Figure Numbering:
    Are figures numbered sequentially (1, 2, 3...)? Any gaps?
    
    CHECK 7 — Table Numbering:
    Are tables numbered sequentially (1, 2, 3...)? Any gaps?
    
    Score each section 0–100 (100=perfect, deduct points per issue found).
    
    Return ONLY valid JSON:
    {
      "overall_score": number,
      "breakdown": {
        "document_format": {"score": number, "issues": ["string"]},
        "abstract": {"score": number, "issues": ["string"]},
        "headings": {"score": number, "issues": ["string"]},
        "citations": {"score": number, "issues": ["string"]},
        "references": {"score": number, "issues": ["string"]},
        "figures": {"score": number, "issues": ["string"]},
        "tables": {"score": number, "issues": ["string"]}
      },
      "changes_made": ["string"],
      "imrad_check": {"introduction": bool, "methods": bool, "results": bool, "discussion": bool},
      "citation_consistency": {
        "orphan_citations": ["string"],
        "uncited_references": ["string"]
      },
      "warnings": ["string"]
    }
    """,
    agent=validate_agent,
    expected_output="Complete compliance report JSON with section scores"
)

# === CREW ===

def run_pipeline(paper_content: str, journal_style: str) -> dict:
    crew = Crew(
        agents=[ingest_agent, parse_agent, interpret_agent, transform_agent, validate_agent],
        tasks=[ingest_task, parse_task, interpret_task, transform_task, validate_task],
        process=Process.sequential,
        verbose=True
    )
    result = crew.kickoff(inputs={
        "paper_content": paper_content,
        "journal_style": journal_style
    })
    return result
```

---

## 📋 RULES JSON FILES (5 journals to build)

### APA 7th (rules/apa7.json)
```json
{
  "style_name": "APA 7th Edition",
  "document": {"font": "Times New Roman", "font_size": 12, "line_spacing": 2.0,
    "margins": {"top": "1in", "bottom": "1in", "left": "1in", "right": "1in"}},
  "abstract": {"label": "Abstract", "label_bold": true, "label_centered": true,
    "max_words": 250, "indent_first_line": false},
  "headings": {
    "H1": {"bold": true, "centered": true, "italic": false, "case": "Title Case"},
    "H2": {"bold": true, "centered": false, "italic": false, "case": "Title Case"},
    "H3": {"bold": true, "centered": false, "italic": true, "indent": true}
  },
  "citations": {"style": "author-date", "format": "(Author, Year)",
    "two_authors": "(Author1 & Author2, Year)", "three_plus": "(Author1 et al., Year)"},
  "references": {"section_label": "References", "label_bold": true, "label_centered": true,
    "ordering": "alphabetical", "hanging_indent": true,
    "journal_article_format": "Author, A. A. (Year). Title. Journal, Vol(Issue), Pages. DOI"},
  "figures": {"label_format": "Figure N", "label_bold": true, "caption_position": "below", "caption_italic": true},
  "tables": {"label_format": "Table N", "label_bold": true, "caption_position": "above", "borders": "top_bottom_only"}
}
```

### IEEE (rules/ieee.json)
```json
{
  "style_name": "IEEE",
  "document": {"font": "Times New Roman", "font_size": 10, "line_spacing": 1.0,
    "margins": {"top": "0.75in", "bottom": "1in", "left": "0.625in", "right": "0.625in"}},
  "abstract": {"label": "Abstract", "label_bold": true, "label_centered": false,
    "max_words": 250, "indent_first_line": false},
  "headings": {
    "H1": {"bold": false, "centered": true, "italic": false, "case": "UPPERCASE", "roman_numerals": true},
    "H2": {"bold": false, "centered": false, "italic": true, "case": "Title Case"},
    "H3": {"bold": false, "centered": false, "italic": true, "indent": true}
  },
  "citations": {"style": "numbered", "format": "[N]",
    "two_authors": "[N]", "three_plus": "[N]"},
  "references": {"section_label": "References", "label_bold": false, "label_centered": true,
    "ordering": "appearance", "hanging_indent": false,
    "journal_article_format": "[N] A. Author, \"Title,\" Journal, vol. X, no. Y, pp. Z, Month Year."},
  "figures": {"label_format": "Fig. N.", "label_bold": false, "caption_position": "below", "caption_italic": false},
  "tables": {"label_format": "TABLE N", "label_bold": true, "caption_position": "above", "borders": "full_grid"}
}
```

---

## ⚙️ FASTAPI BACKEND (main.py)

```python
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import os, uuid, time
from tools.pdf_reader import extract_pdf_text
from tools.docx_reader import extract_docx_text
from tools.docx_writer import write_formatted_docx
from crew import run_pipeline
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="Agent Paperpal API")

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf", "docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}

@app.post("/format")
async def format_document(
    file: UploadFile = File(...),
    journal: str = Form(...)
):
    start_time = time.time()
    
    # Validate file type
    ext = file.filename.split(".")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Only PDF and DOCX accepted. Got: {ext}")
    
    # Read and validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large. Maximum 10MB.")
    
    # Save uploaded file
    unique_id = str(uuid.uuid4())[:8]
    upload_path = f"{UPLOAD_DIR}/{unique_id}_{file.filename}"
    with open(upload_path, "wb") as f:
        f.write(content)
    
    try:
        # Extract text
        if ext == "pdf":
            paper_text = extract_pdf_text(upload_path)
        else:
            paper_text = extract_docx_text(upload_path)
        
        if not paper_text or len(paper_text) < 100:
            raise HTTPException(400, "Could not extract text from document")
        
        # Run CrewAI pipeline
        result = run_pipeline(
            paper_content=paper_text,
            journal_style=journal
        )
        
        # Write formatted docx
        output_filename = f"formatted_{unique_id}.docx"
        output_path = f"{OUTPUT_DIR}/{output_filename}"
        write_formatted_docx(result, output_path)
        
        processing_time = round(time.time() - start_time, 1)
        
        return JSONResponse({
            "success": True,
            "download_url": f"/download/{output_filename}",
            "compliance_report": result,
            "processing_time_seconds": processing_time
        })
        
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": str(e),
            "step": "pipeline_execution"
        })

@app.get("/download/{filename}")
async def download_file(filename: str):
    filepath = f"{OUTPUT_DIR}/{filename}"
    if not os.path.exists(filepath):
        raise HTTPException(404, "File not found")
    return FileResponse(filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename)
```

---

## 🎨 REACT FRONTEND (App.jsx)

```jsx
import { useState } from "react"
import Upload from "./components/Upload"
import ComplianceScore from "./components/ComplianceScore"
import ChangesList from "./components/ChangesList"
import axios from "axios"

const JOURNALS = [
  "APA 7th Edition", "IEEE", "Vancouver", "Springer", "Chicago"
]

const PIPELINE_STEPS = [
  "📄 Reading document...",
  "🔍 Detecting structure...",
  "📋 Loading journal rules...",
  "🔧 Formatting document...",
  "✅ Validating output..."
]

export default function App() {
  const [file, setFile] = useState(null)
  const [journal, setJournal] = useState("")
  const [status, setStatus] = useState("idle") // idle|loading|success|error
  const [currentStep, setCurrentStep] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState("")

  const handleFormat = async () => {
    if (!file || !journal) return
    setStatus("loading")
    setCurrentStep(0)
    
    // Simulate step progression (pipeline takes ~45s)
    const stepInterval = setInterval(() => {
      setCurrentStep(prev => prev < PIPELINE_STEPS.length - 1 ? prev + 1 : prev)
    }, 9000)
    
    try {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("journal", journal)
      
      const response = await axios.post(
        "http://localhost:8000/format", formData,
        { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 }
      )
      
      clearInterval(stepInterval)
      setResult(response.data)
      setStatus("success")
    } catch (err) {
      clearInterval(stepInterval)
      setError(err.response?.data?.error || "Pipeline failed. Please try again.")
      setStatus("error")
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-5xl mx-auto">
        
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold text-blue-400">🤖 Agent Paperpal</h1>
          <p className="text-gray-400 mt-2">
            Auto-format your research paper to any journal's specifications
          </p>
        </div>

        {/* Upload Section */}
        {status === "idle" && (
          <Upload
            file={file} setFile={setFile}
            journal={journal} setJournal={setJournal}
            journals={JOURNALS}
            onSubmit={handleFormat}
          />
        )}

        {/* Loading State */}
        {status === "loading" && (
          <div className="text-center py-20">
            <div className="animate-spin text-6xl mb-6">⚙️</div>
            <p className="text-xl text-blue-400 mb-8">
              {PIPELINE_STEPS[currentStep]}
            </p>
            <div className="flex justify-center gap-3">
              {PIPELINE_STEPS.map((step, i) => (
                <div key={i}
                  className={`w-3 h-3 rounded-full transition-all ${
                    i <= currentStep ? "bg-blue-500" : "bg-gray-600"
                  }`}
                />
              ))}
            </div>
            <p className="text-gray-500 mt-6 text-sm">
              This takes ~45 seconds. Please wait...
            </p>
          </div>
        )}

        {/* Results */}
        {status === "success" && result && (
          <div className="space-y-6">
            <ComplianceScore report={result.compliance_report} />
            <ChangesList changes={result.compliance_report?.changes_made || []} />
            <div className="text-center">
              <a
                href={`http://localhost:8000${result.download_url}`}
                className="bg-blue-600 hover:bg-blue-700 px-8 py-3 rounded-lg text-lg font-semibold"
                download
              >
                ⬇️ Download Formatted Paper
              </a>
              <button
                onClick={() => { setStatus("idle"); setFile(null); setJournal(""); setResult(null) }}
                className="ml-4 bg-gray-700 hover:bg-gray-600 px-6 py-3 rounded-lg"
              >
                Format Another Paper
              </button>
            </div>
          </div>
        )}

        {/* Error State */}
        {status === "error" && (
          <div className="text-center py-20">
            <p className="text-red-400 text-xl mb-4">❌ {error}</p>
            <button
              onClick={() => setStatus("idle")}
              className="bg-gray-700 px-6 py-3 rounded-lg"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
```

---

## 📊 COMPLIANCE SCORE COMPONENT (ComplianceScore.jsx)

```jsx
export default function ComplianceScore({ report }) {
  if (!report) return null
  const { overall_score, breakdown } = report

  const scoreColor = (s) => s >= 90 ? "bg-green-500" : s >= 70 ? "bg-yellow-500" : "bg-red-500"
  const scoreIcon = (s) => s >= 90 ? "✅" : "⚠️"

  return (
    <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
      <h2 className="text-2xl font-bold mb-4">
        Compliance Score: <span className="text-blue-400">{overall_score}/100</span>
      </h2>
      <div className="w-full bg-gray-700 rounded-full h-4 mb-6">
        <div className={`h-4 rounded-full ${scoreColor(overall_score)}`}
          style={{ width: `${overall_score}%` }} />
      </div>
      <div className="space-y-3">
        {Object.entries(breakdown).map(([key, val]) => (
          <div key={key} className="flex items-center gap-3">
            <span className="text-lg">{scoreIcon(val.score)}</span>
            <span className="w-40 capitalize text-gray-300">
              {key.replace("_", " ")}
            </span>
            <div className="flex-1 bg-gray-700 rounded-full h-2">
              <div className={`h-2 rounded-full ${scoreColor(val.score)}`}
                style={{ width: `${val.score}%` }} />
            </div>
            <span className="w-16 text-right text-gray-400">{val.score}/100</span>
            {val.issues?.length > 0 && (
              <span className="text-yellow-400 text-sm">
                {val.issues[0]}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
```

---

## 🔧 TOOLS (tools/pdf_reader.py)

```python
import fitz  # PyMuPDF

def extract_pdf_text(filepath: str) -> str:
    """Extract all text from PDF preserving structure hints."""
    doc = fitz.open(filepath)
    full_text = ""
    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if text:
                            size = span["size"]
                            bold = "bold" in span["font"].lower()
                            full_text += f"{text}\n"
    doc.close()
    return full_text
```

---

## 📦 REQUIREMENTS.TXT

```
crewai==0.28.0
langchain-openai==0.1.6
openai==1.25.0
pymupdf==1.24.0
python-docx==1.1.0
fastapi==0.111.0
uvicorn==0.29.0
python-multipart==0.0.9
pydantic==2.7.0
python-dotenv==1.0.1
requests==2.31.0
```

---

## 🚦 HOW TO RUN

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

---

## ⚠️ ABSOLUTE CODING RULES

1. Every agent has ONE job — never combine responsibilities
2. main.py contains ONLY FastAPI routing — zero business logic
3. All journal rules live in rules/*.json — never hardcode in agents
4. Always validate file type AND size before processing
5. Always handle both PDF and DOCX inputs
6. Output is always a .docx file — never return plain text only
7. Frontend MUST show loading state — pipeline takes 40–50 seconds
8. Compliance report MUST have per-section scores — not just overall
9. Never hardcode API keys — always use .env + os.getenv()
10. Every tool function must have try/except with meaningful error messages

---

## 🎯 EVALUATION CRITERIA ALIGNMENT

| Criteria | Weight | How We Score High |
|----------|--------|------------------|
| Style guide accuracy | 30% | Pre-built precise rules JSON + LLM verification |
| Working demo | 30% | Live upload → format → download in ~45 seconds |
| Presentation + Mentor engagement | 20% | Show Paperpal product knowledge + internship pitch |
| Tech scalability | 20% | Modular agents, new journal = new JSON file only |

> **PS explicitly says:** Even partial steps are evaluated equally.
> Build and demo in this order: Ingest → Parse → Interpret → Transform → Validate

---

## 💬 INTERNSHIP PITCH (say this to mentors)

> "Paperpal currently checks and suggests fixes. Our agent auto-transforms the entire document and outputs a submission-ready .docx. This could be a new 'Auto-Format' feature inside Paperpal — one click, fully formatted paper."

> "We used Paperpal's manuscript check and preflight features before building this. We noticed the gap: the tool tells you what's wrong but doesn't fix it automatically. That's exactly what Agent Paperpal solves."

---

## 🏁 BUILD THIS IN ORDER (36–48 hours)

```
Hour 0–2:   Setup repo, install deps, create folder structure
Hour 2–6:   tools/pdf_reader.py + tools/docx_reader.py
Hour 6–8:   rules/apa7.json + rules/ieee.json
Hour 8–10:  tools/rule_loader.py
Hour 10–14: agents/ingest_agent.py + agents/parse_agent.py
Hour 14–18: agents/interpret_agent.py
Hour 18–24: agents/transform_agent.py + tools/docx_writer.py
Hour 24–28: agents/validate_agent.py
Hour 28–30: crew.py (assemble all agents)
Hour 30–34: backend/main.py (FastAPI endpoints)
Hour 34–40: frontend (React components)
Hour 40–44: Full integration testing with real papers
Hour 44–48: UI polish + pitch prep + use Paperpal product
```
