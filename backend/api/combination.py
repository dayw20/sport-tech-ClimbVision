from __future__ import annotations

import cv2
import numpy as np
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
    spots = projected_pose_json.get("points", [])

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

    return {
        "radius_px":              radius_px,
        "min_consecutive_frames": min_consecutive_frames,
        "frame_interval":         frame_interval,
        "num_holds_total":        len(result_holds),
        "num_holds_used":         num_used,
        "holds":                  result_holds,
    }


# ── visualisation ─────────────────────────────────────────────────────────────

def draw_combination(
    ref_img_bgr: np.ndarray,
    combination_json: dict,
    *,
    fill_alpha: float = 0.25,
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
                          thickness=3 if is_used else 1)

        if is_used:
            center = hold.get("projected_center")
            label = hold.get("sequence_label_str", "")
            if center and len(center) == 2 and label:
                cx, cy = int(center[0]), int(center[1])
                # Dark background pill for readability
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(out, (cx + 3, cy - th - 5), (cx + 5 + tw, cy - 1), (0, 0, 0), -1)
                cv2.putText(out, label, (cx + 4, cy - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

            for hit in hold.get("hits", []):
                color = _KIND_COLOR.get(hit.get("kind", ""), _DEFAULT_COLOR)
                hx, hy = int(round(hit["x"])), int(round(hit["y"]))
                cv2.circle(out, (hx, hy), 7, color, -1)
                cv2.circle(out, (hx, hy), 7, (255, 255, 255), 1)

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

    job.result_image.save(
        f"{job.id}_combination.jpg",
        ContentFile(encoded.tobytes()),
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
        "result_image", "combination_json", "message", "status", "updated_at"
    ])
