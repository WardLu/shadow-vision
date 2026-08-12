"""Validate version, tag and changelog metadata before publishing."""

from __future__ import annotations

import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _section(version: str, changelog: str) -> str | None:
    heading = re.compile(rf"^##\s+\[?{re.escape(version)}\]?[^\n]*$", re.MULTILINE)
    match = heading.search(changelog)
    if not match:
        return None
    rest = changelog[match.end() :]
    next_heading = re.search(r"^##\s+", rest, re.MULTILINE)
    end = match.end() + (next_heading.start() if next_heading else len(rest))
    return changelog[match.start() : end].strip()


def _version_from_init(path: Path) -> str:
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', path.read_text(), re.MULTILINE)
    if not match:
        raise ValueError(f"{path} 缺少 __version__")
    return match.group(1)


def validate_release_metadata(root: Path = ROOT, release_tag: str = "") -> dict[str, str]:
    python_version = _version_from_init(root / "vision_mcp" / "__init__.py")
    npm_text = (root / "npm" / "shadow-vision" / "package.json").read_text()
    npm_version = re.search(r'"version"\s*:\s*"([^"]+)"', npm_text)
    if not npm_version:
        raise ValueError("npm/shadow-vision/package.json 缺少 version")
    if npm_version.group(1) != python_version:
        raise ValueError("Python 包与 npm 包版本号不一致")

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", python_version):
        raise ValueError("版本号不是有效的语义化版本")
    expected_tag = f"v{python_version}"
    if release_tag and release_tag != expected_tag:
        raise ValueError(f"Release Tag {release_tag} 必须匹配 {expected_tag}")

    section = _section(python_version, (root / "CHANGELOG.md").read_text())
    if not section:
        raise ValueError(f"CHANGELOG.md 缺少版本 {python_version} 的发布说明")
    body = re.sub(r"^##[^\n]+\n?", "", section).strip()
    if not body:
        raise ValueError("发布说明为空")
    if re.fullmatch(r"Released on \d{4}-\d{2}-\d{2}", body, re.IGNORECASE):
        raise ValueError("发布说明不能使用日期占位文案")
    if len(body) < 40:
        raise ValueError("发布说明过短")
    return {"version": python_version, "tag": expected_tag, "notes": section}


if __name__ == "__main__":
    metadata = validate_release_metadata(release_tag=os.environ.get("RELEASE_TAG", ""))
    print(f"Release metadata validated for {metadata['tag']}")
