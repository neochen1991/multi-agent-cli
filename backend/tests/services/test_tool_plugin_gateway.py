"""Tool 插件加载与执行测试。"""

from __future__ import annotations

import json

from app.services.tool_plugin_gateway import ToolPluginGateway
from app.services.tool_plugin_loader import ToolPluginLoader


def test_tool_plugin_loader_loads_tool_json(tmp_path):
    """验证 ToolPluginLoader 可从扩展目录读取 tool.json。"""

    tool_dir = tmp_path / "tools" / "demo_tool"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.json").write_text(
        json.dumps(
            {
                "tool_id": "demo_tool",
                "name": "Demo Tool",
                "runtime": "python",
                "entry": "run.py",
                "timeout_seconds": 5,
                "allowed_agents": ["LogAgent"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (tool_dir / "run.py").write_text(
        (
            "import json, sys\n"
            "payload = json.loads(sys.stdin.read() or '{}')\n"
            "print(json.dumps({'success': True, 'echo': payload.get('x')}, ensure_ascii=False))\n"
        ),
        encoding="utf-8",
    )

    loader = ToolPluginLoader(tmp_path / "tools")
    plugin = loader.get("demo_tool")

    assert plugin is not None
    assert plugin.tool_id == "demo_tool"
    assert plugin.entry == "run.py"
    assert "LogAgent" in plugin.allowed_agents


def test_tool_plugin_gateway_executes_plugin(tmp_path):
    """验证 ToolPluginGateway 可以执行 Python 插件并返回结构化结果。"""

    tool_dir = tmp_path / "tools" / "demo_tool"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.json").write_text(
        json.dumps(
            {
                "tool_id": "demo_tool",
                "name": "Demo Tool",
                "runtime": "python",
                "entry": "run.py",
                "timeout_seconds": 5,
                "allowed_agents": ["LogAgent"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (tool_dir / "run.py").write_text(
        (
            "import json, sys\n"
            "payload = json.loads(sys.stdin.read() or '{}')\n"
            "print(json.dumps({'success': True, 'message': 'ok', 'echo': payload.get('x')}, ensure_ascii=False))\n"
        ),
        encoding="utf-8",
    )

    gateway = ToolPluginGateway(tmp_path / "tools")
    outputs = gateway.invoke_for_agent(
        agent_name="LogAgent",
        requested_tools=["demo_tool"],
        payload={"x": 7},
    )

    assert len(outputs) == 1
    assert outputs[0]["tool_name"] == "demo_tool"
    assert outputs[0]["success"] is True
    assert outputs[0]["echo"] == 7


def test_tool_plugin_gateway_respects_allowed_agents(tmp_path):
    """验证 ToolPluginGateway 会遵守插件的 allowed_agents 限制。"""

    tool_dir = tmp_path / "tools" / "demo_tool"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.json").write_text(
        json.dumps(
            {
                "tool_id": "demo_tool",
                "name": "Demo Tool",
                "runtime": "python",
                "entry": "run.py",
                "timeout_seconds": 5,
                "allowed_agents": ["DatabaseAgent"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (tool_dir / "run.py").write_text("print('{}')\n", encoding="utf-8")

    gateway = ToolPluginGateway(tmp_path / "tools")
    outputs = gateway.invoke_for_agent(
        agent_name="LogAgent",
        requested_tools=["demo_tool"],
        payload={"x": 7},
    )

    assert outputs == []
