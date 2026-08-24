# GPT Image Playground Skill

一个面向其他 AI 工具的图片生成编排技能。它不是单纯的 React 图片应用，而是把 CLI、REST、OpenAPI、Responses Agent、Web 工作台和多个图片 Provider 统一成可调用的技能接口。

```text
Claude / Codex / Gemini / 自定义 Agent / CLI / Web
                         ↓
              gpt-image-playground skill
                         ↓
 Images API / Responses API / fal.ai / Custom Provider
```

当前版本：`2.7.1`

## 其他 Agent 安装

其他支持 `SKILL.md` 的 Agent 不需要 Node.js/npm。使用 Python 安装器下载已构建运行包：

```sh
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" https://raw.githubusercontent.com/joeshu/gpt-image-playground/main/scripts/install.py -o /tmp/install-gpt-image-playground.py
GITHUB_TOKEN="$GITHUB_TOKEN" python3 /tmp/install-gpt-image-playground.py --target "$HOME/.skills/gpt-image-playground"
cd "$HOME/.skills/gpt-image-playground" && python3 scripts/skill.py check
```

如果仓库是私有仓库，`GITHUB_TOKEN` 需要具备仓库读取权限。安装包已经包含 React `web-react/dist`，安装后直接启动 Web，不需要构建环境：

```sh
python3 scripts/skill.py serve
```

## 本地运行目录

在仓库工作区运行时，生成图片默认保存到：

```text
outputs/gpt-image-playground/
```

运行数据和连接配置默认保存到：

```text
.monkeycode/runtime/gpt-image-playground/
```

平台托管环境可以通过 `GPT_IMAGE_PLAYGROUND_DATA` 和 `GPT_IMAGE_PLAYGROUND_ATTACHMENTS` 覆盖这两个目录。

## 最小运行时打包

本技能 Web 使用原生 HTML/CSS/JavaScript，不需要 Node.js、npm 或任何前端构建环境。

```bash
python3 scripts/package_runtime.py
```

打包器只包含 Python 后端、必要配置和轻量 `web/index.html`，不包含测试、`.git`、缓存和生成产物。Provider API Key 仍只放在后端环境变量或运行时 Profile 中。

## 跨 Agent 调用

Codex、Minis、Claude 和其他 Agent 使用统一入口：

```sh
python3 scripts/skill.py check
python3 scripts/skill.py generate --profile default --prompt "生成一张产品海报"
python3 scripts/skill.py agent --profile default --prompt "生成三张独立场景图"
```

入口使用 JSON stdout 契约，完整调用约定和能力说明均位于 `SKILL.md`。

## 规范使用指南

### 技能定位

`gpt-image-playground` 是一个图片生成与编辑编排技能，适合由 CLI、其他 Agent、Web 工作台或 REST 客户端调用。技能负责统一处理 Profile、Provider、图片参数、参考图、遮罩、批量任务、Agent 编排、任务历史和结果文件。

技能入口文件为 `SKILL.md`。自动化 Agent 应先读取 `SKILL.md`，再从项目根目录执行脚本；详细案例、配置方式和安全约束以本 README 为准。

### 标准调用流程

1. 检查技能和 Profile 配置。

```sh
python3 scripts/skill.py check
python3 scripts/playground.py --validate-profiles
```

2. 根据任务类型选择入口。

| 任务目标 | 推荐入口 | 说明 |
| --- | --- | --- |
| 单张图片生成 | `scripts/playground.py` | 文生图、参数控制、参考图和遮罩 |
| 同一提示词生成多张图片 | `scripts/playground.py` | 使用 `--n` 控制数量 |
| 多个不同提示词任务 | `scripts/playground.py` | 使用 `--batch` 和 `--concurrency` |
| 多轮规划和连续创作 | `scripts/agent.py` | 使用 Responses Agent 编排任务 |
| 提供给其他工具调用 | `scripts/api_server.py` | 使用 REST/OpenAPI 和异步 Job |
| 人工操作和结果浏览 | Web 工作台 | 创建、画廊、历史和设置 |

