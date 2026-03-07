const IconBolt = () => (
  <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
  </svg>
);

export default function FormatButton({ onClick, disabled, loading }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        width: "100%", padding: "15px",
        background: disabled
          ? "linear-gradient(135deg, #d4d4d4, #a3a3a3)"
          : "linear-gradient(135deg, var(--orange), var(--orange-hover))",
        color: "#fff", border: "none", borderRadius: "var(--radius-sm)",
        fontSize: "1rem", fontWeight: 700, fontFamily: "var(--font)",
        cursor: disabled ? "not-allowed" : "pointer",
        boxShadow: disabled ? "none" : "0 6px 20px rgba(249,115,22,0.28)",
        transition: "transform 0.2s, box-shadow 0.2s, opacity 0.2s",
        display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
        opacity: disabled ? 0.5 : 1,
        marginTop: 8,
        animation: "fadeUp 0.4s ease 0.1s both",
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          e.target.style.transform = "translateY(-2px)";
          e.target.style.boxShadow = "0 10px 28px rgba(249,115,22,0.38)";
        }
      }}
      onMouseLeave={(e) => {
        e.target.style.transform = "translateY(0)";
        e.target.style.boxShadow = disabled ? "none" : "0 6px 20px rgba(249,115,22,0.28)";
      }}
    >
      {loading ? (
        <>
          <svg style={{ width: 18, height: 18, animation: "spin 1s linear infinite" }} viewBox="0 0 24 24" fill="none">
            <circle opacity="0.25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path opacity="0.75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Processing...
        </>
      ) : (
        <>
          <IconBolt />
          Format Paper
        </>
      )}
    </button>
  );
}
