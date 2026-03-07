# Agent Paperpal — Frontend

> React 19 + Vite 7 + TailwindCSS 4 — standalone web interface for autonomous manuscript formatting.

The frontend is a single-page application that guides users through a multi-step manuscript formatting workflow: upload a paper, select a journal style, choose a formatting mode, view a pre-format compliance score, watch real-time pipeline progress, and download the formatted document with a detailed compliance report. Features a landing page with scroll animations, a TipTap-based live document editor, and before/after compliance score comparison.

---

## Table of Contents

- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Technology Stack](#technology-stack)
- [Components](#components)
- [Application Flow](#application-flow)
- [API Integration](#api-integration)
- [Styling & Design System](#styling--design-system)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Running](#running)
- [Build & Deploy](#build--deploy)

---

## Architecture

The app is a **state-machine SPA** — all routing is managed via React `useState` (no React Router). The `App.jsx` component orchestrates 6 view states:

```
landing → tool → pre-check → loading → success
                                     → error
```

### State Machine

| View | Description |
|------|-------------|
| `landing` | Hero section, features grid, "How It Works" steps, sticky navbar |
| `tool` | Multi-step form: Upload → Journal → Mode → Submit |
| `pre-check` | Animated circular gauge + 5-category breakdown + "Format My Paper" CTA |
| `loading` | 4-step pipeline progress with polling, typewriter text, confetti on completion |
| `success` | 2-column results: document preview (left) + compliance score (right) |
| `error` | Error message with "Try Again" button |

---

## Directory Structure

```
frontend/
├── src/
│   ├── components/                  # 14 React components
│   │   ├── Upload.jsx               # Drag-and-drop file upload zone (104 lines)
│   │   ├── ProgressScreen.jsx       # Real-time pipeline progress with polling (326 lines)
│   │   ├── ResultsScreen.jsx        # 2-column results layout (406 lines)
│   │   ├── SemiCustomPanel.jsx      # 13-field journal override config (369 lines)
│   │   ├── GuidelinesUpload.jsx     # Custom PDF guidelines upload (159 lines)
│   │   ├── LiveDocumentEditor.jsx   # TipTap rich-text editor for preview (169 lines)
│   │   ├── ComplianceScore.jsx      # Circular score gauge component (67 lines)
│   │   ├── ProcessingLoader.jsx     # Legacy 5-step Lucide icon loader (167 lines)
│   │   ├── ChangesList.jsx          # Numbered changes list (26 lines)
│   │   ├── ViolationsDetected.jsx   # Expandable violations display (111 lines)
│   │   ├── IMRADCheck.jsx           # IMRAD structure check pills (72 lines)
│   │   ├── OverrideChips.jsx        # Override parser chips (144 lines)
│   │   └── TransformationReport.jsx # Accordion report sections (88 lines)
│   │
│   ├── App.jsx                      # Root component: state machine + all views (1020 lines)
│   ├── index.css                    # Design tokens + 50+ animations + layout (500+ lines)
│   └── main.jsx                     # React DOM entry point
│
├── public/                          # Static assets (vite.svg)
├── package.json                     # Dependencies + scripts
├── vite.config.js                   # Vite + React plugin
├── tailwind.config.js               # Tailwind theme (dark mode class, custom animations)
├── postcss.config.js                # PostCSS + Tailwind + Autoprefixer
├── eslint.config.js                 # ESLint 9 + React hooks + React Refresh
├── .env                             # Backend URL config
├── .env.example                     # Environment template
└── index.html                       # HTML entry point
```

---

## Technology Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 19.2.0 | UI component library |
| React DOM | 19.2.0 | DOM rendering |
| Vite | 7.3.1 | Dev server (HMR) + production build |
| TailwindCSS | 4.2.1 | Utility-first CSS framework |
| Axios | 1.13.6 | HTTP client for backend API |
| TipTap | 3.20.1 | Headless rich-text editor (document preview editing) |
| Tippy.js | 6.3.7 | Tooltip popups for violation details |
| ESLint | 9.39.1 | Code linting with React hooks rules |
| Autoprefixer | 10.4.27 | CSS vendor prefixes |

---

## Components

### App.jsx (Root — 1020 lines)

The main orchestrator. Contains:
- **18 inline SVG icon definitions** (logo, file, journals, chart, bolt, upload, AI, download, check, arrow, user, lock, error)
- **Landing page** with hero, scroll-triggered animations, bubbles particle system, features grid, "How It Works" section
- **Tool view** with multi-step form (upload → journal → mode → submit)
- **Pre-check screen** with animated count-up gauge and category breakdown
- **Shutter transition** (orange panels sweeping away between views)
- **Scroll progress sidebar** (fixed left, showing vertical scroll position)
- **Sticky navbar** with glass effect

### Upload.jsx

Drag-and-drop file upload zone.
- Accepts PDF and DOCX (max 10 MB)
- File info display (name, size)
- Shake animation on invalid drops
- Remove button to clear selection

### ProgressScreen.jsx

Real-time pipeline progress while the backend formats.
- 4-step pipeline visualization with icons
- Typewriter text effect for the active step name
- Progress bar (0-100%)
- Elapsed time counter
- Confetti particle animation on completion
- Polls `/format/status/{jobId}` every 2 seconds
- Long-wait warning after 90 seconds
- Auto-fetches result after completion

### ResultsScreen.jsx

Two-column results display (desktop) / tabbed view (mobile).
- **Left column**: Live document preview (iframe or TipTap editor)
- **Right column**: Before/after compliance gauges, delta badge, automation bar, section breakdown, formatting report tabs (Done / Your Overrides / Manual Action)
- Download dropdown (DOCX/PDF)
- Edit/Stop Edit toggle for live preview
- "New Paper" CTA

### SemiCustomPanel.jsx

Journal override configuration for semi-custom mode.
- 13 overridable fields (font, size, spacing, margins, alignment, headings, references, figure/table captions)
- Fetches defaults from `/journal-defaults/{journal}`
- Active overrides summary with chips
- Reset to Default button

### GuidelinesUpload.jsx

Upload a custom journal guidelines PDF for full-custom mode.
- PDF file picker with size display
- Loading indicator during extraction

### LiveDocumentEditor.jsx

TipTap-based rich-text document editor.
- Renders `documentStructure` (title, authors, abstract, sections)
- Highlights violations with `violation-mark` spans
- Tippy.js tooltips with "Apply Fix" / "Ignore" buttons
- Contenteditable toggle

### ComplianceScore.jsx

Circular SVG progress gauge.
- Animated stroke-dashoffset fill
- Color-coded thresholds (green >=80, orange 60-79, red <60)
- Status text

### Other Components

| Component | Purpose |
|-----------|---------|
| `ProcessingLoader.jsx` | Legacy 5-step loader with Lucide icons |
| `ChangesList.jsx` | Numbered list of applied changes with staggered fade-in |
| `ViolationsDetected.jsx` | Expandable violation rows with category color coding |
| `IMRADCheck.jsx` | IMRAD structure pills (green=present, red=missing) |
| `OverrideChips.jsx` | Textarea-based override parser with applied/blocked chips |
| `TransformationReport.jsx` | Accordion with Done/Skipped/User Action sections |

---

## Application Flow

```
1. LANDING PAGE
   - Animated hero with bubbles particle system
   - Feature cards (staggered scroll-reveal)
   - "How It Works" 3-step guide
   - "Get Started" CTA → navigates to tool

2. TOOL PAGE
   a) File Upload (drag-drop or click)
   b) Journal Selection (APA, IEEE, Vancouver, Springer, Chicago, Custom)
   c) Formatting Mode
      - Standard (use journal defaults)
      - Semi-Custom (edit 13 overridable fields via SemiCustomPanel)
      - Full-Custom (upload guidelines PDF via GuidelinesUpload)
   d) Submit → POST /upload → POST /score/pre

3. PRE-CHECK SCREEN
   - Animated circular gauge (count-up 0 → score)
   - Status message ("Significant changes needed" / "Moderate" / "Well structured")
   - 5-category breakdown (abstract, headings, citations, references, document)
   - "Format My Paper" CTA → POST /format
   - "Edit Overrides" back button

4. LOADING SCREEN (ProgressScreen)
   - 4-step pipeline with typewriter labels
   - Progress bar (0-100%)
   - Elapsed timer
   - Polls GET /format/status/{jobId} every 2 seconds
   - Confetti on completion
   - Auto-fetch result via GET /format/result/{jobId}

5. RESULTS SCREEN
   - Before/After compliance gauges with delta badge
   - Document preview (iframe or TipTap editor)
   - Section breakdown bars
   - Formatting report tabs (Done / Overrides / Manual)
   - Download (DOCX/PDF)
   - "New Paper" button

6. ERROR SCREEN
   - Error message display
   - "Try Again" button (resets to tool)
```

---

## API Integration

**Backend Base URL**: `import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'`

All HTTP calls use Axios. Timeouts: 30s default, 60s for rule extraction.

| Method | Endpoint | Purpose | Timeout |
|--------|----------|---------|---------|
| POST | `/upload` | Upload file, get `doc_id` | 30s |
| POST | `/extract-rules` | Extract rules from custom PDF | 60s |
| POST | `/score/pre` | Pre-format compliance score | 30s |
| GET | `/journal-defaults/{journal}` | Fetch overridable field defaults | 30s |
| POST | `/format` | Start async formatting pipeline | 30s |
| GET | `/format/status/{jobId}` | Poll pipeline progress (every 2s) | 30s |
| GET | `/format/result/{jobId}` | Fetch completed results | 30s |
| GET | `/download/{filepath}?format=pdf` | Download DOCX/PDF (blob) | 30s |
| POST | `/rebuild-docx` | Rebuild DOCX from edited HTML | 30s |

**Error Handling**: Catches `err.response?.data?.detail` (string or object), falls back to `err.message` or generic message.

---

## Styling & Design System

### Design Tokens (index.css)

```css
--bg: #ffffff            /* White background */
--bg-soft: #F8FAFF       /* Very light blue */
--bg-muted: #F1F5FF      /* Light blue */
--primary: #2563EB       /* Blue */
--orange: #F97316        /* Orange (brand accent) */
--text: #0F172A          /* Dark text */
--text-secondary: #475569 /* Gray text */
--success: #10B981       /* Green */
--error: #EF4444         /* Red */
--warning: #F59E0B       /* Amber */
--radius: 16px           /* Card border radius */
--radius-sm: 10px        /* Button border radius */
--radius-pill: 999px     /* Pill border radius */
--font: 'Outfit', sans-serif  /* Google Fonts */
```

### Theme

Light mode with white backgrounds, dark text, blue/orange accents. Color coding: green (success), orange (warning/pending), red (error).

### Animations (50+ CSS keyframes)

- `fadeUp` — Slide up + fade in on scroll reveal
- `slideDown` — Slide down + fade
- `bubbleRise` — Hero particle system
- `blobMove` — Background blob animation
- `shimmer` — Skeleton loading shimmer
- `fill-bar` — Progress bar fill
- `countUp` — Number counter animation
- `confetti` — Completion celebration
- Staggered `animation-delay` for sequential reveals

### Tailwind Config

- Dark mode: `"class"` (available but not active)
- Extended colors: `gray-950: "#0a0a0f"`
- Custom animations: `shimmer`, `fill-bar`, `fade-in`
- Content: `./index.html`, `./src/**/*.{js,ts,jsx,tsx}`

### Icons

All icons are **inline SVG definitions** in `App.jsx` (18 SVGs). No external icon library in the main flow. `lucide-react` is used only in legacy components (`ProcessingLoader`, `ViolationsDetected`, `IMRADCheck`).

---

## Installation

### Prerequisites

- Node.js 18+
- npm

### Steps

```bash
cd frontend
npm install
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_BACKEND_URL` | No | `http://localhost:8000` | Backend API base URL |

Access in code: `import.meta.env.VITE_BACKEND_URL`

---

## Running

### Development (HMR)

```bash
npm run dev
```

Opens at **http://localhost:5173**. Hot Module Replacement enabled via `@vitejs/plugin-react`.

### Lint

```bash
npm run lint
```

ESLint 9 with React hooks and React Refresh rules. Warns on unused vars (except capitalized/underscore-prefixed).

---

## Build & Deploy

### Production Build

```bash
npm run build       # Outputs to frontend/dist/
npm run preview     # Preview the production build locally
```

### Build Output

```
dist/
├── index.html
├── assets/
│   ├── index-<hash>.js    # Minified React bundle
│   └── index-<hash>.css   # Minified CSS (Tailwind + custom)
└── vite.svg
```

### Deploy

Serve the `dist/` directory via any static hosting (Vercel, Netlify, GitHub Pages, S3, etc.). Set `VITE_BACKEND_URL` to the production backend URL before building.

---

*Frontend — Agent Paperpal · HackaMined 2026*
