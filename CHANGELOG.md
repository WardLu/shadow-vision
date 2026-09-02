# Changelog

**English** | [简体中文](./CHANGELOG.zh-CN.md)

This project adheres to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and Semantic Versioning.

## [0.1.1] - 2026-08-07

### Fixed
- Fixed MCP configuration and template command entry point from `vision-mcp` to `shadow-vision`; previously `uv run vision-mcp` failed with `Failed to spawn`, preventing MCP startup.

### Changed
- Changed default vision model from `qwen3-vl:2b` to `qwen3-vl:2b-instruct` (non-thinking version, significantly reducing latency and token usage).

### Added
- `VISION_OLLAMA_NO_THINK`: Ollama backend appends `/no_think` to prompt endings (enabled by default, applies to Qwen3 models supporting this instruction).
- Added integration examples for Chinese OpenAI-compatible platforms such as Zhipu `glm-4v-flash` in README and configuration templates.
- Brand visuals: Added product logo (07e double-eye vertical slim edition, following shadow-nexus design language) + redesigned cyberpunk Hero banner + horizontal wordmark.

## [0.1.0] - 2026-08-05

### Added
- Initial release: `vision_ocr` / `vision_inspect` across four backends (Ollama / OpenAI-compatible / Anthropic / Gemini).
- Automatic image compression + multi-crop tiling (R1).
- User annotation awareness with `vision_annotate` (R3).
- Layout analysis with `vision_layout` and screenshot reconstruction with `vision_reconstruct` (R2 v1 open-loop).
- Built-in retries and fine-grained timeout breakdowns (R4).
- Task-guided routing with `task` parameter (M2).
- Remote URL image input with SSRF protection via `image_url` (F1).
- Multi-image batch comparison with `vision_compare` (F3).
- R2 v2 closed-loop screenshot reconstruction rendering (Playwright, optional `[render]` extra).
- One-click npm/PyPI distribution (`uvx shadow-vision` / `npx shadow-vision`).
