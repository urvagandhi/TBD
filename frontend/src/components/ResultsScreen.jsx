import { useState, useEffect, useRef, useCallback } from 'react'
import LiveDocumentEditor from './LiveDocumentEditor'

const API = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

// ── Edit icon ───────────────────────────────────────────────
const IconEdit = () => (
  <svg width="15" height="15" fill="none" viewBox="0 0 24 24">
    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <path d="M18.5 2.5a2.121 2.121 0 113 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

// ── Icons ────────────────────────────────────────────────────
const IconCheck = () => (
  <svg width="15" height="15" fill="none" viewBox="0 0 24 24">
    <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)
const IconGear = () => (
  <svg width="15" height="15" fill="none" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" stroke="currentColor" strokeWidth="1.5" />
  </svg>
)
const IconWarn = () => (
  <svg width="15" height="15" fill="none" viewBox="0 0 24 24">
    <path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)
const IconDownload = () => (
  <svg width="16" height="16" fill="none" viewBox="0 0 24 24">
    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <polyline points="7 10 12 15 17 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
)
const IconFile = () => (
  <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    <path d="M14 2v6h6M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
)

// ── Score Gauge (small, reusable) ────────────────────────────
function ScoreGauge({ score, label, size = 140 }) {
  const [animated, setAnimated] = useState(0)

  useEffect(() => {
    setAnimated(0)
    const duration = 1000
    const start = performance.now()
    const animate = (now) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setAnimated(Math.round(eased * score))
      if (progress < 1) requestAnimationFrame(animate)
    }
    requestAnimationFrame(animate)
  }, [score])

  const radius = size * 0.38
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (animated / 100) * circumference
  const color = score >= 80 ? 'var(--success)' : score >= 60 ? 'var(--orange)' : 'var(--error)'
  const center = size / 2

  return (
    <div className="rs-gauge">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={center} cy={center} r={radius} fill="none" stroke="var(--border)" strokeWidth="8" />
        <circle
          cx={center} cy={center} r={radius} fill="none"
          stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
          transform={`rotate(-90 ${center} ${center})`}
          style={{ transition: 'stroke-dashoffset 0.05s linear' }}
        />
      </svg>
      <div className="rs-gauge-center">
        <span className="rs-gauge-number" style={{ color, fontSize: size * 0.2 }}>{animated}</span>
        <span className="rs-gauge-unit">/100</span>
      </div>
      <p className="rs-gauge-label">{label}</p>
    </div>
  )
}

// ── Report Tab Content ───────────────────────────────────────
function ReportList({ items, emptyMsg, colorClass }) {
  if (!items || items.length === 0) {
    return <p className="rs-report-empty">{emptyMsg}</p>
  }
  return (
    <ul className="rs-report-list">
      {items.map((item, i) => (
        <li key={i} className={`rs-report-item ${colorClass}`} style={{ animationDelay: `${i * 0.05}s` }}>
          <span className="rs-report-dot" />
          <span>{typeof item === 'string' ? item : item.description || item.message || JSON.stringify(item)}</span>
        </li>
      ))}
    </ul>
  )
}

// ── Download Dropdown ────────────────────────────────────────
function DownloadDropdown({ onDownload, downloading, dlType }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handlePick = (type) => {
    setOpen(false)
    onDownload(type)
  }

  return (
    <div className="rs-dl-dropdown" ref={ref}>
      <button className="rs-dl-btn rs-dl-docx" onClick={() => setOpen(!open)} disabled={downloading}>
        <IconDownload />
        {downloading ? `Downloading ${dlType === 'pdf' ? 'PDF' : 'DOCX'}...` : 'Download'}
        <svg width="10" height="10" viewBox="0 0 10 10" style={{ marginLeft: 4 }}>
          <path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div className="rs-dl-menu">
          <button className="rs-dl-menu-item" onClick={() => handlePick('doc')}>
            <IconDownload /> Download DOCX
          </button>
          <button className="rs-dl-menu-item" onClick={() => handlePick('pdf')}>
            <IconDownload /> Download PDF
          </button>
        </div>
      )}
    </div>
  )
}

