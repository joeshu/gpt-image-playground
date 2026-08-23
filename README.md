# GPT Image Playground v1.4

## 首次使用配置

首次没有环境变量时，运行：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --setup
```

或导入标准 JSON：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --setup-json /var/minis/skills/gpt-image-playground/connection.example.json
```

配置文件位于：

```text
/var/minis/workspace/gpt-image-playground/connection.json
```

权限为 `600`。API Key 不进入任务、日志、历史、OpenAPI 或浏览器 localStorage。

API 配置接口：

```text
GET  /v1/setup/status
POST /v1/setup
GET  /openapi.json
```


## 本地 REST API

启动：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/api_server.py \
  --host 127.0.0.1 --port 8765
```

同步生成：

```sh
curl -X POST http://127.0.0.1:8765/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"电影海报","profile":"aiwanwu","dry_run":true}'
```

异步 Job：

```sh
curl -X POST http://127.0.0.1:8765/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"长任务","profile":"aiwanwu","async":true}'

curl http://127.0.0.1:8765/v1/jobs/<job-id>
```

接口还提供 `/healthz`、`/v1/profiles`、`/v1/history`、`/v1/batch` 和 `/v1/agent`。默认只绑定 localhost；设置 `GPT_PLAYGROUND_API_TOKEN` 后启用 Bearer Token 鉴权。API 不接受客户端传入密钥或 endpoint，图片路径限制在 Minis 共享目录。


## Responses Agent

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py \
  --profile aiwanwu \
  --prompt '生成一张角色设定图，再基于它生成三张场景图'
```

Agent 通过 Responses API 规划，调用 `generate_image`、`generate_image_batch` 和 `continue_generation`，实际图片生成仍回到主 Playground 执行器。最多 8 轮、每批最多 16 张、批量最多 4 路并发。

Responses endpoint 优先级：`--endpoint` → `GPT_AGENT_ENDPOINT` → Profile `agent_endpoint` → Profile `baseUrl/responses`。

Dry-run 不需要 API Key：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py \
  --profile aiwanwu --prompt '生成电影海报' --dry-run
```

Agent 记录保存在 `/var/minis/workspace/gpt-image-playground/agent-history.jsonl`。

查询 Agent 历史：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py --history-list --history-limit 20
python3 /var/minis/skills/gpt-image-playground/scripts/agent.py --history-get <conversation-id>
```

Agent 请求可使用 `--agent-retry 2` 重试网络错误、超时、429 和 5xx。批量工具采用失败隔离，单个失败不会影响其他结果；图片引用支持已生成图片 ID、`ref:id` 和 `<ref id="..." />`。


## Web 工作台

启动 API 后打开 `http://127.0.0.1:8765/`：

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/api_server.py \
  --host 127.0.0.1 --port 8765
```

支持单图、批量、Agent、参考图、遮罩、异步 Job、结果预览和历史列表。浏览器上传图片不会写入 API 请求日志，服务端临时文件执行后自动删除。



## 常用命令

```sh
# 文生图
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --prompt '电影感的雪山湖泊' --style cinematic --size 16:9

# 批量生成
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --batch /var/minis/skills/gpt-image-playground/tasks.batch.sample.json \
  --concurrency 2 --retry 1

# 遮罩编辑
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py \
  --prompt '只修改选区中的物体' --image source.png --mask mask.png
```

## Profile 管理

```sh
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --validate-profiles
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --test-profile aiwanwu
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --export-profiles backup.json
python3 /var/minis/skills/gpt-image-playground/scripts/playground.py --import-profiles profiles.json --merge-profiles
```

`--test-profile` 只做 HEAD 连通性探测，不发起图片生成。Profile 不保存 API Key，密钥只从 `api_key_env` 指定的环境变量读取。

## 自定义供应商

- `profiles.custom.sync.example.json`：同步 JSON、multipart 编辑和遮罩
- `profiles.custom.async.example.json`：异步 task ID、状态轮询、URL/Base64 结果映射
- `scripts/custom_provider.py`：声明式 Provider 执行器

支持模板变量：`$prompt`、`$profile.model`、`$params.*`、`$inputImages.dataUrls`、`$mask.dataUrl`。

## 产物

- 图片：`/var/minis/attachments/gpt-image-playground/`
- 任务、响应、诊断：`/var/minis/workspace/gpt-image-playground/`
- 历史：`/var/minis/workspace/gpt-image-playground/history.jsonl`

不要把 API Key 写入 Profile、任务 JSON、Shell 参数或对话。

## v1.2 新增

- 多 Profile 独立连接和 Secret
- Images / Responses 双 API 模式
- fal.ai Queue Provider
- Job SSE 事件流
- 实际参数和 revised prompt 摘要
- GitHub Actions 自动测试

## v1.3 Web 与历史增强

- Canvas 遮罩编辑器
- 参考图拖拽和剪贴板粘贴
- SQLite 任务索引和历史搜索
- Agent session 分支元数据

历史搜索示例：

```text
GET /v1/history?q=海报&status=completed&profile=default
```

## v1.4 画廊、收藏与备份

新增图片 SHA-256 索引、画廊 API、收藏接口、manifest 完整备份 ZIP，以及 Web 历史搜索和画廊入口。图片索引与任务索引共用 `workspace/gpt-image-playground/tasks.sqlite3`，不会写入技能仓库。
