"""Image compression and tiling (R1).

Compression rescales oversized images to a max long edge; tiling splits
extra-long screenshots into ordered, overlapping blocks. Both operate on
raw image bytes and re-encode output as JPEG.
"""

from __future__ import annotations

import math
from io import BytesIO

from PIL import Image


def compress_if_needed(
    data: bytes,
    mime: str,
    *,
    max_long_edge: int = 1800,
    max_pixels: int = 3_500_000,
    quality: int = 85,
) -> tuple[bytes, str]:
    """Scale down and re-encode to JPEG when over the thresholds; else return as-is."""
    img = Image.open(BytesIO(data))
    w, h = img.size
    if max(w, h) <= max_long_edge and w * h <= max_pixels:
        return data, mime
    scale = max_long_edge / max(w, h)
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue(), "image/jpeg"


def _axis_tiles(length: int, tile: int, overlap: int) -> int:
    step = tile - overlap
    return max(1, math.ceil((length - overlap) / step))


def _within_tile_limit(img: Image.Image, tile: int, overlap: int, max_tiles: int) -> Image.Image:
    w, h = img.size
    dominant = h if h >= w else w
    while _axis_tiles(dominant, tile, overlap) > max_tiles:
        step = tile - overlap
        scale = (max_tiles * step + overlap) / dominant
        new_w = max(1, round(w * scale))
        new_h = max(1, round(h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        w, h, dominant = new_w, new_h, new_h if new_h >= new_w else new_w
    return img


def _crop(img: Image.Image, box: tuple[int, int, int, int], index: int, total: int, width: int, height: int) -> tuple[bytes, str, dict]:
    x, y, x2, y2 = box
    area = img.crop(box)
    buf = BytesIO()
    area.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg", {
        "index": index, "total": total, "x": x, "y": y, "w": x2 - x, "h": y2 - y,
    }


def tile_if_needed(
    data: bytes,
    mime: str,
    *,
    tile_long_edge: int = 3600,
    overlap: int = 100,
    max_tiles: int = 8,
) -> list[tuple[bytes, str, dict]]:
    """Split a tall/wide image into overlapping ordered tiles when it exceeds
    `tile_long_edge`. Returns [(tile_bytes, mime, meta)]; a single block when
    no split is needed. `max_tiles` caps the block count by pre-scaling."""
    img = Image.open(BytesIO(data))
    w, h = img.size
    if max(w, h) <= tile_long_edge:
        return [(data, mime, {"index": 0, "total": 1, "x": 0, "y": 0, "w": w, "h": h})]
    img = _within_tile_limit(img, tile_long_edge, overlap, max_tiles)
    w, h = img.size
    tiles: list[tuple[bytes, str, dict]] = []
    step = tile_long_edge - overlap
    if h > w:
        total = _axis_tiles(h, tile_long_edge, overlap)
        for i in range(total):
            y = i * step
            hh = min(tile_long_edge, h - y)
            tiles.append(_crop(img, (0, y, w, y + hh), i, total, w, h))
    elif w > h:
        total = _axis_tiles(w, tile_long_edge, overlap)
        for i in range(total):
            x = i * step
            ww = min(tile_long_edge, w - x)
            tiles.append(_crop(img, (x, 0, x + ww, h), i, total, w, h))
    else:
        rows = _axis_tiles(h, tile_long_edge, overlap)
        cols = _axis_tiles(w, tile_long_edge, overlap)
        total = rows * cols
        idx = 0
        for r in range(rows):
            y = r * step
            hh = min(tile_long_edge, h - y)
            for c in range(cols):
                x = c * step
                ww = min(tile_long_edge, w - x)
                tiles.append(_crop(img, (x, y, x + ww, y + hh), idx, total, w, h))
                idx += 1
    return tiles
