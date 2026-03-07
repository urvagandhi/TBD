import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import Upload from './components/Upload'
import ProgressScreen from './components/ProgressScreen'
import ResultsScreen from './components/ResultsScreen'
import SemiCustomPanel from './components/SemiCustomPanel'

// Prevent browser from restoring scroll position on refresh
if (typeof window !== 'undefined') {
  history.scrollRestoration = 'manual'
  window.scrollTo(0, 0)
}

const API = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

// ─── SVG Icon Set ────────────────────────────────────────────
const Icons = {
  logo: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <rect x="4" y="2" width="16" height="20" rx="3" fill="currentColor" opacity="0.15"/>
      <path d="M8 7h8M8 11h8M8 15h5" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  ),
  file: (
    <svg width="28" height="28" fill="none" viewBox="0 0 24 24">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/>
      <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.8"/>
    </svg>
  ),
  journals: (
    <svg width="28" height="28" fill="none" viewBox="0 0 24 24">
      <path d="M4 19.5A2.5 2.5 0 016.5 17H20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" stroke="currentColor" strokeWidth="1.8"/>
    </svg>
  ),
  chart: (
    <svg width="28" height="28" fill="none" viewBox="0 0 24 24">
      <path d="M18 20V10M12 20V4M6 20v-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  ),
  bolt: (
    <svg width="28" height="28" fill="none" viewBox="0 0 24 24">
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/>
    </svg>
  ),
  upload: (
    <svg width="28" height="28" fill="none" viewBox="0 0 24 24">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <polyline points="17 8 12 3 7 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1="12" y1="3" x2="12" y2="15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  ),
  ai: (
    <svg width="28" height="28" fill="none" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8"/>
      <path d="M12 2v3M12 19v3M3.22 5.64l2.12 2.12M18.66 16.24l2.12 2.12M2 12h3M19 12h3M3.22 18.36l2.12-2.12M18.66 7.76l2.12-2.12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  ),
  download: (
    <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      <polyline points="7 10 12 15 17 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  ),
  check: (
    <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
      <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  arrow: (
    <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
      <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  user: (
    <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
      <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      <circle cx="12" cy="7" r="4" stroke="currentColor" strokeWidth="2"/>
    </svg>
  ),
  lock: (
    <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
      <rect x="3" y="11" width="18" height="11" rx="2" stroke="currentColor" strokeWidth="2"/>
      <path d="M7 11V7a5 5 0 0110 0v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  ),
  error: (
    <svg width="28" height="28" fill="none" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.8"/>
      <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  )
}

const FEATURES = [
  { icon: Icons.file,     iconClass: 'fi-blue',   title: 'PDF & DOCX Input',     desc: 'Upload any research paper up to 10MB. We preserve every word.' },
  { icon: Icons.journals, iconClass: 'fi-orange',  title: '5 Journal Styles',     desc: 'APA 7th, IEEE, Vancouver, Springer & Chicago — built in.' },
  { icon: Icons.chart,    iconClass: 'fi-blue',   title: 'Compliance Score',     desc: 'Section-by-section accuracy score from 0–100.' },
  { icon: Icons.bolt,     iconClass: 'fi-orange',  title: 'Sub-60 Second Speed', desc: 'Gemini 3 Flash runs 5 AI agents in parallel for fast results.' }
]

const STEPS = [
  { icon: Icons.upload, title: 'Upload Your Paper',    desc: 'Drop a PDF or DOCX. We extract every section, heading, and citation.' },
  { icon: Icons.ai,     title: 'AI Agents Format It',  desc: '5 Gemini agents fix fonts, headings, citations, and references.' },
  { icon: Icons.download,title: 'Download & Submit',  desc: 'Get a Word document formatted to your journal — ready to submit.' }
]

// Observer hook for scroll animations
function useVisible(threshold = 0.15) {
  const ref = useRef(null)
  const [vis, setVis] = useState(false)
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setVis(true); obs.disconnect() } }, { threshold })
    if (ref.current) obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])
  return [ref, vis]
}

// ─── Category icon map for breakdown cards ───────────────────
const CATEGORY_ICONS = {
  abstract: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/>
      <path d="M14 2v6h6M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  ),
  citations: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <path d="M10 11h-4a1 1 0 01-1-1V6a1 1 0 011-1h3a1 1 0 011 1v5zm0 0a4 4 0 01-4 4M20 11h-4a1 1 0 01-1-1V6a1 1 0 011-1h3a1 1 0 011 1v5zm0 0a4 4 0 01-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  references: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <path d="M4 19.5A2.5 2.5 0 016.5 17H20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" stroke="currentColor" strokeWidth="1.8"/>
    </svg>
  ),
  headings: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <path d="M4 12h8M4 6v12M12 6v12M20 8v8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  ),
  document_format: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.8"/>
      <path d="M3 9h18M9 21V9" stroke="currentColor" strokeWidth="1.8"/>
    </svg>
  ),
}

