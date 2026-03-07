import { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

const IconCheck = () => (
  <svg width="12" height="12" fill="none" viewBox="0 0 24 24">
    <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

// Field definitions matching backend OVERRIDE_SCHEMA
const FIELDS = [
  {
    key: 'abstract.max_words',
    section: 'abstract', field: 'max_words',
    label: 'Abstract Word Limit',
    type: 'number', min: 50, max: 1000,
  },
  {
    key: 'document.font',
    section: 'document', field: 'font',
    label: 'Font Family',
    type: 'select',
    options: [
      { value: 'Times New Roman', label: 'Times New Roman' },
      { value: 'Arial', label: 'Arial' },
      { value: 'Calibri', label: 'Calibri' },
      { value: 'Georgia', label: 'Georgia' },
    ],
  },
  {
    key: 'document.font_size',
    section: 'document', field: 'font_size',
    label: 'Font Size',
    type: 'select',
    options: [8, 9, 10, 11, 12, 14, 16].map(v => ({ value: v, label: `${v}pt` })),
  },
  {
    key: 'document.line_spacing',
    section: 'document', field: 'line_spacing',
    label: 'Line Spacing',
    type: 'select',
    options: [
      { value: 1.0, label: 'Single (1.0)' },
      { value: 1.15, label: '1.15' },
      { value: 1.5, label: '1.5' },
      { value: 2.0, label: 'Double (2.0)' },
    ],
  },
  {
    key: 'headings.numbering_style',
    section: 'headings', field: 'numbering_style',
    label: 'Heading Numbering',
    type: 'select',
    options: [
      { value: 'roman', label: 'Roman (I, II, III)' },
      { value: 'numeric', label: 'Numeric (1, 2, 3)' },
      { value: 'alpha', label: 'Alpha (A, B, C)' },
    ],
  },
  {
    key: 'references.style',
    section: 'references', field: 'style',
    label: 'Reference Style',
    type: 'select',
    options: [
      { value: 'ieee',      label: 'IEEE (Numbered)' },
      { value: 'apa',       label: 'APA 7th' },
      { value: 'mla',       label: 'MLA' },
      { value: 'chicago',   label: 'Chicago' },
      { value: 'vancouver', label: 'Vancouver' },
      { value: 'springer',  label: 'Springer' },
    ],
  },
  {
    key: 'figures.caption_position',
    section: 'figures', field: 'caption_position',
    label: 'Figure Caption',
    type: 'toggle',
    options: [
      { value: 'above', label: 'Above' },
      { value: 'below', label: 'Below' },
    ],
  },
  {
    key: 'tables.caption_position',
    section: 'tables', field: 'caption_position',
    label: 'Table Caption',
    type: 'toggle',
    options: [
      { value: 'above', label: 'Above' },
      { value: 'below', label: 'Below' },
    ],
  },
]

// Map journal heading numbering from rules H1.numbering to our schema values
function resolveHeadingNumbering(rules) {
  const h1 = rules?.headings?.H1?.numbering
  if (!h1 || h1 === 'none') return undefined
  return h1 // "roman", "numeric", "alpha" match our enum
}

// Map journal name to our reference style enum
function resolveReferenceStyle(rules) {
  const name = (rules?.style_name || '').toLowerCase()
  if (name.includes('ieee'))       return 'ieee'
  if (name.includes('apa'))        return 'apa'
  if (name.includes('chicago'))    return 'chicago'
  if (name.includes('vancouver'))  return 'vancouver'
  if (name.includes('springer'))   return 'springer'
  return undefined
}

export default function SemiCustomPanel({ journal, overrides, onChange }) {
  const [defaults, setDefaults] = useState({})
  const [rulesData, setRulesData] = useState({})   // full API response (style_name etc.)
  const [loading, setLoading] = useState(false)

  // Fetch journal defaults when journal changes
  useEffect(() => {
    if (!journal) return
    setLoading(true)
    axios.get(`${API}/journal-defaults/${encodeURIComponent(journal)}`)
      .then(res => {
        setDefaults(res.data.defaults || {})
        setRulesData(res.data)   // keep style_name for resolveReferenceStyle()
      })
      .catch(err => {
        console.warn('Failed to load journal defaults:', err.message)
      })
      .finally(() => setLoading(false))
  }, [journal])

  const getDefault = (fieldDef) => {
    // Try the direct API defaults first (e.g. abstract.max_words, document.font, etc.)
    const apiDefault = defaults[fieldDef.key]
    if (apiDefault !== undefined && apiDefault !== null) return apiDefault

    // Special case: references.style is not a direct field in the rules JSONs.
    // Derive it from style_name (returned by the API alongside defaults).
    if (fieldDef.key === 'references.style') {
      return resolveReferenceStyle(rulesData)
    }

    return undefined
  }

  const getCurrentValue = (fieldDef) => {
    return overrides?.[fieldDef.section]?.[fieldDef.field]
  }

  const isChanged = (fieldDef) => {
    return getCurrentValue(fieldDef) !== undefined
  }

  const handleChange = (fieldDef, value) => {
    const next = { ...overrides }
    const def = getDefault(fieldDef)

    // If value matches default, remove the override
    // Use loose comparison for numbers (e.g. "10" == 10)
    if (value === undefined || value === '' || String(value) === String(def)) {
      if (next[fieldDef.section]) {
        delete next[fieldDef.section][fieldDef.field]
        if (Object.keys(next[fieldDef.section]).length === 0) {
          delete next[fieldDef.section]
        }
      }
    } else {
      if (!next[fieldDef.section]) next[fieldDef.section] = {}
      // Coerce types
      if (fieldDef.type === 'number') {
        next[fieldDef.section][fieldDef.field] = parseInt(value, 10)
      } else if (fieldDef.key === 'document.font_size') {
        next[fieldDef.section][fieldDef.field] = parseInt(value, 10)
      } else if (fieldDef.key === 'document.line_spacing') {
        next[fieldDef.section][fieldDef.field] = parseFloat(value)
      } else {
        next[fieldDef.section][fieldDef.field] = value
      }
    }

    onChange(next)
  }

  const handleReset = () => {
    onChange({})
  }

  // Compute active overrides for the summary chips
  const activeOverrides = FIELDS.filter(f => isChanged(f)).map(f => {
    const val = getCurrentValue(f)
    let display = String(val)
    if (f.type === 'select' || f.type === 'toggle') {
      const opt = f.options.find(o => String(o.value) === String(val))
      if (opt) display = opt.label
    }
    if (f.key === 'abstract.max_words') display = `${val} words`
    if (f.key === 'document.font_size') display = `${val}pt`
    return { label: f.label, display }
  })

  if (loading) {
    return (
      <div className="scp-loading">
        Loading journal defaults...
      </div>
    )
  }

  return (
    <div className="scp-panel">
      <div className="scp-grid">
        {FIELDS.map(fieldDef => {
          const def = getDefault(fieldDef)
          const current = getCurrentValue(fieldDef)
          const changed = isChanged(fieldDef)
          const displayValue = current !== undefined ? current : (def !== undefined ? def : '')

          if (fieldDef.type === 'number') {
            return (
              <div key={fieldDef.key} className={`scp-field ${changed ? 'scp-field-changed' : ''}`}>
                <label className="scp-label">{fieldDef.label}</label>
                <input
                  type="number"
                  className="scp-input"
                  min={fieldDef.min}
                  max={fieldDef.max}
                  value={displayValue}
                  placeholder={def !== undefined ? `${journal} default: ${def}` : ''}
                  onChange={e => handleChange(fieldDef, e.target.value)}
                />
                {def !== undefined && (
                  <span className="scp-default-hint">Default: {def}</span>
                )}
              </div>
            )
          }

          if (fieldDef.type === 'select') {
            return (
              <div key={fieldDef.key} className={`scp-field ${changed ? 'scp-field-changed' : ''}`}>
                <label className="scp-label">{fieldDef.label}</label>
                <select
                  className="scp-select"
                  value={displayValue}
                  onChange={e => handleChange(fieldDef, e.target.value)}
                >
                  {!changed && def !== undefined && (
                    <option value={def}>
                      {fieldDef.options.find(o => String(o.value) === String(def))?.label || def} (default)
                    </option>
                  )}
                  {fieldDef.options.map(opt => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}{String(opt.value) === String(def) ? ' (default)' : ''}
                    </option>
                  ))}
                </select>
                {def !== undefined && (
                  <span className="scp-default-hint">
                    Default: {fieldDef.options.find(o => String(o.value) === String(def))?.label || def}
                  </span>
                )}
              </div>
            )
          }

          if (fieldDef.type === 'toggle') {
            return (
              <div key={fieldDef.key} className={`scp-field ${changed ? 'scp-field-changed' : ''}`}>
                <label className="scp-label">{fieldDef.label}</label>
                <div className="scp-toggle-group">
                  {fieldDef.options.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      className={`scp-toggle-btn ${String(displayValue) === String(opt.value) ? 'active' : ''}`}
                      onClick={() => handleChange(fieldDef, opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
                {def !== undefined && (
                  <span className="scp-default-hint">
                    Default: {fieldDef.options.find(o => String(o.value) === String(def))?.label || def}
                  </span>
                )}
              </div>
            )
          }

          return null
        })}
      </div>

      {/* Active overrides summary */}
      <div className="scp-summary">
        <div className="scp-summary-header">
          <span className="scp-summary-title">Your Active Overrides:</span>
          {activeOverrides.length > 0 && (
            <button type="button" className="scp-reset-btn" onClick={handleReset}>
              Reset to Default
            </button>
          )}
        </div>
        {activeOverrides.length === 0 ? (
          <p className="scp-summary-empty">
            No overrides — using standard {journal} rules
          </p>
        ) : (
          <div className="scp-chips">
            {activeOverrides.map(o => (
              <span key={o.label} className="scp-chip">
                <IconCheck />
                {o.label}: {o.display}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
