# 影瞳 Shadow Vision · Roadmap 批量需求设计文档

> 起草日期：2026-08-05
> 分支：`feature/roadmap-batch`
> 覆盖范围：ROADMAP.md 中「近期高价值 4 项」+「中期任务引导路由」+「远期远程 URL/SSRF 与多图批量」
> 状态：设计中，待评审后进入实现

## 1. 背景与目标

ROADMAP.md 基于对竞品 luma-mcp 的对比分析，列出若干工程短板。本次集中交付其中 7 项，目标是把影瞳的工程成熟度补齐到与 luma 同档，同时保持「本地优先、轻量单目录、依赖极少」的差异化护城河。

本批次覆盖：

| 编号 | 需求 | ROADMAP 分档 | 优先级 |
|---|---|---|---|
| R1 | 图片自动压缩 + 多裁剪 | 近期高价值 | P0 |
| R2 | 视觉布局分析 + 截图复刻闭环 | 近期高价值 | P0 |
| R3 | 用户标注感知 | 近期高价值 | P0 |
| R4 | 内置重试与超时细分 | 近期高价值 | P0 |
| M2 | 任务引导路由（task 提示词） | 中期 | P1 |
| F1 | 远程 URL 图片输入 + SSRF 防护 | 远期 | P1 |
| F3 | 多图片 / 批量图片理解 | 远期 | P1 |

不在本批次：M1（HTTP/局域网共享模式）、F2（npm/PyPI 分发）。原因见 §10。

## 2. 现状与约束

### 2.1 现有架构

```
vision_mcp/
├── server.py     # MCP 工具定义与分发：vision_ocr / vision_inspect
├── backends.py   # VisionBackend 抽象 + Ollama/OpenAI/Anthropic/Gemini 四实现 + _read_image
├── config.py     # 环境变量驱动的 frozen dataclass 配置
└── __init__.py
```

- 工具层 `server.py` 只做分发，视觉逻辑全在 `backends.py`。
- `backend.analyze(prompt, image_data: str, mime: str, model: str) -> str`：单图、base64 字符串、同步 httpx。
- `_read_image(path, base64, mime) -> (base64_str, mime)`：只支持本地路径与 base64。
- 依赖仅 `mcp` + `httpx[socks]`，无图像处理库。
- 测试仅 `test_openai_compatible.py`，覆盖配置与 payload。

### 2.2 约束

- **向后兼容**：现有 `VISION_*` / `OPENAI_*` 环境变量与工具入参必须继续工作；新能力全部有默认值，零配置可用。
- **轻量依赖**：新增依赖需谨慎。图像处理无法用纯标准库实现，唯一现实选择是 Pillow（见 §5.1）。
- **单进程同步**：当前 backend 同步阻塞（`httpx.post`）。本批次不改为 async，避免触碰 MCP 事件循环；重试与多图在同步层完成。
- **安全关键路径**：F1 的 SSRF 防护必须有测试覆盖，不能仅靠代码审查。

## 3. 总体架构

### 3.1 模块演进

```
vision_mcp/
├── server.py          # 扩展：新增工具 + image_url/image_url 多图入口 + task 路由
├── backends.py        # 重构：analyze 改多图签名 + 基类 _post 统一重试 + 各 backend 多图 payload
├── config.py          # 扩展：重试/超时/压缩/裁剪/SSRF/批量 配置项
├── imageproc.py       # 新增：压缩 + 多裁剪（Pillow）
├── prompts.py         # 新增：任务提示词库 + 启发式路由
├── fetch.py           # 新增：远程 URL 获取 + SSRF 校验
└── __init__.py
tests/
├── test_openai_compatible.py   # 现有，随签名变更更新
├── test_imageproc.py           # 新增
├── test_prompts.py             # 新增
├── test_fetch_ssrf.py          # 新增（安全关键）
├── test_retry.py               # 新增
└── test_backends_multi.py      # 新增
```

### 3.2 核心数据流（统一后）