// ── Main Results Screen ──────────────────────────────────────
export default function ResultsScreen({ result, trustScore, onDownload, onDownloadEdited, downloading, dlType, onReset }) {
  const [reportTab, setReportTab] = useState('done')
  const [mobileTab, setMobileTab] = useState('score') // mobile: 'preview' | 'score'
  const [editing, setEditing] = useState(false)
  const [hasEdits, setHasEdits] = useState(false)
  const iframeRef = useRef(null)

  const report = result.compliance_report || {}
  const applied = report.applied_transformations || report.changes_made || []
  const skipped = report.skipped_transformations || []
  const manual = report.manual_action_required || []

  const preScore = trustScore?.total_score ?? null
  const postScore = result.post_format_score?.total_score ?? report.overall_score ?? null
  const delta = (preScore !== null && postScore !== null) ? postScore - preScore : null

  const totalChanges = applied.length + skipped.length + manual.length
  const autoPct = totalChanges > 0 ? Math.round((applied.length / totalChanges) * 100) : 100

  // Toggle contenteditable in the iframe
  const toggleEdit = useCallback(() => {
    const newEditing = !editing
    setEditing(newEditing)
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        { type: 'SET_EDITABLE', editable: newEditing }, '*'
      )
    }
    if (newEditing) setHasEdits(true)
  }, [editing])

  // Request edited HTML from iframe, then call parent's download handler
  const handleDownloadEdited = useCallback((type = 'doc') => {
    if (!iframeRef.current?.contentWindow) return

    const handler = (e) => {
      if (e.data?.type === 'EDITED_HTML') {
        window.removeEventListener('message', handler)
        onDownloadEdited(e.data.html, type)
      }
    }
    window.addEventListener('message', handler)

    iframeRef.current.contentWindow.postMessage({ type: 'GET_HTML' }, '*')

    // Timeout cleanup
    setTimeout(() => window.removeEventListener('message', handler), 5000)
  }, [onDownloadEdited])

  const REPORT_TABS = [
    { id: 'done', label: 'Done', icon: <IconCheck />, count: applied.length, color: 'rs-tab-green' },
    { id: 'overrides', label: 'Your Overrides', icon: <IconGear />, count: skipped.length, color: 'rs-tab-amber' },
    { id: 'manual', label: 'Manual Action', icon: <IconWarn />, count: manual.length, color: 'rs-tab-red' },
  ]

  const MOBILE_TABS = [
    { id: 'score', label: 'Compliance' },
    { id: 'preview', label: 'Preview' },
  ]

  return (
    <div className="rs-screen">
      {/* Header */}
      <div className="rs-header">
        <div className="rs-header-left">
          <h2>Formatting Complete</h2>
          <span className="rs-time-badge">Processed in {result.processing_time_seconds}s</span>
        </div>
        <div className="rs-header-actions">
          <button className="rs-new-btn" onClick={onReset}>
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24">
              <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
            New Paper
          </button>
          {result.preview_url && (
            <button
              className={`rs-edit-btn ${editing ? 'active' : ''}`}
              onClick={toggleEdit}
              title={editing ? 'Exit edit mode' : 'Edit document'}
            >
              <IconEdit />
              {editing ? 'Stop Editing' : 'Edit'}
            </button>
          )}
          {hasEdits ? (
            <DownloadDropdown onDownload={handleDownloadEdited} downloading={downloading} dlType={dlType} />
          ) : (
            <DownloadDropdown onDownload={onDownload} downloading={downloading} dlType={dlType} />
          )}
        </div>
      </div>

      {/* Mobile tab bar */}
      <div className="rs-mobile-tabs">
        {MOBILE_TABS.map(t => (
          <button
            key={t.id}
            className={`rs-mobile-tab ${mobileTab === t.id ? 'active' : ''}`}
            onClick={() => setMobileTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 2-column layout */}
      <div className="rs-body">

        {/* LEFT — Document Preview */}
        <div className={`rs-col rs-col-preview ${mobileTab === 'preview' ? 'mobile-visible' : ''}`}>
          <div className="rs-panel">
            <div className="rs-panel-header">
              <IconFile /> Formatted Preview
            </div>
            <div className="rs-preview-frame" id="viewer-panel">
              {result.preview_url ? (
                <iframe
                  ref={iframeRef}
                  src={`${API}${result.preview_url}`}
                  className="rs-preview-iframe"
                  title="Formatted Paper Preview"
                  sandbox="allow-same-origin allow-scripts"
                />
              ) : result.document_structure ? (
                <LiveDocumentEditor
                  documentStructure={result.document_structure}
                  violations={result.interpretation_results?.violations || []}
                />
              ) : (
                <div className="rs-preview-placeholder">
                  <div className="rs-preview-icon"><IconFile /></div>
                  <p>No preview available.</p>
                  <p className="rs-preview-hint">Download the DOCX to view your formatted paper.</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT — Compliance Score + Formatting Report merged */}
        <div className={`rs-col rs-col-score ${mobileTab === 'score' ? 'mobile-visible' : ''}`}>
          <div className="rs-panel">
            <div className="rs-panel-header">Compliance Score</div>

            {/* Side-by-side gauges */}
            <div className="rs-score-comparison">
              {preScore !== null && (
                <ScoreGauge score={preScore} label="Before Formatting" size={120} />
              )}
              {preScore !== null && postScore !== null && (
                <div className="rs-score-arrow">
                  <svg width="24" height="24" fill="none" viewBox="0 0 24 24">
                    <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
              )}
              {postScore !== null && (
                <ScoreGauge score={postScore} label="After Formatting" size={120} />
              )}
            </div>

            {/* Delta badge */}
            {delta !== null && (
              <div className={`rs-delta ${delta > 0 ? 'positive' : delta < 0 ? 'negative' : 'neutral'}`}>
                {delta > 0 ? '+' : ''}{delta} compliance points {delta > 0 ? 'improved' : delta < 0 ? 'decreased' : 'unchanged'}
              </div>
            )}

            {/* Auto percentage */}
            <div className="rs-auto-stat">
              <div className="rs-auto-bar-track">
                <div className="rs-auto-bar-fill" style={{ width: `${autoPct}%` }} />
              </div>
              <p className="rs-auto-label">
                <strong>{autoPct}%</strong> of formatting applied automatically
              </p>
            </div>

            {/* Section breakdown */}
            {report.breakdown && (
              <div className="rs-breakdown">
                <p className="rs-breakdown-title">Section Breakdown</p>
                {Object.entries(report.breakdown).map(([key, val]) => {
                  const s = val.score ?? 0
                  const barColor = s >= 80 ? 'var(--success)' : s >= 60 ? 'var(--orange)' : 'var(--error)'
                  return (
                    <div key={key} className="rs-break-row">
                      <span className="rs-break-label">{key.replace(/_/g, ' ')}</span>
                      <div className="rs-break-track">
                        <div className="rs-break-fill" style={{ width: `${s}%`, background: barColor }} />
                      </div>
                      <span className="rs-break-num" style={{ color: barColor }}>{s}</span>
                    </div>
                  )
                })}
              </div>
            )}

            {/* ── Formatting Report (merged into compliance) ── */}
            <div className="rs-formatting-section">
              <div className="rs-formatting-header">
                <span className="rs-formatting-title">Formatting Report</span>
                <span className="rs-formatting-sub">
                  {applied.length} applied, {skipped.length} overrides, {manual.length} manual
                </span>
              </div>

              {/* Tabs */}
              <div className="rs-tabs">
                {REPORT_TABS.map(t => (
                  <button
                    key={t.id}
                    className={`rs-tab ${t.color} ${reportTab === t.id ? 'active' : ''}`}
                    onClick={() => setReportTab(t.id)}
                  >
                    {t.icon}
                    <span className="rs-tab-label">{t.label}</span>
                    <span className="rs-tab-count">{t.count}</span>
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div className="rs-tab-content">
                {reportTab === 'done' && (
                  <ReportList
                    items={applied}
                    emptyMsg="No formatting changes were applied."
                    colorClass="green"
                  />
                )}
                {reportTab === 'overrides' && (
                  <ReportList
                    items={skipped}
                    emptyMsg="No user overrides were applied."
                    colorClass="amber"
                  />
                )}
                {reportTab === 'manual' && (
                  <ReportList
                    items={manual}
                    emptyMsg="No manual actions required — everything was handled automatically!"
                    colorClass="red"
                  />
                )}
              </div>
            </div>

            {/* Download buttons
            <div className="rs-score-actions">
              <DownloadDropdown onDownload={onDownload} downloading={downloading} dlType={dlType} />
            </div> */}
          </div>
        </div>
      </div>
    </div>
  )
}
