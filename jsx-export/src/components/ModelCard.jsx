import { Icon } from "./Icon";
import { Btn } from "./Btn";
import { StatusPill, Spinner } from "./StatusPill";
import { mono } from "../styles/tokens";

export function ModelCard({ title, sub, model, ready, running, disabled, count, countLabel, onRun, accent }) {
  const accentColor = accent === "blue" ? "oklch(0.45 0.14 240)" : "var(--accent)";
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 8, padding: 12,
      display: "flex", flexDirection: "column", gap: 10,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: "-0.01em" }}>{title}</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 1 }}>{sub}</div>
        </div>
        {ready && <StatusPill status="ready" label="done"/>}
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{ ...mono, fontSize: 10, color: "var(--muted)", padding: "3px 6px", background: "var(--surface-2)", borderRadius: 4, border: "1px solid var(--border)" }}>
          {model}
        </div>
        {ready && count !== null && count !== undefined && (
          <div style={{ ...mono, fontSize: 11, color: accentColor, fontWeight: 600 }}>
            {count} {countLabel}
          </div>
        )}
      </div>
      <Btn size="sm" variant={ready ? "secondary" : "primary"}
           disabled={disabled}
           icon={running ? <Spinner/> : <Icon.Play/>}
           onClick={onRun}
           style={{ width: "100%" }}>
        {running ? "Running…" : ready ? "Re-run" : "Run"}
      </Btn>
    </div>
  );
}
