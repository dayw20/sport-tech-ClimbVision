import { useState, useEffect, useMemo } from "react";
import { Icon } from "./components/Icon";
import { Btn } from "./components/Btn";
import { StatusPill, Spinner } from "./components/StatusPill";
import { Stepper } from "./components/Stepper";
import { CalibrationModal } from "./components/CalibrationModal";
import { ViewTabs } from "./components/ViewTabs";
import { ModelCard } from "./components/ModelCard";
import { ParamInput } from "./components/ParamInput";
import { Stat } from "./components/Stat";
import { mono, card } from "./styles/tokens";
import "./App.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const VIEW_KEYS = ["projected", "clean", "pose", "rectified", "holds", "reference"];

export default function App() {
  const [file, setFile] = useState(null);
  const [job, setJob] = useState(null);
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState("");
  const [view, setView] = useState("projected");
  const [modalOpen, setModalOpen] = useState(false);
  const [refPoints, setRefPoints] = useState([]);
  const [isSavingCalibration, setIsSavingCalibration] = useState(false);
  const [isRunningHolds, setIsRunningHolds] = useState(false);
  const [isRunningPose, setIsRunningPose] = useState(false);
  const [isRunningCombine, setIsRunningCombine] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [minFrames, setMinFrames] = useState(3);
  const [radiusPx, setRadiusPx] = useState(0);

  const jobId = job?.id;
  const calibReady = job?.calibration_status === "ready";
  const hasHolds = !!job?.projected_holds_json;
  const hasPose = !!job?.projected_pose_json;
  const hasCombine = !!job?.combination_json;
  const canCombine = hasHolds && hasPose;

  // Derive pipeline stage (0-4) from job state
  const stage = !job ? 0
    : !calibReady ? 1
    : hasCombine ? 4
    : (hasHolds || hasPose) ? 3
    : 2;

  const stepStates = {
    upload:    stage >= 1 ? "done" : "active",
    calibrate: stage >= 2 ? "done" : stage === 1 ? "active" : "idle",
    analyze:   stage >= 3 ? "done" : stage === 2 ? "active" : "idle",
    combine:   stage >= 4 ? "done" : stage === 3 ? "active" : "idle",
  };

  const available = useMemo(() => {
    const s = new Set();
    if (job?.reference_frame_image_url) s.add("reference");
    if (job?.reference_rectified_image_url) s.add("rectified");
    if (job?.hold_overlay_image_url) s.add("holds");
    if (job?.pose_result_image_url) s.add("pose");
    if (job?.result_image_url) s.add("projected");
    if (job?.clean_summary_image_url) s.add("clean");
    return s;
  }, [job]);

  const ts = (url) => url ? `${url}?t=${encodeURIComponent(job?.updated_at || Date.now())}` : null;

  const viewSrc = {
    projected: ts(job?.result_image_url),
    clean:     ts(job?.clean_summary_image_url),
    pose:      ts(job?.pose_result_image_url),
    rectified: ts(job?.reference_rectified_image_url),
    holds:     ts(job?.hold_overlay_image_url),
    reference: ts(job?.reference_frame_image_url),
  };

  const currentSrc = viewSrc[view];

  // Auto-fallback to first available view
  useEffect(() => {
    if (!available.has(view)) {
      const fallback = VIEW_KEYS.find((k) => available.has(k));
      if (fallback) setView(fallback);
    }
  }, [available, view]);

  // Sync ref points with job
  useEffect(() => {
    if (Array.isArray(job?.reference_quad) && job.reference_quad.length === 4) {
      setRefPoints(job.reference_quad);
    }
  }, [job?.reference_quad]);

  async function apiFetch(url, opts = {}) {
    const resp = await fetch(`${API_BASE}${url}`, opts);
    if (!resp.ok) { const t = await resp.text(); throw new Error(`${resp.status} ${t}`); }
    return resp.json();
  }

  async function onUpload(selected) {
    const f = selected || file;
    if (!f) return;
    setJob(null); setRefPoints([]); setStatusText(""); setError("");
    setIsUploading(true);
    try {
      const form = new FormData();
      form.append("video", f);
      setStatusText("Uploading…");
      const created = await apiFetch("/api/jobs/", { method: "POST", body: form });
      setJob(created);

      setStatusText("Generating reference frame…");
      const withRef = await apiFetch(`/api/jobs/${created.id}/reference-frame/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ t: 0.5 }),
      });
      setJob(withRef);
      setRefPoints(Array.isArray(withRef.reference_quad) ? withRef.reference_quad : []);
      setStatusText(
        withRef.calibration_status === "ready"
          ? "Model calibration ready — review or re-calibrate."
          : "Reference frame ready. Select 4 calibration points."
      );
      setModalOpen(true);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setIsUploading(false);
    }
  }

  async function handleConfirmCalibration() {
    if (!jobId || refPoints.length !== 4) return;
    try {
      setIsSavingCalibration(true); setError("");
      const updated = await apiFetch(`/api/jobs/${jobId}/reference-quad/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quad: refPoints }),
      });
      setJob(updated);
      setStatusText("Calibration ready — run a model.");
      setModalOpen(false);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setIsSavingCalibration(false);
    }
  }

  async function handleRunHolds() {
    if (!jobId) return;
    try {
      setError(""); setIsRunningHolds(true); setStatusText("Running hold detection…");
      const updated = await apiFetch(`/api/jobs/${jobId}/projected-holds/`, { method: "POST" });
      setJob(updated); setView("holds"); setStatusText("Hold detection done.");
    } catch (e) { setError(String(e.message || e)); }
    finally { setIsRunningHolds(false); }
  }

  async function handleRunPose() {
    if (!jobId) return;
    try {
      setError(""); setIsRunningPose(true); setStatusText("Running pose tracking…");
      const updated = await apiFetch(`/api/jobs/${jobId}/pose-trajectory/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pose_model: "lite" }),
      });
      setJob(updated); setView("pose"); setStatusText("Pose tracking done.");
    } catch (e) { setError(String(e.message || e)); }
    finally { setIsRunningPose(false); }
  }

  async function handleCombine() {
    if (!jobId) return;
    try {
      setError(""); setIsRunningCombine(true); setStatusText("Combining…");
      const updated = await apiFetch(`/api/jobs/${jobId}/combine/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ radius_px: radiusPx, min_consecutive_frames: minFrames }),
      });
      setJob(updated); setView("clean"); setStatusText("Combination done.");
    } catch (e) { setError(String(e.message || e)); }
    finally { setIsRunningCombine(false); }
  }

  function reset() {
    setFile(null); setJob(null); setRefPoints([]);
    setStatusText(""); setError(""); setModalOpen(false);
  }

  const footerHint =
    stage === 0 ? "Upload a video to begin analysis."
    : stage === 1 ? "Set 4 reference corners on the wall to enable analysis."
    : stage === 2 ? "Run hold detection and pose tracking — either order works."
    : stage === 3 ? "Combine holds with pose to identify which holds were used."
    : "Analysis complete. Compare views above or export via debug links.";

  return (
    <div className="cv-root">
      {/* Top bar */}
      <header className="cv-header">
        <div className="cv-brand">
          <div className="cv-logo">
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path d="M4 20L10 8L14 16L16 12L20 20Z" fill="var(--accent)" stroke="#fff" strokeWidth="0.5"/>
            </svg>
          </div>
          <div>
            <h1 style={{margin:0, fontSize:16, fontWeight:700, letterSpacing:"-0.02em"}}>ClimbVision</h1>
            <div style={{...mono, fontSize:10, color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.12em", marginTop:1}}>
              Route analyzer · v0.3
            </div>
          </div>
        </div>
        <div style={{display:"flex", alignItems:"center", gap:12}}>
          {jobId && (
            <div style={{...mono, fontSize:11, color:"var(--muted)"}}>
              job <span style={{color:"var(--ink)"}}>{String(jobId).slice(0,13)}</span>
            </div>
          )}
          <Btn size="sm" variant="ghost" icon={<Icon.Reset/>} onClick={reset}>Reset</Btn>
        </div>
      </header>

      <div style={{marginBottom:18}}>
        <Stepper stepStates={stepStates}/>
      </div>

      {/* Status/error banner */}
      {(statusText || error) && (
        <div style={{
          marginBottom:14, padding:"10px 14px", borderRadius:8, fontSize:13,
          background: error ? "var(--err-soft)" : "var(--accent-soft)",
          color:      error ? "var(--err)"      : "var(--accent-ink)",
          border:     `1px solid ${error ? "var(--err-soft)" : "var(--accent-soft)"}`,
        }}>
          {error || statusText}
        </div>
      )}

      <div className="cv-grid">
        {/* Left */}
        <section style={{...card, padding:0, display:"flex", flexDirection:"column"}}>
          <div className="cv-section-head">
            <div className="cv-eyebrow">01 / Source</div>
            <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginTop:4}}>
              <h2 className="cv-section-title">Input video</h2>
              {jobId && <StatusPill status="ready" label="loaded"/>}
            </div>
          </div>

          <div style={{padding:18, borderBottom:"1px solid var(--border)"}}>
            {!jobId ? (
              <label className="cv-dropzone">
                <input type="file" accept="video/*" style={{display:"none"}}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); onUpload(f); }}}/>
                <div className="cv-dropzone-icon"><Icon.Upload style={{width:16, height:16}}/></div>
                <div style={{fontSize:13, fontWeight:500}}>
                  {isUploading ? "Uploading…" : "Drop a video or click to upload"}
                </div>
                <div style={{...mono, fontSize:11, color:"var(--muted)"}}>MP4, MOV · up to 200 MB</div>
              </label>
            ) : (
              <div style={{display:"flex", gap:14, alignItems:"center", justifyContent:"space-between"}}>
                <div style={{display:"flex", alignItems:"center", gap:12, minWidth:0}}>
                  <div className="cv-file-icon"><Icon.Play/></div>
                  <div style={{minWidth:0}}>
                    <div style={{fontSize:13, fontWeight:600, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>
                      {file?.name || "uploaded.mp4"}
                    </div>
                    <div style={{...mono, fontSize:11, color:"var(--muted)", marginTop:2}}>
                      {file ? `${Math.round(file.size/1024/1024)} MB` : ""}
                    </div>
                  </div>
                </div>
                <label>
                  <input type="file" accept="video/*" style={{display:"none"}}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); onUpload(f); }}}/>
                  <span className="cv-btn-ghost-inline">Replace</span>
                </label>
              </div>
            )}
          </div>

          <div style={{padding:18, flex:1, display:"flex", flexDirection:"column"}}>
            <div style={{display:"flex", justifyContent:"space-between", alignItems:"baseline", marginBottom:10}}>
              <div style={{fontSize:13, fontWeight:600}}>Preview</div>
              <div style={{...mono, fontSize:11, color:"var(--muted)"}}>source</div>
            </div>
            <div className="cv-media">
              {job?.video_url ? (
                <video src={job.video_url} controls style={{width:"100%", height:"100%", objectFit:"contain"}}/>
              ) : (
                <div className="cv-placeholder">upload a video</div>
              )}
            </div>
          </div>
        </section>

        {/* Right */}
        <section style={{...card, padding:0, display:"flex", flexDirection:"column"}}>
          {/* Calibrate */}
          <div className="cv-section-head">
            <div style={{display:"flex", alignItems:"center", justifyContent:"space-between"}}>
              <div>
                <div className="cv-eyebrow">02 / Calibrate</div>
                <h2 className="cv-section-title" style={{marginTop:4}}>Reference plane</h2>
              </div>
              <div style={{display:"flex", alignItems:"center", gap:10}}>
                <StatusPill
                  status={calibReady ? "ready" : stage===1 ? "active" : "idle"}
                  label={calibReady ? "ready" : stage===1 ? "awaiting points" : "not set"}
                />
                <Btn size="sm" variant={calibReady ? "secondary" : "accent"} icon={<Icon.Target/>}
                     disabled={!jobId} onClick={() => setModalOpen(true)}>
                  {calibReady ? "Re-calibrate" : "Calibrate"}
                </Btn>
              </div>
            </div>
          </div>

          {/* Analyze */}
          <div style={{padding:"16px 18px", borderBottom:"1px solid var(--border)"}}>
            <div className="cv-eyebrow">03 / Analyze</div>
            <h2 className="cv-section-title" style={{margin:"4px 0 12px"}}>Run models</h2>

            <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, marginBottom:10}}>
              <ModelCard
                title="Hold detection" sub="Identifies holds on wall" model="YOLO-seg"
                ready={hasHolds} running={isRunningHolds}
                disabled={!calibReady || isRunningHolds}
                count={job?.projected_holds_json?.num_holds ?? null} countLabel="holds"
                onRun={handleRunHolds} accent="orange"
              />
              <ModelCard
                title="Pose tracking" sub="Joint trajectory over frames" model="MediaPipe Lite"
                ready={hasPose} running={isRunningPose}
                disabled={!calibReady || isRunningPose}
                count={job?.projected_pose_json?.num_spots ?? null} countLabel="spots"
                onRun={handleRunPose} accent="blue"
              />
            </div>

            <div style={{marginTop:10, background:"var(--surface-2)", border:"1px solid var(--border)", borderRadius:8, padding:12}}>
              <div style={{display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10}}>
                <div style={{display:"flex", alignItems:"center", gap:10}}>
                  <div className="cv-eyebrow">04 / Combine</div>
                  <StatusPill status={hasCombine ? "ready" : "idle"} label={hasCombine ? "done" : "pending"}/>
                </div>
                <Btn size="sm" variant={canCombine ? "primary" : "secondary"}
                     disabled={!canCombine || isRunningCombine}
                     icon={isRunningCombine ? <Spinner/> : <Icon.Merge/>}
                     onClick={handleCombine}>
                  {isRunningCombine ? "Combining…" : hasCombine ? "Re-run combine" : "Combine holds + pose"}
                </Btn>
              </div>
              <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:10}}>
                <ParamInput label="Min consecutive frames" value={minFrames} onChange={setMinFrames} min={1} max={60} hint="filter jitter"/>
                <ParamInput label="Radius buffer (px)" value={radiusPx} onChange={setRadiusPx} min={0} max={100} hint="match tolerance"/>
              </div>
            </div>
          </div>

          {/* Result */}
          <div style={{padding:18, flex:1, display:"flex", flexDirection:"column", minHeight:0}}>
            <div style={{display:"flex", justifyContent:"space-between", alignItems:"baseline", marginBottom:10}}>
              <div style={{fontSize:13, fontWeight:600}}>Result</div>
              <div style={{...mono, fontSize:11, color:"var(--muted)"}}>
                viewing · <span style={{color:"var(--ink)"}}>{view}</span>
              </div>
            </div>
            <div style={{marginBottom:10}}>
              <ViewTabs current={view} onChange={setView} available={available}/>
            </div>
            <div className="cv-media">
              {currentSrc ? (
                <img src={currentSrc} alt={view} style={{width:"100%", height:"100%", objectFit:"contain"}}/>
              ) : (
                <div className="cv-placeholder">
                  {stage===0 ? "upload to begin" : !calibReady ? "calibrate to continue" : "run a model to see results"}
                </div>
              )}
            </div>

            {stage >= 3 && (
              <div style={{display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:6, marginTop:12}}>
                <Stat label="Holds" value={job?.holds_json?.num_holds ?? "—"}/>
                <Stat label="Projected" value={job?.projected_holds_json?.num_holds ?? "—"}/>
                <Stat label="Pose spots" value={job?.projected_pose_json?.num_spots ?? "—"}/>
                <Stat label="Used"
                      value={hasCombine ? `${job.combination_json.num_holds_used} / ${job.combination_json.num_holds_total}` : "—"}
                      accent={hasCombine}/>
              </div>
            )}

            {jobId && (
              <div style={{marginTop:12, paddingTop:12, borderTop:"1px solid var(--border)",
                display:"flex", flexWrap:"wrap", gap:14, ...mono, fontSize:11}}>
                <div style={{color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.1em", fontSize:10}}>debug →</div>
                {job?.reference_frame_image_url && <a className="cv-debug-link" href={job.reference_frame_image_url} target="_blank" rel="noreferrer">reference_frame <Icon.External/></a>}
                {job?.reference_rectified_image_url && <a className="cv-debug-link" href={job.reference_rectified_image_url} target="_blank" rel="noreferrer">rectified <Icon.External/></a>}
                {job?.hold_overlay_image_url && <a className="cv-debug-link" href={job.hold_overlay_image_url} target="_blank" rel="noreferrer">hold_overlay <Icon.External/></a>}
                {job?.pose_result_image_url && <a className="cv-debug-link" href={job.pose_result_image_url} target="_blank" rel="noreferrer">pose <Icon.External/></a>}
                {job?.clean_summary_image_url && <a className="cv-debug-link" href={job.clean_summary_image_url} target="_blank" rel="noreferrer">clean_summary <Icon.External/></a>}
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="cv-footer-hint">
        <Icon.Arrow style={{color:"var(--accent)"}}/>
        <span>{footerHint}</span>
      </div>

      <CalibrationModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        imageSrc={job?.reference_frame_image_url ? `${job.reference_frame_image_url}?t=${job.updated_at || ""}` : null}
        rectifiedSrc={job?.reference_rectified_image_url ? `${job.reference_rectified_image_url}?t=${job.updated_at || ""}` : null}
        refPoints={refPoints}
        setRefPoints={setRefPoints}
        status={calibReady ? "ready" : "idle"}
        onConfirm={handleConfirmCalibration}
        saving={isSavingCalibration}
      />
    </div>
  );
}
