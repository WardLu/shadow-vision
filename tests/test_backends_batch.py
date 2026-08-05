"""Batch image loading tests (F3)."""
import base64
from unittest.mock import patch

import pytest

from vision_mcp.backends import _load_images_batch
from vision_mcp.config import Config


def _args(items):
    return {"images": items}


def test_batch_loads_images_and_labels() -> None:
    args = _args([
        {"image_base64": base64.b64encode(b"a").decode(), "mime_type": "image/png", "label": "left"},
        {"image_base64": base64.b64encode(b"b").decode(), "mime_type": "image/png", "label": "right"},
    ])
    images, labels = _load_images_batch(Config(auto_compress=False), args)
    assert len(images) == 2
    assert labels == ["left", "right"]
    assert images[0][1] == "image/png"


def test_batch_rejects_missing_images() -> None:
    with pytest.raises(ValueError, match="images array"):
        _load_images_batch(Config(), {})


def test_batch_enforces_max() -> None:
    items = [{"image_base64": "eA==", "mime_type": "image/png"} for _ in range(6)]
    with pytest.raises(ValueError, match="too many"):
        _load_images_batch(Config(max_batch_images=5), _args(items))