3. 先执行 Dry Run 验证参数，再执行真实请求。

```sh
python3 scripts/playground.py \
  --profile default \
  --prompt "产品海报，暖色纸张质感，大面积留白" \
  --size 4:5 \
  --quality medium \
  --dry-run
```

4. 读取 JSON stdout，使用 `saved_images`、`images`、`job_id`、`error` 和诊断字段处理结果。

5. 真实任务完成后，根据需要从 `outputs/gpt-image-playground/` 获取图片，从历史或画廊接口获取任务索引。

### 入口一：通用技能入口

`scripts/skill.py` 适合其他 Agent 或自动化脚本统一调用。

检查技能：

```sh
python3 scripts/skill.py check
```

生成图片：

```sh
python3 scripts/skill.py generate \
  --profile default \
  --prompt "极简风格的红色咖啡杯产品图"
```

调用 Agent：

```sh
python3 scripts/skill.py agent \
  --profile default \
  --prompt "先设计一个角色，再生成三张不同场景图"
```

启动 Web/API 服务：

```sh
python3 scripts/skill.py serve \
  --host 127.0.0.1 \
  --port 8765
```

### 入口二：CLI 图片生成

使用 `scripts/playground.py` 处理单图、参考图、遮罩、批量和 Provider 参数。

最小调用：

```sh
python3 scripts/playground.py \
  --profile default \
  --prompt "雨夜霓虹城市电影海报"
```

常用参数：

| 参数 | 用途 | 示例 |
| --- | --- | --- |
| `--profile` | 选择 Profile | `--profile default` |
| `--prompt` | 输入提示词 | `--prompt "产品摄影"` |
| `--image` | 添加参考图，可重复 | `--image source.png` |
| `--mask` | 指定局部编辑遮罩 | `--mask mask.png` |
| `--size` | 画布比例或尺寸 | `--size 16:9` |
| `--quality` | 图片质量 | `--quality high` |
| `--n` | 同提示词生成数量 | `--n 4` |
| `--style` | 风格提示 | `--style editorial` |
| `--execution-mode` | 执行策略 | `auto`、`native`、`script` |
| `--api-mode` | Provider API 模式 | `images`、`responses` |
| `--stream` | 请求流式事件 | 适用于 Responses API |
| `--dry-run` | 只校验参数 | 不调用 Provider |

### 入口三：Agent 编排

使用 `scripts/agent.py` 处理需要拆解步骤、连续生成、会话恢复或分支实验的任务。

```sh
python3 scripts/agent.py \
  --profile default \
  --execution-mode native \
  --max-rounds 6 \
  --prompt "设计一个橘猫侦探角色，再生成三张不同场景图"
```

执行策略：

- `native`：使用 Provider 原生图片生成工具，适合作为默认模式。
- `script`：使用本地 `generate_image` 工具，适合需要本地工具编排的场景。
- `auto`：根据 Provider 能力和请求结果自动选择可用路径。

流式输出：

```sh
python3 scripts/agent.py \
  --profile default \
  --stream \
  --prompt "生成一组统一风格的角色设定图"
```

恢复中断会话：

```sh
python3 scripts/agent.py \
  --resume agent-session.json \
  --prompt "继续完成剩余场景"
```

创建分支会话和重生成指定轮次：

```sh
python3 scripts/agent.py \
  --branch-from agent-session.json \
  --branch-to experiment-session.json

python3 scripts/agent.py \
  --regenerate-session agent-session.json \
  --round-index 2 \
  --branch-to regenerated-session.json
```

### 入口四：REST/OpenAPI 服务

启动本地服务：

```sh
python3 scripts/api_server.py \
  --host 127.0.0.1 \
  --port 8765
```

健康检查：

```sh
curl --max-time 10 http://127.0.0.1:8765/healthz
```

查看 OpenAPI：

```sh
curl --max-time 10 http://127.0.0.1:8765/openapi.json
```

同步生成请求：

```sh
curl --max-time 120 \
  -X POST http://127.0.0.1:8765/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "profile": "default",
    "prompt": "极简风格产品海报",
    "size": "4:5",
    "quality": "medium",
    "n": 1
  }'
```

