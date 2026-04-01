import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const btn = {
  base: {
    border: "none",
    borderRadius: 8,
    padding: "10px 18px",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    transition: "opacity 0.15s",
  },
  primary: { background: "#2563eb", color: "#fff" },
  success: { background: "#16a34a", color: "#fff" },
  neutral: { background: "#f3f4f6", color: "#374151", border: "1px solid #d1d5db" },
  danger:  { background: "#dc2626", color: "#fff" },
  small:   { padding: "6px 12px", fontSize: 13 },
};

function Btn({ variant = "neutral", size, disabled, onClick, children, style }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        ...btn.base,
        ...btn[variant],
        ...(size === "sm" ? btn.small : {}),
        opacity: disabled ? 0.45 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        ...style,
      }}
    >
      {children}
    </button>
  );
}

function StatusBadge({ status }) {
  const map = {
    ready:   { bg: "#dcfce7", color: "#15803d", label: "Ready" },
    error:   { bg: "#fee2e2", color: "#b91c1c", label: "Error" },
    not_set: { bg: "#f3f4f6", color: "#6b7280", label: "Not set" },
  };
  const s = map[status] || map["not_set"];
  return (
    <span style={{
      background: s.bg, color: s.color,
      borderRadius: 99, padding: "2px 10px", fontSize: 12, fontWeight: 600,
    }}>
      {s.label}
    </span>
  );
}

