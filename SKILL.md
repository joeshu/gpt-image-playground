---
name: gpt-image-playground
description: 可被其他 AI 工具调用的图片生成编排技能。支持文生图、参考图、遮罩、批量任务、OpenAI Images/Responses、fal.ai、自定义 Provider、Responses Agent、REST/OpenAPI、异步 Job、Web 工作台、首次配置、历史、画廊、收藏、备份恢复和安全文件管理。用户要求生成/编辑/批量处理图片，或需要图片 Provider、Agent、API、Web 工作台时使用。
version: 2.0.3
---

# GPT Image Playground 技能

## 定位

这是一个**可被其他 AI 工具直接调用的图片生成技能**，不是单纯的前端项目。它把自然语言、CLI、REST、OpenAPI 和 Agent 工具调用统一编排到图片 Provider：

```text
其他 AI / CLI / Web
        ↓
gpt-image-playground
        ↓
Images API / Responses API / fal.ai / 自定义 Provider
        ↓
图片文件、任务历史、画廊和 Agent 会话
```

底层 OpenAI-compatible 图片请求继续复用 `gpt-image-tool`；本技能负责配置、参数、任务、Provider、Agent、Web 和安全边界。

## 何时使用

- 生成一张或多张图片
- 使用参考图或 mask 编辑图片
- 批量生成、失败隔离和重试
- 通过 Responses Agent 多轮规划图片
- 接入 OpenAI-compatible、Responses、fal.ai 或自定义图片接口
- 为其他 AI 工具提供本地 REST/OpenAPI 图片能力
- 查看历史、画廊、收藏、导出或恢复备份

## 首次配置

没有环境变量时首次运行：

```sh
python3 scripts/playground.py --setup
```

或导入 JSON：

```sh
python3 scripts/playground.py --setup-json connection.example.json
```

配置保存在：

```text
/var/minis/workspace/gpt-image-playground/connection.json
```

权限为 `600`。真实 API Key 不进入仓库、任务、历史、OpenAPI 或浏览器 localStorage。

查看状态：

```sh
python3 scripts/playground.py --connection-status
```

生产/CI 可使用环境变量：

```text
GPT_IMAGE_ENDPOINT
GPT_IMAGE_API_KEY
GPT_AGENT_ENDPOINT
FAL_KEY
```

环境变量优先于本地连接配置。

## CLI

普通生成：

```sh
python3 scripts/playground.py \
  --profile default \
  --prompt "电影海报，夜晚城市，宽幅构图"
```

参考图和 mask：

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

Profile 校验：

```sh
python3 scripts/playground.py --validate-profiles
```

Agent：

```sh
python3 scripts/agent.py \
  --profile default \
  --prompt "先设计角色，再生成三张场景图"
```

Agent 分支和指定轮次重生成：

```sh
python3 scripts/agent.py \
  --branch-from session.json \
  --branch-to branch.json

python3 scripts/agent.py \
  --regenerate-session session.json \
  --round-index 2 \
  --branch-to regenerated.json
```

## Provider

Profile 文件：

```text
profiles.json
profiles.custom.sync.example.json
profiles.custom.async.example.json
```

支持：

```text
provider=openai-compatible
api_mode=images
api_mode=responses
provider=fal
provider=custom
```

Responses 模式：

```json
{
  "api_mode": "responses"
}
```

fal.ai 示例：

```json
{
  "provider": "fal",
  "model": "fal-ai/gpt-image-1"
}
```

自定义 Provider 支持 JSON、multipart、同步、异步轮询、task_id、URL/Base64 图片和响应路径映射。

## REST / OpenAPI

启动服务：

```sh
python3 scripts/api_server.py --host 127.0.0.1 --port 8765
```

停止服务：

```sh
python3 scripts/api_server.py --stop
```

主要接口：

```text
GET  /healthz
GET  /openapi.json
GET  /v1/profiles
GET  /v1/setup/status
POST /v1/setup
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
POST /v1/export-zip
POST /v1/backup/export
POST /v1/backup/import
GET  /v1/thumbnails
POST /v1/agent/branch
POST /v1/agent/regenerate
```

异步任务：

```json
{
  "prompt": "生成产品图",
  "profile": "default",
  "async": true
}
```

通过 `/v1/jobs/{id}/events` 获取 SSE：

```text
event: running
event: completed
event: failed
```

首次配置接口：

```json
{
  "profile": "default",
  "endpoint": "https://api.example.com/v1/images/generations",
  "api_key": "首次填写",
  "model": "gpt-image-2"
}
```

远程监听必须配置 `GPT_PLAYGROUND_API_TOKEN`，否则服务只允许 localhost。图片 URL 只允许 Data URL 或 Minis 白名单本地路径，防止 SSRF。

## Web 工作台

启动 API 后打开：

```text
http://127.0.0.1:8765/
```

支持：

