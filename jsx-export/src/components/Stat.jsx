import { mono } from "../styles/tokens";

export function Stat({ label, value, accent=false }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 2,
      padding: "8px 12px",
      background: accent ? "var(--accent-soft)" : "var(--surface-2)",
      borderRadius: 6, minWidth: 0,
    }}>
      <span style={{ ...mono, fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
        {label}
      </span>
      <span style={{ ...mono, fontSize: 14, fontWeight: 600, color: accent ? "var(--accent-ink)" : "var(--ink)" }}>
        {value}
      </span>
    </div>
  );
}