异步任务：

```sh
curl --max-time 30 \
  -X POST http://127.0.0.1:8765/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "profile": "default",
    "prompt": "生成一张产品图",
    "async": true
  }'
```

响应中的 `job_id` 用于查询任务和订阅事件：

```text
GET /v1/jobs/<job-id>
GET /v1/jobs/<job-id>/events
```

### 入口五：Web 工作台

Web 工作台和 API 服务使用同一个 Python 服务。启动后访问 `http://127.0.0.1:8765/`。

```sh
python3 scripts/api_server.py \
  --host 127.0.0.1 \
  --port 8765
```

主要视图：

- 创建图片：使用单张、批量或智能代理模式提交任务。
- 画廊：搜索、筛选、收藏、选择、批量操作和查看图片详情。
- 历史任务：搜索任务记录并打开任务详情。
- 设置：选择 Profile、配置 Provider、设置默认生成参数和浏览器偏好。

Web 端默认中文显示，保留 `Profile`、`Provider`、`API Key`、模型名和接口地址等技术标识。API Key 只提交到本地服务，浏览器 Token 只有在用户主动保存时才写入 localStorage。

### 输出契约

自动化调用应把 stdout 当作 JSON 接口处理，不应依赖人类可读日志。常见成功字段：

| 字段 | 用途 |
| --- | --- |
| `saved_images` | CLI 生成图片的本地保存路径 |
| `images` | Agent 或 REST 返回的图片结果 |
| `job_id` | 异步任务标识 |
| `requested_params` | 用户请求的规范化参数 |
| `actual_params` | Provider 实际使用的参数 |
| `attempts` | 请求尝试和重试信息 |
| `timing.elapsed_ms` | 任务耗时 |
| `events_file` | Agent JSONL 事件文件 |
| `error` | 失败原因 |
| `error_code` | 稳定错误分类 |

批量结果使用 `batch_id` 和 `batch_item_id` 作为稳定标识。部分失败批次可以通过 `--retry-task <batch_id>` 重试失败项，成功项会复用已有结果。

### 配置与安全规则

1. 首次使用先执行 `--setup` 或 `--connection-status`。
2. 用户项目配置使用 `GPT_IMAGE_*`、`GPT_AGENT_*`、`FAL_KEY` 和 `GPT_PLAYGROUND_*` 变量。
3. API Key 仅由用户通过环境变量或本地连接文件提供。
4. 连接文件使用 `600` 权限并存放在运行数据目录。
5. API Key 不进入 Git、任务文件、历史、日志、API 响应或浏览器存储。
6. 将服务绑定到非 localhost 地址时，必须配置 `GPT_PLAYGROUND_API_TOKEN`。
7. 远程图片 URL 会被 REST 输入校验拒绝；本地图片必须位于允许的输入目录。

### 验证清单

完成安装、配置或代码修改后，按顺序执行：

```sh
python3 scripts/skill.py check
python3 scripts/playground.py --validate-profiles
python3 scripts/playground.py --prompt "验证参数" --dry-run
python3 scripts/agent.py --prompt "验证 Agent" --dry-run
python3 -m py_compile scripts/*.py tests/*.py
PYTHONPATH=scripts python3 tests/test_api.py
PYTHONPATH=scripts python3 tests/test_providers.py
git diff --check
```

## 适用场景

- 文生图、参考图、多图融合、遮罩编辑
- 批量生成、并发、失败隔离、网络重试
- OpenAI Images API、Responses 图片 API、fal.ai、自定义 Provider
- 自定义异步 Provider 支持 408/429/5xx 与网络错误恢复、指数退避和轮询事件记录
- Responses Agent 多轮图片规划
- 提供给其他 AI 工具的本地 REST/OpenAPI 图片服务
- 任务历史、SQLite 索引、画廊、收藏、缩略图
- 结果 ZIP、完整备份、备份恢复

### 执行结果与 Agent 事件

