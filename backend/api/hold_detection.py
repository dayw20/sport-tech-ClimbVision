from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests

_API_KEY = os.environ.get("ROBOFLOW_API_KEY", "iEjEjqDWmLZ5DW7s9nDm")
_API_URL = "https://serverless.roboflow.com/hold-detector-rnvkl/2"


def _detect_from_array(img: np.ndarray, conf: int) -> dict[str, Any]:
    """Core detection logic — accepts a BGR numpy array, returns the detection dict."""
    h, w = img.shape[:2]

    _, buffer = cv2.imencode(".jpg", img)
    img_b64 = base64.b64encode(buffer).decode("utf-8")

    response = requests.post(
        _API_URL,
        params={"api_key": _API_KEY, "confidence": conf},
        data=img_b64,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()

    overlay = img.copy()
    holds = []

    for i, pred in enumerate(result.get("predictions", []), start=1):
        cx_f, cy_f = pred["x"], pred["y"]
        pw, ph = pred["width"], pred["height"]
        x1 = int(cx_f - pw / 2)
        y1 = int(cy_f - ph / 2)
        x2 = int(cx_f + pw / 2)
        y2 = int(cy_f + ph / 2)

        raw_points = pred.get("points", [])
        if raw_points:
            contour = [[int(p["x"]), int(p["y"])] for p in raw_points]
            poly = np.array(contour, dtype=np.int32)
            area = float(cv2.contourArea(poly))
            perimeter = float(cv2.arcLength(poly, closed=True))
            M = cv2.moments(poly)
            if M["m00"] != 0:
                cx_f = M["m10"] / M["m00"]
                cy_f = M["m01"] / M["m00"]
        else:
            contour = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            poly = np.array(contour, dtype=np.int32)
            area = float((x2 - x1) * (y2 - y1))
            perimeter = float(2 * ((x2 - x1) + (y2 - y1)))

        cx, cy = int(round(cx_f)), int(round(cy_f))

        holds.append({
            "id": i,
            "class": pred.get("class", "hold"),
            "confidence": float(pred.get("confidence", 0)),
            "bbox": [x1, y1, x2, y2],
            "bbox_normalized": {
                "x_min": round(x1 / w, 6),
                "y_min": round(y1 / h, 6),
                "x_max": round(x2 / w, 6),
                "y_max": round(y2 / h, 6),
            },
            "center": [cx, cy],
            "area": area,
            "perimeter": perimeter,
            "contour": contour,
        })

        color = (0, 200, 0) if pred.get("class") == "hold" else (200, 100, 0)
        if raw_points:
            cv2.polylines(overlay, [poly], isClosed=True, color=color, thickness=2)
        else:
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.circle(overlay, (cx, cy), 4, (0, 255, 255), -1)
        cv2.putText(overlay, f"id={i}", (x1, max(y1 - 5, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    return {
        "image_width": w,
        "image_height": h,
        "num_holds": len(holds),
        "holds": holds,
        "overlay_bgr": overlay,
    }


def detect_holds(image_path: str | Path, *, conf: int = 50) -> dict[str, Any]:
    """Run detection on an image file path."""
    image_path = Path(image_path)
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    return _detect_from_array(img, conf)


def detect_holds_from_array(img: np.ndarray, *, conf: int = 50) -> dict[str, Any]:
    """Run detection on an in-memory BGR numpy array (e.g. a rectified video frame)."""
    return _detect_from_array(img, conf)
