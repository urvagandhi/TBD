# 🎨 STEP 6 — Build Complete React Frontend
# Agent Paperpal | frontend/src/
# Paste this entire prompt into Claude IDE Extension

---

## 📌 CONTEXT — READ EVERYTHING BEFORE WRITING CODE

You are building the **complete React frontend** for Agent Paperpal.
The backend is fully working at `http://localhost:8000`.
Your job is to build a clean, demo-ready UI that connects to it.

---

## 🏗️ CURRENT PROJECT STATE

```
frontend/
├── src/
│   ├── App.jsx                    ← ⬅️ MAIN APP — BUILD THIS
│   ├── index.css                  ← ⬅️ GLOBAL STYLES — BUILD THIS
│   └── components/
│       ├── Upload.jsx             ← ⬅️ STEP 1 UI
│       ├── ProcessingLoader.jsx   ← ⬅️ LOADING STATE
│       ├── ComplianceScore.jsx    ← ⬅️ SCORE DASHBOARD
│       ├── ChangesList.jsx        ← ⬅️ CHANGES LIST
│       └── IMRADCheck.jsx         ← ⬅️ IMRAD STRUCTURE DISPLAY
├── package.json                   ← DONE
├── vite.config.js                 ← DONE
└── tailwind.config.js             ← DONE
```

### Backend API (already running)
```
Base URL: http://localhost:8000

GET  /health
→ { status, supported_journals: ["APA 7th Edition", "IEEE", ...] }

POST /format  (multipart/form-data)
→ Body: file (PDF/DOCX) + journal (string)
→ Response: { success, download_url, compliance_report, changes_made, processing_time_seconds }
→ Takes: 40–60 seconds

GET /download/{filename}
→ Returns: .docx file binary
```

---

## ⚙️ TECH STACK

```
React 18 (functional components + hooks only)
TailwindCSS (utility classes only — no custom CSS framework)
Axios (HTTP client)
Lucide React (icons)
No Redux — use useState/useContext only
No React Router — single page, state-driven views
```

---

## 🎨 DESIGN DIRECTION

```
Theme:     Dark (background: #0a0a0f)
Accent:    Electric Blue (#3b82f6) + Purple (#8b5cf6)
Font:      Monospace for code/labels, Sans-serif for body
Feel:      Professional AI tool — clean, technical, trustworthy
NOT:       Flashy animations, purple gradient on white, generic SaaS look

Color System:
  bg-primary:    #0a0a0f   (page background)
  bg-card:       #111827   (card background)
  bg-card-dark:  #0f172a   (darker card)
  border:        #1f2937   (default border)
  text-primary:  #f1f5f9   (headings)
  text-muted:    #94a3b8   (body text)
  text-dim:      #64748b   (labels, captions)
  accent-blue:   #3b82f6
  accent-purple: #8b5cf6
  success:       #22c55e
  warning:       #f59e0b
  danger:        #ef4444

Score Color Rules:
  score >= 90 → #22c55e (green)
  score >= 70 → #f59e0b (yellow/amber)
  score < 70  → #ef4444 (red)
```

---

## 📱 APP STATES (State Machine)

The entire app is ONE page with these exclusive states:

```
"idle"       → Show upload form
"loading"    → Show pipeline progress (40-60 sec)
"success"    → Show compliance dashboard + download
"error"      → Show error message + retry button
```

State transitions:
```
idle → loading     (user clicks Format button)
loading → success  (API returns 200)
loading → error    (API returns 4xx/5xx OR network timeout)
success → idle     (user clicks "Format Another Paper")
error → idle       (user clicks "Try Again")
```

---

## 📄 FILE 1: src/App.jsx

### Full App Structure

```jsx
// App.jsx manages:
// 1. Global app state (idle/loading/success/error)
// 2. API calls (health check on mount, format on submit)
// 3. State data (file, journal, result, error)
// 4. Renders correct component based on state

import { useState, useEffect } from "react"
import axios from "axios"
import Upload from "./components/Upload"
import ProcessingLoader from "./components/ProcessingLoader"
import ComplianceScore from "./components/ComplianceScore"
import ChangesList from "./components/ChangesList"
import IMRADCheck from "./components/IMRADCheck"

const API_BASE = "http://localhost:8000"
const FORMAT_TIMEOUT_MS = 120_000  // 2 minutes max wait
```