图片任务结果会统一提供 `requested_params`、`actual_params`、`attempts` 和 `timing.elapsed_ms` 字段。`execution_mode=auto` 仅在 Provider 缺少 endpoint、Provider 文件、响应解析失败、空结果或底层请求失败时回退到 Script；认证失败和输入参数错误会直接返回，避免重复请求。

Agent 结果包含 `events_file`，文件采用 JSONL 格式记录 `round.started`、`tool.started`、`tool.completed`、`tool.failed` 和 `round.completed` 事件。每个工具事件携带 `tool_call_id`，生成图片结果携带 `task_id` 和 `tool_call_id`，便于 REST、UI 和恢复逻辑关联任务。

异步调用 `/v1/agent` 时，API 会把同一批事件转发到 `/v1/jobs/{job_id}/events`。事件数据会增加 `job_id` 和稳定的 `event_id`，客户端可以使用 `event_id` 去重并按事件顺序更新进度。

Agent 任务运行期间 API 会实时读取该 Job 专属的事件文件并推送 SSE，客户端可以在图片生成过程中更新进度；任务完成时会再执行一次尾部读取，确保最后事件进入队列。

Agent 会在收到模型工具调用后先保存 `pending_tool_calls` 检查点，再执行本地图片任务。进程中断后使用 `--resume <session-path>` 会先恢复这些工具调用，完成后继续请求模型，避免恢复过程遗漏或重复整轮规划。

每个工具完成后都会更新 `completed_tool_calls`，恢复时通过 `tool_call_id` 复用已完成结果，剩余工具继续执行。批量失败结果也会保留 `batch_id`、`batch_item_id` 和 `requested_params`。

## 快速开始

### 1. 首次配置

没有环境变量时：

```sh
python3 scripts/playground.py --setup
```

或者导入配置模板：

```sh
python3 scripts/playground.py --setup-json connection.example.json
```

配置保存于：

```text
/var/minis/workspace/gpt-image-playground/connection.json
```

文件权限为 `600`。API Key 不进入 Git、任务文件、历史、API 响应或浏览器 localStorage。

查看状态：

```sh
python3 scripts/playground.py --connection-status
```

服务器部署可使用：

```text
GPT_IMAGE_ENDPOINT
GPT_IMAGE_API_KEY
GPT_AGENT_ENDPOINT
FAL_KEY
```

### 2. CLI 生成

```sh
python3 scripts/playground.py \
  --profile default \
  --prompt "电影海报，夜晚城市，宽幅构图"
```

参考图和遮罩：

```sh
python3 scripts/playground.py \
  --prompt "只修改选区内容" \
  --image /var/minis/attachments/source.png \
  --mask /var/minis/attachments/mask.png
```

Dry Run：

```sh
python3 scripts/playground.py --prompt "测试" --dry-run
```

### 3. Agent

```sh
python3 scripts/agent.py \
  --profile default \
  --prompt "先设计角色，再生成三张场景图"
```

Session 分支：

```sh
python3 scripts/agent.py \
  --branch-from session.json \
  --branch-to branch.json
```

指定轮次重生成请求：

```sh
python3 scripts/agent.py \
  --regenerate-session session.json \
  --round-index 2 \
  --branch-to regenerated.json
```

## REST / OpenAPI

启动：

```sh
python3 scripts/api_server.py --host 127.0.0.1 --port 8765
```

停止：

```sh
python3 scripts/api_server.py --stop
```

OpenAPI：

```text
GET /openapi.json
```

主要接口：

```text
POST /v1/generate
POST /v1/batch
POST /v1/agent
GET  /v1/jobs/{id}
GET  /v1/jobs/{id}/events
GET  /v1/history
GET  /v1/gallery
GET  /v1/favorites
POST /v1/favorite
POST /v1/delete-images
POST /v1/backup/export
POST /v1/backup/import
GET  /v1/thumbnails
POST /v1/agent/branch
POST /v1/agent/regenerate
```

异步调用：

```json
{
  "prompt": "生成产品图",
  "profile": "default",
  "async": true
}
```

然后通过 SSE 获取：