```
MCP 工具调用
  │  (image_path | image_base64 | image_url)[]  +  task / question
  ▼
server._call_tool
  │  1. _load_images → list[(bytes, mime, meta)]  # 本地/base64/远程 三入口归一
  │  2. imageproc.tile_if_needed                # R1 先切块（基于原始布局；仅单图走，F3 多图不走）
  │  3. imageproc.compress_if_needed            # R1 后压缩（对每块独立压缩）
  │  4. prompts.route(task, question) → prompt  # M2 路由 + 切块提示注入
  │  5. backend.analyze(prompt, images, model)  # 多图 + 重试(R4)
  ▼
CallToolResult
```

关键变更：**内部图片表示统一为 `list[tuple[bytes, mime]]`**，base64 编码下沉到各 backend（因为 Anthropic 用裸 base64、OpenAI 用 data URL、Ollama 用裸 base64、Gemini 用 base64 字段，编码位置不同）。

### 3.3 后端接口签名变更

```python
# 旧
def analyze(self, prompt: str, image_data: str, mime: str, model: str) -> str

# 新
def analyze(self, prompt: str, images: list[tuple[bytes, str]], model: str) -> str
```

破坏性变更，但属内部接口。`server.py` 是唯一调用方，测试同步更新。单图场景传 `[(bytes, mime)]`。

**`_load_images` 归属**：保留在 `backends.py`（紧邻现有 `_read_image`），由 `server.py` 调用。依赖方向单向：`server -> backends -> {imageproc, fetch}`，避免 server↔backends 循环依赖。`_load_images` 返回 `list[tuple[bytes, mime]]`，内部按 `image_base64 > image_path > image_url` 优先级归一；远程 URL 经 `fetch.fetch_image_from_url` 获取。

## 4. 详细设计

### 4.1 R4 — 内置重试与超时细分（基础设施，最先实现）

**目标**：网络/模型瞬时失败自动重试；超时细分为连接超时与读取超时。

**重试策略**：
- 默认重试 2 次（总 3 次请求），对齐 luma。
- **可重试**：`httpx.TransportError`、`httpx.TimeoutException`、HTTP 5xx。
- **不重试**：HTTP 4xx（含 413 图片过大、401 鉴权失败、400 参数错误）、`ValueError`、JSON 解析错误。重试这些只会浪费配额。
- 指数退避 + 抖动：`delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)`，默认 `base_delay=1.0s`。

**超时细分**：
- `VISION_CONNECT_TIMEOUT`（默认 10s）：建立连接。
- `VISION_READ_TIMEOUT`（默认 180s，= 现有 `VISION_TIMEOUT`）：等待模型推理完成。
- `VISION_TIMEOUT` 保留，作为 `VISION_READ_TIMEOUT` 的向后兼容别名。
- 用 `httpx.Timeout(connect=..., read=..., write=10, pool=10)`。

**实现位置**：`VisionBackend` 基类新增 `_post(url, *, headers, json) -> httpx.Response`，封装重试 + 超时。各 backend 的 `analyze` 调用 `self._post(...)`。`Config` 持有 `httpx.Timeout` 实例，复用。

**配置项**：
| 变量 | 默认 | 说明 |
|---|---|---|
| `VISION_MAX_RETRIES` | `2` | 失败后的重试次数（总请求 = 1 + 此值） |
| `VISION_RETRY_BASE_DELAY` | `1.0` | 指数退避基础秒数 |
| `VISION_CONNECT_TIMEOUT` | `10` | 连接超时秒数 |
| `VISION_READ_TIMEOUT` | `180` | 读取超时秒数（等同旧 `VISION_TIMEOUT`） |

### 4.2 R1 — 图片自动压缩 + 多裁剪

**目标**：大图（长边 ≥1800px 或 ≥350 万像素）自动压缩；超长图进一步拆分为有序图块再送模型。

**新增模块 `imageproc.py`**：

```python
def compress_if_needed(
    data: bytes, mime: str, *,
    max_long_edge: int = 1800,
    max_pixels: int = 3_500_000,
    quality: int = 85,
) -> tuple[bytes, str]:
    """超过阈值则等比缩放并重编码为 JPEG；否则原样返回。"""

def tile_if_needed(
    data: bytes, mime: str, *,
    tile_long_edge: int = 3600,
    overlap: int = 100,
) -> list[tuple[bytes, str, dict]]:
    """长边超过 tile_long_edge 则切分为带重叠的有序图块。
    返回 [(tile_bytes, mime, {index, total, x, y, w, h})]。
    未超阈值时返回 [(data, mime, {index:0, total:1, ...})]。"""
```

