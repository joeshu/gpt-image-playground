# Darwin Skill 优化报告

版本：`3.0.0`
对象：`SKILL.md`
日期：2026-08-25

## 基线

- `SKILL.md`：181 行，7,947 字节
- `skill.py check`：ready
- `skill.py doctor`：ready
- API 测试：12 passed
- Provider 测试：ok
- Skill matrix：13/13 passed
- Runtime 红灯扫描：未命中 Claude/Cursor 专属措辞

## 测试 Prompt

详见 `test-prompts.json`，覆盖：

1. 典型单图生成；
2. 参考图和 Alpha mask 编辑；
3. 批量、幂等和失败项重试；
4. gpt-image-2 透明背景和网关能力诊断。

## 本轮改进

新增到 `SKILL.md`：

- 标准执行流程：CHECK → PLAN → DRY RUN → EXECUTE → VERIFY → REPORT；
- 显式 `CHECKPOINT · STOP` 高风险动作门禁；
- 透明背景的官方能力与兼容网关差异说明；
- endpoint + model + 实际请求的三重能力确认；
- 失败模式处理矩阵；
- 反例与禁止操作清单；
- `test-prompts.json` 和 `TEST_CASES.md` 资源入口。

## 评审限制

计划调用独立 paired judge，但当前唯一可用的 `minis-model-use` 是图片生成模型；将文本版 SKILL.md 评审请求发送到 Images endpoint 会被 Provider 拒绝。因此本轮 paired judge 标记为 `unavailable`，没有伪造评审结果。

保留依据：Darwin 规范要求评审不可用时退化为干跑验证，并明确标注限制。本轮采用静态 9 维 rubric + 本地回归 + 真实测试记录完成验证。

## 验证结果

优化后重新通过：

```text
python3 -m py_compile scripts/*.py tests/*.py
python3 tests/test_api.py
python3 tests/test_providers.py
python3 tests/test_skill_matrix.py
python3 scripts/skill.py check
python3 scripts/skill.py doctor
```

结果：`API 12 passed`、`provider ok`、`matrix 13/13 passed`、`doctor ready`。