### State Variables
```jsx
const [appState, setAppState] = useState("idle")  // "idle"|"loading"|"success"|"error"
const [file, setFile] = useState(null)
const [journal, setJournal] = useState("")
const [journals, setJournals] = useState([])    // from /health
const [result, setResult] = useState(null)      // API success response
const [error, setError] = useState(null)        // { message, code, step }
const [loadingStep, setLoadingStep] = useState(0)  // current pipeline step index
```

### On Mount: Fetch Supported Journals
```jsx
useEffect(() => {
  // Fetch supported journals from /health
  // If backend is down, use hardcoded fallback
  const fetchJournals = async () => {
    try {
      const res = await axios.get(`${API_BASE}/health`, { timeout: 5000 })
      setJournals(res.data.supported_journals || FALLBACK_JOURNALS)
    } catch {
      setJournals(FALLBACK_JOURNALS)  // never block UI on this failure
    }
  }
  fetchJournals()
}, [])

const FALLBACK_JOURNALS = [
  "APA 7th Edition",
  "IEEE",
  "Vancouver",
  "Springer",
  "Chicago 17th Edition"
]
```

### handleFormat Function
```jsx
const handleFormat = async () => {
  // Guard: must have file and journal
  if (!file || !journal) return

  setAppState("loading")
  setLoadingStep(0)
  setError(null)
  setResult(null)

  // Advance loading step every ~10 seconds
  // Pipeline: Ingest(10s) → Parse(10s) → Interpret(2s) → Transform(15s) → Validate(10s)
  const stepTimings = [10000, 10000, 2000, 15000, 10000]
  let stepIndex = 0
  const stepInterval = setInterval(() => {
    stepIndex++
    if (stepIndex < 5) setLoadingStep(stepIndex)
    else clearInterval(stepInterval)
  }, stepTimings[stepIndex] || 10000)

  try {
    const formData = new FormData()
    formData.append("file", file)
    formData.append("journal", journal)

    const response = await axios.post(
      `${API_BASE}/format`,
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: FORMAT_TIMEOUT_MS,
      }
    )

    clearInterval(stepInterval)
    setResult(response.data)
    setAppState("success")

  } catch (err) {
    clearInterval(stepInterval)

    // Parse error response carefully
    let errorObj = {
      message: "An unexpected error occurred. Please try again.",
      code: "unknown_error",
      step: null,
    }

    if (err.code === "ECONNABORTED") {
      errorObj = {
        message: "Request timed out after 2 minutes. The paper may be too large or complex.",
        code: "timeout",
        step: null,
      }
    } else if (err.code === "ERR_NETWORK" || err.message === "Network Error") {
      errorObj = {
        message: "Cannot connect to the backend server. Make sure it is running on port 8000.",
        code: "network_error",
        step: null,
      }
    } else if (err.response) {
      const detail = err.response.data?.detail || err.response.data
      if (typeof detail === "object") {
        errorObj = {
          message: detail.message || "Processing failed.",
          code: detail.error || `http_${err.response.status}`,
          step: detail.step || null,
        }
      } else {
        errorObj = {
          message: String(detail),
          code: `http_${err.response.status}`,
          step: null,
        }
      }
    }

    setError(errorObj)
    setAppState("error")
  }
}

const handleReset = () => {
  setAppState("idle")
  setFile(null)
  setJournal("")
  setResult(null)
  setError(null)
  setLoadingStep(0)
}
```

### Download Handler
```jsx
const handleDownload = () => {
  if (!result?.download_url) return
  // Open in new tab — browser handles DOCX download
  window.open(`${API_BASE}${result.download_url}`, "_blank")
}
```

