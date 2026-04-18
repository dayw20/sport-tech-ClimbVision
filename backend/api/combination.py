from __future__ import annotations

import cv2
import numpy as np
from collections import defaultdict
from django.core.files.base import ContentFile


# ── colour palette for limb kinds ────────────────────────────────────────────
_KIND_COLOR = {
    "LH":   (0,  165, 255),   # orange  – left hand
    "RH":   (0,   80, 255),   # red     – right hand
    "LF":   (50, 220,  50),   # green   – left foot
    "RF":   (0,  200, 100),   # teal    – right foot
    # legacy kinds from older pose pipeline
    "hand": (0,  165, 255),
    "foot": (50, 220,  50),
}
_DEFAULT_COLOR = (200, 200, 200)

# Mapping from legacy kinds to canonical kinds (for sequence labelling)
_KIND_CANONICAL = {
    "LH": "LH", "RH": "RH", "LF": "LF", "RF": "RF",
    "hand": "H", "foot": "F",
}

# Kinds used for hold matching (excludes body-landmark kinds)
_HOLD_MATCH_KINDS = {"LH", "RH", "LF", "RF", "hand", "foot"}

# ── stable state detection ────────────────────────────────────────────────────

_STABLE_MOVEMENT_THRESHOLD_PX = 35.0
_STABLE_MIN_FRAMES             = 4    # minimum consecutive stable samples (~0.3 s at 10 fps)
_STABLE_MIN_LIMB_COVERAGE      = 0.2   # fraction of window frames a limb must appear in
_STABLE_MIN_LIMBS              = 2   # at least 2 of 4 limbs must meet coverage

_LIMB_KINDS_SET = {"LH", "RH", "LF", "RF"}
_STABLE_MERGE_DIST_PX = 80   # fallback pixel distance for limbs not on any hold
_MAX_DISPLAY_STATES = 4       # cap for stick figures drawn on summary images


def _select_evenly_spaced_states(states: list[dict], n: int = _MAX_DISPLAY_STATES) -> list[dict]:
    """
    From a chronologically ordered list of stable states, pick at most `n`
    that are as evenly spaced as possible across the temporal range.

    Uses frame_start as the time coordinate.  If len(states) <= n, returns all.
    """
    if len(states) <= n:
        return states
    # Evenly sample indices across [0, len-1]
    indices = [round(i * (len(states) - 1) / (n - 1)) for i in range(n)]
    return [states[i] for i in indices]


def _merge_nearby_states(states: list[dict]) -> list[dict]:
    """
    Pixel-distance fallback deduplication for states where limbs are not on holds.
    Used as a second pass after hold-fingerprint deduplication.
    """
    if not states:
        return states

    def _max_limb_dist(a: dict, b: dict) -> float:
        shared = set(a["positions"]) & set(b["positions"]) & _LIMB_KINDS_SET
        if not shared:
            return float("inf")
        return max(
            ((a["positions"][k][0] - b["positions"][k][0]) ** 2 +
             (a["positions"][k][1] - b["positions"][k][1]) ** 2) ** 0.5
            for k in shared
        )

    candidates = sorted(states, key=lambda s: s["n_samples"], reverse=True)
    kept: list[dict] = []
    for candidate in candidates:
        if all(_max_limb_dist(candidate, k) >= _STABLE_MERGE_DIST_PX for k in kept):
            kept.append(candidate)

    kept.sort(key=lambda s: s["frame_start"])
    return kept


