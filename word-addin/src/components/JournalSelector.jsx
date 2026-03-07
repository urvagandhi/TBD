const JOURNALS = [
  { value: "APA 7th Edition", label: "APA 7th Edition", color: "#2563EB" },
  { value: "IEEE", label: "IEEE", color: "#F97316" },
  { value: "Springer", label: "Springer", color: "#10B981" },
  { value: "Vancouver", label: "Vancouver", color: "#8B5CF6" },
  { value: "Chicago", label: "Chicago", color: "#F59E0B" },
];

const IconBook = () => (
  <svg width="22" height="22" fill="none" viewBox="0 0 24 24">
    <path d="M4 19.5A2.5 2.5 0 016.5 17H20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" stroke="currentColor" strokeWidth="1.8" />
  </svg>
);

export default function JournalSelector({ value, onChange, disabled }) {
  return (
    <div style={{ animation: "fadeUp 0.4s ease" }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8, marginBottom: 10,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: "var(--orange-light)", color: "var(--orange)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <IconBook />
        </div>
        <label style={{
          fontSize: "0.87rem", fontWeight: 600, color: "var(--text)",
        }}>
          Target Journal Style
        </label>
      </div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        style={{
          width: "100%", padding: "13px 16px",
          border: "1.5px solid var(--border)", borderRadius: "var(--radius-sm)",
          background: "#fff", color: "var(--text)",
          fontSize: "0.95rem", fontWeight: 500, fontFamily: "var(--font)",
          appearance: "none", cursor: "pointer",
          backgroundImage: `url("data:image/svg+xml,%3Csvg width='12' height='8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%23475569' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E")`,
          backgroundRepeat: "no-repeat", backgroundPosition: "right 16px center",
          transition: "border-color 0.2s, box-shadow 0.2s",
          opacity: disabled ? 0.5 : 1,
        }}
        onFocus={(e) => {
          e.target.style.borderColor = "var(--orange)";
          e.target.style.boxShadow = "var(--shadow-glow)";
        }}
        onBlur={(e) => {
          e.target.style.borderColor = "var(--border)";
          e.target.style.boxShadow = "none";
        }}
      >
        <option value="">Select a style...</option>
        {JOURNALS.map((j) => (
          <option key={j.value} value={j.value}>
            {j.label}
          </option>
        ))}
      </select>
    </div>
  );
}
