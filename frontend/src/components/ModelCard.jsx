import { Icon } from "./Icon";
import { Btn } from "./Btn";
import { StatusPill, Spinner } from "./StatusPill";
import { mono } from "../styles/tokens";

export function ModelCard({ title, sub, model, ready, running, disabled, count, countLabel, onRun, accent }) {
  const accentColor = accent === "blue" ? "oklch(0.45 0.14 240)" : "var(--accent)";
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 8, padding: "8px 10px",
      display: "flex", flexDirection: "column", gap: 6,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: "-0.01em" }}>{title}</div>
        <div style={{ display:"flex", alignItems:"center", gap:6 }}>
          {ready && count !== null && count !== undefined && (
            <div style={{ ...mono, fontSize: 10, color: accentColor, fontWeight: 600 }}>{count} {countLabel}</div>
          )}
          {ready && <StatusPill status="ready" label="done"/>}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{ ...mono, fontSize: 10, color: "var(--muted)", padding: "2px 5px", background: "var(--surface-2)", borderRadius: 4, border: "1px solid var(--border)" }}>
          {model}
        </div>
        <Btn size="sm" variant={ready ? "secondary" : "primary"}
             disabled={disabled}
             icon={running ? <Spinner/> : <Icon.Play/>}
             onClick={onRun}>
          {running ? "Running…" : ready ? "Re-run" : "Run"}
        </Btn>
      </div>
    </div>
  );
}
