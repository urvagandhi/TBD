const IconAlert = () => (
  <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.8" />
    <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

export default function ErrorBanner({ message, onRetry }) {
  if (!message) return null;

  return (
    <div style={{
      background: "var(--error-bg)",
      border: "1px solid rgba(239,68,68,0.2)",
      borderRadius: "var(--radius-sm)",
      padding: "14px 16px",
      animation: "fadeUp 0.3s ease",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ color: "var(--error)", flexShrink: 0, marginTop: 1 }}>
          <IconAlert />
        </div>
        <div>
          <p style={{
            fontSize: "0.85rem", color: "var(--error)", fontWeight: 500,
            lineHeight: 1.5, whiteSpace: "pre-wrap",
          }}>
            {message}
          </p>
          {onRetry && (
            <button
              onClick={onRetry}
              style={{
                marginTop: 10, padding: "6px 16px",
                background: "transparent",
                border: "1.5px solid rgba(239,68,68,0.3)",
                borderRadius: "var(--radius-pill)",
                fontSize: "0.78rem", fontWeight: 600,
                color: "var(--error)", cursor: "pointer",
                fontFamily: "var(--font)",
                transition: "background 0.2s, color 0.2s",
              }}
              onMouseEnter={(e) => { e.target.style.background = "var(--error)"; e.target.style.color = "#fff"; }}
              onMouseLeave={(e) => { e.target.style.background = "transparent"; e.target.style.color = "var(--error)"; }}
            >
              Try Again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