**切分策略**：
- 超长截图（高 ≫ 宽）：垂直切分；超宽图：水平切分；两者都大：网格切分。
- 重叠区 `overlap`（默认 100px）避免文字/元素被切断。
- 每块标注 `index/total`，由 prompt 引导模型按序输出。

**压缩与切分的关系（实现顺序：先切后压）**：`_load_images` 先按**原始布局**判断是否切块（`tile_long_edge`），需切则先切出带重叠的有序块，再对**每块**独立压缩（`max_long_edge`）。原因：若先压缩到 `max_long_edge`(1800) 长边恒 ≤1800 < `tile_long_edge`(3600)，切块将永不触发；先切后压既保证超长截图能正确切块，切块又基于原始布局更保真。两道阈值独立，避免普通图被误切。

**多图 backend 支持**：R1 的多块输出依赖 §3.3 的多图接口。切分后 `images = [(t[0], t[1]) for t in tiles]`，prompt 注入"这是大图切分的第 i/n 块，按序输出，重叠区可能重复，仅保留一份"。

**块数上限与多图上限的关系**：多裁剪是对**单张图**的拆分，与 F3 的多张图批量是不同维度。切块结果**直接进入 `backend.analyze`**，**不走** `vision_compare` 的 `VISION_MAX_BATCH_IMAGES` 上限。为防超长图切出过多块导致上下文爆炸，定义独立上限 `VISION_MAX_TILES`（默认 8）：切分时若估算块数超限，先等比缩放长边直到块数 ≤ 上限（牺牲分辨率换可控块数），再切分。

**OCR 拼接**：不做过激的后处理去重（易误删），仅靠 prompt 引导 + 序号标注。inspect 场景让模型综合所有块描述。

**配置项**：
| 变量 | 默认 | 说明 |
|---|---|---|
| `VISION_AUTO_COMPRESS` | `true` | 是否启用自动压缩 |
| `VISION_MAX_LONG_EDGE` | `1800` | 压缩阈值：长边像素 |
| `VISION_MAX_PIXELS` | `3500000` | 压缩阈值：总像素 |
| `VISION_COMPRESS_QUALITY` | `85` | JPEG 重编码质量 |
| `VISION_AUTO_TILE` | `true` | 是否启用多裁剪 |
| `VISION_TILE_LONG_EDGE` | `3600` | 切分阈值：长边像素 |
| `VISION_TILE_OVERLAP` | `100` | 切分重叠像素 |
| `VISION_MAX_TILES` | `8` | 单图切块数上限，超限先缩放再切 |

### 4.3 M2 — 任务引导路由（task 提示词）

**目标**：为 `vision_ocr` / `vision_inspect` 增加任务专用提示词与启发式路由，提升保真度。

**新增模块 `prompts.py`**：

```python
@dataclass(frozen=True)
class TaskPrompt:
    name: str
    user_prefix: str          # 拼在用户问题前
    output_hint: str = ""     # 输出格式约束（如 JSON 结构提示）

# 内部 key 用 {tool}_{task} 组合；对外枚举值不带工具前缀（工具本身已区分上下文）。
TASKS: dict[str, TaskPrompt] = {
    "ocr_general":          TaskPrompt("ocr_general", OCR_PROMPT),
    "ocr_error":            TaskPrompt("ocr_error", "...报错截图专用..."),
    "ocr_table":            TaskPrompt("ocr_table", "...保留表格结构..."),
    "inspect_general":      TaskPrompt("inspect_general", ""),
    "inspect_ui_structure": TaskPrompt("inspect_ui_structure", "...组件树/布局..."),
    "inspect_ui_bug":       TaskPrompt("inspect_ui_bug", "...找视觉/布局问题..."),
    "inspect_chart":        TaskPrompt("inspect_chart", "...图表数据..."),
}

# 对外枚举（用户在工具入参里传的值）：
#   vision_ocr.task     ∈ {general, error, table}
#   vision_inspect.task ∈ {general, ui_structure, ui_bug, chart}

def route(tool: str, task: str | None, question: str) -> TaskPrompt:
    """显式 task 优先（拼内部 key `{tool}_{task}` 查 TASKS）；未指定时对 inspect
    做轻量文本启发式；ocr 默认通用。无效 task 报错。"""
```

