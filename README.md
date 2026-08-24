# GPT Image Playground

> 图片生成与编辑编排技能：CLI、REST/OpenAPI、Responses Agent、Web 工作台和多种 Provider 的统一入口。

**当前版本：`2.7.2`** · Python-only runtime · 不需要 Node.js/npm

## 目录

- [适用场景](#适用场景)
- [安装](#安装)
- [5 分钟运行](#5-分钟运行)
- [选择入口](#选择入口)
- [图片生成与编辑](#图片生成与编辑)
- [批量、幂等与异步 Job](#批量幂等与异步-job)
- [Agent](#agent)
- [Provider 与 Profile](#provider-与-profile)
- [REST API](#rest-api)
- [Web 工作台](#web-工作台)
- [配置与安全](#配置与安全)
- [验证、排错与发布](#验证排错与发布)

## 适用场景

| 目标 | 推荐入口 |
|---|---|
| 单图生成、参考图、遮罩编辑 | `scripts/playground.py` |
| 多个不同提示词 | `scripts/playground.py --batch` 或 `POST /v1/batch` |
| 多轮规划、连续创作、工具调用 | `scripts/agent.py` |
| 给其他 Agent/程序调用 | `scripts/skill.py` 或 REST/OpenAPI |
| 人工生成、画廊、历史、设置 | Web 工作台 |

支持：Native/Script/Auto 执行模式、OpenAI-compatible Images/Responses、fal.ai Queue、声明式 Custom Provider、异步 Job、SSE、历史、SQLite 画廊、收藏、缩略图和备份。

## 安装

### 公开仓库

```sh
curl -fsSL https://raw.githubusercontent.com/joeshu/gpt-image-playground/main/scripts/install.py \
  -o /tmp/install-gpt-image-playground.py
python3 /tmp/install-gpt-image-playground.py \
  --target "$HOME/.skills/gpt-image-playground"
cd "$HOME/.skills/gpt-image-playground"
python3 scripts/skill.py check
```

私有仓库需要在当前 shell 中提供有读取权限的 `GITHUB_TOKEN`。不要把 Token 写进脚本、配置或提交记录。

### 从源码运行

```sh
git clone https://github.com/joeshu/gpt-image-playground.git
cd gpt-image-playground
python3 scripts/skill.py check
```

### 运行时打包

```sh
python3 scripts/package_runtime.py
```

打包结果只包含运行所需后端、配置和轻量 Web 文件，不包含测试、Git、缓存或生成产物。

## 5 分钟运行

### 1. 检查环境

```sh
python3 scripts/skill.py check
python3 scripts/skill.py doctor
python3 scripts/playground.py --validate-profiles
```

### 2. 配置连接

推荐使用环境变量：

```sh
export GPT_IMAGE_ENDPOINT="https://api.example.com/v1/images/generations"
export GPT_IMAGE_API_KEY="..."
```

也可以使用交互式配置：

```sh
python3 scripts/playground.py --setup
```

连接文件默认保存于运行数据目录，权限为 `600`。真实 Key 不应写入仓库。

### 3. 先 Dry Run，再真实调用

```sh
python3 scripts/playground.py \
  --profile default \
  --prompt "极简产品海报，暖色纸张质感，大面积留白" \
  --size 4:5 \
  --quality medium \
  --dry-run
```

确认请求参数后，去掉 `--dry-run` 执行真实请求：

```sh
python3 scripts/playground.py \
  --profile default \
  --prompt "极简产品海报，暖色纸张质感，大面积留白" \
  --size 4:5 \
  --quality medium
```

成功时读取 JSON stdout 的 `saved_images`、`actual_params` 和 `timing`。

## 选择入口

### 统一入口

```sh
python3 scripts/skill.py check
python3 scripts/skill.py generate --profile default --prompt "红色咖啡杯产品图"
python3 scripts/skill.py agent --profile default --prompt "设计角色并生成三张场景图"
python3 scripts/skill.py serve --host 127.0.0.1 --port 8765
```

### CLI 图片生成

```sh
python3 scripts/playground.py \
  --profile default \
  --prompt "雨夜霓虹城市电影海报" \
  --size 16:9 \
  --quality high \
  --n 2 \
  --execution-mode auto
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--profile` | 选择 Profile |
| `--prompt` | 文生图提示词 |
| `--image` | 参考图，可重复 |
| `--mask` | 局部编辑遮罩 |
| `--size` | 比例或尺寸，如 `1:1`、`16:9` |
| `--quality` | `low`、`medium`、`high` |
| `--n` | 同提示词生成数量 |
| `--execution-mode` | `auto`、`native`、`script` |
| `--api-mode` | `images`、`responses` |
| `--stream` | 启用支持的流式响应 |
| `--dry-run` | 只生成请求计划，不调用 Provider |

### 编辑与遮罩

```sh
python3 scripts/playground.py \
  --prompt "把背景改成浅蓝色，保留主体材质" \
  --image ./source.png \
  --mask ./mask.png \
  --execution-mode native
```

Native 模式带参考图或遮罩时，会自动使用 multipart，并把 `/images/generations` 切换为 `/images/edits`。本地 REST 输入图片必须位于允许目录；远程 URL 默认拒绝。

## 批量、幂等与异步 Job

### CLI 批量

```sh
python3 scripts/playground.py \
  --batch ./tasks.json \
  --concurrency 4 \
  --execution-mode auto
```

批量结果包含：

```text
batch_id
batch_item_id
status
succeeded
failed
reused
retried
retry_of
```

部分失败重试只执行失败子项；成功子项复用，不重复生成。

### REST 幂等重试

对 `/v1/generate`、`/v1/batch`、`/v1/agent` 使用稳定的 Header：

```sh
curl -X POST http://127.0.0.1:8765/v1/generate \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: poster-2027-001' \
  -d '{"prompt":"极简产品海报","execution_mode":"auto"}'
```

也可以在 JSON 中传：

```json
{"request_id":"poster-2027-001","prompt":"极简产品海报"}
```

重复请求直接返回第一次结果，不重复调用 Provider。默认保留 24 小时，可用 `GPT_PLAYGROUND_IDEMPOTENCY_TTL` 调整。

### 异步 Job

```sh
curl -X POST http://127.0.0.1:8765/v1/batch \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: batch-001' \
  -d '{"batch_id":"batch-001","async":true,"tasks":[{"prompt":"蓝色海报"},{"prompt":"红色海报"}]}'
```

返回 `job_id` 后：

```sh
curl http://127.0.0.1:8765/v1/jobs/JOB_ID
curl -N http://127.0.0.1:8765/v1/jobs/JOB_ID/events
```

批量 Job 状态包含 `parent_task_id`、`batch_id` 和 `total`。事件包含 `job_id`、`event_id`；最终结果可能重复持久化事件，这是正常行为。

## Agent

### 基本调用

```sh
python3 scripts/agent.py \
  --profile default \
  --prompt "先设计一个角色，再生成三张不同场景图" \
  --execution-mode native
```

### 流式事件

```sh
python3 scripts/agent.py \
  --profile default \
  --prompt "生成一组产品视觉" \
  --stream
```

Agent 支持：

- 多轮 Responses 编排和图片生成工具；
- Native 模式直接使用 Provider 原生图片能力；
- `script`/`auto` 混合本地 `generate_image` 工具；
- 稳定图片 ID 和提示词中的 `<ref id="..." />`；
- 会话恢复、分支和 pending tool call 恢复；
- `tool_call_id` 缓存，恢复时只执行未完成调用；
- JSONL `events_file` 和 REST Job SSE。

## Provider 与 Profile

Profile 位于 `profiles.json`。选择规则：

```text
provider=openai-compatible, api_mode=images  -> Native Images
api_mode=responses                          -> Responses Provider
provider=fal                                -> fal.ai Queue
自定义 provider id                          -> Custom adapter
```

执行模式：

| 模式 | 行为 |
|---|---|
| `auto` | 优先 Native；仅对可恢复的 Provider/网络错误回退 Script |
| `native` | 强制 Native；失败不回退 |
| `script` | 强制本地 Script Provider |

结果中的 `execution_mode`、`provider`、`fallback_from`、`fallback_reason` 代表实际路径。配置错误、非法输入和明确不支持不会盲目回退。

自定义 Provider 示例：

```text
profiles.custom.sync.example.json
profiles.custom.async.example.json
```

## REST API

启动：

```sh
python3 scripts/api_server.py --host 127.0.0.1 --port 8765
```

主要路由：

```text
GET  /healthz
GET  /openapi.json
GET  /v1/profiles
GET  /v1/models
POST /v1/generate
POST /v1/batch
POST /v1/agent
GET  /v1/jobs/{id}
GET  /v1/jobs/{id}/events
GET  /v1/history
GET  /v1/gallery
POST /v1/backup/export
POST /v1/backup/import
```

结构化错误示例：

```json
{
  "error": {
    "code": "native_request_failed",
    "message": "Native 请求失败",
    "details": {
      "mode": "auto",
      "retryable": true,
      "fallback_available": true
    }
  }
}
```

外部监听前必须设置：

```sh
export GPT_PLAYGROUND_API_TOKEN="..."
```

## Web 工作台

```sh
python3 scripts/skill.py serve --host 127.0.0.1 --port 8765
```

Web 支持：

- 单图、批量、Agent 模式；
- 参考图拖放和遮罩编辑；
- Native/Script/Auto 选择；
- 异步 Job 状态和 SSE；
- 批量成功/失败/失败子项摘要；
- request_id、执行模式、回退原因和结构化错误；
- 历史、画廊、收藏、批量删除、备份恢复。

## 配置与运行目录

常用环境变量：

```text
GPT_IMAGE_ENDPOINT
GPT_IMAGE_API_KEY
GPT_AGENT_ENDPOINT
FAL_KEY
GPT_PLAYGROUND_API_TOKEN
GPT_IMAGE_PLAYGROUND_ROOT
GPT_IMAGE_PLAYGROUND_DATA
GPT_IMAGE_PLAYGROUND_ATTACHMENTS
GPT_IMAGE_PLAYGROUND_INPUT_ROOT
GPT_PLAYGROUND_IDEMPOTENCY_TTL
```

默认运行数据：

```text
输出图片：outputs/gpt-image-playground/
连接、Job、历史：.monkeycode/runtime/gpt-image-playground/
```

可用 `GPT_IMAGE_PLAYGROUND_DATA` 和 `GPT_IMAGE_PLAYGROUND_ATTACHMENTS` 覆盖。推荐把外部数据放在仓库之外。

## 安全要求

- API Key 只放环境变量或本地 `600` 权限连接文件。
- 不把 Key 写入任务、历史、日志、API 响应、浏览器存储或 Git。
- REST 默认拒绝远程输入图片 URL；只接受允许目录内的本地图片。
- ZIP 恢复经过路径校验和 staging；物理删除图片必须显式请求。
- 对外绑定 API 前启用 `GPT_PLAYGROUND_API_TOKEN`，并使用 HTTPS 反向代理。
- 提供日志前检查 `request`、`response`、环境变量和图片 Data URL，确认没有敏感信息。

## 验证与排错

```sh
python3 scripts/skill.py check
python3 scripts/skill.py doctor
python3 scripts/playground.py --validate-profiles
python3 scripts/playground.py --prompt "test" --dry-run
python3 scripts/agent.py --prompt "test" --dry-run
python3 -m py_compile scripts/*.py tests/*.py
python3 tests/test_api.py
python3 tests/test_providers.py
git diff --check
```

排错顺序：

1. 看退出码和 stdout JSON；
2. 读取 `error.code`、`error.message`、`error.details`；
3. 检查 Profile、endpoint、Key、模型和输入路径；
4. 检查 Native/Script/Auto 实际执行字段；
5. 再看 request/response 文件和 `events_file`；
6. 配置错误和非法输入不要重复重试，网络类错误才考虑 `auto` 回退。

## 开发与发布

修改后至少运行：

```sh
python3 -m py_compile scripts/*.py tests/*.py
python3 tests/test_api.py
python3 tests/test_providers.py
python3 tests/test_skill_matrix.py
python3 scripts/skill.py doctor
git diff --check
```

发布前：

1. 更新 `scripts/version.py`、`SKILL.md`、`README.md`；
2. 清理缓存、运行时请求、真实连接文件和生成产物；
3. 扫描敏感信息；
4. commit 并推送 `main`；
5. 创建并推送版本标签；
6. 复核远端提交和工作区干净。

## 许可证与仓库

源码仓库：<https://github.com/joeshu/gpt-image-playground>

技能入口：`SKILL.md`。Agent 先读 `SKILL.md`，人类用户和集成开发者再读本 README。
