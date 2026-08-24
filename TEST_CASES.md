# GPT Image Playground 测试案例

版本：`2.7.4`

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

## 真实 Provider 验收记录

2026-08-24 使用已安装技能的 default Profile 完成真实测试：

### 真实文生图：通过

- 模式：`auto`
- Provider：`images-native`
- 参数：`n=1`、`quality=low`、`size=1:1`
- 结果：返回完整图片、`saved_images`、`revised_prompt` 和耗时信息。

### 真实参考图 + Alpha 遮罩编辑：通过

- 模式：`native`
- Provider：`images-native`
- 结果：`/images/generations` 自动切换到 `/images/edits`，返回完整编辑结果，主体和眼镜保留，窗外背景变为浅蓝色。
- 注意：遮罩必须包含 Alpha 通道；无 Alpha 时服务端返回 `invalid_mask_image_format`。

### 测试中发现并修复

1. Native multipart 编辑请求的 CRLF 边界原先被错误写成字面量 `\\r\\n`，服务端报 `multipart: NextPart: EOF`；已修复为真实 CRLF。
2. multipart 编辑原先没有与普通生成一致的有限网络重试；已加入最多 3 次、指数退避重试。
3. multipart HTTP 400 原先只显示底层异常；现在保留服务端 JSON 的 `code`、`message` 和 HTTP 状态，便于诊断。
4. TLS EOF 被纳入可重试网络错误分类。

## 多场景真实生图验收记录

2026-08-24 使用已安装技能 `default` Profile 完成 6 个真实 Provider 场景：

| ID | 场景 | 模式 | 结果 |
|---|---|---|---|
| R01 | 1:1 红色咖啡杯产品摄影 | auto | 通过 |
| R02 | 16:9 海边灯塔横构图 | native | 通过 |
| R03 | 4:5 黄色雨衣小狗，JPG | native | 通过，扩展名和 JPEG 格式一致 |
| R04 | 透明背景蓝色玻璃星球 | native | 服务端拒绝：当前模型不支持透明背景 |
| R05 | 参考图蓝紫电影海报调色 | native | 通过 |
| R06 | Alpha mask 窗外夕阳编辑 | native | 通过 |

R04 暴露了能力声明问题：当前 `/v1/capabilities` 报告支持透明背景，但实际模型返回 `invalid_value`。该错误已归类为 `provider_request_rejected`，不会被 Auto 当作网络错误反复回退或重试；透明背景是否可用仍以 Profile/模型实际能力为准。

主要结果文件位于 `outputs/gpt-image-playground/`，每个成功任务均返回 `saved_images`、`revised_prompt`、实际执行模式和耗时。

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