### App Layout (JSX)
```jsx
return (
  <div className="min-h-screen" style={{ background: "#0a0a0f", color: "#f1f5f9" }}>

    {/* Header — always visible */}
    <header style={{ borderBottom: "1px solid #1f2937", padding: "16px 24px" }}>
      <div style={{ maxWidth: "900px", margin: "0 auto", display: "flex", alignItems: "center", gap: "12px" }}>
        <span style={{ fontSize: "28px" }}>🤖</span>
        <div>
          <div style={{ fontSize: "18px", fontWeight: "800", letterSpacing: "-0.5px" }}>
            Agent Paperpal
          </div>
          <div style={{ fontSize: "12px", color: "#64748b", fontFamily: "monospace" }}>
            HackaMined 2026 · Cactus Communications
          </div>
        </div>
        {appState === "success" && (
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{
              background: "#052e16",
              border: "1px solid #22c55e",
              borderRadius: "20px",
              padding: "4px 12px",
              fontSize: "12px",
              color: "#22c55e",
              fontWeight: "700"
            }}>
              ✓ Formatted in {result?.processing_time_seconds}s
            </div>
          </div>
        )}
      </div>
    </header>

    {/* Main Content */}
    <main style={{ maxWidth: "900px", margin: "0 auto", padding: "32px 24px" }}>

      {appState === "idle" && (
        <Upload
          file={file}
          setFile={setFile}
          journal={journal}
          setJournal={setJournal}
          journals={journals}
          onSubmit={handleFormat}
        />
      )}

      {appState === "loading" && (
        <ProcessingLoader
          currentStep={loadingStep}
          journal={journal}
          filename={file?.name}
        />
      )}

      {appState === "error" && (
        <ErrorDisplay error={error} onRetry={handleReset} />
      )}

      {appState === "success" && result && (
        <SuccessView
          result={result}
          onDownload={handleDownload}
          onReset={handleReset}
        />
      )}

    </main>
  </div>
)
```

### ErrorDisplay Component (inline in App.jsx)
```jsx
function ErrorDisplay({ error, onRetry }) {
  return (
    <div style={{ textAlign: "center", padding: "60px 20px" }}>
      <div style={{ fontSize: "48px", marginBottom: "16px" }}>❌</div>
      <div style={{ fontSize: "20px", fontWeight: "700", color: "#ef4444", marginBottom: "8px" }}>
        Processing Failed
      </div>
      <div style={{
        background: "#1f0a0a",
        border: "1px solid #ef4444",
        borderRadius: "12px",
        padding: "16px 24px",
        maxWidth: "560px",
        margin: "0 auto 24px",
        fontSize: "14px",
        color: "#fca5a5",
        lineHeight: "1.6"
      }}>
        {error?.message}
        {error?.step && (
          <div style={{ marginTop: "8px", fontSize: "12px", color: "#ef4444", fontFamily: "monospace" }}>
            Failed at step: {error.step}
          </div>
        )}
      </div>
      <button onClick={onRetry} style={{
        background: "#1e3a5f",
        border: "1px solid #3b82f6",
        color: "#60a5fa",
        padding: "10px 28px",
        borderRadius: "8px",
        cursor: "pointer",
        fontSize: "14px",
        fontWeight: "700"
      }}>
        ← Try Again
      </button>
    </div>
  )
}
```

### SuccessView Component (inline in App.jsx)
```jsx
function SuccessView({ result, onDownload, onReset }) {
  const { compliance_report, changes_made } = result
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>

      {/* Download Banner */}
      <div style={{
        background: "linear-gradient(135deg, #052e16, #0f2e1a)",
        border: "1px solid #22c55e",
        borderRadius: "16px",
        padding: "20px 24px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "12px"
      }}>
        <div>
          <div style={{ fontSize: "16px", fontWeight: "800", color: "#22c55e" }}>
            ✅ Paper Formatted Successfully
          </div>
          <div style={{ fontSize: "13px", color: "#86efac", marginTop: "4px" }}>
            Reformatted to comply with {compliance_report?.breakdown ? "journal standards" : "selected style"}
          </div>
        </div>
        <div style={{ display: "flex", gap: "10px" }}>
          <button
            onClick={onDownload}
            style={{
              background: "#22c55e",
              border: "none",
              color: "#000",
              padding: "10px 24px",
              borderRadius: "8px",
              cursor: "pointer",
              fontSize: "14px",
              fontWeight: "800"
            }}
          >
            ⬇ Download .docx
          </button>
          <button
            onClick={onReset}
            style={{
              background: "transparent",
              border: "1px solid #374151",
              color: "#94a3b8",
              padding: "10px 18px",
              borderRadius: "8px",
              cursor: "pointer",
              fontSize: "14px"
            }}
          >
            Format Another
          </button>
        </div>
      </div>

      {/* Score Dashboard */}
      <ComplianceScore report={compliance_report} />

      {/* IMRAD Check */}
      {compliance_report?.imrad_check && (
        <IMRADCheck imrad={compliance_report.imrad_check} />
      )}

      {/* Changes List */}
      {changes_made?.length > 0 && (
        <ChangesList changes={changes_made} />
      )}

      {/* Recommendations */}
      {compliance_report?.recommendations?.length > 0 && (
        <RecommendationsCard recs={compliance_report.recommendations} />
      )}

    </div>
  )
}

function RecommendationsCard({ recs }) {
  return (
    <div style={{
      background: "#111827",
      border: "1px solid #1f2937",
      borderRadius: "16px",
      padding: "20px 24px"
    }}>
      <div style={{ fontSize: "14px", fontWeight: "700", color: "#f59e0b", marginBottom: "12px" }}>
        💡 Recommendations
      </div>
      {recs.map((rec, i) => (
        <div key={i} style={{
          display: "flex",
          gap: "10px",
          padding: "8px 0",
          borderBottom: i < recs.length - 1 ? "1px solid #1f2937" : "none",
          fontSize: "13px",
          color: "#94a3b8"
        }}>
          <span style={{ color: "#f59e0b", flexShrink: 0 }}>→</span>
          <span>{rec}</span>
        </div>
      ))}
    </div>
  )
}
```

