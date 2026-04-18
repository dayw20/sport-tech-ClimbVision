import { useRef } from "react";
import { Icon } from "./Icon";
import { Btn } from "./Btn";
import { StatusPill } from "./StatusPill";
import { mono } from "../styles/tokens";

export function CalibrationModal({ open, onClose, imageSrc, rectifiedSrc, refPoints, setRefPoints, status, onConfirm, saving }) {
  const imgRef = useRef(null);
  if (!open) return null;
  const labels = ["Top-left", "Top-right", "Bottom-right", "Bottom-left"];

  function handleImageClick(e) {
    if (!imageSrc || refPoints.length >= 4 || !imgRef.current) return;
    const img = imgRef.current;
    const rect = img.getBoundingClientRect();
    const scaleX = img.naturalWidth / rect.width;
    const scaleY = img.naturalHeight / rect.height;
    setRefPoints([...refPoints, [
      (e.clientX - rect.left) * scaleX,
      (e.clientY - rect.top)  * scaleY,
    ]]);
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(26,26,26,0.55)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 100, padding: 24, backdropFilter: "blur(6px)",
    }}>
      <div style={{
        width: "min(840px, 96vw)", maxHeight: "92vh", overflow: "auto",
        background: "var(--surface)", borderRadius: 14,
        border: "1px solid var(--border)",
        boxShadow: "0 24px 60px -20px rgba(0,0,0,0.25)",
      }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "flex-start",
          padding: "20px 24px", borderBottom: "1px solid var(--border)",
        }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
              <span style={{ ...mono, fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
                Step 02 / Calibrate
              </span>
              <StatusPill status={status==="ready" ? "ready" : "idle"}
                          label={status==="ready" ? "Model ready" : "Awaiting points"}/>
            </div>
            <h2 style={{ margin: 0, fontSize: 19, fontWeight: 600, letterSpacing: "-0.02em" }}>
              Reference plane calibration
            </h2>
            <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--muted)", maxWidth: 620 }}>
              Review the model's auto-suggestion. If it's off, clear the points and click the four corners of the wall —
              top-left, top-right, bottom-right, bottom-left.
            </p>
          </div>
          <Btn variant="ghost" size="sm" icon={<Icon.X/>} onClick={onClose}>Close</Btn>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
          <div style={{ padding: 20, borderRight: "1px solid var(--border)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Reference frame</div>
              <span style={{ ...mono, fontSize: 11, color: "var(--muted)" }}>
                {refPoints.length} / 4 points
              </span>
            </div>
            <div style={{
              position: "relative", background: "var(--surface-2)",
              borderRadius: 10, overflow: "hidden", border: "1px solid var(--border)",
              aspectRatio: "3/4", maxHeight: 320, margin: "0 auto",
            }}>
              {imageSrc ? (
                <>
                  <img ref={imgRef} src={imageSrc} alt="reference"
                    onClick={handleImageClick}
                    style={{
                      position: "absolute", inset: 0, width: "100%", height: "100%",
                      objectFit: "cover",
                      cursor: refPoints.length < 4 ? "crosshair" : "default",
                    }}/>
                  {refPoints.map(([x, y], i) => {
                    const img = imgRef.current;
                    if (!img) return null;
                    const rect = img.getBoundingClientRect();
                    return (
                      <div key={i} style={{
                        position: "absolute",
                        left: (x / img.naturalWidth) * rect.width,
                        top:  (y / img.naturalHeight) * rect.height,
                        transform: "translate(-50%, -50%)",
                        width: 22, height: 22, borderRadius: "50%",
                        background: "var(--accent)", color: "#fff",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600,
                        boxShadow: "0 0 0 2px #fff, 0 2px 8px rgba(0,0,0,0.25)",
                        pointerEvents: "none",
                      }}>{i+1}</div>
                    );
                  })}
                </>
              ) : (
                <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted-2)" }}>
                  Loading reference frame…
                </div>
              )}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 14 }}>
              {labels.map((l, i) => {
                const done = i < refPoints.length;
                return (
                  <div key={i} style={{
                    display: "flex", alignItems: "center", gap: 8, fontSize: 12,
                    padding: "6px 10px",
                    background: done ? "var(--accent-soft)" : "var(--surface-2)",
                    borderRadius: 6,
                    color: done ? "var(--accent-ink)" : "var(--muted)",
                  }}>
                    <span style={{
                      width: 18, height: 18, borderRadius: "50%",
                      background: done ? "var(--accent)" : "transparent",
                      border: done ? "none" : "1px dashed var(--muted-2)",
                      color: "#fff",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600,
                    }}>{done ? <Icon.Check/> : i+1}</span>
                    <span style={{ fontWeight: done ? 500 : 400 }}>{l}</span>
                  </div>
                );
              })}
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 14, justifyContent: "space-between" }}>
              <Btn size="sm" variant="ghost" icon={<Icon.Reset/>} onClick={() => setRefPoints([])}>
                Clear points
              </Btn>
              <div style={{ display: "flex", gap: 8 }}>
                <Btn size="sm" variant="secondary" onClick={onClose} disabled={saving}>Cancel</Btn>
                <Btn size="sm" variant="primary" disabled={refPoints.length !== 4 || saving} onClick={onConfirm}>
                  {saving ? "Saving…" : "Save calibration"}
                </Btn>
              </div>
            </div>
          </div>

          <div style={{ padding: 20, background: "var(--bg)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Rectified plane</div>
              <span style={{ ...mono, fontSize: 11, color: "var(--muted)" }}>Preview</span>
            </div>
            <div style={{
              position: "relative", background: "var(--surface)",
              borderRadius: 10, overflow: "hidden", border: "1px solid var(--border)",
              aspectRatio: "3/4", maxHeight: 320, margin: "0 auto",
            }}>
              {status === "ready" && rectifiedSrc ? (
                <img src={rectifiedSrc} alt="rectified"
                  style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain" }}/>
              ) : (
                <div style={{
                  position: "absolute", inset: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexDirection: "column", gap: 10,
                  color: "var(--muted-2)", fontSize: 13,
                }}>
                  <Icon.Grid style={{ width: 28, height: 28, opacity: 0.5 }}/>
                  <span>Save calibration to preview</span>
                </div>
              )}
            </div>
            <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--ink-2)" }}>
              <div style={{ ...mono, fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
                How it works
              </div>
              Four corners define a homography. Detected holds and pose joints get projected onto this rectified plane so every frame shares one coordinate system.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
