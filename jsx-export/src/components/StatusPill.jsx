import { Icon } from "./Icon";

export function Spinner({ color="currentColor", size=10 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" style={{ animation: "cv-spin 0.8s linear infinite" }}>
      <circle cx="8" cy="8" r="6" stroke={color} strokeWidth="2" fill="none" opacity="0.25"/>
      <path d="M8 2a6 6 0 016 6" stroke={color} strokeWidth="2" fill="none" strokeLinecap="round"/>
    </svg>
  );
}

export function StatusPill({ status, label }) {
  const map = {
    ready:   { bg: "var(--ok-soft)",     fg: "var(--ok)" },
    error:   { bg: "var(--err-soft)",    fg: "var(--err)" },
    active:  { bg: "var(--accent-soft)", fg: "var(--accent-ink)" },
    idle:    { bg: "var(--surface-2)",   fg: "var(--muted)" },
    running: { bg: "var(--accent-soft)", fg: "var(--accent-ink)" },
  };
  const s = map[status] || map.idle;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      background: s.bg, color: s.fg,
      fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 500,
      textTransform: "uppercase", letterSpacing: "0.08em",
      padding: "3px 8px", borderRadius: 4,
    }}>
      {status === "running" && <Spinner color={s.fg}/>}
      {status === "ready" && <Icon.Dot style={{ color: s.fg }}/>}
      {label}
    </span>
  );
}
