# Extension Skills

`AgentSkillService` 默认会并行扫描两个目录：

- `backend/skills`（内置 Skill）
- `backend/extensions/skills`（扩展 Skill）

新增扩展 Skill 的最小结构：

```text
backend/extensions/skills/<skill-id>/
  SKILL.md
  metadata.json   # 可选，推荐
```

`metadata.json` 可用于声明：

- `applicable_experts` / `bound_experts`
- `required_tools`（命中该 skill 后自动触发的插件工具）
- `activation_hints`

## 生产根因分析推荐 Skill 组合

- `timeout-cascade-rca` -> `required_tools: ["upstream_timeout_chain"]`
- `db-lock-contention-triage` -> `required_tools: ["db_lock_hotspot"]`
- `release-regression-correlation` -> `required_tools: ["release_regression_guard"]`

实践建议：在主 Agent 的命令里补充 `skill_hints` 或 `tool_hints`，可强制命中对应扩展能力。