---

## 📄 FILE 2: src/components/Upload.jsx

### Complete Spec

```
Layout:
  ┌────────────────────────────────────────┐
  │  Upload Your Research Paper            │
  │  (subtitle text)                       │
  │                                        │
  │  ┌──────────────────────────────────┐  │
  │  │  Drag & drop PDF or DOCX here   │  │
  │  │          OR                     │  │
  │  │     [Browse File]               │  │
  │  │                                 │  │
  │  │  ✅ selected_paper.pdf (0.8 MB) │  │ ← when file selected
  │  └──────────────────────────────────┘  │
  │                                        │
  │  Select Target Journal Style:          │
  │  [APA 7th Edition          ▼]          │
  │                                        │
  │  [▶ Format My Paper]  ← disabled until both selected
  └────────────────────────────────────────┘
```

### Drag & Drop Logic
```jsx
// Handle dragover — prevent default to allow drop
// Handle drop — extract file from dataTransfer.files[0]
// Handle dragenter — set isDragging state (visual feedback)
// Handle dragleave — clear isDragging state
// Validate file type on drop (only accept pdf/docx)
// If wrong file type dropped → show inline error, don't set file

const ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
]
const ALLOWED_EXTENSIONS = [".pdf", ".docx"]

// Validation:
const isValidFile = (f) => {
  const name = f.name.toLowerCase()
  return ALLOWED_EXTENSIONS.some(ext => name.endsWith(ext))
}
```

### File Size Display
```jsx
// Show human-readable file size
const formatFileSize = (bytes) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Warn if file is large (>5MB) — not an error, just a notice
// "Large files take longer to process (~60 seconds)"
```

### Journal Dropdown
```jsx
// journals prop = array from /health or fallback
// If journals is empty (still loading) → show "Loading journals..." disabled option
// Show a check icon next to selected journal
// First option = "Select a journal style..." (placeholder, disabled)
```

### Submit Button States
```jsx
// DISABLED: file not selected OR journal not selected
// DISABLED: visual = bg-gray-800, cursor-not-allowed
// ENABLED:  file selected AND journal selected
// ENABLED:  visual = blue gradient, hover effect, cursor-pointer
// Show helper text below: "Processing takes ~45 seconds"
```

### Edge Cases
```
- User drops a .txt or .jpg file → show inline error: "Only PDF and DOCX files accepted"
- User drops multiple files → only use the first one, ignore rest
- User selects file > 10MB → show inline warning (but still allow — server validates)
- File input: clicking "Browse File" button triggers hidden <input type="file">
- File name too long (>40 chars) → truncate with ellipsis in display
- journals array empty → show skeleton/placeholder rows in dropdown
- Clear file: show ✕ button on selected file row to deselect
```

---

## 📄 FILE 3: src/components/ProcessingLoader.jsx

### Complete Spec

```
Layout:
  ┌────────────────────────────────────────┐
  │         ⚙️  (spinning)                 │
  │                                        │
  │    Formatting your paper...            │
  │    Applying APA 7th Edition rules      │
  │                                        │
  │  ① Reading document          ✓ done   │
  │  ② Detecting structure       ✓ done   │
  │  ③ Loading journal rules     ⟳ active │
  │  ④ Applying formatting       ○ pending│
  │  ⑤ Validating compliance     ○ pending│
  │                                        │
  │    ●●●●●○○○○○  (progress bar)          │
  │                                        │
  │    "This typically takes 40–60 sec"    │
  └────────────────────────────────────────┘
```

