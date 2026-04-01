from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from django.core.files.base import ContentFile

from .hold_detection import detect_holds_from_array
from .pose_projection import build_reference_homography
from .extract import extract_frames_first_20s


# ── NMS helpers ───────────────────────────────────────────────────────────────

def _iou_bbox(b1: list, b2: list) -> float:
    """IoU between two [x1, y1, x2, y2] bboxes."""
    ix1 = max(b1[0], b2[0])
    iy1 = max(b1[1], b2[1])
    ix2 = min(b1[2], b2[2])
    iy2 = min(b1[3], b2[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    return inter / (area1 + area2 - inter)


def _nms_holds(holds: list, iou_threshold: float = 0.3, min_frame_votes: int = 1) -> list:
    """
    Deduplicate holds detected across multiple frames and filter by frame support.

    Each hold in `holds` must have a "_frame_idx" field (set before calling).
    The highest-confidence detection wins each cluster; every subsequent detection
    that overlaps it (IoU > iou_threshold) casts a vote for that cluster.

    Only clusters with votes from at least `min_frame_votes` distinct frames are
    kept — this removes false positives caused by the climber's body, which moves
    between frames and therefore rarely overlaps in the same position across frames.
    """
    sorted_holds = sorted(holds, key=lambda h: h.get("confidence", 0), reverse=True)
    kept = []       # list of hold dicts (the best detection per cluster)
    votes = []      # parallel list of sets — distinct frame indices that voted

    for candidate in sorted_holds:
        matched = False
        for i, existing in enumerate(kept):
            if _iou_bbox(candidate["bbox"], existing["bbox"]) > iou_threshold:
                votes[i].add(candidate.get("_frame_idx", 0))
                matched = True
                break
        if not matched:
            kept.append(candidate)
            votes.append({candidate.get("_frame_idx", 0)})

    # Filter by minimum frame support
    result = []
    for hold, vote_set in zip(kept, votes):
        if len(vote_set) >= min_frame_votes:
            hold = dict(hold)
            hold["frame_votes"] = len(vote_set)   # expose for debug
            hold.pop("_frame_idx", None)
            result.append(hold)

    return result


# ── visualisation ─────────────────────────────────────────────────────────────

def draw_projected_holds_on_reference(ref_img_bgr, projected_holds_json):
    out = ref_img_bgr.copy()

    for hold in projected_holds_json.get("holds", []):
        contour = hold.get("projected_contour") or []
        center  = hold.get("projected_center")
        hold_id = hold.get("id")

        if contour and len(contour) >= 3:
            pts = np.array(contour, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [pts], isClosed=True, color=(0, 255, 0), thickness=2)

        if center and len(center) == 2:
            cx, cy = int(center[0]), int(center[1])
            cv2.circle(out, (cx, cy), 4, (0, 255, 255), -1)
            cv2.putText(out, f"id={hold_id}", (cx + 4, max(cy - 4, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    return out


# ── main pipeline ─────────────────────────────────────────────────────────────

def build_projected_hold_summary_for_job(job, *, n_frames: int = 6):
    """
    Detect holds across multiple video frames to overcome occlusion by the climber.

    Steps:
    1. Sample n_frames spread over the first 20 s of the video.
    2. Warp each frame to the rectified reference plane using the calibration H.
    3. Run Roboflow detection on each rectified frame.
    4. Merge all detections and deduplicate with IoU-based NMS.
    5. Draw the merged result on the rectified reference image.
    """
    if not job.video_file:
        raise ValueError("job has no video_file")
    if not job.reference_quad:
        raise ValueError("job has no reference_quad — complete calibration first")
    if not job.reference_rectified_image:
        raise ValueError("job has no reference_rectified_image")
    if not job.reference_canvas_width or not job.reference_canvas_height:
        raise ValueError("job has no reference canvas size")

    out_w = int(job.reference_canvas_width)
    out_h = int(job.reference_canvas_height)

    H = build_reference_homography(job.reference_quad, out_w=out_w, out_h=out_h)

    # ── Step 1: extract frames ────────────────────────────────────────────────
    tmp_dir = Path("/tmp") / f"{job.id}_hold_frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    frame_paths, times_s, _ = extract_frames_first_20s(
        job.video_file.path,
        tmp_dir,
        n=n_frames,
        prefix="hold_frame",
    )

    if not frame_paths:
        raise RuntimeError("no frames could be extracted from the video")

    # ── Steps 2 & 3: rectify each frame and detect holds ─────────────────────
    all_holds: list = []
    last_overlay: np.ndarray | None = None

    for frame_idx, frame_path in enumerate(frame_paths):
        frame_bgr = cv2.imread(str(frame_path))
        if frame_bgr is None:
            continue

        rectified = cv2.warpPerspective(frame_bgr, H, (out_w, out_h))
        result = detect_holds_from_array(rectified)

        for hold in result["holds"]:
            hold["_frame_idx"] = frame_idx  # tag for frame-vote filtering
        all_holds.extend(result["holds"])
        last_overlay = result["overlay_bgr"]  # keep last for debug overlay

    num_frames_used = len(frame_paths)

    if not all_holds:
        # Fallback: try the static rectified reference image
        ref_result = detect_holds_from_array(
            cv2.imread(job.reference_rectified_image.path)
        )
        for hold in ref_result["holds"]:
            hold["_frame_idx"] = 0
        all_holds = ref_result["holds"]
        last_overlay = ref_result["overlay_bgr"]
        num_frames_used = 1

    # ── Step 4: deduplicate and filter by frame support ───────────────────────
    # Require a hold to appear in at least ceil(2/3 × n_frames) distinct frames.
    # This rejects false positives from the climber's body, which moves between frames.
    min_frame_votes = max(2, math.ceil(num_frames_used * 2 / 3))
    unique_holds = _nms_holds(all_holds, iou_threshold=0.3, min_frame_votes=min_frame_votes)

    # Renumber IDs sequentially
    for idx, hold in enumerate(unique_holds, start=1):
        hold["id"] = idx

    # ── Step 5: build output dicts ────────────────────────────────────────────
    image_w = out_w
    image_h = out_h

    detection = {
        "image_width":  image_w,
        "image_height": image_h,
        "num_holds":    len(unique_holds),
        "holds":        unique_holds,
        "frames_used":  len(frame_paths),
    }

    # Detected on rectified plane → coords already in reference space
    projected_holds = []
    for hold in unique_holds:
        projected_holds.append({
            "id":               hold["id"],
            "area":             hold.get("area"),
            "perimeter":        hold.get("perimeter"),
            "projected_center": hold.get("center"),
            "projected_bbox":   hold.get("bbox"),
            "projected_contour": hold.get("contour"),
        })

    projected_holds_json = {
        "plane_width":  out_w,
        "plane_height": out_h,
        "num_holds":    len(projected_holds),
        "holds":        projected_holds,
    }

    # ── Draw and save ─────────────────────────────────────────────────────────
    overlay_bgr = last_overlay if last_overlay is not None else np.zeros((out_h, out_w, 3), dtype=np.uint8)
    ok_overlay, overlay_encoded = cv2.imencode(".jpg", overlay_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok_overlay:
        raise RuntimeError("failed to encode hold overlay image")

    ref_img = cv2.imread(job.reference_rectified_image.path, cv2.IMREAD_COLOR)
    if ref_img is None:
        raise RuntimeError("failed to read reference_rectified_image")

    vis = draw_projected_holds_on_reference(ref_img, projected_holds_json)
    ok_vis, vis_encoded = cv2.imencode(".jpg", vis, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok_vis:
        raise RuntimeError("failed to encode projected hold summary image")

    job.hold_overlay_image.save(
        f"{job.id}_hold_overlay.jpg",
        ContentFile(overlay_encoded.tobytes()),
        save=False,
    )
    job.result_image.save(
        f"{job.id}_projected_hold_summary.jpg",
        ContentFile(vis_encoded.tobytes()),
        save=False,
    )

    job.holds_json = detection
    job.projected_holds_json = projected_holds_json
    job.message = (
        f"hold detection ready — {len(unique_holds)} holds "
        f"(seen in ≥{min_frame_votes}/{num_frames_used} frames)"
    )
    job.status = job.Status.DONE
    job.save(update_fields=[
        "hold_overlay_image", "result_image",
        "holds_json", "projected_holds_json",
        "message", "status", "updated_at",
    ])
