import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

const STEPS = [
  { label: 'Extracting structure',    sublabel: 'Reading and parsing your document' },
  { label: 'Applying format rules',   sublabel: 'Fixing fonts, headings, citations' },
  { label: 'Validating citations',    sublabel: 'Checking references and cross-links' },
  { label: 'Generating document',     sublabel: 'Writing your formatted DOCX' },
]

// SVG icons for each step
const StepIcons = {
  0: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/>
      <path d="M14 2v6h6M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  ),
  1: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <path d="M12 20h9M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4L16.5 3.5z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  2: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <path d="M10 11h-4a1 1 0 01-1-1V6a1 1 0 011-1h3a1 1 0 011 1v5zm0 0a4 4 0 01-4 4M20 11h-4a1 1 0 01-1-1V6a1 1 0 011-1h3a1 1 0 011 1v5zm0 0a4 4 0 01-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  3: (
    <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <polyline points="7 10 12 15 17 10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  ),
}

// Typewriter text component
function Typewriter({ text, speed = 40, className = '' }) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    setDisplayed('')
    setDone(false)
    let i = 0
    const interval = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) {
        setDone(true)
        clearInterval(interval)
      }
    }, speed)
    return () => clearInterval(interval)
  }, [text, speed])

  return (
    <span className={className}>
      {displayed}
      {!done && <span className="typewriter-cursor">|</span>}
    </span>
  )
}

// Confetti particle system
function Confetti() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    canvas.width = canvas.offsetWidth
    canvas.height = canvas.offsetHeight

    const colors = ['#F97316', '#2563EB', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899']
    const particles = Array.from({ length: 80 }, () => ({
      x: canvas.width / 2 + (Math.random() - 0.5) * 100,
      y: canvas.height / 2,
      vx: (Math.random() - 0.5) * 12,
      vy: -Math.random() * 14 - 4,
      color: colors[Math.floor(Math.random() * colors.length)],
      size: Math.random() * 6 + 3,
      rotation: Math.random() * 360,
      rotSpeed: (Math.random() - 0.5) * 12,
      opacity: 1,
    }))

    let frame = 0
    const maxFrames = 120
    const animate = () => {
      if (frame >= maxFrames) return
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      particles.forEach(p => {
        p.x += p.vx
        p.vy += 0.3 // gravity
        p.y += p.vy
        p.rotation += p.rotSpeed
        p.opacity = Math.max(0, 1 - frame / maxFrames)

        ctx.save()
        ctx.translate(p.x, p.y)
        ctx.rotate((p.rotation * Math.PI) / 180)
        ctx.globalAlpha = p.opacity
        ctx.fillStyle = p.color
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6)
        ctx.restore()
      })
      frame++
      requestAnimationFrame(animate)
    }
    requestAnimationFrame(animate)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute', top: 0, left: 0,
        width: '100%', height: '100%', pointerEvents: 'none', zIndex: 10,
      }}
    />
  )
}

