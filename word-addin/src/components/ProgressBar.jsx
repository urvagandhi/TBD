import { useState, useEffect } from "react";

const STEPS = [
  { label: "Extracting structure", icon: "doc" },
  { label: "Applying format rules", icon: "edit" },
  { label: "Validating citations", icon: "cite" },
  { label: "Generating document", icon: "download" },
];

const StepIcon = ({ type, active }) => {
  const color = active ? "#fff" : "var(--text-muted)";
  const icons = {
    doc: <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />,
    edit: <path d="M12 20h9M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4L16.5 3.5z" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />,
    cite: <><path d="M10 11h-4a1 1 0 01-1-1V6a1 1 0 011-1h3a1 1 0 011 1v5zm0 0a4 4 0 01-4 4" stroke={color} strokeWidth="1.8" /><path d="M20 11h-4a1 1 0 01-1-1V6a1 1 0 011-1h3a1 1 0 011 1v5zm0 0a4 4 0 01-4 4" stroke={color} strokeWidth="1.8" /></>,
    download: <><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke={color} strokeWidth="1.8" strokeLinecap="round" /><polyline points="7 10 12 15 17 10" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /><line x1="12" y1="15" x2="12" y2="3" stroke={color} strokeWidth="1.8" strokeLinecap="round" /></>,
  };
  return <svg width="16" height="16" fill="none" viewBox="0 0 24 24">{icons[type]}</svg>;
};

export default function ProgressBar({ progress, stage }) {
  const pct = Math.min(100, Math.max(0, progress || 0));
  const currentStage = stage || "Starting...";
  const [typewriterText, setTypewriterText] = useState("");

  useEffect(() => {
    setTypewriterText("");
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setTypewriterText(currentStage.slice(0, i));
      if (i >= currentStage.length) clearInterval(interval);
    }, 30);
    return () => clearInterval(interval);
  }, [currentStage]);

  // Determine active step index from progress
  const stepIndex = pct < 25 ? 0 : pct < 50 ? 1 : pct < 75 ? 2 : 3;

  return (
    <div style={{
      background: "#fff", border: "1px solid var(--border)", borderRadius: "var(--radius)",
      padding: "28px 24px", boxShadow: "var(--shadow-lg)",
      animation: "fadeIn 0.4s ease",
    }}>
      {/* Orbit animation */}
      <div style={{
        position: "relative", width: 64, height: 64,
        margin: "0 auto 20px",
      }}>
        <div style={{
          width: 18, height: 18, borderRadius: "50%",
          background: "linear-gradient(135deg, var(--orange), var(--orange-hover))",
          position: "absolute", top: "50%", left: "50%",
          transform: "translate(-50%,-50%)",
          boxShadow: "0 0 16px rgba(249,115,22,0.5)",
          animation: "glow 2s ease infinite",
        }} />
        <div style={{
          width: 9, height: 9, borderRadius: "50%",
          background: "var(--orange)", position: "absolute",
          top: "50%", left: "50%",
          animation: "orbitDot 1.4s linear infinite",
        }} />
        <div style={{
          width: 7, height: 7, borderRadius: "50%",
          background: "var(--primary)", position: "absolute",
          top: "50%", left: "50%",
          animation: "orbitDot 1.9s linear infinite",
          animationDelay: "-0.5s",
        }} />
        <div style={{
          width: 5, height: 5, borderRadius: "50%",
          background: "var(--success)", position: "absolute",
          top: "50%", left: "50%",
          animation: "orbitDot 2.3s linear infinite",
          animationDelay: "-1s",
        }} />
      </div>

      {/* Stage text with typewriter */}
      <p style={{
        textAlign: "center", fontSize: "0.95rem", fontWeight: 600,
        color: "var(--text)", minHeight: 24, marginBottom: 4,
        animation: "stepFade 0.3s ease",
      }}>
        {typewriterText}
        <span style={{ opacity: 0.4, animation: "fadeIn 0.5s ease infinite alternate" }}>|</span>
      </p>

      <p style={{
        textAlign: "center", fontSize: "0.8rem", color: "var(--text-muted)",
        marginBottom: 20,
      }}>
        {pct}% complete
      </p>

      {/* Step dots */}
      <div style={{
        display: "flex", gap: 6, justifyContent: "center", marginBottom: 20,
      }}>
        {STEPS.map((_, i) => (
          <div key={i} style={{
            width: 8, height: 8, borderRadius: "50%",
            background: i <= stepIndex ? "var(--orange)" : "var(--border)",
            transition: "background 0.3s, transform 0.3s",
            transform: i === stepIndex ? "scale(1.4)" : "scale(1)",
          }} />
        ))}
      </div>

      {/* Step labels */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {STEPS.map((step, i) => {
          const isActive = i === stepIndex;
          const isDone = i < stepIndex;
          return (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "8px 12px", borderRadius: "var(--radius-sm)",
              background: isActive ? "var(--orange-light)" : isDone ? "var(--success-bg)" : "var(--bg-soft)",
              border: isActive ? "1px solid rgba(249,115,22,0.25)" : "1px solid transparent",
              transition: "all 0.3s ease",
              animation: isActive ? "slideRight 0.3s ease" : undefined,
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: "50%",
                background: isActive
                  ? "var(--orange)"
                  : isDone
                    ? "var(--success)"
                    : "var(--border)",
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0, transition: "background 0.3s",
              }}>
                {isDone ? (
                  <svg width="14" height="14" fill="none" viewBox="0 0 24 24">
                    <path d="M20 6L9 17l-5-5" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : (
                  <StepIcon type={step.icon} active={isActive} />
                )}
              </div>
              <span style={{
                fontSize: "0.82rem",
                fontWeight: isActive ? 600 : 500,
                color: isActive ? "var(--orange)" : isDone ? "var(--success)" : "var(--text-muted)",
              }}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