```text
GET /v1/jobs/<job-id>/events
```

首次连接配置：

```http
POST /v1/setup
```

```json
{
  "profile": "default",
  "endpoint": "https://api.example.com/v1/images/generations",
  "api_key": "首次填写",
  "model": "gpt-image-2"
}
```

## 使用文档与案例

### 调用选择

| 目标 | 入口 | 主要参数 |
| --- | --- | --- |
| 单图生成 | `scripts/playground.py` | `--prompt` |
| 多张同提示词图片 | `scripts/playground.py` | `--n` |
| 多个不同任务 | `scripts/playground.py` | `--batch` |
| 参考图编辑 | `scripts/playground.py` | `--image` |
| 局部编辑 | `scripts/playground.py` | `--image`、`--mask` |
| 多轮规划 | `scripts/agent.py` | `--prompt` |
| 给其他 Agent 调用 | `scripts/api_server.py` | REST/OpenAPI |
| 检查请求不调用 API | CLI 或 Agent | `--dry-run` |

所有命令从项目根目录运行。自动化 Agent 应读取 JSON stdout，图片从 `saved_images` 或 `images` 字段获取。

### 配置案例

交互式配置：

```sh
python3 scripts/playground.py --setup
```

从配置模板导入：

```sh
python3 scripts/playground.py --setup-json connection.example.json
```

通过环境变量配置 CI 或容器：

```sh
GPT_IMAGE_ENDPOINT="https://api.example.com/v1/images/generations" \
GPT_IMAGE_API_KEY="用户自行提供的项目 Key" \
python3 scripts/playground.py --prompt "CI dry run" --dry-run
```

查看配置状态：

```sh
python3 scripts/playground.py --connection-status
```

### 文生图案例

宽幅电影海报：

```sh
python3 scripts/playground.py \
  --profile default \
  --prompt "电影海报，雨夜霓虹城市，主体位于右侧，左侧保留标题空间" \
  --size 16:9 \
  --quality high \
  --output-format png
```

指定模型和数量：

```sh
python3 scripts/playground.py \
  --model gpt-5.6-sol \
  --n 4 \
  --size 1:1 \
  --prompt "四种不同构图的极简应用图标"
```

透明背景：

```sh
python3 scripts/playground.py \
  --prompt "单个红色咖啡杯，产品摄影" \
  --output-format png \
  --transparent-background local
```

只检查最终请求：

```sh
python3 scripts/playground.py \
  --model gpt-5.6-terra \
  --size 4:3 \
  --quality medium \
  --prompt "检查模型和尺寸" \
  --dry-run
```

### 参考图与遮罩案例

改变参考图风格：

```sh
python3 scripts/playground.py \
  --prompt "保持主体结构，改为复古胶片风格" \
  --image /var/minis/attachments/source.png
```

融合多张参考图：

```sh
python3 scripts/playground.py \
  --prompt "融合建筑参考图和配色参考图，生成统一产品场景" \
  --image /var/minis/attachments/building.png \
  --image /var/minis/attachments/palette.png
```

只修改遮罩区域：

```sh
python3 scripts/playground.py \
  --prompt "只替换遮罩区域中的天空，其他区域保持不变" \
  --image /var/minis/attachments/source.png \
  --mask /var/minis/attachments/mask.png
```

主图和 mask 应保持相同尺寸。技能会执行工作尺寸预处理，并在结果中记录 `mask_metadata`。

### 批量任务案例

同一提示词生成多张图：

```sh
python3 scripts/playground.py \
  --prompt "极简风格产品展示图" \
  --n 4 \
  --concurrency 2
```

不同提示词使用任务文件：

```sh
python3 scripts/playground.py \
  --batch tasks.batch.sample.json \
  --concurrency 3
```

任务文件：

```json
{
  "size": "1:1",
  "quality": "medium",
  "tasks": [
    {"prompt": "红色产品背景", "style": "product"},
    {"prompt": "蓝色产品背景", "style": "product"}
  ]
}
```