function CalibrationModal({ open, imageSrc, rectifiedSrc, calibrationStatus, refPoints, setRefPoints, onClose, onConfirm, isSaving }) {
  const refImgRef = useRef(null);
  if (!open) return null;

  function handleImageClick(e) {
    if (!imageSrc || refPoints.length >= 4 || !refImgRef.current) return;
    const rect = refImgRef.current.getBoundingClientRect();
    const scaleX = refImgRef.current.naturalWidth / rect.width;
    const scaleY = refImgRef.current.naturalHeight / rect.height;
    setRefPoints((prev) => [...prev, [
      (e.clientX - rect.left) * scaleX,
      (e.clientY - rect.top)  * scaleY,
    ]]);
  }

  const labels = ["Top-left", "Top-right", "Bottom-right", "Bottom-left"];

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 9999, padding: 20,
    }}>
      <div style={{
        width: "min(1180px, 96vw)", maxHeight: "92vh", overflow: "auto",
        background: "#fff", borderRadius: 16, padding: 24,
        boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
      }}>

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 20 }}>Reference Plane Calibration</h2>
            <p style={{ margin: "6px 0 0", fontSize: 14, color: "#6b7280" }}>
              Review the model suggestion first. If it looks wrong, clear it and click 4 corners in order: top-left → top-right → bottom-right → bottom-left
            </p>
          </div>
          <Btn variant="neutral" size="sm" onClick={onClose}>✕ Close</Btn>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 20, alignItems: "start" }}>

          {/* Left: image click */}
          <div style={{ background: "#f8fafc", border: "1px solid #e5e7eb", borderRadius: 12, padding: 16, display: "grid", gap: 14 }}>
            <div style={{ fontWeight: 600, fontSize: 15 }}>
              Step 1 — Review Or Select 4 Corner Points
              <span style={{ marginLeft: 10, fontWeight: 400, color: "#6b7280", fontSize: 13 }}>
                {refPoints.length} / 4 selected
              </span>
            </div>

            {calibrationStatus === "ready" && refPoints.length === 4 && (
              <div style={{ background: "#eff6ff", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#1d4ed8" }}>
                Model calibration is already applied. Close this modal if it looks correct, or clear the points and save a manual override.
              </div>
            )}

            <div style={{
              height: "55vh", minHeight: 360, background: "#f3f4f6", borderRadius: 10,
              overflow: "hidden", position: "relative", display: "flex",
              alignItems: "center", justifyContent: "center", padding: 10,
            }}>
              {imageSrc ? (
                <div style={{ position: "relative", display: "inline-block" }}>
                  <img
                    ref={refImgRef}
                    src={imageSrc}
                    alt="reference frame"
                    onClick={handleImageClick}
                    style={{
                      maxWidth: "100%", maxHeight: "62vh", display: "block", borderRadius: 8,
                      cursor: refPoints.length < 4 ? "crosshair" : "default",
                    }}
                  />
                  {refPoints.map(([x, y], idx) => {
                    const img = refImgRef.current;
                    if (!img) return null;
                    const rect = img.getBoundingClientRect();
                    return (
                      <div key={idx} style={{
                        position: "absolute",
                        left: (x / img.naturalWidth) * rect.width,
                        top:  (y / img.naturalHeight) * rect.height,
                        width: 22, height: 22, borderRadius: "50%",
                        background: "#ef4444", color: "#fff",
                        fontSize: 11, fontWeight: 700,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        transform: "translate(-50%, -50%)",
                        pointerEvents: "none", boxShadow: "0 0 0 2px white",
                      }} title={labels[idx]}>
                        {idx + 1}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ color: "#9ca3af" }}>Loading reference frame...</div>
              )}
            </div>

            {/* Point checklist */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              {labels.map((label, idx) => (
                <div key={idx} style={{
                  display: "flex", alignItems: "center", gap: 8,
                  fontSize: 13, color: idx < refPoints.length ? "#15803d" : "#9ca3af",
                }}>
                  <span style={{
                    width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
                    background: idx < refPoints.length ? "#ef4444" : "#e5e7eb",
                    color: idx < refPoints.length ? "#fff" : "#9ca3af",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 10, fontWeight: 700,
                  }}>{idx + 1}</span>
                  {label} {idx < refPoints.length ? "✓" : ""}
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <Btn variant="neutral" size="sm" onClick={() => setRefPoints([])}>Clear Points</Btn>
              <Btn variant="neutral" size="sm" onClick={onClose} disabled={isSaving}>Cancel</Btn>
              <Btn
                variant="primary"
                disabled={refPoints.length !== 4 || isSaving}
                onClick={onConfirm}
              >
                {isSaving ? "Saving..." : "Save Calibration"}
              </Btn>
            </div>
          </div>

          {/* Right: preview */}
          <div style={{ background: "#f8fafc", border: "1px solid #e5e7eb", borderRadius: 12, padding: 16, display: "grid", gap: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontWeight: 600, fontSize: 15 }}>Step 2 — Preview Reference Plane</span>
              <StatusBadge status={calibrationStatus} />
            </div>

            <div style={{
              height: "55vh", minHeight: 360,
              background: rectifiedSrc ? "#fff" : "#f3f4f6",
              border: rectifiedSrc ? "1px solid #e5e7eb" : "1px dashed #d1d5db",
              borderRadius: 10, overflow: "hidden",
              display: "flex", alignItems: "center", justifyContent: "center", padding: 10,
            }}>
              {rectifiedSrc ? (
                <img src={rectifiedSrc} alt="reference plane" style={{ maxWidth: "100%", maxHeight: "62vh", objectFit: "contain" }} />
              ) : (
                <div style={{ color: "#9ca3af", textAlign: "center", fontSize: 14 }}>
                  Confirm calibration to preview the reference plane.
                </div>
              )}
            </div>

            {calibrationStatus === "ready" && (
              <div style={{ background: "#dcfce7", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#15803d" }}>
                Calibration is ready. Close this modal and use the <b>Run Hold Detection</b> or <b>Run Pose</b> buttons.
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}

export default function App() {
  const TOP_BLOCK_MIN_H = 120;
  const [file, setFile]     = useState(null);
  const [job, setJob]       = useState(null);
  const [statusText, setStatusText] = useState("");
  const [error, setError]   = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [debugView, setDebugView] = useState("projected");

  const [refPoints, setRefPoints]                     = useState([]);
  const [isCalibrationModalOpen, setIsCalibrationModalOpen] = useState(false);
  const [isSavingCalibration, setIsSavingCalibration] = useState(false);
  const [isRunningHolds, setIsRunningHolds]           = useState(false);
  const [isRunningPose, setIsRunningPose]             = useState(false);
  const [isRunningCombine, setIsRunningCombine]       = useState(false);
  const [combineRadiusPx, setCombineRadiusPx]         = useState(0);
  const [combineMinFrames, setCombineMinFrames]       = useState(3);

  const gridRef     = useRef(null);
  const draggingRef = useRef(false);
  const [split, setSplit] = useState(0.6);
  const pollTimerRef = useRef(null);

  const jobId        = job?.id;
  const calibReady   = job?.calibration_status === "ready";
  const canSubmit    = useMemo(() => !!file && !isUploading, [file, isUploading]);

  const ts = (url) => url ? `${url}?t=${encodeURIComponent(job?.updated_at || Date.now())}` : null;
  const resultImageSrc       = ts(job?.result_image_url);
  const referenceRectifiedSrc = ts(job?.reference_rectified_image_url);
  const referenceFrameSrc    = ts(job?.reference_frame_image_url);
  const holdOverlaySrc       = ts(job?.hold_overlay_image_url);
  const hasDisplayImage      = !!(job?.result_image_url || job?.reference_rectified_image_url);

  const currentDisplaySrc =
    debugView === "overlay"    ? holdOverlaySrc :
    debugView === "reference"  ? referenceFrameSrc :
    debugView === "rectified"  ? referenceRectifiedSrc :
    resultImageSrc || referenceRectifiedSrc || holdOverlaySrc || referenceFrameSrc;

  useEffect(() => () => { if (pollTimerRef.current) clearInterval(pollTimerRef.current); }, []);

  useEffect(() => {
    if (Array.isArray(job?.reference_quad) && job.reference_quad.length === 4) {
      setRefPoints(job.reference_quad);
    }
  }, [job?.reference_quad]);

  useEffect(() => {
    const onMove = (e) => {
      if (!draggingRef.current) return;
      const el = gridRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      setSplit(Math.max(0.28, Math.min(0.72, (e.clientX - rect.left) / rect.width)));
    };
    const onUp = () => { draggingRef.current = false; };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, []);

  async function apiFetch(url, opts = {}) {
    const resp = await fetch(`${API_BASE}${url}`, opts);
    if (!resp.ok) { const t = await resp.text(); throw new Error(`${resp.status} ${t}`); }
    return resp.json();
  }

  function startPolling(id) {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = setInterval(async () => {
      try {
        const latest = await apiFetch(`/api/jobs/${id}/`);
        setJob(latest);
        if (latest.status === "done") {
          setStatusText("Done ✅");
          clearInterval(pollTimerRef.current); pollTimerRef.current = null;
        } else if (latest.status === "error") {
          setStatusText("Error ❌");
          clearInterval(pollTimerRef.current); pollTimerRef.current = null;
        } else {
          setStatusText(`Processing... (${latest.status})`);
        }
      } catch (e) { setError(String(e.message || e)); }
    }, 1000);
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (!file) return;
    setJob(null); setRefPoints([]); setStatusText(""); setError("");
    setIsCalibrationModalOpen(false); setIsUploading(true);

    try {
      const form = new FormData();
      form.append("video", file);
      setStatusText("Uploading...");
      const created = await apiFetch("/api/jobs/", { method: "POST", body: form });
      setJob(created);

      setStatusText("Generating reference frame...");
      const withRef = await apiFetch(`/api/jobs/${created.id}/reference-frame/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ t: 0.5 }),
      });
      setJob(withRef);
      setRefPoints(Array.isArray(withRef.reference_quad) ? withRef.reference_quad : []);
      setStatusText(
        withRef.calibration_status === "ready"
          ? "Model calibration ready. Review it, or clear the points to set calibration manually."
          : "Reference frame ready. Select 4 calibration points."
      );
      setIsCalibrationModalOpen(true);
    } catch (e) {
      setError(String(e.message || e)); setStatusText("");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleConfirmCalibration() {
    if (!job?.id || refPoints.length !== 4) return;
    try {
      setIsSavingCalibration(true); setError("");
      setStatusText("Saving calibration...");
      const updated = await apiFetch(`/api/jobs/${job.id}/reference-quad/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quad: refPoints }),
      });
      setJob(updated);
      setRefPoints(Array.isArray(updated.reference_quad) ? updated.reference_quad : refPoints);
      setStatusText("Calibration ready ✅ — now run Hold Detection or Pose.");
    } catch (e) {
      setError(String(e.message || e)); setStatusText("");
    } finally {
      setIsSavingCalibration(false);
    }
  }

  async function handleRunHoldDetection() {
    if (!jobId) return;
    try {
      setError(""); setIsRunningHolds(true);
      setStatusText("Running hold detection...");
      const updated = await apiFetch(`/api/jobs/${jobId}/projected-holds/`, { method: "POST" });
      setJob(updated);
      setDebugView("projected");
      setStatusText("Hold detection done ✅");
    } catch (e) {
      setError(String(e.message || e)); setStatusText("Hold detection failed ❌");
    } finally {
      setIsRunningHolds(false);
    }
  }

  async function handleRunCombine() {
    if (!jobId) return;
    try {
      setError(""); setIsRunningCombine(true);
      setStatusText("Combining holds and pose...");
      const updated = await apiFetch(`/api/jobs/${jobId}/combine/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ radius_px: combineRadiusPx, min_consecutive_frames: combineMinFrames }),
      });
      setJob(updated);
      setDebugView("projected");
      setStatusText("Combination done ✅");
    } catch (e) {
      setError(String(e.message || e)); setStatusText("Combination failed ❌");
    } finally {
      setIsRunningCombine(false);
    }
  }

  async function handleRunPose() {
    if (!jobId) return;
    try {
      setError(""); setIsRunningPose(true);
      setStatusText("Running pose detection... this may take a moment.");
      const updated = await apiFetch(`/api/jobs/${jobId}/pose-trajectory/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pose_model: "lite" }),
      });
      setJob(updated);
      setDebugView("projected");
      setStatusText("Pose detection done ✅");
    } catch (e) {
      setError(String(e.message || e)); setStatusText("Pose detection failed ❌");
    } finally {
      setIsRunningPose(false);
    }
  }

  function onReset() {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = null;
    setFile(null); setJob(null); setRefPoints([]); setStatusText(""); setError("");
    setIsUploading(false); setIsCalibrationModalOpen(false); setIsSavingCalibration(false);
    setIsRunningHolds(false); setIsRunningPose(false); setIsRunningCombine(false);
  }

  return (
    <div style={{ maxWidth: 1200, margin: "24px auto", padding: "0 12px", fontFamily: "system-ui, -apple-system" }}>
      <CalibrationModal
        open={isCalibrationModalOpen}
        imageSrc={referenceFrameSrc}
        rectifiedSrc={referenceRectifiedSrc}
        calibrationStatus={job?.calibration_status}
        refPoints={refPoints}
        setRefPoints={setRefPoints}
        onClose={() => setIsCalibrationModalOpen(false)}
        onConfirm={handleConfirmCalibration}
        isSaving={isSavingCalibration}
      />

      <header style={{ textAlign: "center", marginBottom: 10 }}>
        <h1 className="appTitle">ClimbVision Route Analyzer</h1>
      </header>

      <div ref={gridRef} style={{ display: "grid", gridTemplateColumns: `${split}fr 10px ${1 - split}fr`, gap: 16, alignItems: "stretch" }}>

        {/* ── Left panel ── */}
        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16, display: "flex", flexDirection: "column" }}>
          <div style={{ minHeight: TOP_BLOCK_MIN_H }}>
            <h2 style={{ marginTop: 0, fontSize: 18 }}>Upload Video</h2>
            <form onSubmit={onSubmit} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <input type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              <Btn variant="primary" disabled={!canSubmit} onClick={onSubmit}>
                {isUploading ? "Uploading..." : "Upload & Start"}
              </Btn>
              <Btn variant="danger" onClick={onReset}>Reset</Btn>
            </form>
            {file && (
              <p style={{ marginTop: 10, marginBottom: 0, fontSize: 13, color: "#555" }}>
                {file.name} ({Math.round(file.size / 1024 / 1024)} MB)
              </p>
            )}
          </div>

          <hr style={{ margin: "16px 0", border: "none", borderTop: "1px solid #eee" }} />

          <h2 style={{ marginTop: 0, fontSize: 18 }}>Video Preview</h2>
          <div style={{ width: "100%", display: "flex", justifyContent: "center" }}>
            <div style={{
              aspectRatio: "3 / 4", maxHeight: 500, height: "min(500px, 70vh)", width: "auto", maxWidth: "100%",
              background: "#f3f4f6", borderRadius: 12, overflow: "hidden",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              {job?.video_url ? (
                <video src={job.video_url} controls style={{ width: "100%", height: "100%", objectFit: "contain" }} />
              ) : (
                <div style={{ color: "#bbb", fontSize: 14, textAlign: "center", padding: 16 }}>
                  Upload a video to preview it here.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Divider ── */}
        <div
          onMouseDown={() => (draggingRef.current = true)}
          style={{ height: "100%", cursor: "col-resize", borderRadius: 999, background: "#eaeaea" }}
        />

        {/* ── Right panel ── */}
        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16, display: "flex", flexDirection: "column" }}>
          <div style={{ minHeight: TOP_BLOCK_MIN_H }}>

            {/* Status bar */}
            {(statusText || error) && (
              <div style={{
                marginBottom: 14, padding: "10px 14px", borderRadius: 8, fontSize: 13,
                background: error ? "#fee2e2" : "#eff6ff",
                color:      error ? "#b91c1c"  : "#1d4ed8",
                border:     `1px solid ${error ? "#fca5a5" : "#bfdbfe"}`,
              }}>
                {error || statusText}
              </div>
            )}

            {/* Calibration */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                <h2 style={{ margin: 0, fontSize: 18 }}>Calibration</h2>
                <StatusBadge status={job?.calibration_status || "not_set"} />
              </div>
              <Btn
                variant="neutral"
                disabled={!referenceFrameSrc}
                onClick={() => setIsCalibrationModalOpen(true)}
              >
                {calibReady ? "✏️ Re-calibrate" : "📐 Open Calibration"}
              </Btn>
            </div>

            <hr style={{ margin: "0 0 16px", border: "none", borderTop: "1px solid #eee" }} />

            {/* Action buttons */}
            <h2 style={{ marginTop: 0, marginBottom: 12, fontSize: 18 }}>Run Analysis</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>

              <button
                type="button"
                onClick={handleRunHoldDetection}
                disabled={!calibReady || isRunningHolds}
                style={{
                  ...btn.base,
                  background: (!calibReady || isRunningHolds) ? "#e5e7eb" : "#16a34a",
                  color:      (!calibReady || isRunningHolds) ? "#9ca3af" : "#fff",
                  opacity: 1,
                  cursor: (!calibReady || isRunningHolds) ? "not-allowed" : "pointer",
                  display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center",
                  gap: 4, padding: "14px 12px", fontSize: 14,
                }}
              >
                <span style={{ fontSize: 24 }}>🪨</span>
                {isRunningHolds ? "Detecting..." : "Run Hold Detection"}
              </button>

              <button
                type="button"
                onClick={handleRunPose}
                disabled={!calibReady || isRunningPose}
                style={{
                  ...btn.base,
                  background: (!calibReady || isRunningPose) ? "#e5e7eb" : "#7c3aed",
                  color:      (!calibReady || isRunningPose) ? "#9ca3af" : "#fff",
                  opacity: 1,
                  cursor: (!calibReady || isRunningPose) ? "not-allowed" : "pointer",
                  display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center",
                  gap: 4, padding: "14px 12px", fontSize: 14,
                }}
              >
                <span style={{ fontSize: 24 }}>🧗</span>
                {isRunningPose ? "Running..." : "Run Pose"}
              </button>

            </div>

            {/* Combine — needs both holds + pose results */}
            {(() => {
              const hasHolds = !!job?.projected_holds_json;
              const hasPose  = !!job?.projected_pose_json;
              const canCombine = hasHolds && hasPose && !isRunningCombine;
              return (
                <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
                  {/* Parameter controls */}
                  <div style={{
                    display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center",
                    padding: "8px 12px", background: "#f8fafc",
                    border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 13,
                  }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      Min consecutive frames
                      <input
                        type="number" min={1} max={60} value={combineMinFrames}
                        onChange={e => setCombineMinFrames(Math.max(1, parseInt(e.target.value) || 1))}
                        style={{ width: 52, padding: "2px 6px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 13 }}
                      />
                    </label>
                    <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      Radius buffer (px)
                      <input
                        type="number" min={0} max={100} value={combineRadiusPx}
                        onChange={e => setCombineRadiusPx(Math.max(0, parseInt(e.target.value) || 0))}
                        style={{ width: 52, padding: "2px 6px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 13 }}
                      />
                    </label>
                  </div>

                  <button
                    type="button"
                    onClick={handleRunCombine}
                    disabled={!canCombine}
                    style={{
                      ...btn.base,
                      background: canCombine ? "#d97706" : "#e5e7eb",
                      color:      canCombine ? "#fff"    : "#9ca3af",
                      opacity: 1,
                      cursor:  canCombine ? "pointer" : "not-allowed",
                      display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                    }}
                  >
                    <span style={{ fontSize: 18 }}>🔗</span>
                    {isRunningCombine ? "Combining..." : "Combine Holds + Pose"}
                    {!hasHolds && <span style={{ fontSize: 11, opacity: 0.7 }}>(run Hold Detection first)</span>}
                    {hasHolds && !hasPose && <span style={{ fontSize: 11, opacity: 0.7 }}>(run Pose first)</span>}
                  </button>
                </div>
              );
            })()}

            {!calibReady && jobId && (
              <p style={{ fontSize: 12, color: "#9ca3af", margin: 0 }}>
                Complete calibration first to enable analysis.
              </p>
            )}

            <hr style={{ margin: "16px 0", border: "none", borderTop: "1px solid #eee" }} />

            {/* View selector */}
            <div style={{ marginBottom: 12, fontSize: 13, fontWeight: 600, color: "#374151" }}>View</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[
                { key: "projected", label: "📍 Projected" },
                { key: "rectified", label: "🔲 Rectified" },
                { key: "overlay",   label: "🪨 Hold Detection", disabled: !holdOverlaySrc },
                { key: "reference", label: "🖼 Reference",    disabled: !referenceFrameSrc },
              ].map(({ key, label, disabled }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setDebugView(key)}
                  disabled={disabled}
                  style={{
                    ...btn.base, ...btn.small,
                    background: debugView === key ? "#1e40af" : "#f3f4f6",
                    color:      debugView === key ? "#fff"    : "#374151",
                    border:     debugView === key ? "none"    : "1px solid #d1d5db",
                    opacity: disabled ? 0.4 : 1,
                    cursor:  disabled ? "not-allowed" : "pointer",
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <hr style={{ margin: "16px 0", border: "none", borderTop: "1px solid #eee" }} />

          {/* Result image */}
          <h2 style={{ marginTop: 0, fontSize: 18 }}>Result</h2>
          <div style={{
            width: "100%", aspectRatio: "9 / 16",
            maxHeight: 500, height: "min(500px, 70vh)", maxWidth: "100%", margin: "0 auto",
            background: hasDisplayImage ? "#fff" : "#f3f4f6",
            border: hasDisplayImage ? "1px solid #eee" : "1px dashed #d0d5dd",
            borderRadius: 12, overflow: "hidden",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            {currentDisplaySrc ? (
              <img src={currentDisplaySrc} alt={`view: ${debugView}`} style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            ) : (
              <div style={{ color: "#9ca3af", fontSize: 14, textAlign: "center", padding: 16, lineHeight: 1.7 }}>
                {!jobId
                  ? "Upload a video to get started."
                  : !calibReady
                  ? "Complete calibration, then run Hold Detection or Pose."
                  : "Run Hold Detection or Pose to see results here."}
              </div>
            )}
          </div>

          {/* Debug links */}
          {(referenceFrameSrc || holdOverlaySrc) && (
            <div style={{ marginTop: 14, display: "grid", gap: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>Debug Info</div>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 13 }}>
                {referenceFrameSrc  && <a href={referenceFrameSrc}    target="_blank" rel="noreferrer">Reference frame ↗</a>}
                {holdOverlaySrc     && <a href={holdOverlaySrc}       target="_blank" rel="noreferrer">Hold detection ↗</a>}
                {referenceRectifiedSrc && <a href={referenceRectifiedSrc} target="_blank" rel="noreferrer">Rectified plane ↗</a>}
                {job?.result_image_url && <a href={job.result_image_url} target="_blank" rel="noreferrer">Result image ↗</a>}
              </div>
              <div style={{ fontSize: 12, color: "#6b7280" }}>
                Holds detected: <b>{job?.holds_json?.num_holds ?? "—"}</b>
                &nbsp;·&nbsp;
                Holds projected: <b>{job?.projected_holds_json?.num_holds ?? "—"}</b>
                &nbsp;·&nbsp;
                Pose spots: <b>{job?.projected_pose_json?.num_spots ?? "—"}</b>
                {job?.combination_json && (
                  <span>
                    &nbsp;·&nbsp;
                    Used holds: <b>{job.combination_json.num_holds_used}/{job.combination_json.num_holds_total}</b>
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
