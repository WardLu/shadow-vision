# Shadow Vision Release Notes

**English** | [简体中文](./RELEASE_NOTES.zh-CN.md)

This document summarizes the release notes for Shadow Vision (open-source MCP vision service).

---

## v0.1.1 - 2026-08-07

> **Type**: Startup entry fix and model response performance optimization

### Key Changes
- **Fixed MCP startup command**: Corrected entry command in configuration templates from `vision-mcp` to `shadow-vision`, resolving `Failed to spawn` crashes.
- **Upgraded default vision model**: Changed default model to `qwen3-vl:2b-instruct` (non-thinking version), significantly reducing initial response latency and token usage.
- **Added `VISION_OLLAMA_NO_THINK` option**: Added support for automatically disabling unnecessary extended thinking processes on Qwen3 models, balancing speed and accuracy.
- **Templates for Chinese API providers**: Added fast-start configuration templates for cost-effective domestic vision APIs including Zhipu `glm-4v-flash`.
- **Brand visual alignment**: Added 07e double-eye vector logo and cyberpunk visual banner.

---

## v0.1.0 - 2026-08-05

> **Type**: Initial open-source release

### Key Changes
- **Four aggregated model backends**: Comprehensive native compatibility with Ollama (local private), OpenAI-compatible (Zhipu / Tongyi / DeepSeek / Kimi, etc.), Anthropic, and Google Gemini.
- **Full-stack vision tool matrix**:
  - `vision_ocr`: High-precision screenshot annotation and text extraction;
  - `vision_inspect`: UI structure and visual bug inspection;
  - `vision_annotate`: User annotation and focus box recognition;
  - `vision_layout` & `vision_reconstruct`: Layout analysis and code reconstruction.
- **Minimalist distribution**: Zero-dependency out-of-the-box usage via `uvx shadow-vision`.
