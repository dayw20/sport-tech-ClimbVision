from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from io import BytesIO
from typing import List, Sequence, Tuple

import cv2
import numpy as np
from django.core.files.base import ContentFile
from PIL import Image

from .extract import extract_frame_at_time

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


Point = Tuple[float, float]


def order_quad_points(quad: Sequence[Sequence[float]]) -> np.ndarray:
    """
    Expect 4 points clicked in order:
    top-left, top-right, bottom-right, bottom-left
    """
    if len(quad) != 4:
        raise ValueError("quad must contain exactly 4 points")

    pts = np.array(quad, dtype=np.float32)
    if pts.shape != (4, 2):
        raise ValueError("quad must be shape (4,2)")
    return pts


def compute_reference_canvas_size(quad_pts: np.ndarray) -> tuple[int, int]:
    """
    Compute a reasonable rectified canvas size from the selected quad.
    """
    tl, tr, br, bl = quad_pts

    width_top = np.linalg.norm(tr - tl)
    width_bottom = np.linalg.norm(br - bl)
    height_left = np.linalg.norm(bl - tl)
    height_right = np.linalg.norm(br - tr)

    width = int(round(max(width_top, width_bottom)))
    height = int(round(max(height_left, height_right)))

    width = max(width, 64)
    height = max(height, 64)
    return width, height


def warp_quad_to_canvas(image_bgr: np.ndarray, quad_pts: np.ndarray, out_w: int, out_h: int):
    dst = np.array(
        [
            [0, 0],
            [out_w - 1, 0],
            [out_w - 1, out_h - 1],
            [0, out_h - 1],
        ],
        dtype=np.float32,
    )
    H = cv2.getPerspectiveTransform(quad_pts, dst)
    warped = cv2.warpPerspective(image_bgr, H, (out_w, out_h))
    return warped, H


def encode_image_base64(image_bgr: np.ndarray, max_size: int = 1024) -> str:
    h, w = image_bgr.shape[:2]
    if max(h, w) > max_size:
        scale = max_size / float(max(h, w))
        image_bgr = cv2.resize(
            image_bgr,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    image_pil = Image.fromarray(image_rgb)
    buffer = BytesIO()
    image_pil.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def detect_wall_boundary_with_openai(image_bgr: np.ndarray) -> np.ndarray | None:
    if not OPENAI_AVAILABLE:
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    h, w = image_bgr.shape[:2]
    client = OpenAI(api_key=api_key)
    image_base64 = encode_image_base64(image_bgr, max_size=1024)

    prompt = f"""Analyze this climbing wall photo and identify the wall's boundary quadrilateral.

Image dimensions: {w}x{h} pixels

Return ONLY JSON in this exact shape:
{{
  "wall_boundary": {{
    "top_left": {{"x": <x>, "y": <y>}},
    "top_right": {{"x": <x>, "y": <y>}},
    "bottom_right": {{"x": <x>, "y": <y>}},
    "bottom_left": {{"x": <x>, "y": <y>}}
  }}
}}

Rules:
- Detect the main climbable wall plane only
- Exclude floor, ceiling, side walls, and surrounding gym area
- Coordinates must be pixel positions in the original image
- If uncertain, return {{"wall_boundary": null}}"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        max_tokens=500,
        temperature=0.1,
    )

    content = (response.choices[0].message.content or "").strip()
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0].strip()

    data = json.loads(content)
    boundary = data.get("wall_boundary")
    if boundary is None:
        return None

    quad = np.array(
        [
            [boundary["top_left"]["x"], boundary["top_left"]["y"]],
            [boundary["top_right"]["x"], boundary["top_right"]["y"]],
            [boundary["bottom_right"]["x"], boundary["bottom_right"]["y"]],
            [boundary["bottom_left"]["x"], boundary["bottom_left"]["y"]],
        ],
        dtype=np.float32,
    )
    quad[:, 0] = np.clip(quad[:, 0], 0, w - 1)
    quad[:, 1] = np.clip(quad[:, 1], 0, h - 1)
    return quad


def extract_reference_frame_for_job(job, t_seconds: float = 0.5):
    """
    Extract one frame from the uploaded video and save it to job.reference_frame_image.
    """
    if not job.video_file:
        raise ValueError("job has no video_file")

    video_path = Path(job.video_file.path)
    tmp_out = Path("/tmp") / f"{job.id}_reference_t{t_seconds:.2f}.jpg"

    extract_frame_at_time(video_path, tmp_out, t_seconds=t_seconds)

    with open(tmp_out, "rb") as f:
        content = f.read()

    job.reference_frame_image.save(
        f"{job.id}_reference_frame.jpg",
        ContentFile(content),
        save=False,
    )
    job.reference_frame_time = t_seconds
    job.save(update_fields=["reference_frame_image", "reference_frame_time", "updated_at"])


def auto_calibrate_reference_frame(job) -> bool:
    if not job.reference_frame_image:
        return False

    image_bgr = cv2.imread(job.reference_frame_image.path, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise RuntimeError("failed to read reference frame image")

    try:
        quad_pts = detect_wall_boundary_with_openai(image_bgr)
    except Exception:
        return False

    if quad_pts is None:
        return False

    save_reference_calibration(job, quad_pts.tolist())
    return True


def save_reference_calibration(job, quad: Sequence[Sequence[float]]):
    """
    Use the saved reference_frame_image + user-selected quad
    to build a rectified reference image and save calibration metadata.
    """
    if not job.reference_frame_image:
        raise ValueError("job has no reference_frame_image")

    img = cv2.imread(job.reference_frame_image.path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("failed to read reference frame image")

    quad_pts = order_quad_points(quad)
    out_w, out_h = compute_reference_canvas_size(quad_pts)
    warped, _H = warp_quad_to_canvas(img, quad_pts, out_w, out_h)

    ok, encoded = cv2.imencode(".jpg", warped, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise RuntimeError("failed to encode rectified reference image")

    job.reference_quad = [[float(x), float(y)] for x, y in quad_pts.tolist()]
    job.reference_canvas_width = out_w
    job.reference_canvas_height = out_h
    job.calibration_status = job.CalibrationStatus.READY

    job.reference_rectified_image.save(
        f"{job.id}_reference_rectified.jpg",
        ContentFile(encoded.tobytes()),
        save=False,
    )

    job.save(
        update_fields=[
            "reference_quad",
            "reference_canvas_width",
            "reference_canvas_height",
            "reference_rectified_image",
            "calibration_status",
            "updated_at",
        ]
    )
