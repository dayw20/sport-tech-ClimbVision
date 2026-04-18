import { mono } from "../styles/tokens";

export function ParamInput({ label, value, onChange, min, max, hint }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
        <label style={{ ...mono, fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          {label}
        </label>
        <span style={{ fontSize: 10, color: "var(--muted-2)" }}>{hint}</span>
      </div>
      <div style={{
        display: "flex", alignItems: "center",
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 6, overflow: "hidden",
      }}>
        <button onClick={() => onChange(Math.max(min, (Number(value)||0) - 1))}
          style={{ background: "transparent", border: "none", color: "var(--muted)", padding: "6px 10px", cursor: "pointer", fontSize: 14 }}>−</button>
        <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))} min={min} max={max}
          style={{
            flex: 1, width: "100%", textAlign: "center", border: "none", outline: "none",
            background: "transparent",
            fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 500,
            padding: "6px 0", color: "var(--ink)", MozAppearance: "textfield",
          }}/>
        <button onClick={() => onChange(Math.min(max, (Number(value)||0) + 1))}
          style={{ background: "transparent", border: "none", color: "var(--muted)", padding: "6px 10px", cursor: "pointer", fontSize: 14 }}>+</button>
      </div>
    </div>
  );
}