const CATEGORY_LABELS = {
  abstract: 'Abstract',
  citations: 'Citations',
  references: 'References',
  headings: 'Headings',
  document_format: 'Document Format',
}

// ─── Pre-Check Gauge Component ────────────────────────────────
function PreCheckGauge({ trustScore, onFormat, onBack }) {
  const [animatedScore, setAnimatedScore] = useState(0)
  const score = trustScore.total_score || 0

  // Count-up animation
  useEffect(() => {
    setAnimatedScore(0)
    const duration = 1200
    const start = performance.now()
    const animate = (now) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setAnimatedScore(Math.round(eased * score))
      if (progress < 1) requestAnimationFrame(animate)
    }
    requestAnimationFrame(animate)
  }, [score])

  // SVG circle math
  const radius = 90
  const circumference = 2 * Math.PI * radius
  const strokeOffset = circumference - (animatedScore / 100) * circumference

  // Color thresholds
  const gaugeColor = score < 40 ? 'var(--error)' : score <= 70 ? 'var(--orange)' : 'var(--success)'
  const gaugeBg = score < 40 ? 'var(--error-bg)' : score <= 70 ? 'var(--orange-light)' : 'var(--success-bg)'
  const message = score < 40
    ? 'Significant changes needed'
    : score <= 70
    ? 'Moderate compliance'
    : 'Well structured paper'

  const breakdown = trustScore.breakdown || {}
  const categories = ['abstract', 'citations', 'references', 'headings', 'document_format']

  return (
    <>
      {/* Circular Gauge */}
      <div className="gauge-container">
        <svg className="gauge-svg" viewBox="0 0 200 200">
          {/* Background circle */}
          <circle
            cx="100" cy="100" r={radius}
            fill="none"
            stroke="var(--border)"
            strokeWidth="12"
          />
          {/* Score arc */}
          <circle
            cx="100" cy="100" r={radius}
            fill="none"
            stroke={gaugeColor}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeOffset}
            transform="rotate(-90 100 100)"
            style={{ transition: 'stroke-dashoffset 0.05s linear' }}
          />
        </svg>
        <div className="gauge-center">
          <span className="gauge-number" style={{ color: gaugeColor }}>{animatedScore}</span>
          <span className="gauge-label">/ 100</span>
        </div>
      </div>

      {/* Status message */}
      <div className="gauge-message" style={{ background: gaugeBg, color: gaugeColor }}>
        {message}
      </div>

      {/* Category Breakdown Cards */}
      <div className="category-breakdown">
        <h3 className="category-breakdown-title">Category Breakdown</h3>
        <div className="category-cards">
          {categories.map(key => {
            const val = breakdown[key]
            if (!val) return null
            const catScore = val.score ?? 0
            const barColor = catScore >= 80 ? 'var(--success)' : catScore >= 60 ? 'var(--orange)' : 'var(--error)'
            const icon = CATEGORY_ICONS[key] || CATEGORY_ICONS.document_format
            const label = CATEGORY_LABELS[key] || key.replace(/_/g, ' ')
            return (
              <div key={key} className="category-card">
                <div className="category-card-header">
                  <span className="category-card-icon" style={{ color: barColor }}>{icon}</span>
                  <span className="category-card-label">{label}</span>
                  <span className="category-card-score" style={{ color: barColor }}>{catScore}</span>
                </div>
                <div className="category-bar-track">
                  <div className="category-bar-fill" style={{ width: `${catScore}%`, background: barColor }} />
                </div>
                {val.issue && (
                  <p className="category-card-issue">{val.issue}</p>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* CTA Buttons */}
      <div className="pre-check-actions">
        <button className="btn-primary" style={{ width: 'auto', padding: '14px 32px', margin: 0 }} onClick={onFormat}>
          Format My Paper {Icons.arrow}
        </button>
        <button className="btn-secondary" onClick={onBack}>
          ← Edit Overrides
        </button>
      </div>
    </>
  )
}

// ─── Shutter Transition ───────────────────────────────────────
function Shutter({ onDone }) {
  useEffect(() => { const t = setTimeout(onDone, 1100); return () => clearTimeout(t) }, [])
  return (
    <div className="shutter-wrap">
      <div className="shutter-panel left" />
      <div className="shutter-panel right" />
    </div>
  )
}

// ─── Soda Bubbles ──────────────────────────────────────────────
const BUBBLES = [
  { size:8,  left:'8%',  riseDur:'10s', wobbleDur:'3.1s', delay:'0s'   },
  { size:14, left:'16%', riseDur:'14s', wobbleDur:'4.2s', delay:'2s'   },
  { size:6,  left:'25%', riseDur:'9s',  wobbleDur:'2.8s', delay:'1.2s' },
  { size:20, left:'35%', riseDur:'16s', wobbleDur:'5s',   delay:'0.5s' },
  { size:10, left:'44%', riseDur:'11s', wobbleDur:'3.5s', delay:'3.5s' },
  { size:7,  left:'52%', riseDur:'8s',  wobbleDur:'2.5s', delay:'1.8s' },
  { size:18, left:'60%', riseDur:'15s', wobbleDur:'4.8s', delay:'0.8s' },
  { size:9,  left:'68%', riseDur:'12s', wobbleDur:'3.7s', delay:'4s'   },
  { size:24, left:'75%', riseDur:'18s', wobbleDur:'6s',   delay:'2.2s' },
  { size:12, left:'82%', riseDur:'13s', wobbleDur:'4s',   delay:'0.3s' },
  { size:6,  left:'89%', riseDur:'9s',  wobbleDur:'2.9s', delay:'1.5s' },
  { size:16, left:'93%', riseDur:'14s', wobbleDur:'4.3s', delay:'3s'   },
  { size:11, left:'5%',  riseDur:'12s', wobbleDur:'3.9s', delay:'5s'   },
  { size:8,  left:'30%', riseDur:'10s', wobbleDur:'3.2s', delay:'6s'   },
  { size:22, left:'48%', riseDur:'17s', wobbleDur:'5.5s', delay:'4.5s' },
  { size:7,  left:'57%', riseDur:'8s',  wobbleDur:'2.7s', delay:'7s'   },
  { size:13, left:'72%', riseDur:'13s', wobbleDur:'4.1s', delay:'2.7s' },
  { size:28, left:'87%', riseDur:'18s', wobbleDur:'6.2s', delay:'1s'   },
]
function Bubbles() {
  return (
    <div className="bubbles">
      {BUBBLES.map((b, i) => (
        <span key={i} className="bubble" style={{
          width: b.size, height: b.size, left: b.left,
          animationDuration: `${b.riseDur}, ${b.wobbleDur}`,
          animationDelay: `${b.delay}, ${b.delay}`,
        }} />
      ))}
    </div>
  )
}

// ─── Scroll Section Progress (left sidebar) ───────────────────────
const SECTIONS = [
  { id: 'hero',     label: 'Home' },
  { id: 'features', label: 'Features' },
  { id: 'how',      label: 'How It Works' },
]
function ScrollProgress() {
  const [active, setActive] = useState('hero')
  useEffect(() => {
    const observers = SECTIONS.map(({ id }) => {
      const el = document.getElementById(id)
      if (!el) return null
      const obs = new IntersectionObserver(
        ([e]) => { if (e.isIntersecting) setActive(id) },
        { threshold: 0.2, rootMargin: '0px 0px -10% 0px' }
      )
      obs.observe(el)
      return obs
    })
    return () => observers.forEach(o => o?.disconnect())
  }, [])

  return (
    <div className="scroll-progress">
      {SECTIONS.map((s, i) => {
        const isActive = active === s.id
        return (
          <div key={s.id} className="sp-item">
            {i > 0 && (
              <div className={`sp-connector ${SECTIONS.findIndex(x => x.id === active) >= i ? 'lit' : ''}`} />
            )}
            <div
              className={`sp-dot ${isActive ? 'active' : ''}`}
              onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior:'smooth' })}
              title={s.label}
            />
            <span className={`sp-label ${isActive ? 'lit' : ''}`}>{s.label}</span>
          </div>
        )
      })}
    </div>
  )
}


