# GPT Image Playground 测试案例

版本：`2.7.1`

## 测试原则

本目录的测试默认不调用真实图片 Provider，不消耗额度，不需要 API Key。真实联网生成属于单独的人工验收，不纳入自动测试。

运行全部本地测试：

```sh
python3 -m py_compile scripts/*.py tests/*.py
python3 tests/test_api.py
python3 tests/test_providers.py
python3 tests/test_skill_matrix.py
python3 scripts/skill.py check
python3 scripts/skill.py doctor
```

## 场景矩阵

| ID | 维度 | 场景 | 方式 | 预期 |
|---|---|---|---|---|
| S01 | 安装 | 技能清单和版本 | `skill.py check` | ready，版本正确 |
| S02 | 健康 | Python、SQLite、Profile、Web 检查 | `skill.py doctor` | 所有检查通过 |
| S03 | 单图 | Native 文生图 | `playground.py --dry-run --execution-mode native` | 不联网，输出 Native 请求计划 |
| S04 | 单图 | Script 文生图 | `playground.py --dry-run --execution-mode script` | 不联网，输出 Script 执行计划 |
| S05 | 单图 | Auto 执行策略 | `playground.py --dry-run --execution-mode auto` | 保留 auto 请求策略 |
| S06 | 参数 | 比例、质量、数量归一化 | CLI dry-run | `requested_params` 正确 |
| S07 | 批量 | 多提示词批量 | `--batch tests/batch.fixture.json --dry-run` | 返回总数和子任务计划 |
| S08 | Agent | Native Agent | `agent.py --dry-run --execution-mode native` | 返回 dry_run |
| S09 | Agent | Script Agent | `agent.py --dry-run --execution-mode script` | 返回 dry_run |
| S10 | 输入安全 | 本地参考图和遮罩 | 本地临时图片 + REST validator | 合法白名单路径通过 |
| S11 | 输入安全 | 远程图片拒绝 | `validate_input_image(https://...)` | 抛出 ValueError |
| S12 | 编辑 | Native 参考图 + mask | Provider dry-run | multipart，端点切换到 `/images/edits` |
| S13 | 幂等 | 写入、读取安全请求键 | 临时 API 工作目录 | 同一 Key 可读取原结果 |
| S14 | 脱敏 | Data URL 脱敏 | `safe_json` | 不泄漏 base64 内容 |
| S15 | 脱敏 | 请求字段过滤 | `normalize_task` | 不保留 `api_key`、endpoint 等敏感字段 |
| S16 | Provider | Images/Responses/fal/Custom 路由 | `test_providers.py` | Provider 名称和模式正确 |
| S17 | 回退 | Auto Native 失败回退 Script | Provider fixture | 记录 `fallback_from` 和 `fallback_reason` |
| S18 | 强制模式 | Native 失败不回退 | Provider fixture | 保留原始错误 |
| S19 | API | 结构化错误 | `test_api.py` | error code/details 格式可解析 |
| S20 | 恢复 | 幂等过期清理 | `cleanup_idempotency` fixture | 只删除过期记录 |

## 自动化文件

- `tests/test_api.py`：REST 辅助函数、任务规范化、安全路径、配置权限、事件处理。
- `tests/test_providers.py`：Provider 路由、Auto 回退、强制模式、Agent/Responses 流程、Native 编辑遮罩。
- `tests/test_skill_matrix.py`：已安装技能的跨入口、多场景、输入安全和幂等矩阵。
- `tests/batch.fixture.json`：本地批量测试夹具。

## 当前结果

2026-08-24 在已安装路径 `/var/minis/skills/gpt-image-playground` 执行：

```text
skill matrix: 13/13 passed
API tests: 12 passed
provider_registry_tests: ok
doctor: ready
```

## 暂不自动执行的验收

以下测试需要真实 Provider、API Key 或外部服务，自动套件不会执行：

1. 真实文生图额度和图片质量；
2. 真实 multipart 编辑接口兼容性；
3. fal.ai Queue 的真实提交、轮询和超时；
4. 外部 Agent endpoint 的真实 SSE；
5. 对外监听时的反向代理、HTTPS 和 Token 集成。

执行这些验收前，必须明确授权、确认额度、使用隔离 Profile，并先做单次低成本请求。

## 发布门禁

修改技能后至少通过：

```sh
python3 -m py_compile scripts/*.py tests/*.py
python3 tests/test_api.py
python3 tests/test_providers.py
python3 tests/test_skill_matrix.py
python3 scripts/skill.py doctor
git diff --check
```
