---
name: gpt-image-playground
version: 1.5.0
description: GPT Image Playground 上层编排技能。基于 gpt-image-tool 底层执行器，支持自然语言文生图、图片编辑、多参考图融合、批量生成与风格预设。
---

# GPT Image Playground

这是上层任务编排技能，不直接实现供应商 HTTP 协议。所有实际请求委托给 `/var/minis/skills/gpt-image-tool/scripts/generate.py`，因此 API Key、响应诊断和图片落盘规则保持统一。

## 触发场景

- 生成图片、海报、头像、插画、产品图
- 用附件或多张参考图生成/编辑
- 批量生成多个版本
- 指定比例、尺寸、质量、模型或风格预设
- 将图片生成任务整理成可复用配置

## 执行原则

1. 先判断模式：`generate`、`edit`、`reference` 或 `batch`。
2. 用户未指定图片时执行文生图；有附件时默认将其作为参考图，除非用户明确要求纯文生图。
3. 不猜测 API 协议；调用统一底层执行器。
4. API Key 只从环境变量读取，绝不写入 task/config/日志。
5. 图片保存到 `/var/minis/attachments/gpt-image-playground/`；任务与响应保存到 `/var/minis/workspace/gpt-image-playground/`。
6. 完成后返回每张图片的 Markdown 链接、任务摘要和失败项。

## 参数默认值

- model: `gpt-image-2`
- size: 用户指定比例；未指定为 `1:1`
- quality: `low`
- output_format: `png`
- n: `1`
- 风格预设见 `presets.json`

## 文件输入

按顺序检查：`/var/minis/attachments/`、`/var/minis/workspace/`、`/var/minis/mounts/`。本地图片交给底层工具转换为 data URL，不手动要求用户转码。最多建议 16 张参考图；实际上限以供应商为准。

## 当前版本能力

当前版本：`1.2.0`。

## 首次使用配置

没有环境变量时，第一次使用会要求填写图片服务器地址和 API Key。推荐先运行：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --setup
```

也可以使用标准 JSON 配置，适合其他 AI 工具或自动化安装：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --setup-json /var/minis/skills/gpt-image-playground/connection.example.json
```

真实配置保存于：

```text
/var/minis/workspace/gpt-image-playground/connection.json
```

文件只保存 endpoint、API Key 和 model，权限为 `600`。API Key 不写入任务文件、历史、响应、OpenAPI 或 Web localStorage。

检查配置状态：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --connection-status
```

REST 配置：

```http
GET  /v1/setup/status
POST /v1/setup
```

```json
{
  "endpoint": "https://api.example.com/v1/images/generations",
  "api_key": "首次使用时填写",
  "model": "gpt-image-2"
}
```

其他 AI 工具可以直接调用：

```http
POST /v1/generate
Content-Type: application/json

{"prompt":"一张电影海报","profile":"default","async":true}
```

完整接口定义：

```text
GET /openapi.json
```

环境变量仍然优先于本地配置，适合 CI、Docker 和服务器部署：

```text
GPT_IMAGE_ENDPOINT
GPT_IMAGE_API_KEY
```

## v1.0 生产化接口

API 服务：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/api_server.py \
  --host 127.0.0.1 --port 8765
```

停止：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/api_server.py --stop
```

生产化能力：

- `GET /openapi.json`：OpenAPI 3.0.3 描述
- Job 状态持久化到 `workspace/gpt-image-playground/api/jobs/`
- 服务重启时将未完成 Job 标记为 failed，避免假性 running
- PID 文件：`workspace/gpt-image-playground/api/api-server.pid`
- `POST /v1/export-zip`：从结果摘要导出 ZIP
- `GET /v1/download-zip?result=...`：受控下载 ZIP
- `GET /v1/files?path=...`：受控图片读取
- SIGTERM/KeyboardInterrupt 优雅停止

API 仍默认只监听 localhost，并继续使用 Bearer Token、目录白名单和密钥环境变量隔离。

API 服务同时提供单页 Web 工作台：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/api_server.py \
  --host 127.0.0.1 --port 8765
```

然后打开：

```text
http://127.0.0.1:8765/
```

工作台支持：

- 单图生成、批量生成、Responses Agent 三种模式
- Prompt、Profile、风格、尺寸、质量和生成数量
- 多参考图选择与本地预览
- 遮罩文件选择与本地预览
- 同步请求或异步 Job
- Job 状态轮询
- 生成结果预览和原始摘要
- 历史任务列表
- 可选 API Token

浏览器上传的图片只在 API 进程中短暂落地到临时文件，执行结束后清理；不会写入 API 请求日志。生成结果通过受控的 `GET /v1/files?path=...` 读取，并继续执行目录白名单校验。

已支持本地 REST API：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/api_server.py \
  --host 127.0.0.1 --port 8765
