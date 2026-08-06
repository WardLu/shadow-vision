<p align="center">
  <img src="./assets/readme/hero.svg" width="100%"
       alt="影瞳 Shadow Vision — 开源 MCP 视觉服务，让纯文本 LLM 通过 vision_ocr / vision_inspect / vision_annotate / vision_layout / vision_reconstruct / vision_compare 获得 OCR、图像理解、标注解析、布局分析、截图复刻与多图对比能力">
</p>

# 影瞳 · Shadow Vision

给纯文本 LLM 添加一双眼睛。影瞳是一个开源 MCP 视觉服务，让 AI Agent 通过六个视觉工具**看见、理解并分析真实世界的信息**，无需切换宿主文本模型。

当前版本 **v0.2.0**，支持完全本地运行（Ollama）或接入任意云端视觉后端。

## 为什么不同

- **MCP 原生** — 适配 Codex、Claude Desktop、Cursor 及其他 MCP 客户端，即插即用
- **可插拔后端** — Ollama、OpenAI-compatible、Anthropic、Gemini 四大类，一套接口任意切换
- **本地优先** — 使用 Ollama 时，图片与推理全部留在本机，隐私数据不离开你的设备
- **输入多样** — 支持本地文件路径、base64 图片数据或远程 HTTP(S) URL，自带 SSRF 防护

## 快速开始（30 秒）

不需要 clone 仓库，一行命令即可启动：

```bash
uvx shadow-vision          # Python / uv 用户（推荐）
# 或
npx shadow-vision          # Node 用户（本机需已装 uv）
```

注册为 Codex 的 MCP 服务：

```bash
codex mcp add vision -- uv run shadow-vision
```

其他 MCP 客户端可直接使用以下配置：

```toml
[mcp_servers.vision]
command = "uvx"
args = ["shadow-vision"]
env = { VISION_BACKEND = "ollama", VISION_MODEL = "qwen3-vl:2b-instruct" }
```

重启客户端后，直接让模型「看一下这张图片」即可。

