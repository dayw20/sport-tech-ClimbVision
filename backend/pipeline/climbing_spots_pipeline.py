#!/usr/bin/env python3
"""
Climbing hand & foot spot pipeline.
- YOLO mode: use YOLO to detect person and extract keyframes, then draw hand/foot spots.
- Otherwise: MediaPipe Pose Landmarker to detect wrists/ankles; single frame or composite.
"""

import argparse
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from mediapipe.tasks.python.core import base_options as base_options_lib
from mediapipe.tasks.python.vision import pose_landmarker
from mediapipe.tasks.python.vision.core import image as mp_image_lib

# YOLO for keyframe extraction (person detection)
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

# Pose landmark indices (same as MediaPipe PoseLandmark enum)
# Body joints for stick figure
NOSE           = 0
LEFT_ELBOW     = 13
RIGHT_ELBOW    = 14
LEFT_SHOULDER  = 11
RIGHT_SHOULDER = 12
LEFT_HIP       = 23
RIGHT_HIP      = 24
LEFT_KNEE      = 25
RIGHT_KNEE     = 26
# Hands: midpoint of wrist (15/16) and index finger (19/20)
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_INDEX = 19
RIGHT_INDEX = 20
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
LEFT_FOOT_INDEX = 31  # toe
RIGHT_FOOT_INDEX = 32

HAND_INDICES = (LEFT_WRIST, RIGHT_WRIST, LEFT_INDEX, RIGHT_INDEX)
FOOT_ANKLE_INDICES = (LEFT_ANKLE, RIGHT_ANKLE)
FOOT_TOE_INDICES = (LEFT_FOOT_INDEX, RIGHT_FOOT_INDEX)

# Drawing style
HAND_SPOT_RADIUS = 18
FOOT_SPOT_RADIUS = 22
HAND_COLOR = (0, 165, 255)   # Orange (BGR)
FOOT_COLOR = (0, 255, 0)    # Green (BGR)
SPOT_THICKNESS = 3
MIN_VISIBILITY = 0.6  
MIN_POSE_DETECTION_CONFIDENCE = 0.6  
LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX
LABEL_SCALE = 0.6
LABEL_THICKNESS = 2
LABEL_TEXT_COLOR = (255, 255, 255)   
LABEL_BG_COLOR = (0, 0, 0)          


MOVE_THRESHOLD_PX = 35

MOVE_THRESHOLD_MAJOR_PX = 300

# Pose model variants: lite (faster, less accurate), full (better accuracy)
POSE_MODEL_LITE_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
POSE_MODEL_FULL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker/float16/1/pose_landmarker.task"
)
POSE_MODEL_FILENAME = "pose_landmarker_lite.task"
POSE_MODEL_FULL_FILENAME = "pose_landmarker.task"

# YOLO: COCO class 0 = person
YOLO_PERSON_CLASS_ID = 0
YOLO_MODEL_FILENAME = "yolov8n.pt"


def get_pose_model_path(pose_model: str = "lite") -> Path:
    """Return path to pose landmarker .task file, downloading if needed.
    pose_model: 'lite' (faster) or 'full' (more accurate)."""
    script_dir = Path(__file__).resolve().parent
    if pose_model == "full":
        filename = POSE_MODEL_FULL_FILENAME
        url = POSE_MODEL_FULL_URL
    else:
        filename = POSE_MODEL_FILENAME
        url = POSE_MODEL_LITE_URL
    candidates = [
        script_dir / filename,
        script_dir / "models" / filename,
    ]
    for p in candidates:
        if p.is_file():
            return p
    model_dir = script_dir / "models"
    model_dir.mkdir(exist_ok=True)
    path = model_dir / filename
    if path.is_file():
        return path
    print(f"Downloading pose model ({pose_model}) to {path} ...", file=sys.stderr)
    urllib.request.urlretrieve(url, path)
    return path


def get_yolo_model_path() -> Path:
    """Return path to YOLO .pt file (yolov8n.pt in script dir or models/)."""
    script_dir = Path(__file__).resolve().parent
    for sub in ("", "models"):
        p = script_dir / sub / YOLO_MODEL_FILENAME if sub else script_dir / YOLO_MODEL_FILENAME
        if p.is_file():
            return p
    return script_dir / YOLO_MODEL_FILENAME  # default path for download