**路由规则**：
1. 用户显式传 `task` → 拼内部 key `{tool}_{task}`（如 inspect 工具传 `ui_bug` -> `inspect_ui_bug`）查 `TASKS`，未命中报错。
2. 未传 `task`：
   - `vision_ocr` → `ocr_general`（不做启发式，避免误判降低准确率）。
   - `vision_inspect` → 文本启发式：`question` 含 bug/错误/error → `inspect_ui_bug`；含 布局/结构/layout/组件 → `inspect_ui_structure`；含 图表/chart/趋势 → `inspect_chart`；否则 `inspect_general`。
3. 启发式可用 `VISION_TASK_ROUTING=false` 关闭，退化为全通用。

**设计取舍**：启发式只对 inspect 生效且只看关键词，不做图像特征判断（图像特征判断本身需要一次模型调用，得不偿失）。v1 保持克制，避免过度路由。

**与 server 集成**：两个工具的 `inputSchema` 新增可选 `task` 字段（枚举）。`_call_tool` 调用 `prompts.route(...)` 拿到 `TaskPrompt`，拼装最终 prompt = `task_prompt.user_prefix + question + output_hint`。

**配置项**：`VISION_TASK_ROUTING`（默认 `true`）。

### 4.4 R3 — 用户标注感知

**目标**：识别圈选、箭头、下划线、荧光、涂改、手写文字等标注，输出 `annotation → target` 关系、类型、位置、置信度。

**新增工具 `vision_annotate`**（独立工具，MCP 语义清晰，优于塞进 inspect 的 task）：

```python
Tool(
    name="vision_annotate",
    inputSchema={
        "image_path": ...,
        "image_base64": ...,
        "mime_type": ...,
        "image_url": ...,            # F1 落地后
        "focus": {"type": "string", "description": "用户文字说明，辅助判断标注意图"},
        "model": {"type": "string", "description": "Vision model name", "default": config.model},
    },
)
```

**输出结构化 JSON**（prompt 约束模型输出）：
```json
{
  "annotations": [
    {
      "type": "circle | arrow | underline | highlight | scribble | handwritten_text",
      "bbox": [x, y, w, h],
      "confidence": 0.0,
      "target": {
        "description": "被标注目标描述",
        "bbox": [x, y, w, h],
        "text": "目标区域文字（如有）"
      },
      "handwritten_text": "手写文字内容（如有）"
    }
  ],
  "summary": "整体标注意图总结"
}
```

**实现**：本质是提示词工程（VLM 本身能理解标注）。`prompts.py` 增加 `annotate` 专用 prompt，要求严格 JSON 输出。复用 `backend.analyze` + R1 压缩流程。

**与 R1 的关系**：标注图通常不大，但手写文字识别对分辨率敏感。v1 统一用默认压缩阈值；后续可按 task 覆盖（标注任务放宽 `max_long_edge`），作为 v2 优化点。

### 4.5 R2 — 视觉布局分析 + 截图复刻闭环

本需求最复杂，分两部分，**v1/v2 分阶段交付**以防范围蔓延。

#### 4.5.1 `vision_layout`（布局分析，v1 完整实现）

**输入**：image（+ 可选 `task="layout"`）。
**输出**：结构化 JSON：
```json
{
  "canvas": {"width": 0, "height": 0, "background": "#ffffff"},
  "elements": [
    {
      "id": "el_1",
      "type": "container | text | image | button | icon | qr_code",
      "bbox": [x, y, w, h],
      "text": "文字元素内容",
      "styles": {"font_size": 14, "color": "#111", "font_weight": "normal", "align": "left"},
      "image_region": {"crop_index": 0, "description": "..."},
      "parent": "root",
      "children": ["el_2", "el_3"]
    }
  ],
  "relations": [{"from": "el_1", "to": "el_2", "type": "contains | adjacent | overlaps"}]
}
```