### Pipeline Steps Definition
```jsx
const PIPELINE_STEPS = [
  {
    id: 0,
    label: "Reading document",
    sublabel: "Extracting text from your PDF/DOCX",
    icon: "📄",
    duration: 10,  // approximate seconds
  },
  {
    id: 1,
    label: "Detecting structure",
    sublabel: "Identifying title, abstract, sections, citations",
    icon: "🔍",
    duration: 12,
  },
  {
    id: 2,
    label: "Loading journal rules",
    sublabel: "Fetching formatting requirements",
    icon: "📋",
    duration: 3,
  },
  {
    id: 3,
    label: "Applying formatting",
    sublabel: "Fixing fonts, headings, citations, references",
    icon: "🔧",
    duration: 18,
  },
  {
    id: 4,
    label: "Validating compliance",
    sublabel: "Running 7 quality checks, generating score",
    icon: "✅",
    duration: 12,
  },
]
```

### Step Status Logic
```jsx
// Based on currentStep prop from App.jsx:
// step.id < currentStep  → status: "done"   (show ✓ green)
// step.id === currentStep → status: "active" (show spinning indicator)
// step.id > currentStep  → status: "pending" (show ○ grey)
```

### Progress Bar
```jsx
// Progress = (currentStep / 4) * 100 → percentage
// Smooth animated transition using CSS transition
// Color: blue → fills from left to right
```

### Elapsed Timer
```jsx
// Show live elapsed time: "0:12 elapsed"
// Use useEffect + setInterval to increment every second
// Start timer when component mounts
// Clear interval on unmount
```

### Edge Cases
```
- currentStep stays at 4 (last step) for a long time → animation still looks active
- Component unmounts (success/error) → must clearInterval to prevent memory leak
- Show gentle message after 60s: "Taking longer than usual. Large papers take more time..."
```

---

## 📄 FILE 4: src/components/ComplianceScore.jsx

### Complete Spec

```
Layout:
  ┌────────────────────────────────────────┐
  │  Compliance Score              78/100  │
  │  ██████████████████░░░░  78%           │
  │                                        │
  │  ✅ Document Format    ████████ 100    │
  │  ✅ Headings           ████████ 100    │
  │  ⚠️  Abstract           ██████░░  88   │
  │     → 253 words — 3 over APA limit    │
  │  ⚠️  Citations          █████░░░  85   │
  │     → 1 orphan citation found         │
  │  ⚠️  References         ████░░░░  80   │
  │     → Wei et al. 2021 never cited     │
  │  ❌  Figures            ███░░░░░  70   │
  │     → Figure 2 missing                │
  │  ✅ Tables             ████████ 100    │
  │                                        │
  │  ┌──────────────────────────────────┐  │
  │  │  NOT SUBMISSION READY            │  │ ← if score < 80
  │  │  Score needs to reach 80+        │  │
  │  └──────────────────────────────────┘  │
  └────────────────────────────────────────┘
```

### Props
```jsx
// ComplianceScore({ report })
// report = compliance_report from API response
// report.overall_score = integer 0-100
// report.breakdown = { document_format: {score, issues}, ... }
// report.submission_ready = boolean
```

### Section Display Order (always in this order)
```jsx
const SECTION_ORDER = [
  { key: "document_format", label: "Document Format", icon: "📄" },
  { key: "abstract",        label: "Abstract",         icon: "📝" },
  { key: "headings",        label: "Headings",          icon: "🔤" },
  { key: "citations",       label: "Citations",         icon: "🔗" },
  { key: "references",      label: "References",        icon: "📚" },
  { key: "figures",         label: "Figures",           icon: "🖼️" },
  { key: "tables",          label: "Tables",            icon: "📊" },
]
```

### Score Color + Icon Logic
```jsx
const getScoreColor = (score) => {
  if (score >= 90) return "#22c55e"   // green
  if (score >= 70) return "#f59e0b"   // amber
  return "#ef4444"                    // red
}

const getScoreIcon = (score) => {
  if (score >= 90) return "✅"
  if (score >= 70) return "⚠️"
  return "❌"
}
```

### Overall Score Display
```jsx
// Large number display: e.g. "78"
// Color based on score
// Subtext: "Submission Ready" (green) or "Needs Improvement" (amber/red)
// Big progress bar below the score number
```

