# Claim Graph Benchmark Priority Implementation Plan

日期：2026-03-11

## Task 1 扩展 Fixture Loader

目标：
- 让 benchmark 可以读取 richer fixture 字段

改动文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/benchmark/fixtures.py`
- `/Users/neochen/multi-agent-cli_v2/backend/tests/fixtures/incidents/README.md`

输出：
- `IncidentFixture` 新增：
  - `expected_causal_chain`
  - `must_include`
  - `must_exclude`

## Task 2 扩展 Benchmark Scoring

目标：
- 在 case 级评分里引入 claim-graph 质量门

改动文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/benchmark/scoring.py`

输出：
- `evaluate_case()` 支持：
  - `claim_graph`
  - `expected_causal_chain`
  - `must_include`
  - `must_exclude`
- 返回：
  - `claim_graph_support_score`
  - `claim_graph_exclusion_score`
  - `claim_graph_missing_check_score`
  - `claim_graph_quality_score`

## Task 3 扩展 Runner

目标：
- 把 `DebateResult.claim_graph` 和 fixture 扩展字段真正送进 scoring

改动文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/benchmark/runner.py`

输出：
- baseline case row 增加 claim-graph 相关评分字段

## Task 4 补测试

目标：
- 锁住 richer scoring 行为，避免后续回退

改动文件：
- `/Users/neochen/multi-agent-cli_v2/backend/tests/test_benchmark_scoring.py`
- 新增或扩展 loader 测试

## Task 5 验证

命令：

```bash
PYTHONPATH=backend backend/.venv/bin/pytest \
  backend/tests/test_benchmark_scoring.py
```

必要时补跑：

```bash
PYTHONPATH=backend backend/.venv/bin/pytest \
  backend/tests/test_debate_service_effective_conclusion.py \
  backend/tests/test_judge_payload_recovery.py
```