def _deduplicate_states_by_holds(
    states: list[dict],
    holds: list[dict],
    radius_px: float,
) -> list[dict]:
    """
    Primary deduplication: map each limb in a stable state to the hold it is
    touching (or None if not on any hold). Two states with the same limb→hold
    fingerprint are duplicates — keep the one with more samples.

    Falls back to pixel-distance dedup (_merge_nearby_states) for any states
    whose fingerprints are ambiguous (all limbs mapped to None).
    """
    def _limb_hold_id(pos, holds, radius):
        """Return the id of the first hold containing pos, or None."""
        for hold in holds:
            contour = hold.get("projected_contour") or []
            if _hits_hold(pos[0], pos[1], contour, radius + 20):  # small buffer
                return hold["id"]
        return None

    def _fingerprint(state):
        return tuple(
            (k, _limb_hold_id(state["positions"][k], holds, radius_px))
            for k in sorted(_LIMB_KINDS_SET)
            if k in state["positions"]
        )

    def _partial_match(fp_a, fp_b) -> bool:
        """
        Two fingerprints match if every limb that has a non-None hold ID in BOTH
        states maps to the same hold, and at least one such shared mapping exists.
        Ignores None mismatches — a limb that wasn't detected on a hold in one
        state does not disqualify an otherwise identical position.
        """
        a = {k: v for k, v in fp_a if v is not None}
        b = {k: v for k, v in fp_b if v is not None}
        shared = set(a) & set(b)
        return bool(shared) and all(a[k] == b[k] for k in shared)

    # Sort best-supported first so the highest-quality state wins each cluster
    candidates = sorted(states, key=lambda s: s["n_samples"], reverse=True)
    kept_fps: list = []
    kept_states: list[dict] = []
    for state in candidates:
        fp = _fingerprint(state)
        print(f"[dedup] frame {state['frame_start']}-{state['frame_end']} fingerprint: {fp}")
        if not any(_partial_match(fp, kfp) for kfp in kept_fps):
            kept_fps.append(fp)
            kept_states.append(state)

    deduped = sorted(kept_states, key=lambda s: s["frame_start"])

    # Second pass: pixel-distance fallback for remaining spatial duplicates
    return _merge_nearby_states(deduped)


