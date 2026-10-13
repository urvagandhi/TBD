import { useEffect, useMemo, useState } from 'react'

const API_BASE = import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000'
const GROUPS = [['Document', ['document.']], ['Abstract', ['abstract.']], ['Headings', ['headings.']], ['Citations & References', ['citations.', 'references.']], ['Figures', ['figures.']], ['Tables', ['tables.']], ['Other', ['equations.', 'general_rules.']]]
const ENUMS = {
  'document.alignment': ['left', 'justify', 'center', 'right'],
  'citations.style': ['author-date', 'numbered', 'footnote'],
  'citations.brackets': ['parentheses', 'square', 'none'],
  'references.ordering': ['alphabetical', 'appearance'],
  'figures.caption_position': ['above', 'below'],
  'tables.caption_position': ['above', 'below'],
  'tables.border_style': ['full', 'full_grid', 'top_bottom_only', 'header_only', 'none'],
}
const labelFor = path => path.split('.').map(part => part.replace(/_/g, ' ').replace(/^./, char => char.toUpperCase())).join(' / ')
const badgeStyle = kind => ({ display: 'inline-block', borderRadius: 99, padding: '2px 7px', fontSize: '.68rem', fontWeight: 700, background: kind === 'source' ? 'rgba(34,197,94,.14)' : kind === 'user_override' ? 'rgba(37,99,235,.14)' : 'rgba(245,158,11,.16)', color: kind === 'source' ? 'var(--success)' : kind === 'user_override' ? 'var(--blue)' : 'var(--orange)' })
const sourceLabel = source => (source?.title || source?.url || 'Unnamed source').replace(/\s+/g, ' ').trim().slice(0, 70)

function RuleField({ fact, value, onChange }) {
  const options = ENUMS[fact.path]
  const style = { width: '100%', border: '1px solid var(--border)', borderRadius: 6, padding: '7px 8px', background: '#fff', color: 'var(--text)' }
  let input
  if (typeof value === 'boolean') input = <label style={{ fontSize: '.82rem' }}><input type="checkbox" checked={value} onChange={event => onChange(event.target.checked)} /> Enabled</label>
  else if (options) input = <select value={value} onChange={event => onChange(event.target.value)} style={style}>{options.map(option => <option key={option}>{option}</option>)}</select>
  else if (typeof value === 'number') input = <input type="number" step={Number.isInteger(value) ? '1' : '0.1'} value={value} onChange={event => onChange(event.target.value === '' ? '' : Number(event.target.value))} style={style} />
  else input = <input type="text" value={value ?? ''} onChange={event => onChange(event.target.value)} style={style} />
  return <div style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 5 }}><strong style={{ fontSize: '.78rem' }}>{labelFor(fact.path)}</strong><span style={badgeStyle(fact.provenance)}>{fact.provenance === 'source' ? 'Source-backed' : fact.provenance === 'user_override' ? 'Reviewer edited' : 'Default / not stated'}</span></div>
    {input}
    {fact.excerpt ? <div style={{ fontSize: '.72rem', color: 'var(--text-secondary)', marginTop: 6 }}>Evidence: “{fact.excerpt}”</div> : <div style={{ fontSize: '.72rem', color: 'var(--orange)', marginTop: 6 }}>Fallback value; the selected source did not state it.</div>}
  </div>
}

