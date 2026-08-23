# GPT Image Playground Skill

一个面向其他 AI 工具的图片生成编排技能。它不是单纯的 React 图片应用，而是把 CLI、REST、OpenAPI、Responses Agent、Web 工作台和多个图片 Provider 统一成可调用的技能接口。

```text
Claude / Codex / Gemini / 自定义 Agent / CLI / Web
                         ↓
              gpt-image-playground skill
                         ↓
 Images API / Responses API / fal.ai / Custom Provider
```

当前版本：`2.3.0`

## 适用场景

- 文生图、参考图、多图融合、遮罩编辑
- 批量生成、并发、失败隔离、网络重试
- OpenAI Images API、Responses 图片 API、fal.ai、自定义 Provider
- Responses Agent 多轮图片规划
- 提供给其他 AI 工具的本地 REST/OpenAPI 图片服务
- 任务历史、SQLite 索引、画廊、收藏、缩略图
- 结果 ZIP、完整备份、备份恢复

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
默认模型：Profile.model
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
任务 model > CLI --model > Profile.model
```

`omit_model` 只用于明确要求不发送模型字段的接口。它不能和显式模型同时指定。自定义模型 ID 允许使用，但必须是安全的单行模型标识；请求前会拒绝空格、控制字符和超长值。
