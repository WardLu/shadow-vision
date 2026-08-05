"""Image compression and tiling tests (R1)."""
import io

import pytest
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # allow large test screenshots

from vision_mcp import imageproc


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as img:
        return img.size


def test_small_image_not_compressed() -> None:
    original = _png(100, 100)
    out, mime = imageproc.compress_if_needed(original, "image/png")
    assert out == original
    assert mime == "image/png"


def test_large_image_compressed_to_threshold() -> None:
    out, mime = imageproc.compress_if_needed(_png(3000, 3000), "image/png")
    assert mime == "image/jpeg"
    w, h = _size(out)
    assert max(w, h) <= 1800


def test_tall_image_tiled_into_blocks() -> None:
    tiles = imageproc.tile_if_needed(_png(2000, 6000), "image/png")
    assert len(tiles) > 1
    metas = [t[2] for t in tiles]
    assert metas[0]["total"] == len(tiles) == metas[-1]["total"]
    assert [m["index"] for m in metas] == list(range(len(tiles)))


def test_tile_overlap_is_consistent() -> None:
    overlap = 100
    tiles = imageproc.tile_if_needed(_png(2000, 6000), "image/png", overlap=overlap)
    metas = [t[2] for t in tiles]
    for prev, cur in zip(metas, metas[1:]):
        assert cur["y"] == prev["y"] + prev["h"] - overlap


def test_small_image_tile_returns_single_block() -> None:
    tiles = imageproc.tile_if_needed(_png(500, 500), "image/png")
    assert len(tiles) == 1
    assert tiles[0][2]["total"] == 1
    assert tiles[0][2]["index"] == 0


def test_tile_block_count_respects_limit() -> None:
    tiles = imageproc.tile_if_needed(_png(5000, 30000), "image/png", max_tiles=8)
    assert len(tiles) <= 8
    metas = [t[2] for t in tiles]
    assert metas[-1]["total"] == len(tiles)
