import { useState, useEffect } from "react";

function ScoreGauge({ score, size = 120 }) {
  const [animated, setAnimated] = useState(0);

  useEffect(() => {
    setAnimated(0);
    const duration = 1000;
    const start = performance.now();
    const animate = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setAnimated(Math.round(eased * score));
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [score]);

  const radius = size * 0.38;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (animated / 100) * circumference;
  const color = score >= 80 ? "var(--success)" : score >= 60 ? "var(--orange)" : "var(--error)";
  const center = size / 2;

  return (
    <div style={{ position: "relative", width: size, height: size, margin: "0 auto" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={center} cy={center} r={radius} fill="none" stroke="var(--border)" strokeWidth="8" />
        <circle
          cx={center} cy={center} r={radius} fill="none"
          stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
          transform={`rotate(-90 ${center} ${center})`}
          style={{ transition: "stroke-dashoffset 0.05s linear" }}
        />
      </svg>
      <div style={{
        position: "absolute", inset: 0,
        display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
      }}>
        <span style={{
          fontSize: size * 0.22, fontWeight: 800, color,
          animation: "countUp 0.5s ease both",
        }}>{animated}</span>
        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 500 }}>/100</span>
      </div>
    </div>
  );
}

export default function ComplianceReport({ report }) {
  if (!report) return null;

  const overall = report.overall_score ?? report.score ?? 0;
  const sections = report.breakdown || report.sections || report.section_scores || {};

  const scoreColor = (s) => {
    if (s >= 80) return "var(--success)";
    if (s >= 60) return "var(--orange)";
    return "var(--error)";
  };

  const scoreBg = (s) => {
    if (s >= 80) return "var(--success-bg)";
    if (s >= 60) return "var(--orange-light)";
    return "var(--error-bg)";
  };

  return (
    <div style={{ animation: "fadeUp 0.5s ease" }}>
      {/* Gauge */}
      <ScoreGauge score={overall} />

      <p style={{
        textAlign: "center", fontSize: "0.82rem", fontWeight: 600,
        color: "var(--text-secondary)", marginTop: 8, marginBottom: 20,
      }}>
        Overall Compliance Score
      </p>

      {/* Section breakdown */}
      {Object.keys(sections).length > 0 && (
        <div>
          <p style={{
            fontSize: "0.72rem", fontWeight: 700, letterSpacing: "1.5px",
            textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 10,
          }}>
            Section Breakdown
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {Object.entries(sections).map(([name, scoreData], i) => {
              const val = typeof scoreData === "object" ? scoreData.score : scoreData;
              return (
                <div key={name} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "10px 12px", borderRadius: "var(--radius-sm)",
                  background: "var(--bg-soft)", border: "1px solid var(--border)",
                  animation: `slideRight 0.3s ease ${i * 0.05}s both`,
                }}>
                  <span style={{
                    fontSize: "0.82rem", fontWeight: 500,
                    color: "var(--text-secondary)", textTransform: "capitalize",
                  }}>
                    {name.replace(/_/g, " ")}
                  </span>
                  <span style={{
                    fontSize: "0.78rem", fontWeight: 700,
                    color: scoreColor(val),
                    background: scoreBg(val),
                    padding: "2px 10px", borderRadius: "var(--radius-pill)",
                  }}>
                    {val}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