**实现**：提示词工程 + 严格 JSON 约束。若后端支持 `response_format=json`（OpenAI json_mode）则启用，不强制依赖。复用 R1 压缩到 `max_long_edge`（1800）长边；**layout 任务不做切块**（跨块布局合并在 v1 过于复杂），超长图若压缩后仍超 `tile_long_edge`，则进一步等比缩放到 `tile_long_edge` 以内强制单图输入（牺牲分辨率换整体布局完整性）。输入新增可选 `model`，与现有工具一致。

#### 4.5.2 `vision_reconstruct`（截图复刻，v1 开环 / v2 闭环）

**v1（开环）**：
- 输入：image + `target_format`（`html` / `react` / `svg`）+ 可选 `reference_layout`（来自 `vision_layout` 的 JSON）+ 可选 `model`。
- 输出：代码 + 模型自检（让模型对照原图检查代码与图的对应关系，输出差异说明）。
- 不引入浏览器依赖。
- **自检局限**：同模型对自身输出自检价值有限（自我确认偏差），v1 接受此局限，验收预期以「代码可渲染、主要结构对齐」为准，不要求自检能发现全部差异；真正的高保真校验留给 v2 闭环（用 `vision_inspect` 对比渲染图与原图）。

**v2（闭环，可选依赖）**：
- 流程：生成代码 → Playwright 渲染截图 → `vision_inspect` 对比原图与渲染图 → 差异 > 阈值则反馈迭代 → 最多 N 轮。
- Playwright 通过 `[render]` extras 引入（`pip install vision-mcp[render]`），运行时检测是否可用，不可用则降级为开环。
- `VISION_RECONSTRUCT_RENDER`（默认 `false`）控制是否尝试闭环。

**取舍说明**：闭环渲染依赖浏览器（Playwright ~150MB），与「轻量」定位冲突。v1 先交付开环（覆盖 80% 价值：代码生成 + 自检），闭环作为可选增强。设计文档明确标注，避免实现时范围蔓延。

### 4.6 F1 — 远程 URL 图片输入 + SSRF 防护

**目标**：支持 `image_url` 入参；拒绝内网/私网地址、禁用重定向。

**新增模块 `fetch.py`**：

```python
def is_safe_url(url: str, *, allow_private: bool = False) -> tuple[bool, str]:
    """校验 scheme（仅 http/https）+ 主机解析出的所有 IP 不在禁止段。"""

def fetch_image_from_url(url: str, config) -> tuple[bytes, str]:
    """获取远程图片，返回 (bytes, mime)。"""
```

**SSRF 防护清单**：
1. **Scheme 白名单**：仅 `http` / `https`。
2. **拒绝 userinfo**：URL 含 `user:pass@` 前缀直接拒绝（防 `http://user:pass@internal/` 形式混淆与凭据泄漏）。
3. **IP 禁止段**（默认拒绝，`allow_private=false` 时）：
   - IPv4 私网/保留：`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`、`127.0.0.0/8`、`169.254.0.0/16`（含云元数据 `169.254.169.254`）、`0.0.0.0/8`、`100.64.0.0/10`（CGNAT）。
   - IPv6：`::1`、`fc00::/7`、`fe80::/10`、`::ffff:0:0/96`（IPv4-mapped，需拆出 IPv4 再判）。
4. **禁用重定向**：`follow_redirects=False`，收到 3xx 直接拒绝（ROADMAP 明确要求）。
5. **DNS 解析校验**：`socket.getaddrinfo` 解析全部 IP，任一命中禁止段则拒绝。
6. **响应大小限制**：`VISION_MAX_REMOTE_SIZE`（默认 20MB），流式读取超限即中止。
7. **Content-Type 校验**：仅接受 `image/*`。
8. **独立超时**：`VISION_FETCH_TIMEOUT`（默认 30s）。