### Section Row Spec
```jsx
// Each section row:
// [icon] [label]    [bar fills to score%]    [score/100]
// Issues listed below row in smaller text, indented, amber color
// If no issues → don't show issues div at all
// Bar width animates from 0 → score% on mount (CSS transition)
```

### Submission Ready Banner
```jsx
// If submission_ready = true:
//   Green banner: "✅ Submission Ready — Score meets 80+ threshold"
// If submission_ready = false:
//   Amber banner: "📋 Not Yet Submission Ready — Resolve issues below to reach 80+"
```

### Edge Cases
```
- report is null/undefined → show skeleton loader (grey bars)
- breakdown section has score but no issues array → render with empty issues
- breakdown section missing entirely → show "N/A" for that section
- overall_score = 0 → show red, not blank
- overall_score = 100 → show special "Perfect!" label
- issues array is very long (10+ issues) → show first 3, "Show X more" toggle
- score bar animation: use CSS transition on width, triggered by useEffect on mount
```

---

## 📄 FILE 5: src/components/ChangesList.jsx

### Complete Spec

```
Layout:
  ┌────────────────────────────────────────┐
  │  🔧 Changes Applied (14)               │
  │                                        │
  │  → Font changed: Arial → Times New Roman│
  │  → 14 citations reformatted to APA     │
  │  → References reordered alphabetically │
  │  → H1 headings: centered + bold applied│
  │  → Abstract label: bold + centered     │
  │  → Figure captions moved below figure  │
  │  ...                                   │
  │                                        │
  │  [Show all 14 changes ▼]               │ ← if > 6
  └────────────────────────────────────────┘
```

### Props
```jsx
// ChangesList({ changes })
// changes = string[] from compliance_report.changes_made
```

### Collapse Logic
```jsx
// If changes.length <= 6 → show all, no toggle
// If changes.length > 6  → show first 6, then "Show X more" button
// Toggle expands to show all
// Toggle text: "Show X more" → "Show less"
```

### Change Item Styling
```jsx
// Each change:
// [→ green arrow] [change text in muted color]
// Subtle hover: slightly lighter background
// Monospace font for technical change descriptions
```

### Edge Cases
```
- changes is empty array → don't render component at all (return null)
- changes is null/undefined → return null
- Very long change string (> 100 chars) → wrap naturally, don't truncate
- changes has duplicate strings → render all (don't deduplicate)
```

---

## 📄 FILE 6: src/components/IMRADCheck.jsx

### Complete Spec

```
Layout:
  ┌──────────────────────────────────────────────────┐
  │  📐 IMRAD Structure Check                         │
  │                                                  │
  │  ✅ Introduction  ✅ Methods  ✅ Results  ❌ Discussion │
  │                                                  │
  │  ⚠️  Discussion section not detected.            │
  │     Consider adding a Discussion/Conclusion section │
  └──────────────────────────────────────────────────┘
```

### Props
```jsx
// IMRADCheck({ imrad })
// imrad = { introduction: bool, methods: bool, results: bool, discussion: bool,
//           imrad_complete: bool, missing_sections: [str] }
```

### Display
```jsx
const IMRAD_LABELS = {
  introduction: "Introduction",
  methods: "Methods",
  results: "Results",
  discussion: "Discussion"
}

// Each section: green pill if true, red pill if false
// If imrad_complete → show green "Complete IMRAD structure detected" banner
// If !imrad_complete → list missing_sections with recommendation
```

### Edge Cases
```
- imrad is null → return null
- All four are true → show compact green banner only (no pills needed)
- missing_sections is empty but imrad_complete is false → fallback to checking booleans
```

---

## 📄 FILE 7: src/index.css

```css
/* Global resets and base styles */

*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: #0a0a0f;
  color: #f1f5f9;
  -webkit-font-smoothing: antialiased;
}

/* Score bar animation */
.score-bar-fill {
  transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Drag zone active state */
.drag-active {
  border-color: #3b82f6 !important;
  background: #1e3a5f20 !important;
}

/* Spinning animation for loader */
@keyframes spin {
  to { transform: rotate(360deg); }
}
.spin {
  animation: spin 1s linear infinite;
}

/* Pulse animation for active pipeline step */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.pulse {
  animation: pulse 1.5s ease-in-out infinite;
}

/* Fade in on mount */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.fade-in {
  animation: fadeIn 0.3s ease-out forwards;
}

/* Scrollbar styling for dark theme */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #111827; }
::-webkit-scrollbar-thumb { background: #374151; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #4b5563; }
```

