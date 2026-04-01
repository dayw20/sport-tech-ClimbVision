from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import cv2


PathLike = Union[str, Path]


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    fps: float
    frame_count: int
    duration_s: float
    width: int
    height: int


def get_video_info(video_path: PathLike) -> VideoInfo:
    """
    Read basic video metadata using OpenCV.
    """
    video_path = Path(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    cap.release()

    # duration: prefer frame_count/fps if fps>0, else unknown => 0
    duration_s = (frame_count / fps) if (fps and fps > 1e-6 and frame_count > 0) else 0.0

    return VideoInfo(
        path=video_path,
        fps=fps,
        frame_count=frame_count,
        duration_s=duration_s,
        width=width,
        height=height,
    )


def sample_times_first_20s(
    video_duration_s: Optional[float],
    n: int = 6,
    *,
    start_s: float = 0.5,
    max_s: float = 20.0,
) -> List[float]:
    """
    Uniformly sample n timestamps in [start_s, min(max_s, duration)].

    - start_s defaults to 0.5s to avoid common black/blur first frame.
    - If duration is unknown/0, assume at least max_s.
    """
    if n <= 0:
        return []

    # Determine effective end time
    end_s = max_s
    if video_duration_s is not None and video_duration_s > 0:
        end_s = min(max_s, video_duration_s)

    if end_s <= start_s:
        return [max(0.0, end_s)]

    if n == 1:
        return [start_s]

    step = (end_s - start_s) / (n - 1)
    return [start_s + i * step for i in range(n)]


def _read_frame_at_time(cap: cv2.VideoCapture, t_seconds: float) -> Optional["cv2.Mat"]:
    """
    Seek by milliseconds first (more robust for some codecs), then read.
    """
    # Seek
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t_seconds) * 1000.0)
    ok, frame = cap.read()
    if ok and frame is not None:
        return frame
    return None


def extract_frame_at_time(
    video_path: PathLike,
    out_path: PathLike,
    t_seconds: float = 0.0,
) -> None:
    """
    Backward-compatible: Extract a frame at time t_seconds and save as JPEG to out_path.
    """
    video_path = Path(video_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    frame = _read_frame_at_time(cap, t_seconds)
    cap.release()

    if frame is None:
        raise RuntimeError(f"Failed to read frame at t={t_seconds}s from {video_path}")

    ok = cv2.imwrite(str(out_path), frame)
    if not ok:
        raise RuntimeError(f"Failed to write frame image to {out_path}")


def extract_frames_at_times(
    video_path: PathLike,
    out_dir: PathLike,
    times_s: Sequence[float],
    *,
    prefix: str = "frame",
    jpg_quality: int = 95,
) -> List[Path]:
    """
    Extract multiple frames at given timestamps and write them to out_dir.
    Returns the list of written frame paths (sorted by the input order).

    This is the most useful "model input preparation" function:
    - model teammates can read these JPGs as inputs
    - your task pipeline can loop through the returned paths
    """
    video_path = Path(video_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not times_s:
        return []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    written: List[Path] = []

    # OpenCV JPEG quality
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(jpg_quality)]

    for i, t in enumerate(times_s):
        frame = _read_frame_at_time(cap, float(t))
        if frame is None:
            # You can choose to skip or hard-fail; for pipeline stability, skipping is often nicer.
            # Here we skip but still keep it explicit.
            continue

        out_path = out_dir / f"{prefix}_{i:03d}_t{t:.2f}.jpg"
        ok = cv2.imwrite(str(out_path), frame, encode_params)
        if ok:
            written.append(out_path)

    cap.release()

    if not written:
        raise RuntimeError(f"No frames extracted from {video_path} for times={times_s}")

    return written


def extract_frames_first_20s(
    video_path: PathLike,
    out_dir: PathLike,
    *,
    n: int = 6,
    start_s: float = 0.5,
    max_s: float = 20.0,
    prefix: str = "frame",
    jpg_quality: int = 95,
) -> Tuple[List[Path], List[float], VideoInfo]:
    """
    Convenience wrapper:
    - reads video info
    - samples times in first 20s
    - extracts frames

    Returns: (frame_paths, times_s, video_info)
    """
    info = get_video_info(video_path)
    times = sample_times_first_20s(info.duration_s if info.duration_s > 0 else None, n=n, start_s=start_s, max_s=max_s)
    paths = extract_frames_at_times(info.path, out_dir, times, prefix=prefix, jpg_quality=jpg_quality)
    return paths, times, info