批量结果包含 `batch_id`、`total`、`succeeded`、`failed` 和 `results`。每个子任务包含稳定的 `batch_item_id`，单个子任务失败时，其他子任务继续执行，后续重试可以按子任务 ID 精确关联。

使用 `--retry-task <batch_id>` 重试部分失败批次时，成功子任务直接复用历史结果，失败子任务单独重新执行。批量结果会返回 `reused`、`retried` 和 `retry_of`，便于界面展示和审计。

### Agent 案例

多轮角色和场景生成：

```sh
python3 scripts/agent.py \
  --profile default \
  --max-rounds 6 \
  --prompt "先设计一个橘猫侦探角色，再基于同一角色生成三张不同场景图"
```

恢复会话：

```sh
python3 scripts/agent.py \
  --profile default \
  --resume /var/minis/workspace/gpt-image-playground/agent-session.json
```

查看 Agent 历史：

```sh
python3 scripts/agent.py --history-list --history-limit 20
python3 scripts/agent.py --history-get agent-20260823-064414-01cf59
```

Agent 结果示例：

```json
{
  "status": "completed",
  "conversation_id": "agent-...",
  "text": "生成说明",
  "images": [{"id": "image-1", "path": "/path/to/image.png"}],
  "rounds": 3,
  "session_path": "/path/to/session.json"
}
```

Agent 图片引用：

```text
<ref id="base_character" />
```

Agent 会把工具参数中的 `images` 引用和 prompt 中的 `<ref id="..." />` 引用统一解析为本地图片输入。重复的图片 ID 会自动规范化为 `id`、`id-2` 等稳定标识，便于多轮会话继续引用。

流式 Agent：

```sh
python3 scripts/agent.py \
  --profile default \
  --stream \
  --prompt "先生成角色，再生成三张依赖角色的场景图"
```

流式 Responses 服务会返回文本增量和最终 response 快照；本地会话保存 `raw_responses`、`last_tool_calls`、生成图片 ID 与图片路径，恢复会话时继续使用现有上下文。

### Responses 流式案例

```sh
python3 scripts/playground.py \
  --profile default \
  --api-mode responses \
  --stream \
  --prompt "生成一张电影海报"
```

流式结果包含 `events_file`、`partial_images`、`text` 和最终 `saved_images`。事件文件使用 JSONL 格式。

### Profile 管理案例

```sh
python3 scripts/playground.py --validate-profiles
python3 scripts/playground.py --import-profiles profiles.custom.async.example.json
python3 scripts/playground.py --import-profiles profiles.custom.async.example.json --merge-profiles
python3 scripts/playground.py --export-profiles /tmp/profiles-backup.json
```

模型选择优先级为 `task.model > --model > Profile.model`。`model` 和 `omit_model` 同时显式出现时会返回参数错误。

### REST/OpenAPI 案例

启动服务：

```sh
python3 scripts/api_server.py --host 127.0.0.1 --port 8765
```

健康检查：

```sh
curl http://127.0.0.1:8765/healthz
```

同步生成：

```sh
curl -X POST http://127.0.0.1:8765/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{"profile":"default","prompt":"白色背景极简产品图","size":"1:1","n":1}'
```

异步生成：

```sh
curl -X POST http://127.0.0.1:8765/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{"profile":"default","prompt":"生成四张概念图","n":4,"async":true}'
```

异步返回 `job_id`，查询状态和 SSE 事件：

```sh
curl http://127.0.0.1:8765/v1/jobs/job-...
curl -N http://127.0.0.1:8765/v1/jobs/job-.../events
```

批量 REST 请求：

```json
{
  "profile": "default",
  "concurrency": 2,
  "tasks": [
    {"prompt": "红色背景产品图"},
    {"prompt": "蓝色背景产品图"}
  ]
}
```

REST Agent 请求：

```sh
curl -X POST http://127.0.0.1:8765/v1/agent \
  -H 'Content-Type: application/json' \
  -d '{"profile":"default","prompt":"设计角色并生成三张场景图","async":true}'
```

### Provider 案例

fal.ai Profile：

