# GPT Image Playground

一个可移植的 GPT Image 图片生成编排技能。

它把图片生成拆成四层：

```text
CLI / Web 工作台 / 其他 AI 工具
                ↓
        REST API / Responses Agent
                ↓
       gpt-image-playground 编排器
                ↓
 gpt-image-tool / OpenAI-compatible / 自定义 Provider
```

项目适合在 Minis、iSH、普通 Linux 或服务器环境中运行。底层执行器使用 Python 标准库和已有的 `gpt-image-tool`；Web API 使用 Python 标准库，不依赖 React、Node 或第三方 Web 框架。

## 特性

- 文生图、单图编辑、多参考图融合
- 遮罩编辑与本地透明背景后处理
- 批量任务、并发、失败隔离、网络错误重试
- OpenAI-compatible、声明式同步 Provider、异步 task_id Provider
- Responses Agent 多轮工具调用
- 本地 REST API 与 OpenAPI 3.0.3
- 异步 Job、状态持久化、服务重启恢复
- 单页 Web 工作台
- 图片预览、ZIP 导出、历史查询
- 首次使用配置向导
- API Key 本地权限 600 保存，且不进入任务、日志、响应或浏览器 localStorage
- 远程监听必须配置 Bearer Token
- API 图片输入限制在白名单目录，拒绝远程图片 URL，降低 SSRF 风险

## 快速开始

### 1. 准备底层执行器

本技能默认调用：

```text
/var/minis/skills/gpt-image-tool/scripts/generate.py
```

在其他 Linux 环境中，可将该路径改为兼容的图片执行器，或调整 `scripts/playground.py` 中的 `LOWER` 配置。

### 2. 首次配置

没有环境变量时，交互式填写：

```sh
python3 scripts/playground.py --setup
```

也可以导入 JSON：

```sh
python3 scripts/playground.py --setup-json connection.example.json
```

真实配置保存到：

```text
/var/minis/workspace/gpt-image-playground/connection.json
```

文件权限为 `600`。仓库中的 `connection.example.json` 只有占位内容，不能直接作为生产密钥文件提交。

检查配置：

```sh
python3 scripts/playground.py --connection-status
```

服务器部署或 CI 可以使用环境变量：

```text
GPT_IMAGE_ENDPOINT
GPT_IMAGE_API_KEY
```

环境变量优先于本地配置。

### 3. CLI 生成

```sh
python3 scripts/playground.py \
  --profile aiwanwu \
  --prompt '电影感的雪山湖泊' \
  --style cinematic \
  --size 16:9
```

Dry Run：

```sh
python3 scripts/playground.py \
  --prompt '测试任务' \
  --profile aiwanwu \
  --dry-run
```

### 4. 启动 Web 工作台

```sh
python3 scripts/api_server.py --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765/
```

首次未配置时，页面会显示服务器地址和 API Key 表单。API Key 只提交到服务端，不保存到浏览器。

## REST API

完整接口定义：

```http
GET /openapi.json
```

主要接口：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/healthz` | 健康检查 |
| GET | `/v1/setup/status` | 脱敏配置状态 |
| POST | `/v1/setup` | 首次保存服务器和 API Key |
| GET | `/v1/profiles` | 脱敏 Profile 列表 |
| GET | `/v1/history` | 历史任务 |
| POST | `/v1/generate` | 单图生成 |
| POST | `/v1/batch` | 批量生成 |
| POST | `/v1/agent` | Agent 任务 |
| GET | `/v1/jobs/{job_id}` | Job 状态 |
| GET | `/v1/files` | 受控图片读取 |
| POST | `/v1/export-zip` | 导出结果 ZIP |
| GET | `/v1/download-zip` | 下载 ZIP |

首次配置：

```sh
curl -X POST http://127.0.0.1:8765/v1/setup \
  -H 'Content-Type: application/json' \
  -d '{"endpoint":"https://api.example.com/v1/images/generations","api_key":"首次填写","model":"gpt-image-2"}'
```

生成任务：

```sh
curl -X POST http://127.0.0.1:8765/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"一张电影海报","profile":"default","async":true}'
```

异步请求返回 `202` 和 `job_id`，使用 `/v1/jobs/{job_id}` 轮询。

如果服务监听非 localhost 地址，必须设置：

```text
GPT_PLAYGROUND_API_TOKEN
```

客户端发送：

```http
Authorization: Bearer <token>
```

## Agent

```sh
python3 scripts/agent.py \
  --profile aiwanwu \
  --prompt '先生成角色设定，再生成三张不同场景图'
```

支持工具：

- `generate_image`
- `generate_image_batch`
- `continue_generation`

支持会话保存、恢复、图片引用、批量失败隔离和请求重试。

## 自定义 Provider

示例：

```text
profiles.custom.sync.example.json
profiles.custom.async.example.json
```

支持：

- JSON 请求
- multipart 请求
- 输入图片和 mask
- Base64 或 URL 图片响应
- 异步 task_id
- 状态轮询
- 响应路径映射

验证配置：

```sh
python3 scripts/playground.py --validate-profiles
```

## 测试

运行 API 和连接配置测试：

```sh
python3 tests/test_api.py
```

运行 Python 编译检查：

```sh
python3 -m compileall -q scripts tests
```

项目还包含用于 Provider 和 Agent 的 Mock 服务，位于开发工作副本中；生产仓库不依赖外部 API 才能运行 Dry Run 和基础测试。

## 目录结构

```text
.
├── SKILL.md
├── README.md
├── connection.example.json
├── profiles.json
├── presets.json
├── scripts/
│   ├── agent.py
│   ├── api_server.py
│   ├── connection.py
│   ├── custom_provider.py
│   ├── image_ops.py
│   └── playground.py
├── tests/
│   └── test_api.py
└── web/
    └── index.html
```

## 安全约定

- 不把真实 API Key 写入 `profiles.json`、任务 JSON、Shell 参数或代码仓库
- 不提交 `connection.json`
- 不提交生成图片、历史响应、临时文件和 Python 缓存
- 远程监听必须启用 Bearer Token
- API 只接受白名单本地图片或浏览器 Data URL
- `/v1/setup/status` 只返回 endpoint、host、model 和配置来源，不返回 Key
- 生产环境建议使用环境变量或系统 Secret 管理器

## 许可证

本项目当前未指定开源许可证，默认按私有项目使用。仓库可见性由 GitHub 私有仓库设置控制。
