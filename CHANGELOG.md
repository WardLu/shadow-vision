# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与语义化版本。

## [0.1.0] - 2026-08-05

### Added
- 图片自动压缩 + 多裁剪（R1）
- 用户标注感知 `vision_annotate`（R3）
- 布局分析 `vision_layout` 与截图复刻 `vision_reconstruct`（R2 v1 开环）
- 内置重试与超时细分（R4）
- 任务引导路由 `task`（M2）
- 远程 URL 图片输入 + SSRF 防护 `image_url`（F1）
- 多图批量理解 `vision_compare`（F3）
- R2 v2 截图复刻闭环渲染（Playwright，可选 `[render]` extras）
- npm/PyPI 一键分发（`uvx shadow-vision` / `npx shadow-vision`）

## [0.1.0] - 2026-08-05

### Added
- 初始版本：`vision_ocr` / `vision_inspect`，四后端（Ollama / OpenAI-compatible / Anthropic / Gemini）。