export default function JournalSearch({ onSelect, selectedJournal, disabled }) {
  const [query, setQuery] = useState('')
  const [catalog, setCatalog] = useState([])
  const [draft, setDraft] = useState(null)
  const [edits, setEdits] = useState({})
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [approved, setApproved] = useState(null)
  const [showDetails, setShowDetails] = useState(false)
  useEffect(() => { fetch(API_BASE + '/journals').then(response => response.json()).then(data => { if (data.success) setCatalog(data.journals || []) }).catch(() => setCatalog([])) }, [])
  const matches = useMemo(() => catalog.filter(item => item.name.toLowerCase().includes(query.toLowerCase())).slice(0, 8), [catalog, query])
  const request = async (url, options = {}) => {
    const response = await fetch(API_BASE + url, options)
    const data = await response.json().catch(() => ({}))
    if (!response.ok || !data.success) throw new Error(data?.detail?.error || data?.error || 'The request could not be completed.')
    return data
  }
  const discover = async name => {
    setBusy('discover'); setError(''); setApproved(null)
    try { const data = await request('/journals/discover', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }); setDraft(data.draft); setEdits({}); setShowDetails(false); setQuery(name) } catch (err) { setError(err.message) } finally { setBusy('') }
  }
  const chooseSource = async sourceId => {
    setBusy('source'); setError('')
    try { const data = await request('/journals/discover/' + draft.draft_id + '/select-source', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_id: sourceId }) }); setDraft(data.draft); setEdits({}) } catch (err) { setError(err.message) } finally { setBusy('') }
  }
  const saveEdits = async () => {
    const updates = Object.entries(edits).map(([path, value]) => ({ path, value }))
    if (!updates.length) return
    setBusy('save'); setError('')
    try { const data = await request('/journals/discover/' + draft.draft_id + '/rules', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ updates }) }); setDraft(data.draft); setEdits({}) } catch (err) { setError(err.message) } finally { setBusy('') }
  }
  const approve = async () => {
    setBusy('approve'); setError('')
    try { const data = await request('/journals/discover/' + draft.draft_id + '/approve', { method: 'POST' }); setApproved(data.rule_set); onSelect(data.rule_set.journal_name, 'approved', data.rule_set.rule_set_id) } catch (err) { setError(err.message) } finally { setBusy('') }
  }
  const factsFor = prefixes => (draft?.field_facts || []).filter(fact => prefixes.some(prefix => fact.path.startsWith(prefix)))

  return <div style={{ position: 'relative' }}>
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', border: '1.5px solid var(--border)', borderRadius: 8, padding: '9px 11px', background: '#fff' }}>
      <input value={query} disabled={disabled || !!busy} onChange={event => setQuery(event.target.value)} onKeyDown={event => event.key === 'Enter' && query.trim().length >= 2 && discover(query.trim())} placeholder={selectedJournal || 'Search a journal'} style={{ flex: 1, border: 0, outline: 0, fontSize: '.9rem' }} />
      <button type="button" className="btn-primary" disabled={disabled || !!busy || query.trim().length < 2} onClick={() => discover(query.trim())} style={{ width: 'auto', margin: 0, padding: '7px 10px', fontSize: '.78rem' }}>{busy === 'discover' ? 'Discovering…' : 'Discover'}</button>
    </div>
    {matches.length > 0 && !draft && <div style={{ border: '1px solid var(--border)', background: '#fff', borderRadius: 8, marginTop: 4, overflow: 'hidden' }}>{matches.map(item => <button type="button" key={item.name} disabled={disabled || !!busy} onClick={() => { setQuery(item.name); if (item.source === 'built-in') onSelect(item.name, 'built-in', ''); else discover(item.name) }} style={{ display: 'block', width: '100%', textAlign: 'left', border: 0, borderBottom: '1px solid var(--border)', background: '#fff', padding: '8px 11px', cursor: 'pointer' }}><strong>{item.name}</strong> <span style={{ color: 'var(--text-secondary)', fontSize: '.75rem' }}>{item.source === 'built-in' ? 'Built-in verified profile' : 'Discover official rules'}</span></button>)}</div>}
    {error && <div style={{ marginTop: 10, border: '1px solid var(--error)', color: 'var(--error)', borderRadius: 8, padding: 10, fontSize: '.82rem' }}><strong>Discovery needs attention.</strong> {error}<button type="button" onClick={() => query && discover(query)} style={{ marginLeft: 8, border: 0, background: 'transparent', color: 'inherit', textDecoration: 'underline', cursor: 'pointer' }}>Retry</button><div style={{ marginTop: 4 }}>You can also upload journal guidelines using Full Custom mode.</div></div>}
    {draft && <div style={{ marginTop: 12, border: '1px solid var(--blue)', borderRadius: 10, padding: 15, background: '#fbfdff' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}><div><h3 style={{ margin: 0 }}>{draft.quality?.can_approve ? 'Rules are ready' : 'Discovery needs one more pass'}</h3><div style={{ color: 'var(--text-secondary)', fontSize: '.78rem', marginTop: 4 }}>We selected the strongest guidance source and inspected related official pages for you.</div></div><span style={badgeStyle(draft.quality?.can_approve ? 'source' : 'default')}>{draft.quality?.can_approve ? 'Verified rules' : 'Evidence incomplete'}</span></div>
      <div style={{ marginTop: 12, padding: 10, borderRadius: 8, background: '#fff', border: '1px solid var(--border)', fontSize: '.8rem' }}><strong>{draft.discovery_summary?.pages_inspected || 1} official guidance page{(draft.discovery_summary?.pages_inspected || 1) === 1 ? '' : 's'} inspected</strong> · {draft.quality?.critical_coverage ?? 0}% critical evidence · {draft.quality?.field_evidence_coverage ?? 0}% field evidence<br />Primary source: {draft.selected_source && <a href={draft.selected_source.url} target="_blank" rel="noreferrer">{sourceLabel(draft.selected_source)}</a>}</div>
      {draft.quality?.can_approve ? <div style={{ marginTop: 12 }}><button type="button" className="btn-primary" disabled={!!busy} onClick={approve} style={{ width: 'auto', margin: '0 8px 0 0' }}>{busy === 'approve' ? 'Preparing rules…' : 'Use verified rules'}</button><span style={{ fontSize: '.72rem', color: 'var(--text-secondary)' }}>Using these rules records your acknowledgement of this evidence-backed version.</span></div> : <div style={{ marginTop: 12, color: 'var(--orange)', fontSize: '.8rem' }}><strong>Still missing:</strong> {(draft.quality?.approval_blockers || []).join(' ')}<div style={{ marginTop: 5, color: 'var(--text-secondary)' }}>Open the details to choose another source or upload the journal guideline in Full Custom mode.</div></div>}
      <button type="button" onClick={() => setShowDetails(value => !value)} style={{ width: 'auto', marginTop: 12, border: 0, background: 'transparent', color: 'var(--blue)', textDecoration: 'underline', cursor: 'pointer', fontSize: '.8rem' }}>{showDetails ? 'Hide source and rule details' : 'Review sources and rules'}</button>
      {showDetails && <div style={{ marginTop: 12 }}>
        <div style={{ padding: 10, borderRadius: 8, background: '#fff', border: '1px solid var(--border)', fontSize: '.78rem' }}><strong>Official-source confidence: {draft.quality?.source_trust || 'unknown'}</strong> <span style={{ color: 'var(--text-secondary)' }}>(source identity, not rule completeness)</span><div style={{ color: 'var(--text-secondary)', marginTop: 3 }}>{(draft.selected_source?.trust_reasons || []).join(' · ')}</div><div style={{ marginTop: 8 }}><strong>Inspected sources</strong>{(draft.discovery_summary?.sources_inspected || []).map(item => <div key={item.url} style={{ marginTop: 4 }}><a href={item.url} target="_blank" rel="noreferrer">{sourceLabel(item)}</a> <span style={{ color: 'var(--text-secondary)' }}>({item.credibility})</span></div>)}</div></div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>{(draft.candidates || []).slice(0, 8).map(source => <button type="button" key={source.id} disabled={!!busy || source.id === draft.selected_source?.id} onClick={() => chooseSource(source.id)} title={source.url} style={{ border: '1px solid var(--border)', borderRadius: 99, padding: '5px 9px', background: source.id === draft.selected_source?.id ? 'var(--blue)' : '#fff', color: source.id === draft.selected_source?.id ? '#fff' : 'var(--text)', cursor: 'pointer', fontSize: '.72rem' }}>{source.id === draft.selected_source?.id ? 'Selected: ' : 'Use: '}{sourceLabel(source)} ({source.official_likelihood})</button>)}</div>
        <div style={{ marginTop: 14 }}>{GROUPS.map(([name, prefixes]) => { const facts = factsFor(prefixes); return facts.length ? <details key={name} style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, padding: '0 10px', marginBottom: 8 }}><summary style={{ cursor: 'pointer', padding: '10px 0', fontWeight: 700 }}>{name} ({facts.length} rules)</summary>{facts.map(fact => <RuleField key={fact.path} fact={fact} value={Object.prototype.hasOwnProperty.call(edits, fact.path) ? edits[fact.path] : fact.value} onChange={value => setEdits(current => ({ ...current, [fact.path]: value }))} />)}</details> : null })}</div>
        {Object.keys(edits).length > 0 && <button type="button" className="btn-primary" disabled={!!busy} onClick={saveEdits} style={{ width: 'auto', margin: '4px 0 12px' }}>{busy === 'save' ? 'Validating edits…' : 'Save reviewer edits'}</button>}
        <div style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}><strong style={{ fontSize: '.82rem' }}>Author checklist</strong>{(draft.compilation?.author_checklist || []).map(item => <div key={item.text} style={{ fontSize: '.75rem', marginTop: 7 }}>• {item.text}</div>)}</div>
      </div>}
    </div>}
    {approved && <div style={{ marginTop: 10, border: '1px solid var(--success)', background: 'rgba(34,197,94,.08)', borderRadius: 8, padding: 10, fontSize: '.8rem' }}><strong>Approved rule set: {approved.rule_set_id}</strong><br />The pre-check and formatter will now use this reviewed version.</div>}
  </div>
}