**DNS rebinding 残留风险**：`getaddrinfo` 校验与 `httpx` 实际连接之间理论存在 rebinding 窗口。完整防护需自定义 `httpx` transport 注入解析结果，实现成本高。本地 MCP 场景（用户本机运行、非公网服务）风险低，v1 做到「解析校验 + 禁用重定向 + 大小/类型限制」，文档与代码注释标注此残留风险，v2 可补 transport 级防护。

**与 server 集成**：`_read_image` 升级为 `_load_images`，支持 `image_path` / `image_base64` / `image_url`。优先级：`image_base64` > `image_path` > `image_url`。`image_url` 入参加到所有图片工具。

**配置项**：
| 变量 | 默认 | 说明 |
|---|---|---|
| `VISION_ALLOW_REMOTE_URL` | `true` | 是否启用远程 URL 输入 |
| `VISION_MAX_REMOTE_SIZE` | `20971520` | 远程图片最大字节数（20MB） |
| `VISION_FETCH_TIMEOUT` | `30` | 远程获取超时秒数 |
| `VISION_SSRF_ALLOW_PRIVATE` | `false` | 是否允许私网地址（强烈不建议开） |

### 4.7 F3 — 多图片 / 批量图片理解

**目标**：一次调用分析多张关联图片（diff、对比、序列）。

**新增工具 `vision_compare`**：
```python
Tool(
    name="vision_compare",
    inputSchema={
        "images": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "image_path": ...,
                    "image_base64": ...,
                    "image_url": ...,
                    "mime_type": ...,
                    "label": {"type": "string", "description": "图片标签，便于引用"}
                }
            },
            "maxItems": 5,
        },
        "task": {"type": "string", "enum": ["diff", "compare", "sequence"]},
        "question": ...,
        "model": {"type": "string", "description": "Vision model name", "default": config.model},
    },
)
```

**实现**：复用 §3.3 多图接口。各 backend 多图 payload：
- Ollama：`images: [b64_1, b64_2, ...]`（原生数组）。
- OpenAI：`content` 数组多个 `image_url`。
- Anthropic：`content` 数组多个 `image` block。
- Gemini：`input` 数组多个 `image`。

**限制**：`VISION_MAX_BATCH_IMAGES`（默认 5）防滥用与上下文溢出。每张图先走 R1 压缩，但不做多裁剪（多图 + 多裁剪组合会让上下文爆炸；多图场景要求单图在压缩阈值内）。

**配置项**：`VISION_MAX_BATCH_IMAGES`（默认 `5`）。

## 5. 依赖与配置变更

### 5.1 依赖

| 依赖 | 用途 | 引入方式 | 备注 |
|---|---|---|---|
| `Pillow>=10.0.0` | R1 压缩/裁剪 | `dependencies` | C 扩展但跨平台 wheel 成熟，uv 安装无碍 |
| `playwright` | R2 v2 闭环渲染 | `[render]` extras | 可选，默认不装 |

`pyproject.toml`：
```toml
dependencies = ["mcp>=1.0.0", "httpx[socks]>=0.27.0", "Pillow>=10.0.0"]
[project.optional-dependencies]
render = ["playwright>=1.40.0"]
```

### 5.2 配置项汇总（全部新增，均有默认值）

重试/超时（R4）、压缩/裁剪（R1）、任务路由（M2）、SSRF（F1）、批量（F3）—— 见各节表格。`Config` dataclass 扩展对应字段，全部 `field(default_factory=lambda: ...)` 读环境变量。

### 5.3 工具入参变更

所有图片工具新增可选字段：
- `image_url`（F1）
- `task`（M2，仅 ocr/inspect）

新增工具：`vision_annotate`（R3）、`vision_layout`（R2）、`vision_reconstruct`（R2）、`vision_compare`（F3）。

## 6. 测试策略

遵循 TDD 与奥姆剃刀：只测核心路径，不过度测边界。

