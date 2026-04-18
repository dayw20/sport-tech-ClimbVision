import React from "react";
import { Icon } from "./Icon";

export function Stepper({ stepStates }) {
  const steps = [
    { key: "upload",    label: "Upload" },
    { key: "calibrate", label: "Calibrate" },
    { key: "analyze",   label: "Analyze" },
    { key: "combine",   label: "Combine" },
  ];
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 0,
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 10, padding: 6,
    }}>
      {steps.map((s, i) => {
        const state = stepStates[s.key];
        const isActive = state === "active";
        const isDone = state === "done";
        return (
          <React.Fragment key={s.key}>
            <div style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "6px 14px", borderRadius: 6,
              background: isActive ? "var(--accent-soft)" : "transparent",
              color: isActive ? "var(--accent-ink)" : isDone ? "var(--ink)" : "var(--muted-2)",
            }}>
              <div style={{
                width: 22, height: 22, borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                background: isDone ? "var(--ink)" : isActive ? "var(--accent)" : "transparent",
                color: isDone || isActive ? "#fff" : "var(--muted-2)",
                border: isDone || isActive ? "none" : "1px dashed var(--border-strong)",
                fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600,
              }}>
                {isDone ? <Icon.Check/> : (i+1).toString().padStart(2,"0")}
              </div>
              <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.1 }}>
                <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.1em", opacity: 0.7 }}>
                  Step {i+1}
                </span>
                <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: "-0.01em", marginTop: 1 }}>
                  {s.label}
                </span>
              </div>
            </div>
            {i < steps.length - 1 && (
              <div style={{ flex: "0 0 24px", height: 1, background: isDone ? "var(--ink)" : "var(--border)" }}/>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