首次使用 Ollama 后端时，先确认本机已安装 [Ollama](https://ollama.com/download) 并拉取默认视觉模型：

```bash
ollama serve
ollama pull qwen3-vl:2b-instruct
```

> `npx shadow-vision` 是一个薄壳，内部调用 `uvx shadow-vision`，需要本机已安装 [uv](https://docs.astral.sh/uv/)。两种入口行为一致。

## 工作原理

<p align="center">
  <img src="./assets/readme/workflow.svg" width="100%"
       alt="纯文本 LLM 通过 MCP 调用六大视觉工具，路由到 Ollama、OpenAI-compatible、Anthropic 或 Gemini 视觉后端">
</p>

文本模型通过 MCP 调用影瞳的视觉工具，影瞳把图片和提示词转发到配置的视觉后端，再把文字结果返回给模型。你始终使用同一个宿主文本模型，视觉能力作为插件按需接入。

## 六大视觉工具

<p align="center">
  <img src="./assets/readme/tools.svg" width="100%"
       alt="六大视觉工具：vision_ocr 提取文字、vision_inspect 描述与问答、vision_annotate 理解标注、vision_layout 分析布局、vision_reconstruct 截图复刻、vision_compare 多图对比">
</p>

### `vision_ocr`

从截图、票据、文档或表格中提取文字：

```python
vision_ocr(image_path="/tmp/receipt.png")
```

### `vision_inspect`

描述图片，或回答关于图片的问题：

```python
vision_inspect(image_path="/tmp/design.png", question="List any UI bugs you see.")
```

`vision_ocr` / `vision_inspect` 还支持 `task` 参数（`vision_ocr`: `general`/`error`/`table`；`vision_inspect`: `general`/`ui_structure`/`ui_bug`/`chart`）。

### `vision_annotate`

识别圈选、箭头、下划线、荧光、涂改、手写文字等标注，输出 `annotation → target` 关系、类型、位置与置信度的结构化 JSON：

```python
vision_annotate(image_path="/tmp/marked.png", focus="按圈选顺序说明改动点")
```

### `vision_layout`

分析图片/界面布局结构，输出画布、容器、元素 `bbox`、文字样式及元素关系的结构化 JSON：

```python
vision_layout(image_path="/tmp/ui.png")
```

### `vision_reconstruct`

把截图复刻为代码（`html` / `react` / `svg`），生成代码并附模型自检；可选传入 `vision_layout` 的 JSON 作为布局参考：

```python
vision_reconstruct(image_path="/tmp/ui.png", target_format="html", reference_layout="<layout json>")
```

### `vision_compare`

一次调用分析多张关联图片（`diff` / `compare` / `sequence`），每张图支持 `label` 便于引用：

```python
vision_compare(images=[{"image_path": "/tmp/a.png", "label": "改前"}, {"image_path": "/tmp/b.png", "label": "改后"}], task="diff")
```

所有图片工具都支持 `image_path` / `image_base64` / `image_url` 三选一输入，优先级：`image_base64` > `image_path` > `image_url`。

## 切换模型与后端

`VISION_BACKEND` 决定调用方式，`VISION_MODEL` 决定具体视觉模型。修改 MCP 配置中的环境变量后，重启客户端即可。

切换到本地 Ollama：

```toml
env = { VISION_BACKEND = "ollama", VISION_MODEL = "你已下载的视觉模型", OLLAMA_URL = "http://127.0.0.1:11434/api/chat" }
```

切换到 OpenAI-compatible 服务：

```toml
env = { VISION_BACKEND = "openai_compatible", VISION_MODEL = "服务端提供的视觉模型名", OPENAI_API_BASE = "https://api.example.com/v1", OPENAI_API_KEY = "sk-...", OPENAI_MAX_TOKENS = "1024", OPENAI_MAX_TOKENS_FIELD = "max_tokens" }
```

`OPENAI_*` 也适用于 LM Studio、vLLM 等提供 `/v1/chat/completions` 的服务。国内平台示例（智谱 GLM-4V-Flash）：

```toml
env = { VISION_BACKEND = "openai_compatible", VISION_MODEL = "glm-4v-flash", OPENAI_API_BASE = "https://open.bigmodel.cn/api/paas/v4", OPENAI_API_KEY = "你的智谱key" }
```

其他 OpenAI 兼容的国内平台只需改 `OPENAI_API_BASE` 与 `VISION_MODEL`：硅基流动 `https://api.siliconflow.cn/v1`、阿里百炼 `https://dashscope.aliyuncs.com/compatible-mode/v1`、阶跃星辰 `https://api.stepfun.com/v1`、腾讯混元 `https://api.hunyuan.cloud.tencent.com/v1`、Moonshot `https://api.moonshot.cn/v1` 等。

Anthropic / Gemini：

```bash
VISION_BACKEND=anthropic ANTHROPIC_API_KEY=sk-ant-... VISION_MODEL=your-claude-vision-model uv run shadow-vision
VISION_BACKEND=gemini GEMINI_API_KEY=AIza... VISION_MODEL=your-gemini-vision-model uv run shadow-vision
```

> **隐私提示**：API 后端（含国内平台）会把图片内容以 base64 发送到对应厂商服务器。机密/敏感图片建议改用本地 `ollama` 后端，避免数据外发。

<details>
<summary><b>完整环境变量参考</b></summary>

**通用变量**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VISION_BACKEND` | `ollama` | `ollama` / `openai_compatible` / `anthropic` / `gemini` |
| `VISION_MODEL` | `qwen3-vl:2b-instruct` | 视觉模型名称 |
| `VISION_TIMEOUT` | `180` | 读取超时（秒），`VISION_READ_TIMEOUT` 的兼容别名 |
| `VISION_CONNECT_TIMEOUT` | `10` | 连接超时（秒） |
| `VISION_READ_TIMEOUT` | `180` | 读取超时（秒） |
| `VISION_MAX_RETRIES` | `2` | 瞬时失败/5xx 的重试次数（总请求 = 1 + 此值） |
| `VISION_RETRY_BASE_DELAY` | `1.0` | 指数退避基础秒数 |

**图片与安全**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VISION_AUTO_COMPRESS` | `true` | 是否自动压缩大图 |
| `VISION_MAX_LONG_EDGE` | `1800` | 压缩阈值：长边像素 |
| `VISION_MAX_PIXELS` | `3500000` | 压缩阈值：总像素 |
| `VISION_COMPRESS_QUALITY` | `85` | JPEG 重编码质量 |
| `VISION_AUTO_TILE` | `true` | 是否对超长图自动切块 |
| `VISION_TILE_LONG_EDGE` | `3600` | 切块阈值：长边像素 |
| `VISION_TILE_OVERLAP` | `100` | 切块重叠像素 |
| `VISION_MAX_TILES` | `8` | 单图切块数上限 |
| `VISION_TASK_ROUTING` | `true` | 是否启用 `vision_inspect` 启发式任务路由 |
| `VISION_ALLOW_REMOTE_URL` | `true` | 是否启用远程 URL 图片输入 |
| `VISION_MAX_REMOTE_SIZE` | `20971520` | 远程图片最大字节数（20MB） |
| `VISION_FETCH_TIMEOUT` | `30` | 远程获取超时（秒） |
| `VISION_SSRF_ALLOW_PRIVATE` | `false` | 是否允许私网/内网地址（强烈不建议开启） |
| `VISION_MAX_BATCH_IMAGES` | `5` | `vision_compare` 单次最多图片数 |

**Ollama**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434/api/chat` | Ollama 对话端点 |

使用前执行 `ollama pull <视觉模型名>` 下载模型。

**OpenAI-compatible**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENAI_API_BASE` | `http://127.0.0.1:11434/v1` | 兼容服务基础地址 |
| `OPENAI_API_KEY` | 空 | 本地服务通常可留空 |
| `OPENAI_MAX_TOKENS` | 未设置 | 可选输出 token 上限；未设置时不发送 token 限制字段 |
| `OPENAI_MAX_TOKENS_FIELD` | `max_tokens` | 可选：`max_tokens` 或 `max_completion_tokens` |

不同服务支持的 token 字段不完全一致：支持旧字段就使用 `max_tokens`，只支持新版字段就改成 `max_completion_tokens`，两个字段都不接受时不要设置 `OPENAI_MAX_TOKENS`。旧变量名 `VISION_API_BASE`、`VISION_API_KEY`、`VISION_MAX_TOKENS` 和 `VISION_MAX_TOKENS_FIELD` 仍兼容。

**Anthropic / Gemini**

Anthropic 还支持 `ANTHROPIC_BASE_URL`、`ANTHROPIC_VERSION` 和 `ANTHROPIC_MAX_TOKENS`；Gemini 还支持 `GEMINI_BASE_URL` 和 `GEMINI_MAX_TOKENS`。

</details>

## 本地模型选择与测评

Ollama 模型页可以查看模型包大小、上下文窗口和图像能力，但模型包大小不是最低内存要求。建议从 `qwen3-vl:2b-instruct` 开始（非思考版，延迟低）；如果 OCR 或复杂图表理解不足，再比较 `qwen3-vl:4b`、`qwen3-vl:8b` 或文档 OCR 取向的 `minicpm-v4.5:q4_0`。

准备 3–5 张真实图片，覆盖 OCR、截图、图表和困难样本，并用相同提示词比较模型：

```bash
MODEL=qwen3-vl:2b-instruct
IMAGE=/absolute/path/to/test.png

time ollama run "$MODEL" "$IMAGE" "请准确抄录图片中的全部文字，只输出文字。"
time ollama run "$MODEL" "$IMAGE" "请描述图片内容，并列出你不确定的地方。"
```

记录 OCR 错误数量、关键对象和关系是否正确、幻觉、完整响应延迟，以及 `ollama ps` 中的 processor 状态。先直接测试 Ollama，再通过 `vision_ocr` / `vision_inspect` 测试 MCP 链路，可以区分模型问题和 MCP 配置问题。

推荐资料：

- [Ollama Vision 文档](https://docs.ollama.com/capabilities/vision)
- [Ollama Qwen3-VL 模型页](https://ollama.com/library/qwen3-vl)
- [Qwen3-VL 官方仓库](https://github.com/QwenLM/Qwen3-VL)
- [MiniCPM-V 4.5 官方评测](https://github.com/OpenBMB/MiniCPM-V/blob/main/docs/minicpm_v4dot5_en.md)
- [Ollama Context Length 文档](https://docs.ollama.com/context-length)
- [Ollama Modelfile 参数文档](https://docs.ollama.com/modelfile)

## 支持的 Agent

所有 Agent 都启动同一命令：`uv run shadow-vision`。

| Agent | 配置文件 |
|---|---|
| Codex | `~/.codex/config.toml` |
| Claude Code | `.mcp.json` |
| Cursor | `.cursor/mcp.json` |
| VS Code Copilot | `.vscode/mcp.json` |
| Windsurf | `.windsurf/mcp_config.json` |
| Claude Desktop | `claude_desktop_config.json` |
| OpenCode | `opencode.json` |

## 开发

```bash
uv sync
uv run python -c "import vision_mcp.server; print('ok')"
uv run pytest
```

## 联系我

如果你对 B 端产品、AI 产品开发、供应链数字化或 Shadow 系列产品感兴趣，可以联系我：

- **X（Twitter）**：[@Gollumgulu](https://x.com/Gollumgulu)
- **微信公众号**：Ward 的 AI 产品实战

<p align="center">
  <img src="./assets/readme/wechat-qr.png" width="158" alt="Ward 的 AI 产品实战微信公众号二维码">
</p>

- **小红书 / 微博 / 抖音**：全网同名「Ward 的 AI 产品实战」—— [小红书](https://xhslink.cn/m/4W1NWyRrxv5) · [微博](https://weibo.com/u/8344390431) · [抖音](https://v.douyin.com/1y06PMohfoE/)
- **产品主页**：[Shadow Nexus](https://www.shadow.wang/)
- **Email**：[wardlu@126.com](mailto:wardlu@126.com)

> 可接 1v1 咨询和项目陪跑：产品诊断 · AI 实施 · 工作流 / Skill · 系统定制

## License

MIT