```json
{
  "id": "fal-default",
  "provider": "fal",
  "model": "fal-ai/gpt-image-1",
  "api_key_env": "FAL_KEY"
}
```

自定义异步 Provider 的关键字段：

```json
{
  "submit": {
    "path": "images/generations",
    "method": "POST",
    "contentType": "json",
    "body": {"prompt": "$prompt", "model": "$profile.model"},
    "taskIdPath": "data.task_id"
  },
  "poll": {
    "path": "tasks/{task_id}",
    "statusPath": "data.status",
    "successValues": ["completed"],
    "failureValues": ["failed", "cancelled"],
    "result": {"imageUrlPaths": ["data.result.images.*.url"]}
  }
}
```

异步 Provider 会对 408、425、429、5xx 和可恢复网络错误执行退避重试，并保存轮询事件诊断文件。

### 历史、备份与失败处理

```sh
python3 scripts/playground.py --history-list --history-limit 20
python3 scripts/playground.py --history-list --history-status failed
python3 scripts/playground.py --retry-task gip-... --retry 2
```

导出备份：

```sh
curl -X POST http://127.0.0.1:8765/v1/backup/export
```

失败结果重点读取 `status`、`error_code`、`error` 和进程退出码。`partial_failed` 结果可继续使用成功子任务，并根据 `results` 定位失败项。

## Provider

Profile 配置：

```text
profiles.json
profiles.custom.sync.example.json
profiles.custom.async.example.json
```

支持：

```text
openai-compatible + api_mode=images
openai-compatible + api_mode=responses
fal / fal.ai
custom synchronous
custom asynchronous
multipart provider
```

## Web 工作台

启动 API 后访问：

```text
http://127.0.0.1:8765/
```

支持：

- 首次配置
- 参考图选择、拖拽、剪贴板粘贴
- Canvas 遮罩编辑
- 单图、批量、Agent
- Job 状态和 SSE
- 结果预览和 Lightbox
- Lightbox 上一张/下一张
- 历史搜索
- 画廊和缩略图
- 多选、批量收藏、批量删除
- ZIP 导出和完整备份

## 备份与恢复

导出：

```http
POST /v1/backup/export
```

ZIP 包含：

```text
manifest.json
images/
任务历史
图片索引
收藏状态
```

恢复前先验证：

```json
{
  "path": "/var/minis/workspace/gpt-image-playground/backup.zip",
  "apply": false
}
```

确认后应用：

```json
{
  "path": "/var/minis/workspace/gpt-image-playground/backup.zip",
  "apply": true,
  "conflict": "skip"
}
```

冲突策略：

```text
fail     有冲突立即失败
skip     保留现有内容
replace  用备份内容替换
```

恢复使用 staging、manifest 校验、路径穿越防护和失败文件回滚。

## 安全

- 默认只监听 localhost
- 远程监听必须设置 Bearer Token
- API Key 只在环境变量或权限 `600` 配置文件中
- 拒绝远程图片 URL，防止 SSRF
- 图片路径限制在 Minis 白名单目录
- ZIP 拒绝绝对路径和 `../`
- 删除默认只删除索引，不删除物理文件
- OpenAPI、日志和状态接口不返回 Key

## 测试

```sh
python3 -m compileall -q .
python3 tests/test_api.py
python3 scripts/playground.py --validate-profiles
python3 scripts/playground.py --prompt "test" --dry-run
python3 scripts/agent.py --prompt "test" --dry-run
```

GitHub Actions 自动执行编译、API、CLI 和 Agent 回归。

## 项目结构

```text
scripts/
├── agent.py
├── api_server.py
├── connection.py
├── custom_provider.py
├── fal_provider.py
├── image_ops.py
├── image_store.py
├── playground.py
├── responses_provider.py
└── task_store.py
web/index.html
tests/test_api.py
profiles.json
presets.json
connection.example.json
```

项目仓库为私有：

```text
https://github.com/joeshu/gpt-image-playground
```

## v1.9 变更

