"""根目录 config.json 与 LLM 配置映射测试。"""

from __future__ import annotations

import json

from app.config import _load_root_llm_overrides


def test_load_root_llm_overrides_reads_nested_llm_fields(tmp_path):
    """验证会从 config.json 的 llm 节点提取并映射到 LLM_* 字段。"""

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "llm": {
                    "provider_id": "langgraph",
                    "model": "test-model",
                    "base_url": "https://example.com/v1",
                    "api_key": "test-key",
                    "max_retries": 2,
                    "max_concurrency": 5,
                    "timeouts": {"analysis": 66},
                    "queue_timeouts": {"judge": 88},
                    "debug": {"log_full_prompt": True},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    overrides = _load_root_llm_overrides(config_file)

    assert overrides["LLM_MODEL"] == "test-model"
    assert overrides["LLM_BASE_URL"] == "https://example.com/v1"
    assert overrides["LLM_API_KEY"] == "test-key"
    assert overrides["LLM_MAX_RETRIES"] == 2
    assert overrides["LLM_MAX_CONCURRENCY"] == 5
    assert overrides["LLM_ANALYSIS_TIMEOUT"] == 66
    assert overrides["LLM_JUDGE_QUEUE_TIMEOUT"] == 88
    assert overrides["LLM_LOG_FULL_PROMPT"] is True


def test_load_root_llm_overrides_returns_empty_for_invalid_json(tmp_path):
    """验证 config.json 非法时会安全回退空配置。"""

    config_file = tmp_path / "config.json"
    config_file.write_text("{invalid-json", encoding="utf-8")
    assert _load_root_llm_overrides(config_file) == {}