```

接口：

- `GET /healthz`：健康检查
- `GET /v1/profiles`：脱敏 Profile 列表
- `GET /v1/history?limit=20`：历史任务
- `POST /v1/generate`：单任务生成
- `POST /v1/batch`：批量生成
- `POST /v1/agent`：Agent 任务
- `GET /v1/jobs/<job-id>`：后台 Job 状态

生成、批量和 Agent 请求均支持 `"async": true`，返回 HTTP 202 和 `job_id`，随后轮询 `/v1/jobs/<job-id>`。后台最多保留 32 个活动/排队 Job，最多 2 路执行。

默认只监听 `127.0.0.1`。如需 Token 鉴权，设置 `GPT_PLAYGROUND_API_TOKEN`，客户端使用 `Authorization: Bearer <token>`。API 不接受客户端传入 endpoint、agent_endpoint、api_key 或 api_key_env。图片路径只允许 `/var/minis/attachments`、`/var/minis/workspace` 和 `/var/minis/mounts`。

已支持：文生图、单图/多图参考、风格预设、严格参数校验、唯一任务 ID、批量任务、并发限制、单子任务失败隔离、网络类失败重试、Profile 选择与环境变量映射、声明式同步/异步自定义供应商、请求模板与响应路径映射、Profile 导入导出与连通性测试、Responses Agent 多轮工具调用、Agent 图片引用、Agent 批量并发、历史 JSONL 索引、dry-run、统一诊断、本地 REST API、异步 Job 队列和 Web 工作台。

Profile 配置位于 `profiles.json`。Profile 只保存 endpoint、model 和密钥环境变量名，不保存密钥。执行时可用 `--profile aiwanwu` 或在任务 JSON 中设置 `profile`。

校验 Profile 与自定义供应商清单：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --validate-profiles
```

自定义供应商示例配置：

- `profiles.custom.sync.example.json`：同步 JSON + multipart 编辑/遮罩
- `profiles.custom.async.example.json`：异步 task ID + 状态轮询

导入、导出和连通性测试：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --export-profiles /var/minis/workspace/gpt-image-playground/profiles.backup.json
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --import-profiles /path/to/profiles.json --merge-profiles
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --test-profile aiwanwu
```

`--test-profile` 只做 HEAD 连通性探测，不会生成图片，也不会消耗生成额度。401/403 会报告为“主机可达但需要鉴权”。

## Responses Agent

Agent 入口：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py \
  --profile aiwanwu \
  --prompt '先生成一张角色设定图，再基于它生成三张不同场景图'
```

Agent 使用 Responses API 进行规划，并通过三个受控工具执行：

- `generate_image`：单张图片或基础图
- `generate_image_batch`：相互独立的图片并发生成
- `continue_generation`：依赖前置图片时继续下一轮

限制：最多 8 轮，每次最多 16 张参考图，批量工具最多 4 路并发。生成图片仍委托 Playground 主编排器，因此会保留 Profile、历史、重试和诊断能力。Agent Responses endpoint 可通过 Profile 的 `agent_endpoint`、`GPT_AGENT_ENDPOINT` 或 `--endpoint` 指定。

Agent dry-run：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py \
  --profile aiwanwu --prompt '生成一张电影海报' --dry-run
```

会话保存与恢复：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py \
  --profile aiwanwu --prompt '先生成角色设定，再生成场景图' \
  --session /var/minis/workspace/gpt-image-playground/story-session.json

python3 /var/minis/skills/gpt-image-playground/scripts/agent.py \
  --profile aiwanwu --resume /var/minis/workspace/gpt-image-playground/story-session.json
```

`--endpoint` 只覆盖 Responses Agent 地址；`--image-endpoint` 只覆盖 Agent 工具调用图片生成地址。默认情况下图片调用仍使用主 Playground Profile。

Agent 记录：

```text
/var/minis/workspace/gpt-image-playground/agent-history.jsonl
```

Agent 历史查询：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py --history-list --history-limit 20
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py --history-get <conversation-id>
```

Agent 请求重试：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py \
  --prompt '生成电影海报' --agent-retry 2
```

`--agent-retry` 只重试网络错误、超时、429 和 5xx；Agent 工具批量任务采用失败隔离，单个子任务失败不会丢失其他已完成结果。图片引用支持 `<ref id="..." />`、`ref:id` 和已知图片 ID。

## 批量任务文件格式：

```json
{
  "size": "1:1",
  "quality": "low",
  "tasks": [
    {"prompt": "红色背景的产品图", "style": "product"},
    {"prompt": "蓝色背景的产品图", "style": "product"}
  ]
}
```