- 首次连接配置
- Prompt、Profile、尺寸、质量和生成数量
- 参考图文件选择、拖拽、剪贴板粘贴
- Canvas mask 编辑器
- 同步/异步 Job
- 结果预览和 Lightbox
- Lightbox 上一张/下一张
- 历史搜索
- 画廊、缩略图和收藏
- 多选、批量收藏、批量删除
- ZIP 结果导出和备份导出

## 历史、画廊和备份

任务索引：

```text
/var/minis/workspace/gpt-image-playground/tasks.sqlite3
```

旧版 `history.jsonl` 会在搜索时迁移。图片使用 SHA-256 索引，缩略图缓存于图片目录 `.thumbs/`。

备份导出：

```http
POST /v1/backup/export
```

备份包含：

```text
manifest.json
images/
任务历史
图片索引
收藏状态
```

安全恢复：

```http
POST /v1/backup/import
```

```json
{
  "path": "/var/minis/workspace/gpt-image-playground/backup.zip",
  "apply": true,
  "conflict": "skip"
}
```

`conflict` 可选：

```text
fail     遇到已有任务/图片立即失败
skip     保留现有内容并跳过冲突
replace  用备份内容替换
```

恢复使用 staging、路径校验和失败文件回滚，不直接覆盖原数据库。

## Agent

Agent 受控工具：

```text
generate_image
generate_image_batch
continue_generation
```

支持：

- 最多 8 轮
- 批量并发
- 图片引用
- session 保存/恢复
- branch fork
- 指定轮次重生成请求
- 网络类错误重试
- 单个工具失败隔离

## 安全约束

- API Key 只来自环境变量或权限 `600` 本地配置
- 不上传 `connection.json`
- 不把 Key 写入任务、历史、响应或前端存储
- API 默认监听 localhost
- 远程监听必须 Bearer Token
- 图片路径限制在 `/var/minis/attachments`、`workspace`、`mounts`
- 拒绝远程图片 URL，防止 SSRF
- ZIP 拒绝绝对路径和路径穿越
- 删除默认只删除索引，物理文件删除必须显式指定

## 测试

```sh
python3 -m compileall -q .
python3 tests/test_api.py
python3 scripts/playground.py --validate-profiles
python3 scripts/playground.py --prompt "test" --dry-run
python3 scripts/agent.py --prompt "test" --dry-run
```

GitHub Actions 会执行 Python 编译、API 测试、CLI Dry Run 和 Agent Dry Run。

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

当前版本：`2.0.3`。

## v1.9

- 备份恢复冲突策略：`fail`、`skip`、`replace`
- `apply: true` 恢复失败时删除本次复制文件并终止，不覆盖原有任务
- Agent 指定轮次重生成：`--round-index N`
- Web 画廊多选、批量收藏/删除和 Lightbox 导航

## v2.0 稳定版契约

- API 版本：`2.0.0`，兼容 v1 客户端
- `GET /v1/version` 返回 `min_client_version` 与兼容范围
- API 错误统一为 `{ "error": { "code": "...", "message": "...", "details": {} } }`
- OpenAPI 提供版本、生成、批量、Agent、Job、画廊、备份、图片和配置接口
- 发布前执行编译、API、CLI、Agent、Provider、敏感扫描和 Git 工作区检查

## 原生接口模型模式

部分 OpenAI-compatible 图片接口会在服务端选择默认图片模型，要求请求体**不包含** `model` 字段。此时不要把模型设置为空字符串；使用：

Profile：

```json
{
  "id": "native-images",
  "provider": "openai-compatible",
  "endpoint": "https://api.example.com/v1/images/generations",
  "model": "gpt-image-2",
  "omit_model": true
}
```

CLI：

```sh
python3 scripts/playground.py \
  --profile native-images \
  --omit-model \
  --prompt "一只橘猫头像"
```

任务 JSON 或 REST：

```json
{
  "prompt": "一只橘猫头像",
  "omit_model": true
}
```

`omit_model: true` 的行为是：

```text
任务内部 model = null
最终 HTTP JSON 不包含 model
```

默认值仍为 `false`，标准 OpenAI-compatible 接口继续发送 Profile 中的模型名。Dry Run 会检查最终请求文件，确认 `model` 是否真正省略。

## Provider 能力配置建议

原库的能力边界值得在本技能中显式区分：

- Images API：单图、批量、参考图、遮罩、透明背景参数取决于接口
- Responses API：Agent、多轮上下文、图片工具取决于 Agent endpoint
- fal.ai：通常是队列提交与轮询，不假设支持 Images API 的全部参数
- 自定义 Provider：通过 `customProviders` 声明同步/异步提交、轮询、结果路径和参数映射
- 原生默认模型接口：使用 `omit_model: true`，不要伪造模型名

建议每个 Profile 增加能力声明：

```json
{
  "capabilities": {
    "model_optional": true,
    "supports_images_api": true,
    "supports_responses": false,
    "supports_transparent_background": false,
    "supports_streaming": false
  }
}
```

能力声明用于 UI 提示和请求前校验，不会把 API Key 写入任务或请求日志。