export default function ProgressScreen({ jobId, journal, filename, onComplete, onError }) {
  const [status, setStatus] = useState('processing')
  const [progress, setProgress] = useState(0)
  const [stepIndex, setStepIndex] = useState(0)
  const [stepLabel, setStepLabel] = useState(STEPS[0].label)
  const [elapsed, setElapsed] = useState(0)
  const [completed, setCompleted] = useState(false)
  const pollRef = useRef(null)
  const failCountRef = useRef(0)
  const startRef = useRef(Date.now())

  // Elapsed timer
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const minutes = Math.floor(elapsed / 60)
  const seconds = elapsed % 60
  const elapsedStr = `${minutes}:${String(seconds).padStart(2, '0')}`

  // Poll backend every 2 seconds
  const poll = useCallback(async () => {
    if (!jobId) return
    try {
      const res = await axios.get(`${API}/format/status/${jobId}`)
      const data = res.data
      failCountRef.current = 0  // reset on success

      setProgress(data.progress || 0)
      setStepIndex(data.step_index ?? 0)
      if (data.step) setStepLabel(data.step)
      // Use backend elapsed if available (more accurate than client timer)
      if (data.elapsed_seconds != null) {
        setElapsed(Math.floor(data.elapsed_seconds))
      }

      if (data.status === 'done') {
        setStatus('done')
        setProgress(100)
        setCompleted(true)
        clearInterval(pollRef.current)
        // Fetch full result after brief celebration delay
        setTimeout(async () => {
          try {
            const resultRes = await axios.get(`${API}/format/result/${jobId}`)
            onComplete(resultRes.data)
          } catch (err) {
            onError(err.message || 'Failed to fetch results.')
          }
        }, 2200)
      } else if (data.status === 'error') {
        setStatus('error')
        clearInterval(pollRef.current)
        onError(data.error || 'Pipeline failed.')
      }
    } catch (err) {
      failCountRef.current += 1
      console.warn(`Poll error (${failCountRef.current}):`, err.message)
      // Stop polling after 10 consecutive failures (stale job or server down)
      if (failCountRef.current >= 10) {
        clearInterval(pollRef.current)
        onError('Lost connection to server. Please try again.')
      }
    }
  }, [jobId, onComplete, onError])

  useEffect(() => {
    if (!jobId) return
    pollRef.current = setInterval(poll, 2000)
    // Also poll immediately
    poll()
    return () => clearInterval(pollRef.current)
  }, [jobId, poll])

  const showLongWait = elapsed >= 90

  return (
    <div className="progress-screen">
      {completed && <Confetti />}

      <div className={`progress-card ${completed ? 'progress-card-done' : ''}`}>
        {/* Header */}
        <div className="progress-header">
          {!completed ? (
            <div className="progress-spinner">
              <div className="progress-spinner-ring" />
            </div>
          ) : (
            <div className="progress-check-wrap">
              <svg width="36" height="36" fill="none" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" fill="#10B981" opacity="0.15"/>
                <path d="M8 12l3 3 5-6" stroke="#10B981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
          )}

          <h2 className="progress-title">
            {completed ? 'Formatting Complete!' : 'Formatting your paper...'}
          </h2>

          {journal && (
            <p className="progress-journal">
              Applying <span>{journal}</span> rules
            </p>
          )}
          {filename && (
            <p className="progress-filename">{filename}</p>
          )}
        </div>

        {/* Step list */}
        <div className="progress-steps">
          {STEPS.map((step, i) => {
            const isDone = i < stepIndex || completed
            const isActive = i === stepIndex && !completed
            const isPending = i > stepIndex && !completed

            return (
              <div
                key={i}
                className={`progress-step ${isDone ? 'done' : ''} ${isActive ? 'active' : ''} ${isPending ? 'pending' : ''}`}
              >
                {/* Left indicator */}
                <div className="progress-step-indicator">
                  {isDone ? (
                    <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
                      <circle cx="12" cy="12" r="10" fill="#10B981" opacity="0.15"/>
                      <path d="M8 12l3 3 5-6" stroke="#10B981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  ) : isActive ? (
                    <div className="step-spinner" />
                  ) : (
                    <div className="step-pending-dot" />
                  )}
                </div>

                {/* Icon */}
                <div className="progress-step-icon">
                  {StepIcons[i]}
                </div>

                {/* Label */}
                <div className="progress-step-content">
                  {isActive ? (
                    <>
                      <Typewriter text={step.label + '...'} className="progress-step-label active" />
                      <p className="progress-step-sublabel">{step.sublabel}</p>
                    </>
                  ) : (
                    <span className={`progress-step-label ${isDone ? 'done' : 'pending'}`}>
                      {step.label}
                    </span>
                  )}
                </div>

                {/* Done badge */}
                {isDone && <span className="progress-step-badge">done</span>}
              </div>
            )
          })}
        </div>

        {/* Progress bar */}
        <div className="progress-bar-section">
          <div className="progress-bar-track">
            <div
              className={`progress-bar-fill ${completed ? 'complete' : ''}`}
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="progress-bar-meta">
            <span className="progress-elapsed">
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" style={{ marginRight: 4 }}>
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                <path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              {elapsedStr} elapsed
            </span>
            <span className="progress-pct">{Math.round(progress)}%</span>
          </div>
        </div>

        {/* Footer note */}
        <p className={`progress-note ${showLongWait ? 'warn' : ''}`}>
          {completed
            ? 'Loading your results...'
            : showLongWait
            ? 'Taking longer than usual. Large papers require more time...'
            : "This typically takes a few minutes. Please don't close this tab."}
        </p>
      </div>
    </div>
  )
}
