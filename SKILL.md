---
name: gpt-image-playground
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

从 `python3 scripts/skill.py check` 的 JSON 输出读取版本；不要依赖 frontmatter 维护版本号。

不确定参数或首次接入时，先用 `--dry-run`；不要在没有用户授权时调用真实 Provider。

## 标准执行流程

1. **CHECK**：运行 `check`、`doctor` 和 `--validate-profiles`；确认 Profile、endpoint、model 和输入路径。
2. **PLAN**：根据任务选择 CLI、Agent、REST 或 Web；需要真实调用时先说明预计请求数量和可能费用。
3. **DRY RUN**：先验证参数、执行模式、参考图/遮罩和最终请求文件；确认透明背景等高级能力不能只靠模型名推断。
4. **EXECUTE**：得到授权后执行真实请求；默认单张、低质量、低并发，读取 JSON stdout。
5. **VERIFY**：检查 `status`、`saved_images`/`images`、文件格式、尺寸、实际 Provider、耗时和错误字段。
6. **REPORT**：汇报结果、实际执行路径、失败原因和产物；不输出 API Key 或未脱敏请求体。

🔴 **CHECKPOINT · STOP**：以下动作必须暂停并取得用户确认：真实生图、批量/高质量请求、切换收费 endpoint、对外监听 API、发送或覆盖用户图片、删除数据。`--dry-run`、本地 fixture 和自动化回归不需要额外确认。

测试提示词和预期结果见 `test-prompts.json`；测试案例和门禁见 `TEST_CASES.md`。

## 能力边界

- 图片生成：单张、同提示词多张、批量不同提示词。
- 图片编辑：参考图、局部遮罩；Native 模式自动切换 `/images/edits` multipart。
- 执行策略：`auto`（优先 Native，符合条件时回退 Script）、`native`、`script`。
- Provider：OpenAI-compatible Images、Responses、fal.ai Queue、声明式 Custom Provider。
- Agent：多轮规划、工具调用、会话恢复、分支、稳定图片 ID、`<ref id="..." />` 引用、SSE/JSONL 事件。
- 服务：REST/OpenAPI、异步 Job、Job SSE、历史、SQLite 画廊、收藏、缩略图和备份。

### 能力声明与实际网关能力

`OpenAI-compatible` 只表示请求协议兼容，不表示每个网关实现了上游模型的全部能力。能力判断必须同时看：

1. Profile 的 `endpoint`、`model` 和 `provider`；
2. `GET /v1/capabilities` 的声明；其中 `available` 是代码路径可用，不代表网关已验证，`unknown` 必须探测；
3. 一次低成本 Dry Run 或真实探测请求的实际响应。

能力字段包括 `reference_images`、`mask_alpha`、`transparent_background`、`stream` 和 `formats`；Provider-sensitive 字段可能为 `unknown`，不得按 `true` 处理。

特别是透明背景：官方 GPT Image 文档说明 `gpt-image-2` 支持 `background=transparent`（preview，输出使用 PNG/WebP）；但当前 `api.geniuscoder.net` 网关的 `gpt-image-2` 实测拒绝该参数，返回 `invalid_value`。因此不要仅根据模型名推断透明背景可用。

遇到以下错误时，归类为 Provider 能力/参数拒绝，不要盲目重试或 Auto 回退：

```text
provider_request_rejected
invalid_value
Transparent background is not supported for this model.
```

若当前网关不支持透明背景：改用 `background=opaque/auto`，或切换到确认支持该能力的 endpoint；本地抠图只能作为非等价降级方案。

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

## 失败模式与处理矩阵

| 现象/错误 | 判断 | 动作 |
|---|---|---|
| endpoint、API Key、Profile 缺失 | 配置错误 | 停止；修复配置，不重试 |
| 本地图片不存在、路径不在白名单、mask 无 Alpha | 输入错误 | 停止；修复输入，不回退 |
| `provider_request_rejected`、`invalid_value`、模型不支持参数 | Provider 能力/参数拒绝 | 停止；切换 endpoint/model 或降级参数 |
| `native_request_failed`、TLS EOF、连接重置、超时 | 可恢复网络错误 | `auto` 有限重试/回退 Script；记录原因 |
| `invalid_response`、空图片结果 | Provider 响应错误 | 检查响应文件；有限重试，仍失败则停止 |
| Job 长时间 queued/running | 异步任务异常 | 查询 Job 和 SSE；超时后停止，不重复提交 |
| 幂等 Key 已命中 | 重复请求 | 返回原结果，不再次生成 |

## 反例与禁止操作

- **不要**把 `OpenAI-compatible` 当成完整能力保证；透明背景、stream、编辑和模型参数必须按 endpoint + model 实测。
- **不要**把 `provider_request_rejected` 当作网络故障重试或 Auto 回退。
- **不要**在未授权时执行真实生图、批量、高质量或多张请求。
- **不要**把 API Key 放进提示词、任务 JSON、URL、Git、浏览器 localStorage 或回复文本。
- **不要**把远程图片 URL、未验证的本地路径或无 Alpha mask 直接提交。CLI 默认拒绝远程输入；只有在信任来源且明确设置 `GPT_IMAGE_ALLOW_REMOTE_INPUTS=1` 时才允许下载。
- **不要**重复提交没有 `Idempotency-Key`/`request_id` 的可重试 REST 请求。
- **不要**在没有确认 Job 终态前重复提交异步任务。
- **不要**用成功的普通生成结果推断透明背景或编辑能力已经可用。

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
- `TEST_CASES.md`：多场景测试矩阵、自动化命令和当前测试结果。
- `test-prompts.json`：Darwin 典型测试提示词和预期结果。
- `DARWIN_REPORT.md`：本轮 Darwin 基线、改动和评审限制。
