# Shadow Vision Release Notes

[English](./RELEASE_NOTES.md) | **简体中文**

本文档汇总 Shadow Vision（影瞳 · 开源 MCP 视觉服务）历史版本发布说明。

---

## v0.1.1 - 2026-08-07

> **类型**: 启动入口修复与模型响应性能优化

### 核心变更
- **修复 MCP 进程启动命令**：修正模板配置中的入口命令 `vision-mcp` → `shadow-vision`，解决 `Failed to spawn` 崩溃。
- **默认视觉模型升级**：默认模型调整为 `qwen3-vl:2b-instruct`（非思考版），大幅缩短首次响应时间并降低 token 消耗。
- **新增 `VISION_OLLAMA_NO_THINK` 配置**：支持自动禁用 Qwen3 系列非必要的长思考过程，兼顾效率与识别精度。
- **国内平台接入模板**：新增智谱 `glm-4v-flash` 等国内高性价比视觉 API 快速接入配置。
- **品牌视觉对齐**：新增 07e 双瞳矢量 LOGO 与赛博视觉横幅。

---

## v0.1.0 - 2026-08-05

> **类型**: 初始开源版本发布

### 核心变更
- **四大模型后端聚合**：全面原生兼容 Ollama（本地纯私有）、OpenAI-compatible（智谱/通义/DeepSeek/Kimi 等）、Anthropic 与 Google Gemini。
- **全栈视觉 Tool 矩阵**：
  - `vision_ocr`：高精度截图标注与文字提取；
  - `vision_inspect`：界面结构与视觉元素排查；
  - `vision_annotate`：用户画笔标注与红框焦点识别；
  - `vision_layout` & `vision_reconstruct`：布局分析与代码还原。
- **极简分发**：支持 `uvx shadow-vision` 零依赖开箱即用。