执行：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --batch tasks.batch.sample.json --concurrency 2 --retry 1
```

结果写入：

- 图片：`/var/minis/attachments/gpt-image-playground/`
- 任务和响应：`/var/minis/workspace/gpt-image-playground/`
- 历史索引：`/var/minis/workspace/gpt-image-playground/history.jsonl`

查询历史：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --history-list --history-limit 20
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --history-get <task-id>
```

历史重试（只允许失败任务）：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --retry-task <task-id> --retry 1
```

批量上限为 100 个子任务，并发上限为 4。重试只针对网络、超时、429 和 5xx 等暂时性错误；参数错误不会重试。

### 图片处理能力

遮罩局部编辑：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --prompt '只修改选区中的物体' \
  --image /path/source.png \
  --mask /path/mask.png \
  --dry-run
```

遮罩要求：主图和遮罩必须尺寸一致；超过 1920 像素长边时会按比例缩放到 16 的倍数。遮罩语义不自动反转，具体透明/不透明区域含义以供应商接口文档为准。

本地透明背景后处理：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --prompt '绿色纯色背景的贴纸主体' \
  --transparent-background local \
  --background-color '#00ff00' \
  --background-fuzz '12%'
```

此模式使用 ImageMagick 色键抠图，适合图标、贴纸和单主体素材；复杂发丝、半透明物体或接近背景色的主体可能出现边缘误差。原图和透明结果都会保留。

批量 ZIP 导出：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --batch tasks.batch.sample.json \
  --export-zip /var/minis/attachments/gpt-image-playground/results.zip
```



已支持：文生图、单图/多图参考、批量任务、尺寸/质量/格式、风格预设、dry-run、统一诊断、自定义同步/异步 Provider、Profile 导入导出、Provider 连通性测试、Responses Agent 多轮工具调用、Agent 批量失败隔离、Agent 请求重试、Agent 历史查询、图片引用解析、REST API、异步 Job 队列、OpenAPI、受控图片/ZIP 下载和 Web 工作台。

当前未实现的是浏览器内遮罩涂抹画布与 IndexedDB 离线画廊；文件遮罩编辑、服务端历史和 Web 结果画廊已支持。

## CLI

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --prompt '电影感的雪山湖泊' --size 16:9 --style cinematic --n 2
```

图片编辑：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --prompt '保留主体，改成复古海报' --image /var/minis/attachments/input.png
```

任务文件：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --task tasks.sample.json
```

缺少密钥时设置：
- [设置 GPT_IMAGE_API_KEY](minis://settings/environments?create_key=GPT_IMAGE_API_KEY&create_value=&create_note=GPT%20Image%20Playground%20图片接口密钥)

## 输出规范

底层摘要中的路径会转换为 `minis://attachments/...` 或 `minis://workspace/...` 链接。原始响应保留用于排查，但不得输出密钥和完整 data URL。

## v1.2 Provider 与 API 兼容增强

v1.2 新增：

- Profile 独立连接配置，兼容旧版 `connection.json`
- `api_mode: images|responses`
- OpenAI Responses 图片生成 Provider
- fal.ai Queue REST Provider
- `actual_params` 和 `revised_prompts` 结果摘要
- 异步 Job SSE：`GET /v1/jobs/{job_id}/events`
- 原生 `background`、`moderation`、`quality: auto` 和 `size: auto` 参数
- GitHub Actions Python 编译、API、CLI、Agent Dry Run 自动测试

## v1.3 Web 与历史增强

- Canvas 遮罩编辑器：主图上直接涂抹白色修改区域
- 参考图拖拽上传和剪贴板图片粘贴
- SQLite 任务索引：`workspace/gpt-image-playground/tasks.sqlite3`
- REST 历史搜索：`GET /v1/history?q=关键词&status=completed&profile=default`
- Agent session 增加 `branch_id` 和 `parent_branch_id` 元数据，为后续分支恢复保留兼容字段

## v1.4 画廊、收藏与备份

- 图片 SHA-256 索引：`workspace/gpt-image-playground/tasks.sqlite3`
- 画廊查询：`GET /v1/gallery?favorite=1&limit=50`
- 收藏：`POST /v1/favorite`，请求 `{ "image_id": "...", "favorite": true }`
- 收藏列表：`GET /v1/favorites`
- 完整备份：`POST /v1/backup/export`，生成带 `manifest.json` 的 ZIP
- Web 工作台增加历史搜索和画廊入口
- Agent 会话分支字段保留在 session 中，兼容后续分支重生成

## v1.5 管理与恢复

- 图片删除：`POST /v1/delete-images`，支持 `image_ids` 批量删除；默认只删索引，传 `remove_files: true` 才删除白名单目录中的文件
- Web Lightbox：结果和画廊图片点击放大预览
- 备份导出接口已保留 `manifest.json`，用于后续安全恢复
- Agent session 保留分支元数据，可通过后续分支工具扩展