- 备份恢复冲突策略：`fail`、`skip`、`replace`
- `apply: true` 恢复失败回滚本次复制文件
- Agent 指定轮次重生成：`--round-index N`
- Web 画廊多选、批量收藏/删除和 Lightbox 导航

## 原生默认模型接口

原生接口仍然可以、也通常需要选择具体模型，例如 `gpt-5.6-sol`。`omit_model` 只是特殊兼容开关：只有接口明确要求服务端自动选模型时，才完全省略 `model`。

选择模型：

```sh
python3 scripts/playground.py \
  --profile default \
  --model gpt-5.6-sol \
  --prompt "一只橘猫头像"
```

最终请求体会包含 `model: gpt-5.6-sol`。只有需要服务端自动选模型时才使用：

```sh
python3 scripts/playground.py \
  --profile default \
  --omit-model \
  --prompt "一只橘猫头像"
```

`model` 与 `omit_model` 同时显式指定会报错；显式模型会覆盖 Profile 的 `omit_model`。Dry Run 会校验最终请求体。
## 模型配置

模型由 Profile 和模型目录共同管理，不硬编码到单一 Provider：

```text
图片默认模型：Profile.model
Agent 默认模型：Profile.agent_model
可选目录：Profile.models
全局目录：model_catalog.json
单次覆盖：--model / task.model / REST model
```

当前内置推荐模型：

```text
gpt-image-2
gpt-5.6-sol
gpt-5.6-terra
gpt-5.6-luna
```

查看模型目录：

```http
GET /v1/models
```

单次选择模型：

```sh
python3 scripts/playground.py \
  --profile default \
  --model gpt-5.6-terra \
  --prompt "一张电影海报"
```

模型选择优先级：

```text
图片任务 model > CLI --model > Profile.model

Agent 请求使用 `Profile.agent_model`，默认值为 `gpt-5.6-terra`。Agent 的 Responses 规划模型与图片生成工具调用的 Images 模型分离：Agent 使用文本模型规划，工具内部继续使用 `Profile.model` 生成图片。

Agent 执行模式：

```text
native  → Responses 模型直接使用原生 image_generation 能力返回图片
script  → Agent 调用本地 generate_image / generate_image_batch 工具生成图片
auto    → 可选混合编排模式，保留本地工具调用
```

当 Provider 已支持 Responses 原生生图时，Agent 默认使用 `native`。该模式不会注册或调用本地 `generate_image` 工具。需要混合编排时显式使用 `--execution-mode script` 或 `--execution-mode auto`。
```

`omit_model` 只用于明确要求不发送模型字段的接口。它不能和显式模型同时指定。自定义模型 ID 允许使用，但必须是安全的单行模型标识；请求前会拒绝空格、控制字符和超长值。

## 双执行模式

技能同时支持两种执行模式：

```text
native  → Provider 模块直接执行 HTTP Images API
script  → scripts/generate.py 执行器
auto    → 默认模式，优先 native，失败后回退 script
```

CLI：

```sh
python3 scripts/playground.py --execution-mode native --model gpt-5.6-sol --prompt "一张海报"
python3 scripts/playground.py --execution-mode script --model gpt-image-2 --prompt "一张海报"
```

任务 JSON 或 REST：

```json
{
  "prompt": "一张海报",
  "model": "gpt-5.6-sol",
  "execution_mode": "native"
}
```

`native` 目前用于 Images API；Responses、fal.ai、Custom Provider 继续由各自 Provider 适配器执行。`script` 始终使用主技能内置的 `scripts/generate.py`，不依赖外部 `gpt-image-tool`。

Agent 图片工具也支持执行模式：

```sh
python3 scripts/agent.py \
  --execution-mode native \
  --prompt "生成一张产品图"

python3 scripts/agent.py \
  --execution-mode script \
  --prompt "生成一张产品图"
```

Agent 的 `generate_image` 和 `generate_image_batch` 默认继承 `--execution-mode`。工具调用中提供 `execution_mode` 时，只覆盖当前工具任务。`auto` 优先使用 Native，Native 失败后回退 Script，并在结果中返回 `fallback_from` 和 `fallback_reason`。
