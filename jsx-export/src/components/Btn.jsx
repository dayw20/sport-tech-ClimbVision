export function Btn({ variant="secondary", size="md", disabled, onClick, children, icon, style }) {
  const bg = {
    primary:   "var(--ink)",
    accent:    "var(--accent)",
    secondary: "var(--surface)",
    ghost:     "transparent",
    danger:    "var(--surface)",
  }[variant];
  const color = {
    primary:   "#fff",
    accent:    "#fff",
    secondary: "var(--ink)",
    ghost:     "var(--ink-2)",
    danger:    "var(--err)",
  }[variant];
  const border = {
    primary:   "1px solid var(--ink)",
    accent:    "1px solid var(--accent)",
    secondary: "1px solid var(--border-strong)",
    ghost:     "1px solid transparent",
    danger:    "1px solid var(--err-soft)",
  }[variant];
  const pad = size === "sm" ? "6px 10px" : size === "lg" ? "12px 18px" : "8px 14px";
  const fs = size === "sm" ? 12 : 13;

  return (
    <button type="button" onClick={onClick} disabled={disabled}
      style={{
        display: "inline-flex", alignItems: "center", gap: 7, justifyContent: "center",
        background: bg, color, border, borderRadius: 8,
        padding: pad, fontSize: fs, fontWeight: 500, letterSpacing: "-0.005em",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.4 : 1,
        fontFamily: "var(--font-ui)",
        transition: "background 0.15s, border-color 0.15s, transform 0.1s",
        ...style,
      }}
      onMouseDown={(e) => !disabled && (e.currentTarget.style.transform = "scale(0.98)")}
      onMouseUp={(e) => (e.currentTarget.style.transform = "scale(1)")}
      onMouseLeave={(e) => (e.currentTarget.style.transform = "scale(1)")}
    >
      {icon}{children}
    </button>
  );
}
