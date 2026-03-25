"""testAgentSkill服务相关测试。"""

from __future__ import annotations

from app.models.tooling import AgentSkillConfig
from app.services.agent_skill_service import AgentSkillService


def test_select_skills_disabled():
    """验证选择Skill禁用。"""
    
    service = AgentSkillService()
    payload = service.select_skills(
        agent_name="LogAgent",
        cfg=AgentSkillConfig(enabled=False),
        assigned_command={"task": "分析日志超时"},
        compact_context={},
        incident_context={},
    )
    assert payload["enabled"] is False
    assert payload["used"] is False


def test_select_skills_match_by_command(tmp_path):
    """验证选择Skill匹配by命令。"""
    
    skill_dir = tmp_path / "skills" / "log"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: log-forensics\n"
            "description: 日志排障\n"
            "triggers: 日志,timeout,error\n"
            "agents: LogAgent\n"
            "---\n"
            "\n"
            "## Checklist\n"
            "1. 先看时间线\n"
        ),
        encoding="utf-8",
    )
    service = AgentSkillService()
    payload = service.select_skills(
        agent_name="LogAgent",
        cfg=AgentSkillConfig(
            enabled=True,
            skills_dir=str(tmp_path / "skills"),
            extensions_enabled=False,
            max_skills=2,
        ),
        assigned_command={"task": "请读取日志并分析 timeout 错误"},
        compact_context={},
        incident_context={},
    )
    assert payload["enabled"] is True
    assert payload["used"] is True
    assert payload["status"] == "ok"
    assert len(payload["skills"]) == 1
    assert payload["skills"][0]["name"] == "log-forensics"


def test_select_skills_respects_allowed_agents(tmp_path):
    """验证选择Skill遵守允许Agent。"""
    
    skill_dir = tmp_path / "skills" / "db"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: db-check\ndescription: db\ntriggers: sql\nagents: DatabaseAgent\n---\nbody",
        encoding="utf-8",
    )
    service = AgentSkillService()
    payload = service.select_skills(
        agent_name="LogAgent",
        cfg=AgentSkillConfig(
            enabled=True,
            skills_dir=str(tmp_path / "skills"),
            extensions_enabled=False,
            allowed_agents=["DatabaseAgent"],
        ),
        assigned_command={"task": "分析 sql timeout"},
        compact_context={},
        incident_context={},
    )
    assert payload["used"] is False
    assert payload["status"] == "skipped_by_agent"


def test_select_skills_no_command_no_use(tmp_path):
    """验证选择Skill无命令无use。"""
    
    skill_dir = tmp_path / "skills" / "log"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: log-forensics\ndescription: 日志排障\ntriggers: 日志,timeout\nagents: LogAgent\n---\nbody",
        encoding="utf-8",
    )
    service = AgentSkillService()
    payload = service.select_skills(
        agent_name="LogAgent",
        cfg=AgentSkillConfig(enabled=True, skills_dir=str(tmp_path / "skills"), extensions_enabled=False),
        assigned_command={},
        compact_context={},
        incident_context={},
    )
    # SkillService 本身不做命令门禁，此处保证无命令通常不会命中
    assert payload["used"] is False


def test_select_skills_explicit_hints(tmp_path):
    """验证选择Skill显式提示。"""
    
    skill_dir = tmp_path / "skills" / "log-forensics"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: log-forensics\n"
            "description: 日志排障\n"
            "triggers: 连接池,timeout\n"
            "agents: LogAgent\n"
            "---\n"
            "body"
        ),
        encoding="utf-8",
    )
    service = AgentSkillService()
    payload = service.select_skills(
        agent_name="LogAgent",
        cfg=AgentSkillConfig(
            enabled=True,
            skills_dir=str(tmp_path / "skills"),
            extensions_enabled=False,
            max_skills=3,
        ),
        assigned_command={"skill_hints": ["log-forensics"], "use_tool": True},
        compact_context={},
        incident_context={},
    )
    assert payload["used"] is True
    assert payload["status"] == "ok"
    assert payload["skills"][0]["name"] == "log-forensics"


def test_select_skills_reads_metadata_required_tools(tmp_path):
    """验证 Skill metadata.json 的 required_tools 会被带入结果。"""

    skill_dir = tmp_path / "skills" / "design-consistency-check"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: design-consistency-check\n"
            "description: 设计一致性检查\n"
            "triggers: design,api\n"
            "agents: LogAgent\n"
            "---\n"
            "body"
        ),
        encoding="utf-8",
    )
    (skill_dir / "metadata.json").write_text(
        (
            "{\n"
            "  \"skill_id\": \"design-consistency-check\",\n"
            "  \"name\": \"设计一致性检查\",\n"
            "  \"applicable_experts\": [\"LogAgent\"],\n"
            "  \"required_tools\": [\"design_spec_alignment\"]\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    service = AgentSkillService()
    payload = service.select_skills(
        agent_name="LogAgent",
        cfg=AgentSkillConfig(
            enabled=True,
            skills_dir=str(tmp_path / "skills"),
            extensions_enabled=False,
            max_skills=2,
        ),
        assigned_command={"skill_hints": ["design-consistency-check"], "use_tool": True},
        compact_context={},
        incident_context={},
    )
    assert payload["enabled"] is True
    assert payload["used"] is True
    assert payload["status"] == "ok"
    assert payload["skills"][0]["name"] == "design-consistency-check"
    assert payload["skills"][0]["required_tools"] == ["design_spec_alignment"]


def test_select_skills_reads_extensions_dir(tmp_path):
    """验证 extensions_dir 开启后会加载扩展 Skill。"""

    ext_skill_dir = tmp_path / "extensions" / "skills" / "db-extension"
    ext_skill_dir.mkdir(parents=True, exist_ok=True)
    (ext_skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: db-extension\n"
            "description: 数据库扩展技能\n"
            "triggers: lock,slow sql\n"
            "agents: DatabaseAgent\n"
            "---\n"
            "body"
        ),
        encoding="utf-8",
    )

    service = AgentSkillService()
    payload = service.select_skills(
        agent_name="DatabaseAgent",
        cfg=AgentSkillConfig(
            enabled=True,
            skills_dir=str(tmp_path / "skills"),
            extensions_enabled=True,
            extensions_dir=str(tmp_path / "extensions" / "skills"),
        ),
        assigned_command={"task": "分析 lock 与 slow sql", "use_tool": True},
        compact_context={},
        incident_context={},
    )
    assert payload["enabled"] is True
    assert payload["used"] is True
    assert payload["skills"][0]["name"] == "db-extension"