// ─── Navbar ──────────────────────────────────────────
 function Navbar({ view, onNav }) {
  const isLanding  = view === 'landing'
  const isToolView = ['tool','loading','success','error'].includes(view)
  return (
    <nav className="navbar">
      <div className="container">
        <div className="navbar-inner">
          <div className="navbar-logo" style={{ cursor:'pointer' }} onClick={() => onNav('landing')}>
            <div className="logo-mark" style={{ display:'flex', alignItems:'center', justifyContent:'center', color:'#fff' }}>
              {Icons.logo}
            </div>
            Agent Paperpal
          </div>

          <div className="navbar-links">
            {isLanding && <>
              <button className="nav-link" onClick={() => document.getElementById('features')?.scrollIntoView({ behavior:'smooth' })}>Features</button>
              <button className="nav-link" onClick={() => document.getElementById('how')?.scrollIntoView({ behavior:'smooth' })}>How It Works</button>
            </>}
            {isToolView && (
              <button className="nav-link" onClick={() => onNav('landing')}>← Home</button>
            )}
          </div>

          <div className="navbar-actions">
            <span className="nav-badge">HackaMined 2026</span>
            {isLanding && (
              <button className="navbar-cta" onClick={() => onNav('tool')}>Get Started Free</button>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}

// ─── Landing Page ─────────────────────────────────────────────
function Landing({ onGetStarted }) {
  const [featRef, featVis] = useVisible()
  const [howRef, howVis]   = useVisible(0.2)
  return (
    <>
      <ScrollProgress />
      {/* HERO */}
      <section className="hero" id="hero">
        {/* Orange curtain that sweeps UP before content loads */}
        <div className="hero-curtain">
          <div className="hero-curtain-inner">
            <span>Agent Paperpal</span>
            <div className="hero-curtain-bar" />
          </div>
        </div>
        <div className="hero-bg">
          <div className="grid-overlay" />
          <div className="hero-blob blob-orange" />
          <div className="hero-blob blob-orange" style={{ animationDelay:'-4s', animationDuration:'12s', bottom:'-200px', top:'auto', right:'auto', left:'-200px', opacity:0.07 }} />
          <Bubbles />
        </div>
        <div className="container">
          <div className="hero-inner">
            <div className="hero-pill">
              <span className="pill-dot" />
              AI-Powered Academic Formatter
            </div>
            <h1 className="hero-title">
              Your Research Paper.<br />
              <span className="gradient-blue">Journal-Ready</span>{' '}
              <span className="gradient-orange">in 60s.</span>
            </h1>
            <p className="hero-sub">
              Upload a PDF or DOCX, choose your target journal style, and let 5 AI agents handle every formatting rule — from fonts to citations to references.
            </p>
            <div className="hero-actions">
              <button className="btn-cta-blue" onClick={onGetStarted}>
                Get Started Free {Icons.arrow}
              </button>
              <button className="btn-outline" onClick={() => document.getElementById('how')?.scrollIntoView({ behavior:'smooth' })}>
                See How It Works
              </button>
            </div>
            <div className="hero-demo">
              <div className="demo-card">
                <div className="demo-score-badge">94</div>
                <div className="demo-tag">
                  {Icons.check} APA 7th Edition
                </div>
                <div className="demo-lines">
                  {[70,95,55,80,45].map((w, i) => <div key={i} className="demo-line" style={{ width:`${w}%` }} />)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="features" id="features">
        <div className="container">
          <div className="features-grid" ref={featRef}>
            {FEATURES.map((f, i) => (
              <div key={f.title} className={`feature-card ${featVis ? 'visible' : ''}`} style={{ animationDelay:`${i*0.1}s` }}>
                <div className={`feature-icon-wrap ${f.iconClass}`}>{f.icon}</div>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="how-it-works" id="how">
        <div className="container">
          <div className="section-eyebrow">How It Works</div>
          <h2 className="section-title">Three Steps to Publication</h2>
          <p className="section-sub">No manual reformatting. No style guide hunting. Just upload and download.</p>
          <div className="steps-row" ref={howRef}>
            {STEPS.map((s, i) => (
              <div key={s.title} className={`step ${howVis ? 'visible' : ''}`} style={{ animationDelay:`${i*0.18}s` }}>
                <div className="step-circle">
                  {s.icon}
                  <span className="step-num-badge">{i+1}</span>
                </div>
                <h4>{s.title}</h4>
                <p>{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  )
}



// ─── Journal metadata ─────────────────────────────────────────
const JOURNAL_META = [
  { id:'APA 7th Edition', label:'APA 7th Edition', updated:'Jan 2024' },
  { id:'IEEE',            label:'IEEE',             updated:'Mar 2024' },
  { id:'Vancouver',       label:'Vancouver',        updated:'Feb 2024' },
  { id:'Springer',        label:'Springer',         updated:'Feb 2024' },
  { id:'Chicago',         label:'Chicago',           updated:'Feb 2024' },
]

const MODES = [
  {
    id: 'standard',
    label: 'Standard',
    desc: 'Apply predefined journal rules as-is',
    icon: (
      <svg width="22" height="22" fill="none" viewBox="0 0 24 24">
        <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
        <rect x="9" y="3" width="6" height="4" rx="1.5" stroke="currentColor" strokeWidth="1.8"/>
        <path d="M9 12h6M9 16h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    id: 'semi_custom',
    label: 'Semi Custom',
    desc: 'Journal rules + your own adjustments',
    icon: (
      <svg width="22" height="22" fill="none" viewBox="0 0 24 24">
        <path d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    id: 'full_custom',
    label: 'Full Custom',
    desc: 'Upload your own guidelines document',
    icon: (
      <svg width="22" height="22" fill="none" viewBox="0 0 24 24">
        <path d="M4 16l4-4 4 4 4-8 4 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
        <circle cx="18" cy="6" r="2" stroke="currentColor" strokeWidth="1.8"/>
      </svg>
    ),
  },
]

// ─── Main App ──────────────────────────────────────────
export default function App() {
  // View state
  const [view,         setView]         = useState('landing')

  // Upload state
  const [file,         setFile]         = useState(null)
  const [docId,        setDocId]        = useState(null)
  const [uploadInfo,   setUploadInfo]   = useState(null) // { filename, word_count, char_count, file_type }
  const [uploading,    setUploading]    = useState(false)

  // Mode & config state
  const [selectedMode, setSelectedMode] = useState('standard')
  const [journal,      setJournal]      = useState('')
  const [overrides,    setOverrides]    = useState({})
  const [guidelineFile, setGuidelineFile] = useState(null)
  const [customRules,   setCustomRules]   = useState(null)
  const [extracting,    setExtracting]    = useState(false)

  // Pipeline state
  const [jobId,        setJobId]        = useState(null)

  // Results state
  const [result,       setResult]       = useState(null)
  const [error,        setError]        = useState('')
  const [trustScore,   setTrustScore]   = useState(null)
  const [downloading,  setDownloading]  = useState(false)
  const [dlType,       setDlType]       = useState('doc')

  // ── File upload → POST /upload ──────────────────────────────
  const handleFileSelect = async (f) => {
    setFile(f)
    if (!f) {
      setDocId(null)
      setUploadInfo(null)
      return
    }

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', f)
      const res = await axios.post(`${API}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000,
      })
      const data = res.data
      setDocId(data.doc_id)
      setUploadInfo({
        filename: data.filename,
        word_count: data.word_count,
        char_count: data.char_count,
        file_type: data.file_type,
        size_kb: data.size_kb,
      })
    } catch (err) {
      const detail = err.response?.data?.detail
      const msg = typeof detail === 'object' ? detail.error : detail || err.message
      setError(msg || 'Upload failed.')
      setFile(null)
      setDocId(null)
      setUploadInfo(null)
    } finally {
      setUploading(false)
    }
  }

  // ── Extract rules from guideline (full_custom) ─────────────
  const extractCustomRules = async () => {
    if (!guidelineFile) return null
    setExtracting(true)
    try {
      const fd = new FormData()
      fd.append('guideline_file', guidelineFile)
      const res = await axios.post(`${API}/extract-rules`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      })
      const rules = res.data.rules
      setCustomRules(rules)
      return rules
    } catch (err) {
      const detail = err.response?.data?.detail
      const msg = typeof detail === 'object' ? detail.error : detail || err.message
      throw new Error(msg || 'Failed to extract rules from guideline.')
    } finally {
      setExtracting(false)
    }
  }

  // ── Pre-check → POST /score/pre ────────────────────────────
  const handlePreCheck = async () => {
    if (!docId || !journal) return
    setView('pre-check')
    setTrustScore(null)
    try {
      // For full_custom, extract rules from guideline first
      let rules = customRules
      if (selectedMode === 'full_custom' && guidelineFile && !rules) {
        rules = await extractCustomRules()
      }

      const formData = new FormData()
      formData.append('doc_id', docId)
      formData.append('journal', journal)
      formData.append('mode', selectedMode)
      if (selectedMode === 'semi_custom' && Object.keys(overrides).length > 0) {
        formData.append('overrides', JSON.stringify(overrides))
      }
      if (selectedMode === 'full_custom' && rules) {
        formData.append('custom_rules', JSON.stringify(rules))
      }
      const res = await axios.post(`${API}/score/pre`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000,
      })
      setTrustScore(res.data.pre_format_score)
    } catch (err) {
      const detail = err.response?.data?.detail
      const msg = typeof detail === 'object' ? detail.error : detail || err.message
      setError(msg || 'Pre-check failed.')
      setView('error')
    }
  }

  // ── Format → POST /format (kick off, ProgressScreen handles polling) ──
  const handleFormat = async () => {
    setView('loading')
    setError('')
    try {
      const formData = new FormData()
      formData.append('doc_id', docId)
      formData.append('journal', journal)
      formData.append('mode', selectedMode)
      if (selectedMode === 'semi_custom' && Object.keys(overrides).length > 0) {
        formData.append('overrides', JSON.stringify(overrides))
      }
      if (selectedMode === 'full_custom' && customRules) {
        formData.append('custom_rules', JSON.stringify(customRules))
      }

      const res = await axios.post(`${API}/format`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000,
      })

      setJobId(res.data.job_id)
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data
      const msg = typeof detail === 'object'
        ? detail.error || JSON.stringify(detail)
        : detail || err.message || 'Pipeline failed. Please try again.'
      setError(msg)
      setView('error')
    }
  }

  // Called by ProgressScreen when pipeline completes
  const handlePipelineComplete = (data) => {
    setResult(normalizeResult(data))
    setView('success')
  }

  const handlePipelineError = (msg) => {
    setError(msg)
    setView('error')
  }

  // Normalize backend response to match what components expect
  const normalizeResult = (data) => {
    const report = data.compliance_report || {}
    if (data.changes_made && data.changes_made.length > 0) {
      report.changes_made = data.changes_made
    }
    const fr = data.formatting_report || {}
    report.applied_transformations = fr.done || report.changes_made || []
    report.skipped_transformations = fr.not_done_by_user_choice || []
    report.manual_action_required = fr.needs_manual_attention || []

    return {
      processing_time_seconds: data.processing_time_seconds || 0,
      download_url: data.download_url,
      preview_url: data.preview_url || null,
      compliance_report: report,
      post_format_score: data.post_format_score || null,
    }
  }

  const handleDownload = async (type = 'doc') => {
    if (!result?.download_url) return
    setDownloading(true); setDlType(type)
    try {
      const url  = `${API}${result.download_url}${type === 'pdf' ? '?format=pdf' : ''}`
      const res  = await axios.get(url, { responseType:'blob' })
      const mime = type === 'pdf'
        ? 'application/pdf'
        : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      const blob = new Blob([res.data], { type: mime })
      const href = window.URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = href; a.setAttribute('download', `formatted_paper.${type === 'pdf' ? 'pdf' : 'docx'}`)
      document.body.appendChild(a); a.click(); a.remove()
      window.URL.revokeObjectURL(href)
    } catch { alert('Download failed.') }
    finally { setDownloading(false) }
  }

  const resetToTool = () => {
    setView('tool'); setFile(null); setDocId(null); setUploadInfo(null)
    setJournal(''); setResult(null); setError('')
    setTrustScore(null); setSelectedMode('standard'); setOverrides({})
    setGuidelineFile(null); setCustomRules(null); setJobId(null)
  }

  const handleNav = (target) => {
    if (target === 'landing') {
      resetToTool()
      setView('landing')
    } else setView(target)
  }

  const isToolView = ['tool','pre-check','loading','success','error'].includes(view)
  const journalOk = selectedMode === 'full_custom' ? true : !!journal
  const canSubmit = !!docId && journalOk && !uploading && !extracting
    && (selectedMode !== 'full_custom' || !!guidelineFile)

  return (
    <div className="app">
      <Navbar view={view} onNav={handleNav} />

      {/* ── LANDING ── */}
      {view === 'landing' && <Landing onGetStarted={() => setView('tool')} />}

      {/* ── TOOL: Upload + Mode + Journal + Submit ── */}
      {view === 'tool' && (
        <div className="tool-page">
          <div className="container">
            <div className="tool-header">
              <h2>Format Your Paper</h2>
              <p>Upload your document, choose your target format, and let Gemini AI handle the rest.</p>
            </div>
            <div className="tool-card">

              {/* Step 1: File Upload */}
              <Upload
                file={file} setFile={handleFileSelect}
                journal={journal} setJournal={setJournal}
                journals={JOURNAL_META.map(j => j.id)}
                onSubmit={handlePreCheck}
                hideJournalSelect
              />

              {/* Upload status indicator */}
              {uploading && (
                <div style={{ textAlign:'center', padding:'12px 0', color:'var(--text-secondary)', fontSize:'0.85rem' }}>
                  <div className="loading-orbit" style={{ width:28, height:28, margin:'0 auto 8px' }}>
                    <div className="orbit-center" style={{ width:6, height:6 }} />
                    <div className="orbit-dot" style={{ width:4, height:4 }} />
                  </div>
                  Uploading and extracting text...
                </div>
              )}

              {/* Upload confirmation */}
              {uploadInfo && !uploading && (
                <div style={{
                  background:'var(--bg-soft)', border:'1.5px solid var(--success)',
                  borderRadius:'var(--radius)', padding:'12px 16px', marginTop:8,
                  display:'flex', alignItems:'center', justifyContent:'space-between', gap:12,
                  fontSize:'0.85rem',
                }}>
                  <span style={{ display:'flex', alignItems:'center', gap:8, color:'var(--success)' }}>
                    {Icons.check} {uploadInfo.filename}
                  </span>
                  <span style={{ color:'var(--text-secondary)' }}>
                    {uploadInfo.word_count.toLocaleString()} words · {uploadInfo.file_type.toUpperCase()} · {uploadInfo.size_kb} KB
                  </span>
                </div>
              )}

              {/* Upload error */}
              {error && view === 'tool' && (
                <div style={{
                  background:'rgba(239,68,68,0.08)', border:'1.5px solid var(--error)',
                  borderRadius:'var(--radius)', padding:'12px 16px', marginTop:8,
                  fontSize:'0.85rem', color:'var(--error)',
                }}>
                  {error}
                </div>
              )}


              {/* Step 2: Journal Selection — hidden in Full Custom (guidelines replace preset) */}
              {selectedMode !== 'full_custom' ? (
                <div className="step-box">
                  <label className="form-label" style={{ marginBottom:12, display:'block' }}>Target Format</label>
                  {JOURNAL_META.map(j => (
                    <label
                      key={j.id}
                      className={`journal-option-row ${journal === j.id ? 'selected' : ''}`}
                      style={{ marginBottom:8 }}
                    >
                      <span style={{ display:'flex', alignItems:'center' }}>
                        <input
                          type="radio" name="journal" value={j.id}
                          checked={journal === j.id}
                          onChange={() => setJournal(j.id)}
                        />
                        <span className="journal-label">{j.label}</span>
                      </span>
                      {j.updated && (
                        <span className="journal-updated">Updated {j.updated}</span>
                      )}
                    </label>
                  ))}
                </div>
              ) : (
                <div className="step-box" style={{
                  background: 'var(--orange-light)',
                  border: '1.5px solid rgba(249,115,22,0.3)',
                  display: 'flex', alignItems: 'flex-start', gap: 12,
                }}>
                  <span style={{ fontSize: '1.4rem', lineHeight: 1 }}>📄</span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--orange)', marginBottom: 4 }}>
                      Full Custom — Journal Format Not Required
                    </div>
                    <div style={{ fontSize: '0.82rem', color: '#c05a0e', lineHeight: 1.5 }}>
                      Your uploaded guidelines document will define all formatting rules.
                      No journal preset will be applied.
                    </div>
                  </div>
                </div>
              )}


              {/* Step 3: Mode Selection */}
              {(journal || selectedMode === 'full_custom') && (
                <div className="step-box">
                  <label className="form-label" style={{ marginBottom: 14, display: 'block' }}>
                    Formatting Mode
                  </label>

                  <div className="mode-cards-grid">
                    {MODES.map(m => (
                      <button
                        key={m.id}
                        className={`mode-card${selectedMode === m.id ? ' mode-card--selected' : ''}`}
                        onClick={() => setSelectedMode(m.id)}
                        type="button"
                      >
                        {/* Animated checkmark — only visible when selected */}
                        <span className="mode-card__check">
                          <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                            <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                          </svg>
                        </span>

                        {/* Icon circle */}
                        <div className="mode-card__icon">{m.icon}</div>

                        {/* Label */}
                        <div className="mode-card__label">{m.label}</div>

                        {/* Description */}
                        <div className="mode-card__desc">{m.desc}</div>
                      </button>
                    ))}
                  </div>

                  {/* Semi Custom: Structured override controls */}
                  {selectedMode === 'semi_custom' && (
                    <div style={{ marginTop: 14 }}>
                      <SemiCustomPanel
                        journal={journal}
                        overrides={overrides}
                        onChange={setOverrides}
                      />
                    </div>
                  )}

                  {/* Full Custom: Guidelines PDF upload */}
                  {selectedMode === 'full_custom' && (
                    <div style={{ marginTop: 14 }}>
                      <label className="form-label" style={{ marginBottom: 8, display: 'block', fontSize: '0.85rem' }}>
                        Upload Guidelines Document
                      </label>
                      <div
                        style={{
                          border: '2px dashed var(--border)', borderRadius: 'var(--radius)',
                          padding: '20px', textAlign: 'center', cursor: 'pointer',
                          background: guidelineFile ? 'rgba(34,197,94,0.05)' : 'transparent',
                          borderColor: guidelineFile ? 'var(--success)' : 'var(--border)',
                        }}
                        onClick={() => document.getElementById('guideline-upload')?.click()}
                      >
                        <input
                          id="guideline-upload"
                          type="file"
                          accept=".pdf,.docx,.txt"
                          style={{ display: 'none' }}
                          onChange={(e) => {
                            const f = e.target.files[0]
                            if (f) setGuidelineFile(f)
                          }}
                        />
                        {guidelineFile ? (
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                            <span style={{ color: 'var(--success)' }}>{Icons.check}</span>
                            <span>{guidelineFile.name}</span>
                            <button
                              style={{ background: 'none', border: 'none', color: 'var(--error)', cursor: 'pointer', fontSize: '0.82rem' }}
                              onClick={(e) => { e.stopPropagation(); setGuidelineFile(null) }}
                            >
                              Remove
                            </button>
                          </div>
                        ) : (
                          <>
                            <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                              Drop your guidelines PDF/DOCX here, or click to browse
                            </p>
                            <div className="format-pills" style={{ marginTop: 8, justifyContent: 'center' }}>
                              <span className="format-pill">PDF</span>
                              <span className="format-pill">DOCX</span>
                              <span className="format-pill">TXT</span>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}


              {/* Submit */}
              <button
                className="btn-primary"
                onClick={handlePreCheck}
                disabled={!canSubmit}
                style={{ marginTop:24 }}
              >
                Check Compliance Score {Icons.arrow}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── PRE-CHECK: Compliance Score with Circular Gauge ── */}
      {view === 'pre-check' && (
        <div className="pre-check-wrap">
          <div className="pre-check-card">
            <span className="pre-check-tag">Compliance Check</span>
            <h2>Current Compliance Score</h2>
            <p>
              Your document was analyzed against <strong>{journal}</strong> formatting rules.
            </p>

            {!trustScore ? (
              <div style={{ margin: '32px 0', textAlign: 'center', padding: '40px 0' }}>
                <div className="loading-orbit" style={{ width: 48, height: 48, margin: '0 auto 16px' }}>
                  <div className="orbit-center" style={{ width: 10, height: 10 }} />
                  <div className="orbit-dot" style={{ width: 6, height: 6 }} />
                </div>
                <p style={{ color: 'var(--text-secondary)' }}>
                  {extracting ? 'Extracting rules from your guidelines...' : 'Analyzing your document...'}
                </p>
              </div>
            ) : (
              <PreCheckGauge trustScore={trustScore} onFormat={handleFormat} onBack={() => setView('tool')} />
            )}
          </div>
        </div>
      )}

      {/* ── LOADING: Pipeline Progress ── */}
      {view === 'loading' && jobId && (
        <ProgressScreen
          jobId={jobId}
          journal={journal}
          filename={uploadInfo?.filename}
          onComplete={handlePipelineComplete}
          onError={handlePipelineError}
        />
      )}

      {/* ── SUCCESS: Results ── */}
      {view === 'success' && result && (
        <ResultsScreen
          result={result}
          trustScore={trustScore}
          onDownload={handleDownload}
          downloading={downloading}
          dlType={dlType}
          onReset={resetToTool}
        />
      )}

      {/* ── ERROR ── */}
      {view === 'error' && (
        <div className="container">
          <div className="error-card">
            <div className="error-icon">{Icons.error}</div>
            <div className="error-title">Something went wrong</div>
            <div className="error-msg">{error}</div>
            <button className="btn-secondary" onClick={resetToTool}>Try Again</button>
          </div>
        </div>
      )}

      <footer className="footer">
        <div className="container">
          Built for <span className="accent">HackaMined 2026</span> ·{' '}
          <span className="accent-blue">Agent Paperpal</span> · Powered by Gemini 3 Flash
        </div>
      </footer>
    </div>
  )
}
