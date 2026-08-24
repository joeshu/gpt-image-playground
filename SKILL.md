---
name: gpt-image-playground
description: 图片生成与编辑编排技能。支持文生图、参考图、遮罩、批量任务、OpenAI Images/Responses、fal.ai、自定义 Provider、Responses Agent、REST/OpenAPI 和异步 Job。当用户需要生成、编辑、批量处理图片，或需要图片 Provider、Agent、API 能力时使用。
version: 2.7.0
---

# GPT Image Playground

## Skill Contract

本文件是唯一权威技能入口。支持 Skill.md 规范的 Agent 应先读取本文件，再调用项目脚本。完整使用说明、参数表和案例位于 `README.md`。

## Capabilities

- Text-to-image and image editing
- Reference images and mask editing
- Batch generation with concurrency and failure isolation
- OpenAI-compatible Images API
- Images API supports `execution_mode=auto`, `native` and `script`
- OpenAI Responses API with Agent orchestration and optional SSE streaming
- Agent native mode uses the provider's native image-generation capability directly; mixed mode uses local `generate_image` tools
- Agent supports stable image IDs, prompt-embedded `<ref id="..." />` references, branch-safe session state and streamed text events
- fal.ai queue provider
- Declarative synchronous and asynchronous custom providers
- Local history, SQLite gallery, favorites, thumbnails and backups
- REST/OpenAPI service with asynchronous Jobs and SSE events

## Installation for Other Agents

`SKILL.md` is the capability contract; it is not itself an installer. An Agent should install the prebuilt runtime from the private repository with Python only:

```sh
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" https://raw.githubusercontent.com/joeshu/gpt-image-playground/main/scripts/install.py -o /tmp/install-gpt-image-playground.py
GITHUB_TOKEN="$GITHUB_TOKEN" python3 /tmp/install-gpt-image-playground.py --target "$HOME/.skills/gpt-image-playground"
cd "$HOME/.skills/gpt-image-playground" && python3 scripts/skill.py check
```

For a private repository, `GITHUB_TOKEN` must have repository read access. The installer verifies `SKILL.md`, `scripts/skill.py` and the prebuilt `web-react/dist/index.html`, removes development-only files, and never installs Node.js/npm. After installation, start the Web UI with `python3 scripts/skill.py serve`.

## Entry Points

Run commands from the skill root:

```sh
python3 scripts/skill.py check
python3 scripts/playground.py --prompt "<prompt>"
python3 scripts/agent.py --prompt "<prompt>"
python3 scripts/agent.py --execution-mode native --prompt "<prompt>"
python3 scripts/agent.py --stream --prompt "<prompt>"
python3 scripts/api_server.py --host 127.0.0.1 --port 8765
```

Use `--dry-run` for validation without calling a provider:

```sh
python3 scripts/playground.py --prompt "test" --dry-run
python3 scripts/agent.py --prompt "test" --dry-run
```

## Agent Protocol

- Read JSON from command stdout.
- Treat a zero exit code as a successful command execution.
- Read `saved_images` for image generation results.
- Read `requested_params`, `actual_params`, `attempts` and `timing` for normalized execution diagnostics.
- Read `images` for Agent results.
- Read `events_file` for JSONL Agent round and tool-call lifecycle events.
- For asynchronous `/v1/agent` jobs, consume the same lifecycle events from `/v1/jobs/{id}/events`; each event includes `job_id` and `event_id`.
- Agent Job SSE events are emitted while the subprocess is running; the final response may repeat persisted events for completeness.
- Resuming a session replays persisted `pending_tool_calls` before requesting another model round, preventing an interrupted tool execution from being silently skipped.
- Completed Agent tools are cached by `tool_call_id`; recovery reuses their results and executes only remaining calls.
- Agent defaults to `--execution-mode native`, sends the native image-generation tool, and does not register local `generate_image` tools. `script` and `auto` retain mixed orchestration.
- Read `job_id` for asynchronous REST jobs.
- For batch results, use `batch_id` and each result's `batch_item_id` as stable retry and deduplication keys.
- Retrying a partial batch reuses successful results and executes failed items only; results expose `reused`, `retried` and `retry_of`.
- Read `error`, `error_code` and the non-zero exit code for failures.
- Use `README.md` for complete examples and `GET /openapi.json` for REST schemas.

## Providers

Provider selection uses Profile configuration:

```text
provider=openai-compatible, api_mode=images  -> Images API
api_mode=responses                          -> Responses API
provider=fal                                -> fal.ai queue
custom provider id                          -> custom adapter
```

Profiles are stored in `profiles.json`. Custom provider examples are stored in `profiles.custom.sync.example.json` and `profiles.custom.async.example.json`.

## Configuration

Supported user-project environment variables:

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
```

The local connection file is created by `--setup`, uses permission `600`, and stores user-provided credentials outside the repository.

## REST Contract

The local server listens on `127.0.0.1` by default. Main routes:

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

Set `GPT_PLAYGROUND_API_TOKEN` before binding to a non-localhost address. Use `/v1/jobs/{id}/events` for SSE progress events.

## Safety Contract

- API keys come from user-project environment variables or the local `600` permission connection file.
- Keys are excluded from tasks, history, logs, API responses and browser storage.
- Remote image URLs are rejected by the REST input validator.
- Local image paths must belong to an allowed attachment, data, skill or explicitly configured input directory.
- ZIP restore validates archive paths and uses staging before applying changes.
- Physical image deletion requires an explicit request.

## Verification

```sh
python3 scripts/skill.py check
python3 scripts/playground.py --validate-profiles
python3 scripts/playground.py --prompt "test" --dry-run
python3 scripts/agent.py --prompt "test" --dry-run
python3 -m py_compile scripts/*.py tests/*.py
python3 tests/test_api.py
python3 tests/test_providers.py
```
