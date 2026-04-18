const VIEWS = [
  { key: "projected", label: "Projected",      desc: "Holds + pose on plane" },
  { key: "clean",     label: "Clean summary",  desc: "Only used holds" },
  { key: "pose",      label: "Pose",           desc: "Body trajectory" },
  { key: "rectified", label: "Rectified",      desc: "Reference plane" },
  { key: "holds",     label: "Hold detection", desc: "Raw hold overlay" },
  { key: "reference", label: "Reference",      desc: "Source frame" },
];

export function ViewTabs({ current, onChange, available }) {
  return (
    <div style={{
      display: "flex", flexWrap: "wrap", gap: 4, padding: 4,
      background: "var(--surface-2)", border: "1px solid var(--border)",
      borderRadius: 8,
    }}>
      {VIEWS.map((v) => {
        const isOn = current === v.key;
        const disabled = !available.has(v.key);
        return (
          <button key={v.key}
            onClick={() => !disabled && onChange(v.key)}
            disabled={disabled}
            style={{
              flex: "1 1 0", minWidth: 80, padding: "6px 10px", borderRadius: 6,
              background: isOn ? "var(--surface)" : "transparent",
              border: isOn ? "1px solid var(--border-strong)" : "1px solid transparent",
              color: disabled ? "var(--muted-2)" : isOn ? "var(--ink)" : "var(--ink-2)",
              fontSize: 12, fontWeight: isOn ? 600 : 500,
              fontFamily: "var(--font-ui)",
              cursor: disabled ? "not-allowed" : "pointer",
              opacity: disabled ? 0.5 : 1,
              textAlign: "left", lineHeight: 1.2,
              boxShadow: isOn ? "0 1px 2px rgba(0,0,0,0.04)" : "none",
              transition: "all 0.12s",
            }}
          >
            <div>{v.label}</div>
            <div style={{ fontSize: 10, color: "var(--muted)", fontWeight: 400, marginTop: 2 }}>
              {v.desc}
            </div>
          </button>
        );
      })}
    </div>
  );
}
