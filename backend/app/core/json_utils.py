"""
JSON 提取工具模块

本模块提供从文本中提取 JSON 对象的功能，主要用于解析 LLM 输出。

核心功能：
1. 从混合文本中提取 JSON 对象
2. 支持代码块格式的 JSON
3. 支持前后有额外文本的 JSON
4. 平衡括号匹配算法

使用场景：
- 解析 LLM 输出中的结构化数据
- 从 markdown 代码块中提取 JSON
- 处理 LLM 输出中的格式噪声

JSON extraction helpers.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Optional


def _iter_json_candidates(text: str) -> Iterable[str]:
    """
    迭代生成 JSON 候选字符串

    从文本中提取所有可能的 JSON 对象候选项。
    按优先级顺序生成：
    1. 整个文本（如果文本本身是 JSON）
    2. markdown 代码块中的内容
    3. 平衡括号匹配的子串

    Args:
        text: 原始文本

    Yields:
        str: JSON 候选字符串
    """
    raw = (text or "").strip()
    if not raw:
        return

    # 1. 尝试整个文本作为 JSON
    yield raw

    # 2. 提取 markdown 代码块中的内容
    # 匹配 ```json 或 ``` 包裹的内容
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE):
        candidate = block.strip()
        if candidate:
            yield candidate

    # 3. 平衡括号匹配算法
    # 处理 JSON 前后有额外文本的情况
    n = len(raw)
    for start in range(n):
        if raw[start] != "{":
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, n):
            ch = raw[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    yield raw[start : i + 1]
                    break


def extract_json_dict(text: str) -> Optional[Dict[str, Any]]:
    """
    从文本中提取第一个有效的 JSON 对象

    尝试从文本中提取 JSON 对象，支持多种格式：
    - 纯 JSON 文本
    - markdown 代码块包裹的 JSON
    - 前后有额外文本的 JSON

    Args:
        text: 可能包含 JSON 的文本

    Returns:
        Optional[Dict[str, Any]]: 解析成功返回字典，否则返回 None

    Example:
        >>> extract_json_dict('Some text {"key": "value"} more text')
        {'key': 'value'}
        >>> extract_json_dict('```json\\n{"key": "value"}\\n```')
        {'key': 'value'}
    """
    for candidate in _iter_json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None