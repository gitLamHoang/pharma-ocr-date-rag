"""Clean-up of a scanned page for a second Tesseract pass.

`prepare` makes a black-on-white image: grayscale, light denoise (3x3 median), deskew (the angle
whose horizontal projection profile is sharpest), upscale when the estimated x-height is under
20 px, and an adaptive threshold (ink is darker than its neighbourhood). The rotation and scale
it applied are kept in the image's `info`, so `to_original` can map word boxes back onto the
original page. Pillow only.
"""

from __future__ import annotations

import math
import statistics

from PIL import Image, ImageChops, ImageFilter, ImageOps

from .models import BBox

MAX_SKEW = 3.0  # degrees searched each way
SKEW_WIDTH = 1000  # the skew search runs on a copy this wide
MIN_X_HEIGHT = 20
TARGET_X_HEIGHT = 30
MAX_SCALE = 3.0
THRESHOLD_RADIUS = 15  # px, the neighbourhood of the adaptive threshold
THRESHOLD_OFFSET = 12  # grey levels below the neighbourhood mean that count as ink
ALWAYS_INK = 60  # grey levels at or below this are ink whatever the neighbourhood


def prepare(img: Image.Image) -> Image.Image:
    """The cleaned page; `info` holds `deskew_angle` (degrees), `scale` and `original_size`."""
    gray = ImageOps.grayscale(img).filter(ImageFilter.MedianFilter(3))
    angle = estimate_skew(gray)
    if angle:
        gray = gray.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
    x_height = estimate_x_height(gray)
    scale = min(MAX_SCALE, TARGET_X_HEIGHT / x_height) if x_height and x_height < MIN_X_HEIGHT else 1.0
    if scale > 1:
        gray = gray.resize((round(gray.width * scale), round(gray.height * scale)), Image.Resampling.LANCZOS)
    out = _threshold(gray)
    out.info.update(deskew_angle=angle, scale=scale, original_size=img.size)
    return out


def estimate_skew(gray: Image.Image) -> float:
    """The rotation (degrees, counter-clockwise, as `Image.rotate` takes it) that levels the text
    lines: the angle whose row profile has the highest variance. 0.0 for a blank page."""
    small = (
        gray
        if gray.width <= SKEW_WIDTH
        else gray.resize(
            (SKEW_WIDTH, max(1, round(gray.height * SKEW_WIDTH / gray.width))), Image.Resampling.BOX
        )
    )
    ink = small.point(lambda v: 255 if v < 128 else 0)
    if ink.getbbox() is None:
        return 0.0

    def sharpness(angle: float) -> float:
        rotated = ink.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=0)
        return statistics.pvariance(
            rotated.resize((1, rotated.height), Image.Resampling.BOX).get_flattened_data()
        )

    coarse = max((a / 2 for a in range(int(-2 * MAX_SKEW), int(2 * MAX_SKEW) + 1)), key=sharpness)
    fine = max((coarse + a / 10 for a in range(-5, 6)), key=sharpness)
    return round(fine, 1) if abs(fine) >= 0.1 else 0.0


def estimate_x_height(gray: Image.Image) -> float | None:
    """Median height of the dense core of each text line, in px; None when there is no text.

    A line is a run of rows holding ink; its core is the rows with at least half the line's
    densest row, which for mixed-case text is the x-height band (cap height for capitals)."""
    ink = gray.point(lambda v: 255 if v < 128 else 0)
    rows = list(ink.resize((1, ink.height), Image.Resampling.BOX).get_flattened_data())
    peak = max(rows, default=0)
    if not peak:
        return None
    heights, line = [], []
    for value in [*rows, 0]:
        if value > peak * 0.05:
            line.append(value)
        elif line:
            core = sum(1 for v in line if v >= max(line) / 2)
            if len(line) >= 3:
                heights.append(core)
            line = []
    return float(statistics.median(heights)) if heights else None


def _threshold(gray: Image.Image) -> Image.Image:
    mean = gray.filter(ImageFilter.BoxBlur(THRESHOLD_RADIUS))
    darker = ImageChops.subtract(mean, gray)  # how much darker than its neighbourhood
    local = darker.point(lambda v: 0 if v > THRESHOLD_OFFSET else 255)
    dark = gray.point(lambda v: 0 if v <= ALWAYS_INK else 255)
    return ImageChops.darker(local, dark)


def to_original(box: BBox, prepared: Image.Image) -> BBox:
    """A box on the prepared image mapped back onto the original page (the bounding box of its
    corners, undoing the upscale and then the rotation about the page centre)."""
    scale = prepared.info.get("scale", 1.0)
    angle = math.radians(prepared.info.get("deskew_angle", 0.0))
    width, height = prepared.info.get("original_size", prepared.size)
    cx, cy = width / 2, height / 2
    cos, sin = math.cos(angle), math.sin(angle)
    xs, ys = [], []
    for x, y in ((box.x0, box.y0), (box.x1, box.y0), (box.x0, box.y1), (box.x1, box.y1)):
        dx, dy = x / scale - cx, y / scale - cy
        xs.append(cx + dx * cos - dy * sin)
        ys.append(cy + dx * sin + dy * cos)
    return BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))