---

## 🔌 API INTEGRATION REFERENCE

### All API Calls in the App

```javascript
// 1. Health check (on mount)
GET http://localhost:8000/health
Response: {
  status: "ok",
  supported_journals: ["APA 7th Edition", "IEEE", "Vancouver", "Springer", "Chicago 17th Edition"],
  max_file_size_mb: 10
}

// 2. Format document (on submit)
POST http://localhost:8000/format
Body: FormData { file: File, journal: string }
Timeout: 120,000ms (2 minutes)
Response 200: {
  success: true,
  request_id: "a1b2c3d4",
  download_url: "/download/formatted_abc123.docx",
  compliance_report: {
    overall_score: 78,
    breakdown: {
      document_format: { score: 100, issues: [] },
      abstract: { score: 88, issues: ["253 words — 3 over limit"] },
      headings: { score: 100, issues: [] },
      citations: { score: 85, issues: ["1 orphan citation found"] },
      references: { score: 80, issues: ["Wei et al. 2021 never cited"] },
      figures: { score: 70, issues: ["Figure 2 missing"] },
      tables: { score: 100, issues: [] }
    },
    imrad_check: {
      introduction: true, methods: true,
      results: true, discussion: false,
      imrad_complete: false,
      missing_sections: ["discussion"]
    },
    citation_consistency: {
      orphan_citations: ["(Johnson, 2019)"],
      uncited_references: ["Wei et al. 2021"]
    },
    changes_made: ["Font: Arial → Times New Roman", "..."],
    submission_ready: false,
    recommendations: ["Add a Discussion section"]
  },
  changes_made: ["Font: Arial → Times New Roman", "..."],
  processing_time_seconds: 47.3
}
Response 422: {
  detail: {
    error: "unsupported_journal",
    message: "Journal 'Nature' not found...",
    step: "interpret"
  }
}

// 3. Download (on button click)
GET http://localhost:8000/download/formatted_abc123.docx
→ Browser downloads .docx file
→ Use window.open(url, "_blank") to trigger download
```

---

## ⚠️ GLOBAL FRONTEND RULES

```
1. No class components — functional only
2. No Redux — useState/useContext only
3. No React Router — single page, state-driven
4. All styles using inline style objects or Tailwind classes
5. No <form> tags — use onClick handlers
6. axios for all API calls — not fetch()
7. Every useEffect with interval/timer MUST return cleanup function
8. Never show raw error objects to user — always show human-readable messages
9. Loading state MUST be shown — pipeline takes 40-60 seconds
10. Download URL must prepend API_BASE — "/download/..." is relative
11. All components receive data via props — no direct API calls in children
12. Console.log is OK during dev — do not remove, helps with debugging
```

---

## ✅ FINAL CHECKLIST

```
App.jsx:
  □ Fetches journals from /health on mount (with fallback)
  □ All 4 states handled: idle/loading/success/error
  □ handleFormat clears intervals on both success and error
  □ Error parsing handles: timeout, network error, 422, 500
  □ handleReset clears ALL state variables
  □ handleDownload uses window.open with full API_BASE URL

Upload.jsx:
  □ Drag & drop works (dragover, drop, dragenter, dragleave)
  □ File type validated on drop AND on input change
  □ Wrong file type shows inline error (not alert())
  □ File size shown in human-readable format
  □ Large file (>5MB) shows soft warning
  □ Submit button disabled until file + journal selected
  □ Clear file (✕) button works

ProcessingLoader.jsx:
  □ All 5 pipeline steps shown with correct status
  □ Timer increments every second (clearInterval on unmount)
  □ Progress bar animates smoothly
  □ Long wait message appears after 60s

ComplianceScore.jsx:
  □ Null/undefined report shows skeleton
  □ Score bars animate from 0 to value on mount
  □ All 7 sections always shown (even if missing = N/A)
  □ Issues collapsed if > 3 per section
  □ Submission ready banner shown correctly

ChangesList.jsx:
  □ Returns null for empty/null changes
  □ Shows first 6, toggle for rest
  □ Toggle text updates correctly

IMRADCheck.jsx:
  □ Returns null for null imrad
  □ Green/red pills per section
  □ Missing sections listed clearly

index.css:
  □ spin, pulse, fadeIn, score-bar-fill animations defined
  □ drag-active class for drop zone highlight
  □ Dark scrollbar styles
```
