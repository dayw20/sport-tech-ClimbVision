from __future__ import annotations

from typing import Iterable, Sequence

import cv2
import numpy as np


def build_reference_homography(
    reference_quad: Sequence[Sequence[float]],
    out_w: int,
    out_h: int,
) -> np.ndarray:
    """
    Build homography that maps original-image quad -> rectified reference canvas.
    Quad order must be:
    top-left, top-right, bottom-right, bottom-left
    """
    src = np.array(reference_quad, dtype=np.float32)
    if src.shape != (4, 2):
        raise ValueError("reference_quad must be shape (4, 2)")

    dst = np.array(
        [
            [0, 0],
            [out_w - 1, 0],
            [out_w - 1, out_h - 1],
            [0, out_h - 1],
        ],
        dtype=np.float32,
    )

    H = cv2.getPerspectiveTransform(src, dst)
    return H


def project_points_with_homography(
    points: Iterable[tuple[float, float, str, int]],
    H: np.ndarray,
) -> list[tuple[int, int, str, int]]:
    """
    Project points from original image plane to reference rectified plane.

    Input:
      [(x, y, kind, step), ...]

    Output:
      [(x_proj, y_proj, kind, step), ...]
    """
    points = list(points)
    if not points:
        return []

    xy = np.array([[x, y] for x, y, _kind, _step in points], dtype=np.float32)
    xy = xy.reshape(-1, 1, 2)

    projected = cv2.perspectiveTransform(xy, H).reshape(-1, 2)

    out = []
    for (x_p, y_p), (_x, _y, kind, step) in zip(projected, points):
        out.append((int(round(x_p)), int(round(y_p)), kind, step))
    return out


def clip_projected_points(
    points: Iterable[tuple[int, int, str, int]],
    width: int,
    height: int,
) -> list[tuple[int, int, str, int]]:
    """
    Keep only projected points that fall inside the reference canvas.
    """
    out = []
    for x, y, kind, step in points:
        if 0 <= x < width and 0 <= y < height:
            out.append((x, y, kind, step))
    return out