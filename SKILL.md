---
name: gpt-image-playground
version: 2.7.1
description: "图片生成与编辑编排技能：支持文生图、参考图、遮罩、批量任务、Native/Script/Auto 双执行模式、OpenAI Images/Responses、fal.ai、自定义 Provider、Responses Agent、REST/OpenAPI、异步 Job 和 SSE。当用户要求生成、编辑、批量处理图片，或需要配置图片 Provider、调用 Agent/API、排查生成失败时使用。"
---

# GPT Image Playground

这是本技能的唯一 Agent 入口。读取本文件后，从技能根目录调用脚本；详细参数和长示例见 `README.md`。

## 先做什么

```sh
cd /path/to/gpt-image-playground
python3 scripts/skill.py check
python3 scripts/skill.py doctor
python3 scripts/playground.py --validate-profiles
```

不确定参数或首次接入时，先用 `--dry-run`；不要在没有用户授权时调用真实 Provider。

## 能力边界

- 图片生成：单张、同提示词多张、批量不同提示词。
- 图片编辑：参考图、局部遮罩；Native 模式自动切换 `/images/edits` multipart。
- 执行策略：`auto`（优先 Native，符合条件时回退 Script）、`native`、`script`。
- Provider：OpenAI-compatible Images、Responses、fal.ai Queue、声明式 Custom Provider。
- Agent：多轮规划、工具调用、会话恢复、分支、稳定图片 ID、`<ref id="..." />` 引用、SSE/JSONL 事件。
- 服务：REST/OpenAPI、异步 Job、Job SSE、历史、SQLite 画廊、收藏、缩略图和备份。

不要把本技能当作前端构建项目：运行时 Web 使用原生 HTML/CSS/JavaScript，不需要 Node.js/npm。

## 入口选择

| 需求 | 入口 |
|---|---|
| 生成、编辑、批量 | `python3 scripts/playground.py` |
| 多轮创作或 Agent 工具编排 | `python3 scripts/agent.py` |
| 统一 Agent/CLI 调用 | `python3 scripts/skill.py generate/agent` |
| 给其他程序提供 API | `python3 scripts/api_server.py` |
| 人工操作、历史和画廊 | `python3 scripts/skill.py serve` 后打开 Web |

通用入口示例：

```sh
python3 scripts/skill.py generate --profile default --prompt "极简产品海报"
python3 scripts/skill.py agent --profile default --prompt "设计角色并生成三张场景图"
python3 scripts/skill.py serve --host 127.0.0.1 --port 8765
```

## Agent 输出协议

脚本成功时读取 JSON stdout；零退出码才算成功。不要依赖人类日志文本。

- 生成结果：读取 `saved_images`、`requested_params`、`actual_params`、`attempts`、`timing`。
- Agent 结果：读取 `images`、`final_text`、`events_file`。
- 异步 REST：读取 `job_id`，轮询 `/v1/jobs/{id}`；实时进度消费 `/v1/jobs/{id}/events`。
- 批量：读取 `batch_id`、`batch_item_id`；部分失败时只重试失败项，关注 `reused`、`retried`、`retry_of`。
- 错误：读取结构化 `error.code`、`error.message`、`error.details.mode`、`retryable`、`fallback_available`，并检查退出码。

### 安全重试

对 `/v1/generate`、`/v1/batch`、`/v1/agent` 使用稳定的 `Idempotency-Key` Header，或在 JSON 中传 `request_id`：

```http
Idempotency-Key: poster-2027-001
```

重复请求返回第一次结果，不重复生成。幂等记录默认保留 24 小时，可用 `GPT_PLAYGROUND_IDEMPOTENCY_TTL` 调整。

## Provider 与模式

Profile 在 `profiles.json` 中定义连接和默认模型：

```text
provider=openai-compatible, api_mode=images  -> Images Provider
api_mode=responses                          -> Responses Provider
provider=fal                                -> fal.ai Queue
custom provider id                          -> Custom adapter
```

- `auto`：优先 Native；只有网络/Provider 类可恢复错误才回退 Script。
- `native`：强制 Native，失败不回退。
- `script`：强制本地 Script Provider。
- 结果中的 `execution_mode`、`provider`、`fallback_from`、`fallback_reason` 以实际执行路径为准。

## REST 最小契约

默认只监听本机：`127.0.0.1:8765`。主路由：

```text
GET  /healthz                         健康检查
GET  /openapi.json                    OpenAPI
GET  /v1/profiles                     Profile
GET  /v1/models                       模型目录
POST /v1/generate                     单任务
POST /v1/batch                        批量任务
POST /v1/agent                        Agent
GET  /v1/jobs/{id}                    Job 状态
GET  /v1/jobs/{id}/events             Job SSE
GET  /v1/history                      历史
GET  /v1/gallery                      画廊
POST /v1/backup/export                导出备份
POST /v1/backup/import                导入备份
```

异步批量提交可传 `batch_id`；Job 状态包含 `parent_task_id`、`batch_id`、`total`。非 localhost 监听前必须设置 `GPT_PLAYGROUND_API_TOKEN`。

## 配置与安全

常用环境变量：

```text
GPT_IMAGE_ENDPOINT              Images endpoint
GPT_IMAGE_API_KEY               Images API key
GPT_AGENT_ENDPOINT              Agent endpoint
FAL_KEY                         fal.ai key
GPT_PLAYGROUND_API_TOKEN        非本机 API 认证
GPT_IMAGE_PLAYGROUND_DATA       运行数据目录
GPT_IMAGE_PLAYGROUND_ATTACHMENTS 图片输出目录
GPT_IMAGE_PLAYGROUND_INPUT_ROOT 额外输入图片白名单目录
```

规则：

- Key 只来自环境变量或本地 `600` 权限连接文件；不写入任务、历史、日志、响应或浏览器存储。
- REST 默认拒绝远程图片 URL；本地图片必须位于允许目录。
- ZIP 恢复先校验并 staging；物理删除图片必须显式请求。
- 不要把真实 Key、连接文件、运行时产物或生成图片提交到 Git。

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
```

排错顺序：

1. 先看退出码和 JSON 的 `error`。
2. 再看 `error.code`、`details.retryable`、`fallback_available`。
3. 检查 Profile、endpoint、Key 环境变量和输入图片路径。
4. 检查 `*-request.json`、`*-response.json`、`events_file`；确认没有敏感值后再提供日志。
5. Native 网络类失败可用 `auto` 重试；配置错误、非法输入和强制 Native 失败不要盲目重试。

## 相关文件

- `README.md`：安装、配置、CLI/API 示例和完整说明。
- `profiles.json`：Profile 配置。
- `model_catalog.json`：模型目录。
- `scripts/skill.py`：统一入口、检查和 Web 服务。
- `scripts/playground.py`：图片生成、编辑、批量。
- `scripts/agent.py`：Responses Agent。
- `scripts/api_server.py`：REST/OpenAPI 服务。