| 测试文件 | 覆盖 | 关键用例 |
|---|---|---|
| `test_retry.py` | R4 | 5xx 重试、4xx 不重试、达到上限抛出、指数退避时序 |
| `test_imageproc.py` | R1 | 小图不压缩、大图压缩到阈值、超长图切分、重叠区正确、切分后块数 |
| `test_prompts.py` | M2 | 显式 task 命中、启发式关键词命中、未知 task 报错、路由关闭退化通用 |
| `test_fetch_ssrf.py` | F1 | 私网 IPv4/IPv6 拒绝、`169.254.169.254` 拒绝、3xx 重定向拒绝、非 image content-type 拒绝、超大小中止、正常公网通过 |
| `test_backends_multi.py` | F3/R1 | 四 backend 多图 payload 结构正确、单图向后兼容 |
| `test_openai_compatible.py` | 现有 | 随 `analyze` 签名变更更新 mock 调用 |

SSRF 测试用 mock socket 解析 + mock httpx，不发真实请求；公网通过用例可标记 `@pytest.mark.network` 默认跳过。

## 7. 实施计划与里程碑

按依赖关系排序，每步可独立验证、独立提交：

| 阶段 | 内容 | 依赖 | 验证 |
|---|---|---|---|
| P0 | R4 重试 + 超时细分 + backend `analyze` 多图签名重构 | 无 | `test_retry.py` + 现有测试绿 |
| P1 | R1 `imageproc.py` 压缩 + 多裁剪 + server 接入 | P0 | `test_imageproc.py` + 手动大图验证 |
| P2 | M2 `prompts.py` 任务路由 + ocr/inspect 接入 `task` | 无（可与 P1 并行） | `test_prompts.py` |
| P3 | R3 `vision_annotate` 工具 | P2 | 手动标注图验证 |
| P4 | R2 `vision_layout`（v1）+ `vision_reconstruct`（v1 开环） | P1, P2 | 手动截图验证 |
| P5 | F1 `fetch.py` + SSRF + `image_url` 入参 | 无（可与 P1 并行） | `test_fetch_ssrf.py` |
| P6 | F3 `vision_compare` 工具 | P0 | `test_backends_multi.py` + 手动多图 |
| P7 | 文档同步（README/ROADMAP/配置示例）+ R2 v2 闭环（可选） | 全部 | README 校验 |

P0 是后续多图需求的地基，必须先做。P1/P2/P5 可并行（不同文件），P3/P4/P6 串行收尾。

> **实施状态（2026-08-05 全部完成）**：P0–P7 均已实现，`uv run pytest` 全量 61 项通过。
> 实现偏差：R1 采用「先切后压」顺序（见 §3.2/§4.2 已同步）；R2 v1 开环交付，v2 闭环作为可选增强未实现（不阻塞）。
> 新增测试：`test_retry.py` / `test_imageproc.py` / `test_prompts.py` / `test_fetch_ssrf.py` / `test_backends_multi.py` / `test_backends_batch.py` / `test_server_tools.py`。

## 8. 风险与取舍

| 风险 | 取舍 | 缓解 |
|---|---|---|
| Pillow 引入 C 扩展 | 唯一现实选择，wheel 成熟 | uv 安装验证；保持仅此一个重依赖 |
| 多裁剪 OCR 拼接重复 | 不做激进后处理去重 | prompt 引导 + 序号标注，重叠区重复靠模型识别 |
| R2 闭环需浏览器 | v1 开环、v2 可选 extras | 避免强依赖 Playwright，保住轻量定位 |
| SSRF DNS rebinding | v1 不做 transport 级防护 | 本地场景风险低；代码注释 + 文档标注残留风险 |
| 启发式路由误判 | 仅 inspect 轻量关键词路由 | 可 `VISION_TASK_ROUTING=false` 关闭 |
| `analyze` 签名破坏性变更 | 内部接口，唯一调用方是 server | 测试同步更新；单图传 `[(bytes, mime)]` |

## 9. 验收标准

- [x] 所有现有测试 + 新增测试通过（`uv run pytest`）
- [x] 零配置（不设任何新环境变量）下，原有 `vision_ocr` / `vision_inspect` 行为不变
- [x] 4 个新工具可在 MCP 客户端被列出并调用
- [x] 大图（>1800px）自动压缩可观测（日志/返回）
- [x] 私网 URL 被拒绝、公网 URL 可用
- [x] README 配置表与工具说明同步更新
- [x] ROADMAP.md 对应项打勾