def detect_stable_states(
    points: list,
    *,
    movement_threshold: float = _STABLE_MOVEMENT_THRESHOLD_PX,
    min_frames: int = _STABLE_MIN_FRAMES,
) -> list[dict]:
    """
    Find windows in the pose time series where all visible limbs stay within
    `movement_threshold` pixels between consecutive sampled frames.

    Only limb kinds (LH/RH/LF/RF) drive the movement score; body-landmark kinds
    (LSHO/RSHO/LHIP/RHIP) are included in the output positions for the stick figure.

    A stable state is accepted only if ≥ 3 limbs are visible in ≥ 50 % of frames
    in the window — this prevents states built from mostly-occluded data.

    Returns a list of dicts, chronologically ordered:
      frame_start, frame_end : int
      positions              : {kind: [x, y]}  — median over the window
    """
    # Group all points by frame
    by_frame: dict[int, dict[str, tuple]] = defaultdict(dict)
    for pt in points:
        fi   = pt.get("frame_idx")
        kind = pt.get("kind")
        if fi is None or kind is None:
            continue
        by_frame[fi][kind] = (pt["x"], pt["y"])

    sorted_fids = sorted(by_frame.keys())
    n = len(sorted_fids)
    if n < 2:
        return []

    # Per-consecutive-pair movement score (max displacement across shared limbs)
    raw_scores: list[float] = []
    for i in range(n - 1):
        f1 = by_frame[sorted_fids[i]]
        f2 = by_frame[sorted_fids[i + 1]]
        shared_limbs = (set(f1) & set(f2)) & _LIMB_KINDS_SET
        if not shared_limbs:
            raw_scores.append(float("inf"))
        else:
            max_disp = max(
                ((f1[k][0] - f2[k][0]) ** 2 + (f1[k][1] - f2[k][1]) ** 2) ** 0.5
                for k in shared_limbs
            )
            raw_scores.append(max_disp)

    # Smooth with a 3-frame rolling average so single jitter spikes from the
    # lite pose model don't break an otherwise stable window.
    half = 1
    movement_scores: list[float] = []
    for i in range(len(raw_scores)):
        window = raw_scores[max(0, i - half): i + half + 1]
        finite = [v for v in window if v != float("inf")]
        movement_scores.append(sum(finite) / len(finite) if finite else float("inf"))

    # Find contiguous windows where every smoothed score is below threshold
    is_stable = [m < movement_threshold for m in movement_scores]
    windows: list[tuple[int, int]] = []   # (start_i, end_i) inclusive frame indices
    start = None
    for i, s in enumerate(is_stable):
        if s and start is None:
            start = i
        elif not s and start is not None:
            windows.append((start, i))    # frames start_i … i (i is last stable frame)
            start = None
    if start is not None:
        windows.append((start, n - 1))

    # Debug: log movement score stats
    finite_scores = [m for m in movement_scores if m != float("inf")]
    if finite_scores:
        print(f"[stable] frames={n}  scores: min={min(finite_scores):.1f} "
              f"median={sorted(finite_scores)[len(finite_scores)//2]:.1f} "
              f"max={max(finite_scores):.1f}  threshold={movement_threshold}")
    else:
        print(f"[stable] frames={n}  no finite movement scores")

    # Filter by minimum length
    windows = [(s, e) for s, e in windows if (e - s + 1) >= min_frames]
    print(f"[stable] windows after length filter (min={min_frames}): {len(windows)}")

    # Extract representative state for each window
    result: list[dict] = []
    for start_i, end_i in windows:
        window_fids = sorted_fids[start_i : end_i + 1]
        n_window    = len(window_fids)

        pos_by_kind: dict[str, list] = defaultdict(list)
        for fi in window_fids:
            for kind, pos in by_frame[fi].items():
                pos_by_kind[kind].append(pos)

        # Acceptance check: ≥ _STABLE_MIN_LIMBS limbs covered in ≥ 50 % of frames
        covered = sum(
            1 for k in _LIMB_KINDS_SET
            if len(pos_by_kind.get(k, [])) >= n_window * _STABLE_MIN_LIMB_COVERAGE
        )
        print(f"[stable]   window frames {sorted_fids[start_i]}-{sorted_fids[end_i]} "
              f"({n_window} samples): covered_limbs={covered}")
        if covered < _STABLE_MIN_LIMBS:
            continue

        # Median x and y per kind (robust to outlier detections)
        representative: dict[str, list[int]] = {}
        for kind, positions in pos_by_kind.items():
            xs = sorted(p[0] for p in positions)
            ys = sorted(p[1] for p in positions)
            representative[kind] = [xs[len(xs) // 2], ys[len(ys) // 2]]

        result.append({
            "frame_start": sorted_fids[start_i],
            "frame_end":   sorted_fids[end_i],
            "n_samples":   n_window,
            "positions":   representative,
        })

    print(f"[stable] raw stable windows accepted: {len(result)}")
    return result


# ── stick figure drawing ──────────────────────────────────────────────────────

_FIGURE_LINE_COLOR  = (0, 0, 220)    # red (BGR)
_FIGURE_HEAD_COLOR  = (0, 0, 220)    # red
_FIGURE_LABEL_COLOR = (255, 255,  0) # yellow
_FIGURE_LINE_THICKNESS = 8
_FIGURE_HEAD_RADIUS    = 50   # fixed head radius — same for all figures

def _draw_stick_figure(img: np.ndarray, positions: dict, state_num: int) -> None:
    """
    Draw a stick figure on `img` (in-place) from the median joint positions of
    one stable state.  joints used:
      NOSE              — head dot
      LSHO, RSHO        — shoulders
      LELB, RELB        — elbows
      LHIP, RHIP        — hips
      LKNE, RKNE        — knees
      LH,   RH          — hands (wrist midpoints)
      LF,   RF          — feet
    If shoulder/hip data is absent (old pose runs without body landmarks),
    they are estimated from the four limb endpoints so the figure still renders.
    """
    def _pt(kind) -> tuple[int, int] | None:
        p = positions.get(kind)
        return (int(p[0]), int(p[1])) if p else None

    def _mid(a, b):
        if a and b:
            return ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
        return a or b

    def _line(p1, p2, color=_FIGURE_LINE_COLOR, thickness=_FIGURE_LINE_THICKNESS):
        if p1 and p2:
            cv2.line(img, p1, p2, color, thickness, cv2.LINE_AA)

    lh   = _pt("LH");   rh   = _pt("RH")
    lf   = _pt("LF");   rf   = _pt("RF")
    lsho = _pt("LSHO"); rsho = _pt("RSHO")
    lelb = _pt("LELB"); relb = _pt("RELB")
    lhip = _pt("LHIP"); rhip = _pt("RHIP")
    lkne = _pt("LKNE"); rkne = _pt("RKNE")
    nose = _pt("NOSE")

    # Fall back: estimate shoulders/hips from limb endpoints when body data is missing
    if lsho is None and lhip is None and lh is not None and lf is not None:
        span_y = lf[1] - lh[1]
        lsho = (lh[0], lh[1] + int(span_y * 0.15))
        lhip = (lf[0], lf[1] - int(span_y * 0.20))
    if rsho is None and rhip is None and rh is not None and rf is not None:
        span_y = rf[1] - rh[1]
        rsho = (rh[0], rh[1] + int(span_y * 0.15))
        rhip = (rf[0], rf[1] - int(span_y * 0.20))

    sho_mid = _mid(lsho, rsho)
    hip_mid = _mid(lhip, rhip)

    # Torso
    _line(lsho, rsho)
    _line(lhip, rhip)
    _line(sho_mid, hip_mid)

    # Head: use nose if available, else estimate above shoulder midpoint
    head_r = _FIGURE_HEAD_RADIUS
    if nose:
        head_center = nose
    elif sho_mid:
        head_center = (sho_mid[0], sho_mid[1] - head_r - 3)
    else:
        head_center = None

    if head_center:
        cv2.circle(img, head_center, head_r, _FIGURE_HEAD_COLOR, _FIGURE_LINE_THICKNESS, cv2.LINE_AA)
        # Neck line from shoulder midpoint to head
        if sho_mid and head_center != sho_mid:
            _line(sho_mid, head_center)
        # State label above head
        cv2.putText(
            img, f"S{state_num}",
            (head_center[0] - 14, head_center[1] - head_r - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, _FIGURE_LABEL_COLOR, 2, cv2.LINE_AA,
        )

    # Arms: shoulder → elbow → hand (falls back to shoulder→hand if elbow missing)
    if lelb:
        _line(lsho, lelb)
        _line(lelb, lh)
    else:
        _line(lsho, lh)
    if relb:
        _line(rsho, relb)
        _line(relb, rh)
    else:
        _line(rsho, rh)

    # Legs: hip → knee → foot (falls back to hip→foot if knee missing)
    if lkne:
        _line(lhip, lkne)
        _line(lkne, lf)
    else:
        _line(lhip, lf)
    if rkne:
        _line(rhip, rkne)
        _line(rkne, rf)
    else:
        _line(rhip, rf)

    # Coloured endpoint dots (limb identity)
    for kind, pos in [("LH", lh), ("RH", rh), ("LF", lf), ("RF", rf)]:
        if pos:
            color = _KIND_COLOR.get(kind, _DEFAULT_COLOR)
            cv2.circle(img, pos, 9, color, -1, cv2.LINE_AA)
            cv2.circle(img, pos, 9, (255, 255, 255), 1, cv2.LINE_AA)


# ── helpers ───────────────────────────────────────────────────────────────────

def _hits_hold(x: float, y: float, contour_pts: list, radius_px: float) -> bool:
    """
    True if (x, y) is inside the hold polygon or within `radius_px` pixels of its boundary.
    radius_px=0 means strictly inside (or exactly on boundary).
    """
    if len(contour_pts) < 3:
        return False
    poly = np.array(contour_pts, dtype=np.int32)
    dist = cv2.pointPolygonTest(poly, (float(x), float(y)), measureDist=True)
    return float(dist) >= -radius_px


def _detect_frame_interval(spots: list) -> int:
    """
    Infer the sampling interval (in video frame numbers) from the pose data.
    Uses the most common gap between consecutive sampled frame indices.
    Falls back to 1 if there are fewer than 2 distinct frames.
    """
    frames = sorted({s["frame_idx"] for s in spots if s.get("frame_idx") is not None})
    if len(frames) < 2:
        return 1
    gaps = [frames[i + 1] - frames[i] for i in range(len(frames) - 1)]
    # most common gap = the regular sampling step
    from collections import Counter
    return Counter(gaps).most_common(1)[0][0]


def _max_consecutive_run(frame_indices: set, max_gap: int) -> int:
    """
    Given a set of frame indices that hit a hold, find the length of the
    longest run where consecutive entries differ by at most `max_gap`.

    Example with frame_interval=3, max_gap=6 (allow one missed sample):
      frames = {0, 3, 6, 15, 18, 21, 24}
      runs   = [0,3,6] → length 3
               [15,18,21,24] → length 4   ← returned
    """
    if not frame_indices:
        return 0
    sorted_frames = sorted(frame_indices)
    max_run = current_run = 1
    for i in range(1, len(sorted_frames)):
        if sorted_frames[i] - sorted_frames[i - 1] <= max_gap:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1
    return max_run


# ── sequence labelling ───────────────────────────────────────────────────────

def _assign_sequence_labels(result_holds: list) -> None:
    """
    For each limb kind (LH, RH, LF, RF — or legacy H, F), find all used holds
    hit by that kind, sort by earliest frame_idx, and assign 1-based sequence
    numbers: LH1, LH2, ... RH1, ... etc. (or H1, H2, F1, F2 for legacy data).

    Mutates each hold dict in-place, adding:
      sequence_labels:  dict  e.g. {"LH": 2, "RF": 1}
      sequence_label_str: str  e.g. "LH2 RF1"
    """
    # Detect which kind vocabulary is in use: new (LH/RH/LF/RF) or legacy (hand/foot)
    all_kinds_in_data: set[str] = set()
    for hold in result_holds:
        for h in hold.get("hits", []):
            k = h.get("kind", "")
            if k:
                all_kinds_in_data.add(k)

    has_new_kinds = bool(all_kinds_in_data & {"LH", "RH", "LF", "RF"})
    has_legacy    = bool(all_kinds_in_data & {"hand", "foot"})

    if has_new_kinds:
        canonical_kinds = ("LH", "RH", "LF", "RF")
        kind_match = lambda h, k: h.get("kind") == k  # noqa: E731
    elif has_legacy:
        # legacy data: "hand" → "H", "foot" → "F"
        canonical_kinds = ("H", "F")
        legacy_map = {"H": "hand", "F": "foot"}
        kind_match = lambda h, k: h.get("kind") == legacy_map[k]  # noqa: E731
    else:
        canonical_kinds = ()
        kind_match = lambda h, k: False  # noqa: E731

    for kind in canonical_kinds:
        candidates = []
        for hold in result_holds:
            if not hold["is_used"]:
                continue
            kind_hits = [h for h in hold["hits"] if kind_match(h, kind)]
            if not kind_hits:
                continue
            kind_frames = [
                h["frame_idx"] for h in kind_hits if h.get("frame_idx") is not None
            ]
            if kind_frames:
                sort_key = min(kind_frames)
            else:
                center = hold.get("projected_center") or [0, 0]
                sort_key = center[1]
            candidates.append((hold, sort_key))

        candidates.sort(key=lambda x: x[1])
        for seq, (hold, _) in enumerate(candidates, start=1):
            hold.setdefault("sequence_labels", {})[kind] = seq

    # Build display string (sorted kind order so it's consistent)
    for hold in result_holds:
        labels = hold.get("sequence_labels", {})
        hold["sequence_label_str"] = " ".join(
            f"{k}{v}" for k, v in sorted(labels.items())
        )


# ── main combination logic ────────────────────────────────────────────────────

def compute_combination(
    projected_holds_json: dict,
    projected_pose_json: dict,
    *,
    radius_px: float = 0.0,
    min_consecutive_frames: int = 1,
) -> dict:
    """
    For each detected hold, collect pose spots that overlap it (spatial filter),
    then check if the hold was hit in at least `min_consecutive_frames` consecutive
    sampled frames (temporal filter).

    A hold is marked `is_used = True` only when both conditions are met.

    Each hold entry in the result includes:
      hit_count              – total pose spots overlapping
      frame_count            – unique frames that had at least one hit
      max_consecutive_frames – longest consecutive-frame run among hits
      is_used                – max_consecutive_frames >= min_consecutive_frames
      kinds                  – per-limb breakdown {LH, RH, LF, RF}
      hits                   – list of raw spot dicts that overlapped
    """
    holds = projected_holds_json.get("holds", [])
    all_spots = projected_pose_json.get("points", [])

    # Only limb endpoints (LH/RH/LF/RF) are used for hold matching;
    # body-landmark kinds (LSHO/RSHO/LHIP/RHIP) are excluded here.
    spots = [s for s in all_spots if s.get("kind") in _HOLD_MATCH_KINDS]

    # Detect frame_interval once from the full pose data.
    # Allow up to 2× the interval as a gap so one missed detection doesn't break a run.
    frame_interval = _detect_frame_interval(spots)
    max_gap = frame_interval * 2

    result_holds = []

    for hold in holds:
        contour = hold.get("projected_contour") or []

        hits = [
            spot for spot in spots
            if _hits_hold(spot["x"], spot["y"], contour, radius_px)
        ]

        frame_indices = {
            hit["frame_idx"] for hit in hits if hit.get("frame_idx") is not None
        }
        # Fallback for pose data recorded before frame_idx tracking was added:
        # treat every hit as its own "frame" using a synthetic index.
        if not frame_indices and hits:
            frame_indices = set(range(len(hits)))

        kinds: dict[str, int] = {}
        for hit in hits:
            k = hit.get("kind", "")
            if k:
                kinds[k] = kinds.get(k, 0) + 1

        max_consec = _max_consecutive_run(frame_indices, max_gap)

        result_holds.append({
            "id":                      hold["id"],
            "projected_center":        hold.get("projected_center"),
            "projected_contour":       contour,
            "projected_bbox":          hold.get("projected_bbox"),
            "hit_count":               len(hits),
            "frame_count":             len(frame_indices),
            "max_consecutive_frames":  max_consec,
            "is_used":                 max_consec >= min_consecutive_frames,
            "kinds":                   kinds,
            "hits":                    hits,
        })

    num_used = sum(1 for h in result_holds if h["is_used"])
    _assign_sequence_labels(result_holds)

    # Detect stable states, then deduplicate by hold fingerprint
    stable_states = detect_stable_states(all_spots)
    stable_states = _deduplicate_states_by_holds(stable_states, result_holds, radius_px)
    print(f"[stable] final stable states after dedup: {len(stable_states)}")

    return {
        "radius_px":              radius_px,
        "min_consecutive_frames": min_consecutive_frames,
        "frame_interval":         frame_interval,
        "num_holds_total":        len(result_holds),
        "num_holds_used":         num_used,
        "holds":                  result_holds,
        "stable_states":          stable_states,
    }


# ── visualisation ─────────────────────────────────────────────────────────────

def draw_combination(
    ref_img_bgr: np.ndarray,
    combination_json: dict,
    *,
    fill_alpha: float = 0.55,
) -> np.ndarray:
    """
    Draw on the rectified reference image.
    Uses hold["is_used"] (already computed by compute_combination).
    - Used holds: green filled polygon + thick outline + label
    - Unused holds: thin grey outline
    - Pose spots on used holds: coloured circles by limb kind
    """
    out = ref_img_bgr.copy()
    overlay = out.copy()

    # Pass 1 — filled polygons (blended)
    for hold in combination_json.get("holds", []):
        contour = hold.get("projected_contour") or []
        if len(contour) < 3:
            continue
        pts = np.array(contour, dtype=np.int32).reshape(-1, 1, 2)
        if hold["is_used"]:
            cv2.fillPoly(overlay, [pts], (0, 220, 80))
        else:
            cv2.polylines(overlay, [pts], isClosed=True, color=(120, 120, 120), thickness=1)

    cv2.addWeighted(overlay, fill_alpha, out, 1 - fill_alpha, 0, out)

    # Pass 2 — outlines, labels, and spots (sharp, no transparency)
    for hold in combination_json.get("holds", []):
        contour = hold.get("projected_contour") or []
        is_used = hold["is_used"]

        if len(contour) >= 3:
            pts = np.array(contour, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [pts], isClosed=True,
                          color=(0, 220, 80) if is_used else (120, 120, 120),
                          thickness=5 if is_used else 1)

        if is_used:
            center = hold.get("projected_center")
            label = hold.get("sequence_label_str", "")
            if center and len(center) == 2 and label:
                cx, cy = int(center[0]), int(center[1])
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.4, 3)
                cv2.rectangle(out, (cx + 3, cy - th - 5), (cx + 5 + tw, cy - 1), (0, 0, 0), -1)
                cv2.putText(out, label, (cx + 4, cy - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
        # raw pose hit dots removed — stick figures convey position more clearly

    # Pass 3 — stable state stick figures (at most _MAX_DISPLAY_STATES, evenly spaced)
    stable_states = combination_json.get("stable_states", [])
    display_states = _select_evenly_spaced_states(stable_states)
    for i, state in enumerate(display_states, start=1):
        _draw_stick_figure(out, state["positions"], i)

    # Pass 4 — state transition arrows (body center S1 → S2 → S3 ...)
    def _body_center(state):
        pos = state["positions"]
        pts = [pos[k] for k in ("LSHO", "RSHO", "LHIP", "RHIP") if k in pos]
        if not pts:
            pts = [pos[k] for k in ("LH", "RH", "LF", "RF") if k in pos]
        if not pts:
            return None
        return (int(sum(p[0] for p in pts) / len(pts)),
                int(sum(p[1] for p in pts) / len(pts)))

    centers = [_body_center(s) for s in display_states]
    for i in range(len(centers) - 1):
        a, b = centers[i], centers[i + 1]
        if a and b:
            cv2.arrowedLine(out, a, b, (255, 255, 255), 4, cv2.LINE_AA, tipLength=0.06)

    # Pass 5 — legend (bottom-left corner)
    h, w = out.shape[:2]
    legend_items = [
        (_KIND_COLOR["LH"], "LH  Left hand"),
        (_KIND_COLOR["RH"], "RH  Right hand"),
        (_KIND_COLOR["LF"], "LF  Left foot"),
        (_KIND_COLOR["RF"], "RF  Right foot"),
    ]
    lx, ly = 12, h - 12 - len(legend_items) * 22
    pad, row_h, dot_r = 8, 22, 7
    box_w = 160
    cv2.rectangle(out, (lx - pad, ly - pad), (lx + box_w, ly + len(legend_items) * row_h), (20, 20, 20), -1)
    cv2.rectangle(out, (lx - pad, ly - pad), (lx + box_w, ly + len(legend_items) * row_h), (80, 80, 80), 1)
    for idx, (color, text) in enumerate(legend_items):
        cy_l = ly + idx * row_h + row_h // 2
        cv2.circle(out, (lx + dot_r, cy_l), dot_r, color, -1, cv2.LINE_AA)
        cv2.putText(out, text, (lx + dot_r * 2 + 6, cy_l + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)

    return out


# ── clean summary (white background) ─────────────────────────────────────────

def draw_clean_summary(
    combination_json: dict,
    canvas_w: int,
    canvas_h: int,
) -> np.ndarray:
    """
    Draw a clean summary on a white background:
    - Only used holds (outlined + sequence label)
    - Stick figures at each stable state
    - State transition arrows
    - Legend
    No wall photo — easy to read at a glance.
    """
    out = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)  # white canvas

    # Used holds — dark outline + light green fill + sequence label
    overlay = out.copy()
    for hold in combination_json.get("holds", []):
        if not hold["is_used"]:
            continue
        contour = hold.get("projected_contour") or []
        if len(contour) < 3:
            continue
        pts = np.array(contour, dtype=np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(overlay, [pts], (180, 240, 180))   # light green fill
    cv2.addWeighted(overlay, 0.7, out, 0.3, 0, out)

    for hold in combination_json.get("holds", []):
        if not hold["is_used"]:
            continue
        contour = hold.get("projected_contour") or []
        if len(contour) < 3:
            continue
        pts = np.array(contour, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], isClosed=True, color=(30, 140, 30), thickness=4)

        center = hold.get("projected_center")
        label  = hold.get("sequence_label_str", "")
        if center and label:
            cx, cy = int(center[0]), int(center[1])
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.4, 3)
            cv2.rectangle(out, (cx - tw//2 - 3, cy - th - 4), (cx + tw//2 + 3, cy + 2), (30, 140, 30), -1)
            cv2.putText(out, label, (cx - tw//2, cy - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)

    # Stick figures (at most _MAX_DISPLAY_STATES, evenly spaced temporally)
    stable_states = combination_json.get("stable_states", [])
    display_states = _select_evenly_spaced_states(stable_states)
    for i, state in enumerate(display_states, start=1):
        _draw_stick_figure(out, state["positions"], i)

    # State transition arrows
    def _body_center(state):
        pos = state["positions"]
        pts = [pos[k] for k in ("LSHO", "RSHO", "LHIP", "RHIP") if k in pos]
        if not pts:
            pts = [pos[k] for k in ("LH", "RH", "LF", "RF") if k in pos]
        if not pts:
            return None
        return (int(sum(p[0] for p in pts) / len(pts)),
                int(sum(p[1] for p in pts) / len(pts)))

    centers = [_body_center(s) for s in display_states]
    for i in range(len(centers) - 1):
        a, b = centers[i], centers[i + 1]
        if a and b:
            cv2.arrowedLine(out, a, b, (100, 100, 100), 4, cv2.LINE_AA, tipLength=0.06)

    # Legend
    legend_items = [
        (_KIND_COLOR["LH"], "LH  Left hand"),
        (_KIND_COLOR["RH"], "RH  Right hand"),
        (_KIND_COLOR["LF"], "LF  Left foot"),
        (_KIND_COLOR["RF"], "RF  Right foot"),
    ]
    lx, ly = 12, canvas_h - 12 - len(legend_items) * 22
    pad, row_h, dot_r = 8, 22, 7
    box_w = 160
    cv2.rectangle(out, (lx - pad, ly - pad), (lx + box_w, ly + len(legend_items) * row_h), (230, 230, 230), -1)
    cv2.rectangle(out, (lx - pad, ly - pad), (lx + box_w, ly + len(legend_items) * row_h), (160, 160, 160), 1)
    for idx, (color, text) in enumerate(legend_items):
        cy_l = ly + idx * row_h + row_h // 2
        cv2.circle(out, (lx + dot_r, cy_l), dot_r, color, -1, cv2.LINE_AA)
        cv2.putText(out, text, (lx + dot_r * 2 + 6, cy_l + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1, cv2.LINE_AA)

    return out


# ── job-level entry point ─────────────────────────────────────────────────────

def build_combination_for_job(job, *, radius_px: float = 0.0, min_consecutive_frames: int = 1):
    if not job.projected_holds_json:
        raise ValueError("no projected_holds_json — run Hold Detection first")
    if not job.projected_pose_json:
        raise ValueError("no projected_pose_json — run Pose first")
    if not job.reference_rectified_image:
        raise ValueError("no reference_rectified_image — complete calibration first")

    combination_json = compute_combination(
        job.projected_holds_json,
        job.projected_pose_json,
        radius_px=radius_px,
        min_consecutive_frames=min_consecutive_frames,
    )

    ref_img = cv2.imread(job.reference_rectified_image.path, cv2.IMREAD_COLOR)
    if ref_img is None:
        raise RuntimeError("failed to read reference_rectified_image")

    vis = draw_combination(ref_img, combination_json)
    ok, encoded = cv2.imencode(".jpg", vis, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise RuntimeError("failed to encode combination image")

    out_h, out_w = ref_img.shape[:2]
    clean = draw_clean_summary(combination_json, out_w, out_h)
    ok_c, encoded_c = cv2.imencode(".jpg", clean, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok_c:
        raise RuntimeError("failed to encode clean summary image")

    job.result_image.save(
        f"{job.id}_combination.jpg",
        ContentFile(encoded.tobytes()),
        save=False,
    )
    job.clean_summary_image.save(
        f"{job.id}_clean_summary.jpg",
        ContentFile(encoded_c.tobytes()),
        save=False,
    )
    job.combination_json = combination_json
    job.message = (
        f"combination ready — "
        f"{combination_json['num_holds_used']}/{combination_json['num_holds_total']} holds used "
        f"(min {min_consecutive_frames} consecutive frames, interval={combination_json['frame_interval']})"
    )
    job.status = job.Status.DONE
    job.save(update_fields=[
        "result_image", "clean_summary_image", "combination_json", "message", "status", "updated_at"
    ])
