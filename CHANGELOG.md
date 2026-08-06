# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与语义化版本。

## [0.1.1] - 2026-08-06

### Fixed
- 修复 MCP 配置/模板命令入口 `vision-mcp` → `shadow-vision`，此前 `uv run vision-mcp` 会 `Failed to spawn` 导致 MCP 无法启动。

### Changed
- 默认视觉模型 `qwen3-vl:2b` → `qwen3-vl:2b-instruct`（非思考版，延迟与 token 大幅下降）。

### Added
- `VISION_OLLAMA_NO_THINK`：Ollama 后端在 prompt 末尾追加 `/no_think`（默认开启，对支持该指令的 Qwen3 模型生效）。
- README 与配置模板新增智谱 `glm-4v-flash` 等国内 OpenAI 兼容平台接入示例。

## [0.1.0] - 2026-08-05

### Added
- 初始版本：`vision_ocr` / `vision_inspect`，四后端（Ollama / OpenAI-compatible / Anthropic / Gemini）
- 图片自动压缩 + 多裁剪（R1）
- 用户标注感知 `vision_annotate`（R3）
- 布局分析 `vision_layout` 与截图复刻 `vision_reconstruct`（R2 v1 开环）
- 内置重试与超时细分（R4）
- 任务引导路由 `task`（M2）
- 远程 URL 图片输入 + SSRF 防护 `image_url`（F1）
- 多图批量理解 `vision_compare`（F3）
- R2 v2 截图复刻闭环渲染（Playwright，可选 `[render]` extras）
- npm/PyPI 一键分发（`uvx shadow-vision` / `npx shadow-vision`）