def extract_keyframes_with_yolo(
    video_path: str,
    sample_every: int = 5,
    conf: float = 0.4,
) -> list[tuple[int, np.ndarray]]:
    """
    Run YOLO person detection on video; return list of (frame_index, frame_bgr)
    for frames where at least one person is detected above conf.
    """
    if not YOLO_AVAILABLE:
        raise RuntimeError("ultralytics is required for --yolo. Install with: pip install ultralytics")
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    model_path = str(get_yolo_model_path())
    if not Path(model_path).is_file():
        raise FileNotFoundError(
            f"YOLO model not found: {model_path}. Place yolov8n.pt in project root or install/download it."
        )
    model = YOLO(model_path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    keyframes: list[tuple[int, np.ndarray]] = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample_every != 0:
            frame_idx += 1
            continue
        results = model(frame, classes=[YOLO_PERSON_CLASS_ID], conf=conf, verbose=False)
        if not results:
            frame_idx += 1
            continue
        # Any detection of person in this frame?
        for r in results:
            if r.boxes is not None and len(r.boxes) > 0:
                keyframes.append((frame_idx, frame.copy()))
                break
        frame_idx += 1
    cap.release()
    return keyframes


def get_pose_landmarker(pose_model: str = "lite"):
    """Create and return a PoseLandmarker (use as context manager). Uses CPU to avoid GPU/OpenGL issues.
    pose_model: 'lite' or 'full' (full is more accurate for hand/foot position)."""
    model_path = str(get_pose_model_path(pose_model=pose_model))
    base_options = base_options_lib.BaseOptions(
        model_asset_path=model_path,
        delegate=base_options_lib.BaseOptions.Delegate.CPU,
    )
    options = pose_landmarker.PoseLandmarkerOptions(
        base_options=base_options,
        min_pose_detection_confidence=MIN_POSE_DETECTION_CONFIDENCE,
    )
    return pose_landmarker.PoseLandmarker.create_from_options(options)


def _get_visible_xy(landmarks, idx: int, w: int, h: int) -> tuple[float, float] | None:
    """Return (x, y) in image coords if landmark visibility >= MIN_VISIBILITY, else None."""
    lm = landmarks[idx]
    vis = lm.visibility if lm.visibility is not None else 1.0
    if vis < MIN_VISIBILITY:
        return None
    return (lm.x * w, lm.y * h)


def extract_spots(frame_rgb: np.ndarray, landmarker) -> list[tuple[int, int, str]]:
    """Returns list of (x, y, kind) in image coordinates where kind is one of LH/RH/LF/RF.
    Hands: index finger (contact point on hold). Feet: midpoint of ankle and toe when both visible.
    At most 4 spots per frame; fewer if visibility < MIN_VISIBILITY."""
    h, w = frame_rgb.shape[:2]
    if not frame_rgb.flags.c_contiguous:
        frame_rgb = np.ascontiguousarray(frame_rgb)
    mp_image = mp_image_lib.Image(
        mp_image_lib.ImageFormat.SRGB,
        frame_rgb,
    )
    result = landmarker.detect(mp_image)
    spots = []

    if not result.pose_landmarks:
        return spots

    landmarks = result.pose_landmarks[0]

    # Left hand: midpoint of wrist (15) and index finger (19); fall back to whichever is visible
    wrist_pt = _get_visible_xy(landmarks, LEFT_WRIST, w, h)
    index_pt = _get_visible_xy(landmarks, LEFT_INDEX, w, h)
    if wrist_pt is not None and index_pt is not None:
        spots.append((int((wrist_pt[0] + index_pt[0]) / 2), int((wrist_pt[1] + index_pt[1]) / 2), "LH"))
    elif wrist_pt is not None:
        spots.append((int(wrist_pt[0]), int(wrist_pt[1]), "LH"))
    elif index_pt is not None:
        spots.append((int(index_pt[0]), int(index_pt[1]), "LH"))

    # Right hand: midpoint of wrist (16) and index finger (20); fall back to whichever is visible
    wrist_pt = _get_visible_xy(landmarks, RIGHT_WRIST, w, h)
    index_pt = _get_visible_xy(landmarks, RIGHT_INDEX, w, h)
    if wrist_pt is not None and index_pt is not None:
        spots.append((int((wrist_pt[0] + index_pt[0]) / 2), int((wrist_pt[1] + index_pt[1]) / 2), "RH"))
    elif wrist_pt is not None:
        spots.append((int(wrist_pt[0]), int(wrist_pt[1]), "RH"))
    elif index_pt is not None:
        spots.append((int(index_pt[0]), int(index_pt[1]), "RH"))

    # Left foot: midpoint of ankle (27) and toe (31) when both visible
    ankle_pt = _get_visible_xy(landmarks, LEFT_ANKLE, w, h)
    toe_pt = _get_visible_xy(landmarks, LEFT_FOOT_INDEX, w, h)
    if ankle_pt is not None and toe_pt is not None:
        spots.append((int((ankle_pt[0] + toe_pt[0]) / 2), int((ankle_pt[1] + toe_pt[1]) / 2), "LF"))
    elif ankle_pt is not None:
        spots.append((int(ankle_pt[0]), int(ankle_pt[1]), "LF"))

    # Right foot: midpoint of ankle (28) and toe (32) when both visible
    ankle_pt = _get_visible_xy(landmarks, RIGHT_ANKLE, w, h)
    toe_pt = _get_visible_xy(landmarks, RIGHT_FOOT_INDEX, w, h)
    if ankle_pt is not None and toe_pt is not None:
        spots.append((int((ankle_pt[0] + toe_pt[0]) / 2), int((ankle_pt[1] + toe_pt[1]) / 2), "RF"))
    elif ankle_pt is not None:
        spots.append((int(ankle_pt[0]), int(ankle_pt[1]), "RF"))

    # Body landmarks for stick figure (not used for hold matching)
    for idx, kind in [
        (NOSE,           "NOSE"),
        (LEFT_SHOULDER,  "LSHO"),
        (RIGHT_SHOULDER, "RSHO"),
        (LEFT_ELBOW,     "LELB"),
        (RIGHT_ELBOW,    "RELB"),
        (LEFT_HIP,       "LHIP"),
        (RIGHT_HIP,      "RHIP"),
        (LEFT_KNEE,      "LKNE"),
        (RIGHT_KNEE,     "RKNE"),
    ]:
        pt = _get_visible_xy(landmarks, idx, w, h)
        if pt is not None:
            spots.append((int(pt[0]), int(pt[1]), kind))

    return spots


def _has_moved(
    spots: list[tuple[int, int, str]],
    last_positions: list[tuple[int, int]],
    threshold_px: float,
) -> bool:
    """True if no last positions (first frame) or any current spot is > threshold_px from all last positions."""
    if not spots:
        return False
    if not last_positions:
        return True
    threshold_sq = threshold_px * threshold_px
    for x, y, _ in spots:
        min_d_sq = min((x - px) ** 2 + (y - py) ** 2 for px, py in last_positions)
        if min_d_sq > threshold_sq:
            return True
    return False


_HAND_KINDS = {"LH", "RH", "hand"}
_FOOT_KINDS = {"LF", "RF", "foot"}


def draw_spots_on_frame(frame, spots, hand_radius=HAND_SPOT_RADIUS, foot_radius=FOOT_SPOT_RADIUS):
    out = frame.copy()
    for x, y, kind in spots:
        r = hand_radius if kind in _HAND_KINDS else foot_radius
        color = HAND_COLOR if kind in _HAND_KINDS else FOOT_COLOR
        cv2.circle(out, (x, y), r, color, SPOT_THICKNESS)
    return out


def _draw_label(img, text: str, x: int, y: int, color=LABEL_TEXT_COLOR, bg_color=LABEL_BG_COLOR):
    """Draw a readable label (e.g. step number) at (x, y)."""
    (tw, th), _ = cv2.getTextSize(text, LABEL_FONT, LABEL_SCALE, LABEL_THICKNESS)
    # Center label above the spot; ensure it stays in frame
    tx = x - tw // 2
    ty = y - 24  # above circle
    pad = 2
    # Black background rect for readability
    cv2.rectangle(
        img,
        (tx - pad, ty - th - pad),
        (tx + tw + pad, ty + pad),
        bg_color,
        -1,
    )
    cv2.putText(
        img, text, (tx, ty),
        LABEL_FONT, LABEL_SCALE, color, LABEL_THICKNESS,
        cv2.LINE_AA,
    )


def draw_labeled_spots(
    frame,
    spots_with_step: list[tuple[int, int, str, int]],
    hand_radius=HAND_SPOT_RADIUS,
    foot_radius=FOOT_SPOT_RADIUS,
):
    """Draw spots and label each with its move/step number (x, y, kind, step)."""
    out = frame.copy()
    for x, y, kind, step in spots_with_step:
        r = hand_radius if kind in _HAND_KINDS else foot_radius
        color = HAND_COLOR if kind in _HAND_KINDS else FOOT_COLOR
        cv2.circle(out, (x, y), r, color, SPOT_THICKNESS)
        _draw_label(out, str(step), x, y)
    return out


def run_on_video(
    video_path: str,
    output_image: str,
    composite: bool = False,
    sample_every: int = 5,
    frame_index: int | None = None,
    move_threshold_px: float = MOVE_THRESHOLD_PX,
    pose_model: str = "lite",
):
    """
    Process video and write an image with hand/foot spots.

    - If composite is False and frame_index is None: use the middle frame.
    - If composite is False and frame_index is set: use that frame index.
    - If composite is True: overlay spots only when climber has moved (see move_threshold_px).
    """
    path = Path(video_path)
    if not path.is_file():
        print(f"Error: video file not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"Error: could not open video: {video_path}", file=sys.stderr)
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    with get_pose_landmarker(pose_model=pose_model) as pose:
        if composite:
            # Composite: record spots only when climber has moved (not every frame)
            base_frame = None
            all_spots_with_step: list[tuple[int, int, str, int]] = []  # (x, y, kind, step)
            frame_count = 0
            step = 0
            last_positions: list[tuple[int, int]] = []

            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if base_frame is None:
                    base_frame = frame.copy()
                if frame_count % sample_every != 0:
                    frame_count += 1
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                spots = extract_spots(frame_rgb, pose)

                if _has_moved(spots, last_positions, move_threshold_px):
                    step += 1
                    for x, y, kind in spots:
                        all_spots_with_step.append((x, y, kind, step))
                    last_positions = [(x, y) for x, y, _ in spots]

                frame_count += 1

            cap.release()

            out = draw_labeled_spots(
                base_frame,
                all_spots_with_step,
                hand_radius=HAND_SPOT_RADIUS,
                foot_radius=FOOT_SPOT_RADIUS,
            )
            # Legend: number = move order; orange = hand, green = foot
            h, w = out.shape[:2]
            legend_x, legend_y = 12, h - 50
            cv2.rectangle(out, (legend_x - 4, legend_y - 18), (w - 10, h - 6), (240, 240, 240), -1)
            cv2.rectangle(out, (legend_x - 4, legend_y - 18), (w - 10, h - 6), (80, 80, 80), 1)
            cv2.circle(out, (legend_x + 10, legend_y - 8), 8, HAND_COLOR, 2)
            cv2.putText(out, "Hand", (legend_x + 24, legend_y - 4), LABEL_FONT, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
            cv2.circle(out, (legend_x + 85, legend_y - 8), 8, FOOT_COLOR, 2)
            cv2.putText(out, "Foot", (legend_x + 99, legend_y - 4), LABEL_FONT, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
            cv2.putText(out, "Numbers = move order (recorded when climber moves)", (legend_x, legend_y + 12), LABEL_FONT, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            # Single frame
            target = frame_index if frame_index is not None else max(0, total_frames // 2)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                print("Error: could not read frame", file=sys.stderr)
                sys.exit(1)

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            spots = extract_spots(frame_rgb, pose)
            out = draw_spots_on_frame(frame, spots)

    cv2.imwrite(output_image, out)
    print(f"Saved: {output_image}")


def run_on_video_yolo(
    video_path: str,
    output_image: str,
    sample_every: int = 5,
    yolo_conf: float = 0.4,
    move_threshold_px: float = MOVE_THRESHOLD_MAJOR_PX,
    pose_model: str = "lite",
):
    """
    Use YOLO to select frames where a person is detected, then run pose/spot
    only on frames where the climber has made a major movement (one limb moved
    at least move_threshold_px). Output is a composite with fewer, clearer spots.
    """
    keyframes = extract_keyframes_with_yolo(
        video_path,
        sample_every=sample_every,
        conf=yolo_conf,
    )
    if not keyframes:
        print("No frames with person detected by YOLO. Try lower --yolo-conf or different video.", file=sys.stderr)
        sys.exit(1)
    print(f"YOLO selected {len(keyframes)} keyframes (person detected)", file=sys.stderr)

    base_frame = keyframes[0][1].copy()
    all_spots_with_step: list[tuple[int, int, str, int]] = []
    step = 0
    last_positions: list[tuple[int, int]] = []

    with get_pose_landmarker(pose_model=pose_model) as pose:
        for frame_idx, frame in keyframes:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            spots = extract_spots(frame_rgb, pose)
            if _has_moved(spots, last_positions, move_threshold_px):
                step += 1
                for x, y, kind in spots:
                    all_spots_with_step.append((x, y, kind, step))
                last_positions = [(x, y) for x, y, _ in spots]

    out = draw_labeled_spots(
        base_frame,
        all_spots_with_step,
        hand_radius=HAND_SPOT_RADIUS,
        foot_radius=FOOT_SPOT_RADIUS,
    )
    h, w = out.shape[:2]
    legend_x, legend_y = 12, h - 50
    cv2.rectangle(out, (legend_x - 4, legend_y - 18), (w - 10, h - 6), (240, 240, 240), -1)
    cv2.rectangle(out, (legend_x - 4, legend_y - 18), (w - 10, h - 6), (80, 80, 80), 1)
    cv2.circle(out, (legend_x + 10, legend_y - 8), 8, HAND_COLOR, 2)
    cv2.putText(out, "Hand", (legend_x + 24, legend_y - 4), LABEL_FONT, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.circle(out, (legend_x + 85, legend_y - 8), 8, FOOT_COLOR, 2)
    cv2.putText(out, "Foot", (legend_x + 99, legend_y - 4), LABEL_FONT, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(out, "YOLO keyframes + pose spots (numbers = move order)", (legend_x, legend_y + 12), LABEL_FONT, 0.4, (0, 0, 0), 1, cv2.LINE_AA)

    cv2.imwrite(output_image, out)
    print(f"Saved: {output_image}")
    print(f"Recorded {step} major moves (use --move-threshold to require larger movement)", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Draw climber hand and foot spots on video frames using pose estimation."
    )
    parser.add_argument(
        "video",
        nargs="?",
        default="1-1条.mov",
        help="Input video path (default: 1-1条.mov)",
    )
    parser.add_argument(
        "-o", "--output",
        default="climbing_spots.png",
        help="Output image path (default: climbing_spots.png)",
    )
    parser.add_argument(
        "-c", "--composite",
        action="store_true",
        help="Overlay all hand/foot spots from sampled frames into one image",
    )
    parser.add_argument(
        "--sample-every",
        type=int,
        default=5,
        help="For composite mode: use every Nth frame (default: 5)",
    )
    parser.add_argument(
        "--frame",
        type=int,
        default=None,
        help="Use this frame index for single-frame mode (default: middle frame)",
    )
    parser.add_argument(
        "--move-threshold",
        type=float,
        default=None,
        metavar="PX",
        help="Only record a move when a limb moves more than PX pixels. Default: %s (composite) or %s for --yolo (major moves only)" % (MOVE_THRESHOLD_PX, MOVE_THRESHOLD_MAJOR_PX),
    )
    parser.add_argument(
        "--yolo",
        action="store_true",
        help="Use YOLO to select keyframes (person detection), then draw spots on those frames",
    )
    parser.add_argument(
        "--yolo-conf",
        type=float,
        default=0.4,
        metavar="C",
        help="YOLO person detection confidence threshold (default: 0.4)",
    )
    parser.add_argument(
        "--pose-model",
        choices=("lite", "full"),
        default="lite",
        help="Pose model: lite (faster, default) or full (more accurate hand/foot position)",
    )
    args = parser.parse_args()
    move_threshold = (
        args.move_threshold
        if args.move_threshold is not None
        else (MOVE_THRESHOLD_MAJOR_PX if args.yolo else MOVE_THRESHOLD_PX)
    )

    if args.yolo:
        run_on_video_yolo(
            video_path=args.video,
            output_image=args.output,
            sample_every=args.sample_every,
            yolo_conf=args.yolo_conf,
            move_threshold_px=move_threshold,
            pose_model=args.pose_model,
        )
    else:
        run_on_video(
            video_path=args.video,
            output_image=args.output,
            composite=args.composite,
            sample_every=args.sample_every,
            frame_index=args.frame,
            move_threshold_px=move_threshold,
            pose_model=args.pose_model,
        )


if __name__ == "__main__":
    main()