## 10. 不在本批次

| 需求 | 原因 |
|---|---|
| M1 HTTP/局域网共享模式 | 需引入鉴权、多客户端状态管理，与当前 stdio 单进程架构差异大，独立批次更合适 |
| F2 npm/PyPI 一键分发 | 需建发布流水线、`npx -y` 入口设计，属工程分发而非功能，单独推进 |
| R2 v2 闭环渲染 | 依赖 Playwright，作为 P7 可选增强，不阻塞本批次交付 |

## 11. 评审结论（2026-08-05）

> **状态：✅ 已复核通过（2026-08-05 二次评审）** — 8/8 修订点全部落实，可进入实现。
>
> 评审人：Codex（核对现有 `backends.py` / `server.py` / `config.py` / `pyproject.toml` / `tests` 后评审）。
> 结论：**三个关键取舍均可批准，设计文档整体可以进入实现**；P1/P2/P3 修订点已于 2026-08-05 全部并入正文（见 §3.2/3.3/4.2/4.3/4.4/4.5/4.6/4.7）。

### 11.1 关键取舍确认

| 取舍 | 结论 | 依据 |
|---|---|---|
| 新增 Pillow 依赖 | ✅ 同意 | 图像压缩/裁剪无法用纯标准库实现，Pillow wheel 成熟；`dependencies` 仍保持单一重依赖，符合轻量定位 |
| R2 截图复刻 v1 开环 | ✅ 同意 | Playwright（~150MB）与轻量定位冲突；v1 开环覆盖 80% 价值，闭环作 `[render]` extras 可选增强，运行时降级，范围控制合理 |
| `analyze` 签名破坏性变更 | ✅ 同意 | 已核实 `server.py` 是唯一调用方，属纯内部接口；单图传 `[(bytes, mime)]`，测试同步更新即可 |
| F1 DNS rebinding 残留风险 | ✅ 同意 | v1「解析校验 + 禁用重定向 + 大小/类型限制」对本地 MCP 场景足够，残留风险已在文档/代码注释标注，v2 补 transport 级防护 |

### 11.2 P1 修订点（影响实现正确性，实现前必须并入）

1. **多裁剪块数上限未定义**：`tile_if_needed` 对超长图切块无上限，切出块数可能超过 `VISION_MAX_BATCH_IMAGES`（默认 5），与 F3 多图上限冲突。**修订**：明确多裁剪结果直接进入 `backend.analyze`（绕过多图上限），或为切块定义独立上限。
2. **R2 layout 阈值表述矛盾**：§4.5.1「放宽压缩阈值至 3600×3600」与 R1 压缩逻辑（按长边 1800 等比缩放）不一致，易实现歧义。**修订**：明确 layout 单图压缩到 1800 长边即可、不做切块，无需「放宽到 3600」。

### 11.3 P2 修订点（兼容 / UX）

3. **新增工具缺 `model` 参数**：现有工具入参含 `model`，`vision_compare` / `vision_annotate` / `vision_layout` / `vision_reconstruct` 应统一加 `model`，与现有工具保持一致。
4. **M2 `task` 枚举暴露内部 key**：`ocr_general` / `inspect_ui_bug` 等是内部标识，对用户不友好。**修订**：枚举用语义名（如 `ocr_error` / `ui_structure`），内部再映射到 `TaskPrompt`。
5. **`_load_images` 归属不明确**：`_read_image` 目前在 `backends.py`，§3.2 数据流把 `_load_images` 画在 server 层。**修订**：实现前明确归属，避免 server↔backends 循环依赖。

### 11.4 P3 细节

6. **SSRF 补充**：额外拒绝带 userinfo 的 URL（防 `http://user:pass@...` 混淆）。
7. **流程图标注**：§3.2 的 `tile_if_needed` 步骤注明仅 ocr 单图走，F3 多图不走切块。
8. **reconstruct 自检局限**：同模型对自身输出自检价值有限，v1 可接受但应降低验收预期。
