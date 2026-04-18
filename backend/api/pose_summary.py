from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from django.core.files.base import ContentFile

from .extract import extract_frames_first_20s
from pipeline.climbing_spots_pipeline import (
    get_pose_landmarker,
    extract_spots,
    draw_labeled_spots,
    HAND_SPOT_RADIUS,
    FOOT_SPOT_RADIUS,
)
from .pose_projection import (
    build_reference_homography,
    project_points_with_homography,
    clip_projected_points,
)


def build_projected_pose_summary_for_job(
    job,
    *,
    n_frames: int = 4,
    start_s: float = 0.5,
    max_s: float = 20.0,
    pose_model: str = "lite",
):
    """
    Step 1B:
    - sample frames from video
    - run pose on ORIGINAL frames
    - project spots to reference plane
    - draw projected spots on reference rectified image
    - save to job.result_image
    """
    if not job.video_file:
        raise ValueError("job has no video_file")

    if not job.reference_quad:
        raise ValueError("job has no reference_quad")

    if not job.reference_rectified_image:
        raise ValueError("job has no reference_rectified_image")

    if not job.reference_canvas_width or not job.reference_canvas_height:
        raise ValueError("job has no reference canvas size")

    ref_img = cv2.imread(job.reference_rectified_image.path, cv2.IMREAD_COLOR)
    if ref_img is None:
        raise RuntimeError("failed to read reference_rectified_image")

    out_w = int(job.reference_canvas_width)
    out_h = int(job.reference_canvas_height)

    H_ref = build_reference_homography(
        job.reference_quad,
        out_w=out_w,
        out_h=out_h,
    )

    video_path = Path(job.video_file.path)
    tmp_dir = Path("/tmp") / f"{job.id}_pose_projected_frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    frame_paths, times_s, info = extract_frames_first_20s(
        video_path,
        tmp_dir,
        n=n_frames,
        start_s=start_s,
        max_s=max_s,
        prefix="proj_frame",
        jpg_quality=95,
    )

    if not frame_paths:
        raise RuntimeError("no frames extracted")

    all_original_points = []

    with get_pose_landmarker(pose_model=pose_model) as pose:
        for step, frame_path in enumerate(frame_paths, start=1):
            frame = cv2.imread(str(frame_path))
            if frame is None:
                continue

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            spots = extract_spots(frame_rgb, pose)

            for x, y, kind in spots:
                all_original_points.append((x, y, kind, step))

    projected_points = project_points_with_homography(all_original_points, H_ref)
    projected_points = clip_projected_points(projected_points, out_w, out_h)

    out = draw_labeled_spots(
        ref_img,
        projected_points,
        hand_radius=HAND_SPOT_RADIUS,
        foot_radius=FOOT_SPOT_RADIUS,
    )

    ok, encoded = cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise RuntimeError("failed to encode projected summary image")

    job.result_image.save(
        f"{job.id}_projected_pose_summary.jpg",
        ContentFile(encoded.tobytes()),
        save=False,
    )
    job.message = f"projected pose summary ready ({len(projected_points)} points)"
    job.status = job.Status.DONE
    job.save(update_fields=["result_image", "message", "status", "updated_at"])


def build_pose_trajectory_for_job(job, *, pose_model: str = "lite", sample_fps: float = 10.0):
    """
    Process every frame of the video at sample_fps:
    1. Warp each frame to the reference plane using the calibration homography.
    2. Run pose detection on the warped frame (coordinates are already in reference space).
    3. Draw all collected hand/foot positions on the rectified reference image.
    """
    if not job.video_file:
        raise ValueError("job has no video_file")
    if not job.reference_quad:
        raise ValueError("job has no reference_quad")
    if not job.reference_rectified_image:
        raise ValueError("job has no reference_rectified_image")
    if not job.reference_canvas_width or not job.reference_canvas_height:
        raise ValueError("job has no reference canvas size")

    out_w = int(job.reference_canvas_width)
    out_h = int(job.reference_canvas_height)

    H = build_reference_homography(job.reference_quad, out_w=out_w, out_h=out_h)

    ref_img = cv2.imread(job.reference_rectified_image.path, cv2.IMREAD_COLOR)
    if ref_img is None:
        raise RuntimeError("failed to read reference_rectified_image")

    cap = cv2.VideoCapture(str(job.video_file.path))
    if not cap.isOpened():
        raise RuntimeError("failed to open video file")

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = max(1, int(round(video_fps / sample_fps)))

    all_spots = []
    frame_idx = 0

    with get_pose_landmarker(pose_model=pose_model) as pose:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break

            if frame_idx % frame_interval == 0:
                warped = cv2.warpPerspective(frame_bgr, H, (out_w, out_h))
                frame_rgb = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
                spots = extract_spots(frame_rgb, pose)
                for x, y, kind in spots:
                    all_spots.append((x, y, kind, frame_idx))

            frame_idx += 1

    cap.release()

    out = draw_labeled_spots(
        ref_img,
        all_spots,
        hand_radius=HAND_SPOT_RADIUS,
        foot_radius=FOOT_SPOT_RADIUS,
    )

    ok, encoded = cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise RuntimeError("failed to encode pose trajectory image")

    job.pose_result_image.save(
        f"{job.id}_pose_trajectory.jpg",
        ContentFile(encoded.tobytes()),
        save=False,
    )
    job.projected_pose_json = {
        "num_frames_processed": frame_idx,
        "num_spots": len(all_spots),
        "points": [{"x": x, "y": y, "kind": k, "frame_idx": fi} for x, y, k, fi in all_spots],
    }
    job.message = f"pose trajectory ready ({len(all_spots)} spots across {frame_idx} frames)"
    job.status = job.Status.DONE
    job.save(update_fields=["pose_result_image", "projected_pose_json", "message", "status", "updated_at"])