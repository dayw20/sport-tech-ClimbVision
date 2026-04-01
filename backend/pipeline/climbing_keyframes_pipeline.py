#!/usr/bin/env python3
"""
Stage 1: Use AI (YOLO) to detect moving person and parse video into key-frame pictures.
Stage 2: Feed those pictures to the pose model to generate hand/foot spots and composite.

Usage:
  # Full pipeline: video -> key-frame images -> composite with spots
  python climbing_keyframes_pipeline.py video.mov -o composite.png

  # Only extract key-frame pictures (no spots)
  python climbing_keyframes_pipeline.py video.mov --keyframes-dir ./keyframes

  # Generate spots from an existing folder of images
  python climbing_keyframes_pipeline.py --from-images ./keyframes -o composite.png
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# Stage 1: person detection (YOLO)
try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False

# Stage 2: pose + spots (reuse climbing_spots_pipeline)
from climbing_spots_pipeline import (
    MOVE_THRESHOLD_PX,
    draw_labeled_spots,
    extract_spots,
    get_pose_landmarker,
    HAND_SPOT_RADIUS,
    FOOT_SPOT_RADIUS,
    LABEL_FONT,
    HAND_COLOR,
    FOOT_COLOR,
)

COCO_PERSON_CLASS = 0
# bbox center must move this many pixels to count as a new key frame (higher = fewer frames, only significant moves)
PERSON_MOVE_THRESHOLD_PX = 200
DEFAULT_SAMPLE_EVERY = 5


def _person_bbox_center(results, conf_threshold=0.4):
    """
    From YOLO results for one frame, return (cx, cy) of largest person bbox, or None.
    results: single-frame result from model.predict().
    """
    if not results or len(results) == 0:
        return None
    r = results[0]
    if r.boxes is None:
        return None
    boxes = r.boxes
    person_boxes = []
    for i in range(len(boxes)):
        cls = int(boxes.cls[i].item())
        if cls != COCO_PERSON_CLASS:
            continue
        conf = float(boxes.conf[i].item())
        if conf < conf_threshold:
            continue
        xyxy = boxes.xyxy[i].cpu().numpy()
        x1, y1, x2, y2 = xyxy
        person_boxes.append((x1, y1, x2, y2, (x1 + x2) / 2, (y1 + y2) / 2))
    if not person_boxes:
        return None
    # Largest bbox by area
    largest = max(person_boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    return (largest[4], largest[5])


def _has_person_moved(center, last_center, threshold_px: float):
    if last_center is None:
        return True
    dx = center[0] - last_center[0]
    dy = center[1] - last_center[1]
    return (dx * dx + dy * dy) > (threshold_px * threshold_px)


def extract_keyframes(
    video_path: str,
    keyframes_dir: str | Path,
    sample_every: int = DEFAULT_SAMPLE_EVERY,
    person_move_threshold_px: float = PERSON_MOVE_THRESHOLD_PX,
    person_conf_threshold: float = 0.4,
) -> list[Path]:
    """
    Detect person with YOLO; when person has moved, save frame as image.
    Returns list of saved image paths.
    """
    if not HAS_YOLO:
        print("Error: ultralytics (YOLOv8) is required for key-frame extraction. Install with: pip install ultralytics", file=sys.stderr)
        sys.exit(1)

    path = Path(video_path)
    if not path.is_file():
        print(f"Error: video not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(keyframes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO("yolov8n.pt")  # nano, downloads on first run
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"Error: could not open video: {video_path}", file=sys.stderr)
        sys.exit(1)

    saved_paths: list[Path] = []
    frame_idx = 0
    last_center = None
    key_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample_every != 0:
            frame_idx += 1
            continue

        # YOLO expects RGB or BGR; predict returns list of results (one per source)
        results = model.predict(frame, verbose=False, classes=[COCO_PERSON_CLASS])
        center = _person_bbox_center(results, conf_threshold=person_conf_threshold)

        if center is not None and _has_person_moved(center, last_center, person_move_threshold_px):
            key_count += 1
            out_name = out_dir / f"keyframe_{key_count:04d}_f{frame_idx}.jpg"
            cv2.imwrite(str(out_name), frame)
            saved_paths.append(out_name)
            last_center = center

        frame_idx += 1

    cap.release()
    print(f"Saved {len(saved_paths)} key-frame images to {out_dir}", file=sys.stderr)
    return saved_paths


def spots_from_images(
    image_paths: list[Path],
    output_image: str,
    base_image_path: Path | None = None,
) -> None:
    """
    Run pose on each image, collect all spots with step index, draw on base image and save.
    If base_image_path is None, use the first image as base.
    """
    if not image_paths:
        print("Error: no images to process", file=sys.stderr)
        sys.exit(1)

    base_path = base_image_path or image_paths[0]
    base_frame = cv2.imread(str(base_path))
    if base_frame is None:
        print(f"Error: could not read base image {base_path}", file=sys.stderr)
        sys.exit(1)

    all_spots_with_step: list[tuple[int, int, str, int]] = []

    with get_pose_landmarker() as pose:
        for step, img_path in enumerate(image_paths, start=1):
            frame = cv2.imread(str(img_path))
            if frame is None:
                continue
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            spots = extract_spots(frame_rgb, pose)
            for x, y, kind in spots:
                all_spots_with_step.append((x, y, kind, step))

    out = draw_labeled_spots(
        base_frame,
        all_spots_with_step,
        hand_radius=HAND_SPOT_RADIUS,
        foot_radius=FOOT_SPOT_RADIUS,
    )
    # Legend
    h, w = out.shape[:2]
    legend_x, legend_y = 12, h - 50
    cv2.rectangle(out, (legend_x - 4, legend_y - 18), (w - 10, h - 6), (240, 240, 240), -1)
    cv2.rectangle(out, (legend_x - 4, legend_y - 18), (w - 10, h - 6), (80, 80, 80), 1)
    cv2.circle(out, (legend_x + 10, legend_y - 8), 8, HAND_COLOR, 2)
    cv2.putText(out, "Hand", (legend_x + 24, legend_y - 4), LABEL_FONT, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.circle(out, (legend_x + 85, legend_y - 8), 8, FOOT_COLOR, 2)
    cv2.putText(out, "Foot", (legend_x + 99, legend_y - 4), LABEL_FONT, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(out, "Numbers = move order (from key-frame images)", (legend_x, legend_y + 12), LABEL_FONT, 0.4, (0, 0, 0), 1, cv2.LINE_AA)

    cv2.imwrite(output_image, out)
    print(f"Saved: {output_image}")


def main():
    parser = argparse.ArgumentParser(
        description="Detect moving person (YOLO), extract key-frame pictures, then generate hand/foot spots (pose) and composite."
    )
    parser.add_argument(
        "video",
        nargs="?",
        default=None,
        help="Input video path (required unless --from-images)",
    )
    parser.add_argument(
        "-o", "--output",
        default="climbing_spots_composite.png",
        help="Output composite image path",
    )
    parser.add_argument(
        "--keyframes-dir",
        default="keyframes",
        metavar="DIR",
        help="Directory to save key-frame images (default: keyframes)",
    )
    parser.add_argument(
        "--from-images",
        metavar="DIR",
        help="Skip video; use images from DIR to generate spots composite",
    )
    parser.add_argument(
        "--sample-every",
        type=int,
        default=DEFAULT_SAMPLE_EVERY,
        help="Sample every Nth frame for person detection (default: %s)" % DEFAULT_SAMPLE_EVERY,
    )
    parser.add_argument(
        "--person-move-threshold",
        type=float,
        default=PERSON_MOVE_THRESHOLD_PX,
        metavar="PX",
        help="New key frame only when person bbox center moves more than PX pixels; higher = fewer frames, only significant moves (default: %s)" % PERSON_MOVE_THRESHOLD_PX,
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only extract key-frame images; do not run pose or create composite",
    )
    args = parser.parse_args()

    if args.from_images:
        # Stage 2 only: images -> composite
        img_dir = Path(args.from_images)
        if not img_dir.is_dir():
            print(f"Error: not a directory: {args.from_images}", file=sys.stderr)
            sys.exit(1)
        image_paths = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.jpeg")) + sorted(img_dir.glob("*.png"))
        if not image_paths:
            print(f"Error: no .jpg/.jpeg/.png images in {img_dir}", file=sys.stderr)
            sys.exit(1)
        spots_from_images(image_paths, args.output)
        return

    if not args.video:
        parser.error("video path is required unless --from-images is set")

    # Stage 1: video -> key-frame images
    saved = extract_keyframes(
        args.video,
        args.keyframes_dir,
        sample_every=args.sample_every,
        person_move_threshold_px=args.person_move_threshold,
    )

    if args.extract_only:
        return

    if not saved:
        print("No key frames extracted; cannot generate composite.", file=sys.stderr)
        sys.exit(1)

    # Stage 2: key-frame images -> composite
    spots_from_images(saved, args.output)


if __name__ == "__main__":
    main()
