"""
报告生成服务
Report Generation Service

生成故障分析报告，支持多种格式输出。
"""

import json
import os
import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional
from pathlib import Path
import time

import structlog

from app.core.autogen_client import autogen_client
from app.core.json_utils import extract_json_dict
from app.config import settings

logger = structlog.get_logger()


class ReportGenerationService:
    """报告生成服务"""
    
    def __init__(self):
        self.reports_path = os.getenv("REPORTS_PATH", "/tmp/reports")
        os.makedirs(self.reports_path, exist_ok=True)
    
    async def generate_report(
        self,
        incident: Dict[str, Any],
        debate_result: Dict[str, Any],
        assets: Dict[str, Any],
        format: str = "markdown",
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        生成故障分析报告
        
        Args:
            incident: 故障事件信息
            debate_result: 辩论结果
            assets: 三态资产
            format: 输出格式 (markdown/json/html)
            
        Returns:
            生成的报告
        """
        logger.info(
            "report_generation_started",
            incident_id=incident.get("id"),
            format=format
        )
        
        # 使用 AI 生成报告内容（失败时自动降级，避免整个会话失败）
        try:
            report_content = await self._generate_report_with_ai(
                incident,
                debate_result,
                assets,
                event_callback=event_callback,
            )
        except Exception as e:
            error_text = str(e).strip() or e.__class__.__name__
            logger.warning(
                "report_generation_degraded_to_fallback",
                incident_id=incident.get("id"),
                error=error_text,
            )
            await self._emit_event(
                event_callback,
                {
                    "type": "report_generation_degraded",
                    "phase": "report_generation",
                    "error": error_text,
                    "message": "报告 LLM 超时或失败，已自动降级为模板报告",
                },
            )
            report_content = self._build_fallback_report_content(
                incident=incident,
                debate_result=debate_result,
                assets=assets,
                error_text=error_text,
            )
        
        # 根据格式生成报告
        if format == "markdown":
            report = self._format_as_markdown(report_content, incident, debate_result, assets)
        elif format == "html":
            report = self._format_as_html(report_content, incident, debate_result, assets)
        else:
            report = self._format_as_json(report_content, incident, debate_result, assets)
        
        # 保存报告
        report_path = await self._save_report(report, incident.get("id"), format)
        
        return {
            "report_id": f"rpt_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "incident_id": incident.get("id"),
            "format": format,
            "content": report,
            "file_path": report_path,
            "generated_at": datetime.utcnow().isoformat(),
        }
    
    async def _generate_report_with_ai(
        self,
        incident: Dict[str, Any],
        debate_result: Dict[str, Any],
        assets: Dict[str, Any],
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """使用 AutoGen 多 Agent 生成报告内容"""
        try:
            session = await autogen_client.create_session(
                title="报告生成"
            )
            
            # 构建报告生成提示（压缩输入长度，降低超时概率）
            prompt = self._build_report_prompt(incident, debate_result, assets)
            
            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_started",
                    "phase": "report_generation",
                    "stage": "report_ai_generation",
                    "session_id": session.id,
                    "model": settings.default_model_config.get("name"),
                    "prompt_preview": prompt[:1000],
                },
            )
            started_at = time.perf_counter()
            result: Optional[Dict[str, Any]] = None
            last_error: Optional[Exception] = None
            # 两次尝试：第一次更短超时，第二次使用标准超时
            timeout_plan = [
                max(12, min(settings.llm_timeout, 20)),
                max(18, min(settings.llm_total_timeout, 35)),
            ]
            for attempt_idx, call_timeout in enumerate(timeout_plan, start=1):
                try:
                    if attempt_idx > 1:
                        await self._emit_event(
                            event_callback,
                            {
                                "type": "autogen_call_retry",
                                "phase": "report_generation",
                                "stage": "report_ai_generation",
                                "session_id": session.id,
                                "attempt": attempt_idx,
                                "timeout_seconds": call_timeout,
                            },
                        )
                    result = await asyncio.wait_for(
                        autogen_client.send_prompt(
                            session_id=session.id,
                            parts=[{"type": "text", "text": prompt}],
                            model=settings.default_model_config,
                            max_tokens=max(320, min(int(settings.DEBATE_REPORT_MAX_TOKENS), 900)),
                            format={"type": "json_schema", "schema": self._report_json_schema()},
                            trace_callback=event_callback,
                            trace_context={
                                "phase": "report_generation",
                                "stage": "report_ai_generation",
                            },
                            use_session_history=False,
                        ),
                        timeout=call_timeout,
                    )
                    break
                except Exception as inner_exc:
                    last_error = inner_exc
                    if attempt_idx >= len(timeout_plan):
                        raise
            if result is None and last_error is not None:
                raise last_error
            
            if result and "content" in result:
                await self._emit_event(
                    event_callback,
                    {
                        "type": "autogen_call_completed",
                        "phase": "report_generation",
                        "stage": "report_ai_generation",
                        "session_id": session.id,
                        "model": settings.default_model_config.get("name"),
                        "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                        "response_preview": result.get("content", "")[:1200],
                    },
                )
                structured = result.get("structured") if isinstance(result, dict) else None
                if not isinstance(structured, dict) or not structured:
                    structured = self._parse_ai_report(result["content"])
                return self._normalize_report_structure(structured, incident, debate_result, assets)
            
            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_completed",
                    "phase": "report_generation",
                    "stage": "report_ai_generation",
                    "session_id": session.id,
                    "model": settings.default_model_config.get("name"),
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "response_preview": "",
                },
            )
            raise RuntimeError("报告生成 LLM 返回空响应")
            
        except Exception as e:
            error_text = str(e).strip() or e.__class__.__name__
            logger.error("ai_report_generation_failed", error=error_text)
            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_failed",
                    "phase": "report_generation",
                    "stage": "report_ai_generation",
                    "session_id": session.id if "session" in locals() else None,
                    "model": settings.default_model_config.get("name"),
                    "prompt_preview": prompt[:1000] if "prompt" in locals() else "",
                    "error": error_text,
                },
            )
            raise RuntimeError(f"报告生成 LLM 调用失败: {error_text}") from e
    
    def _build_report_prompt(
        self,
        incident: Dict[str, Any],
        debate_result: Dict[str, Any],
        assets: Dict[str, Any]
    ) -> str:
        """构建报告生成提示"""
        final_judgment = debate_result.get("final_judgment", {}) if isinstance(debate_result, dict) else {}
        root_cause = final_judgment.get("root_cause", {}) if isinstance(final_judgment, dict) else {}
        fix_recommendation = final_judgment.get("fix_recommendation", {}) if isinstance(final_judgment, dict) else {}
        impact = final_judgment.get("impact_analysis", {}) if isinstance(final_judgment, dict) else {}
        risk = final_judgment.get("risk_assessment", {}) if isinstance(final_judgment, dict) else {}
        evidence_chain_raw = final_judgment.get("evidence_chain") or []
        evidence_chain_compact: List[Dict[str, Any]] = []
        if isinstance(evidence_chain_raw, list):
            for item in evidence_chain_raw[:3]:
                if isinstance(item, dict):
                    evidence_chain_compact.append(
                        {
                            "type": item.get("type"),
                            "source": item.get("source"),
                            "location": item.get("location"),
                            "description": str(item.get("description") or "")[:180],
                        }
                    )
                else:
                    evidence_chain_compact.append(
                        {
                            "type": "analysis",
                            "source": "unknown",
                            "location": "",
                            "description": str(item)[:180],
                        }
                    )

        incident_summary = {
            "id": incident.get("id"),
            "title": incident.get("title"),
            "severity": incident.get("severity"),
            "service_name": incident.get("service_name"),
            "environment": incident.get("environment"),
            "description": str(incident.get("description") or "")[:220],
            "log_excerpt": str(incident.get("log_content") or "")[:420],
        }
        debate_summary = {
            "confidence": debate_result.get("confidence"),
            "root_cause": {
                "summary": str(root_cause.get("summary") or "")[:220],
                "category": root_cause.get("category"),
            },
            "evidence_chain": evidence_chain_compact,
            "fix_recommendation": {
                "summary": str(fix_recommendation.get("summary") or "")[:300],
                "steps": [str(step)[:140] for step in (fix_recommendation.get("steps") or [])[:3]],
            },
            "impact_analysis": {
                "affected_services": (impact.get("affected_services") or [])[:4],
                "business_impact": str(impact.get("business_impact") or "")[:180],
                "affected_users": str(impact.get("affected_users") or "")[:120],
            },
            "risk_assessment": {
                "risk_level": risk.get("risk_level"),
                "risk_factors": [str(i)[:120] for i in (risk.get("risk_factors") or [])[:3]],
            },
            "action_items": [str(item)[:140] for item in (debate_result.get("action_items") or [])[:3]],
            "responsible_team": debate_result.get("responsible_team"),
        }
        assets_summary = {
            "runtime_assets_count": len(assets.get("runtime_assets", [])),
            "dev_assets_count": len(assets.get("dev_assets", [])),
            "design_assets_count": len(assets.get("design_assets", [])),
            "interface_mapping": {
                "matched": (assets.get("interface_mapping") or {}).get("matched"),
                "domain": (assets.get("interface_mapping") or {}).get("domain"),
                "aggregate": (assets.get("interface_mapping") or {}).get("aggregate"),
                "owner_team": (assets.get("interface_mapping") or {}).get("owner_team"),
                "matched_endpoint": (assets.get("interface_mapping") or {}).get("matched_endpoint"),
            },
        }

        return f"""作为技术报告撰写专家，请根据以下信息生成一份专业的故障分析报告：

## 故障事件
```json
{json.dumps(incident_summary, ensure_ascii=False, separators=(",", ":"), default=str)}
```

## AI 辩论分析结果
```json
{json.dumps(debate_summary, ensure_ascii=False, separators=(",", ":"), default=str)}
```

## 三态资产摘要
```json
{json.dumps(assets_summary, ensure_ascii=False, separators=(",", ":"), default=str)}
```

请输出中文且精炼，避免冗长。列表项建议不超过 5 条。必须仅返回 JSON，结构如下：
{{
    "executive_summary": {{
        "title": "",
        "severity": "",
        "root_cause_summary": "",
        "resolution_status": ""
    }},
    "incident_overview": {{
        "description": "",
        "timeline": [],
        "affected_services": []
    }},
    "root_cause_analysis": {{
        "primary_cause": "",
        "contributing_factors": [],
        "evidence_chain": []
    }},
    "impact_assessment": {{
        "business_impact": "",
        "technical_impact": "",
        "affected_users": "",
        "duration": ""
    }},
    "recommendations": {{
        "immediate_actions": [],
        "long_term_fixes": [],
        "prevention_measures": []
    }},
    "lessons_learned": [],
    "appendix": {{
        "related_assets": [],
        "debate_summary": ""
    }}
}}"""

    def _build_fallback_report_content(
        self,
        incident: Dict[str, Any],
        debate_result: Dict[str, Any],
        assets: Dict[str, Any],
        error_text: str,
    ) -> Dict[str, Any]:
        final_judgment = self._safe_dict(debate_result.get("final_judgment", {}))
        root_cause = self._safe_dict(final_judgment.get("root_cause", {}))
        impact = self._safe_dict(final_judgment.get("impact_analysis", {}))
        risk = self._safe_dict(final_judgment.get("risk_assessment", {}))
        fix = self._safe_dict(final_judgment.get("fix_recommendation", {}))
        evidence = self._safe_list(final_judgment.get("evidence_chain", []))
        action_items = self._safe_list(debate_result.get("action_items", []))

        return self._normalize_report_structure(
            {
                "executive_summary": {
                    "title": f"故障分析报告 - {incident.get('title', '未知故障')}",
                    "severity": risk.get("risk_level") or incident.get("severity") or "medium",
                    "root_cause_summary": root_cause.get("summary") or "待进一步确认",
                    "resolution_status": "已生成降级报告",
                },
                "incident_overview": {
                    "description": str(incident.get("description") or incident.get("title") or "")[:500],
                    "timeline": [
                        {
                            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "event": f"报告 LLM 超时降级: {error_text}",
                        }
                    ],
                    "affected_services": impact.get("affected_services") or [incident.get("service_name") or "未知服务"],
                },
                "root_cause_analysis": {
                    "primary_cause": root_cause.get("summary") or "待确认",
                    "contributing_factors": risk.get("risk_factors") or [],
                    "evidence_chain": evidence[:6],
                },
                "impact_assessment": {
                    "business_impact": impact.get("business_impact") or "待评估",
                    "technical_impact": "报告由降级模板生成，建议复核原始辩论记录",
                    "affected_users": impact.get("affected_users") or "待评估",
                    "duration": "待补充",
                },
                "recommendations": {
                    "immediate_actions": action_items[:6],
                    "long_term_fixes": self._safe_list(fix.get("steps"))[:6],
                    "prevention_measures": self._safe_list(risk.get("mitigation_suggestions"))[:6],
                },
                "lessons_learned": [
                    "报告阶段出现 LLM 超时，系统已自动降级为模板报告以保证流程可用",
                    "建议缩短输入日志长度并重试以获得更完整的自然语言报告",
                ],
                "appendix": {
                    "related_assets": [
                        {"type": "runtime", "count": len(assets.get("runtime_assets", []))},
                        {"type": "development", "count": len(assets.get("dev_assets", []))},
                        {"type": "design", "count": len(assets.get("design_assets", []))},
                    ],
                    "debate_summary": "报告由降级模板生成，详见辩论阶段原始结论",
                },
            },
            incident=incident,
            debate_result=debate_result,
            assets=assets,
        )
    
    def _parse_ai_report(self, content: str) -> Dict[str, Any]:
        """解析 AI 生成的报告"""
        parsed = extract_json_dict(content)
        if parsed:
            return parsed
        raise RuntimeError("报告生成 LLM 输出不是有效 JSON")

    def _report_json_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "executive_summary": {"type": "object"},
                "incident_overview": {"type": "object"},
                "root_cause_analysis": {"type": "object"},
                "impact_assessment": {"type": "object"},
                "recommendations": {"type": "object"},
                "lessons_learned": {"type": "array"},
                "appendix": {"type": "object"},
            },
            "required": [
                "executive_summary",
                "incident_overview",
                "root_cause_analysis",
                "impact_assessment",
                "recommendations",
                "appendix",
            ],
        }

    def _normalize_report_structure(
        self,
        report: Dict[str, Any],
        incident: Dict[str, Any],
        debate_result: Dict[str, Any],
        assets: Dict[str, Any],
    ) -> Dict[str, Any]:
        """确保报告结构完整，并补齐关键字段。"""
        report = report if isinstance(report, dict) else {}
        merged = self._get_default_report_structure()
        merged.update(report or {})
        merged["executive_summary"] = {
            **self._get_default_report_structure()["executive_summary"],
            **self._safe_dict((report or {}).get("executive_summary")),
        }
        merged["incident_overview"] = {
            **self._get_default_report_structure()["incident_overview"],
            **self._safe_dict((report or {}).get("incident_overview")),
        }
        merged["root_cause_analysis"] = {
            **self._get_default_report_structure()["root_cause_analysis"],
            **self._safe_dict((report or {}).get("root_cause_analysis")),
        }
        merged["impact_assessment"] = {
            **self._get_default_report_structure()["impact_assessment"],
            **self._safe_dict((report or {}).get("impact_assessment")),
        }
        merged["recommendations"] = {
            **self._get_default_report_structure()["recommendations"],
            **self._safe_dict((report or {}).get("recommendations")),
        }
        merged["appendix"] = {
            **self._get_default_report_structure()["appendix"],
            **self._safe_dict((report or {}).get("appendix")),
        }

        final_judgment = self._safe_dict(debate_result.get("final_judgment", {}))
        root_cause = self._safe_dict(final_judgment.get("root_cause", {}))
        risk = self._safe_dict(final_judgment.get("risk_assessment", {}))
        impact = self._safe_dict(final_judgment.get("impact_analysis", {}))
        fix = self._safe_dict(final_judgment.get("fix_recommendation", {}))

        if not merged["executive_summary"].get("title"):
            merged["executive_summary"]["title"] = f"故障分析报告 - {incident.get('title', '未知故障')}"
        if not merged["executive_summary"].get("root_cause_summary"):
            merged["executive_summary"]["root_cause_summary"] = root_cause.get("summary", "待分析")
        if not merged["executive_summary"].get("severity"):
            merged["executive_summary"]["severity"] = risk.get("risk_level", "待定")

        if not merged["incident_overview"].get("description"):
            merged["incident_overview"]["description"] = incident.get("description", "")
        if not merged["incident_overview"].get("affected_services"):
            merged["incident_overview"]["affected_services"] = impact.get(
                "affected_services",
                [incident.get("service_name", "未知")],
            )

        if not merged["root_cause_analysis"].get("primary_cause"):
            merged["root_cause_analysis"]["primary_cause"] = root_cause.get("summary", "")
        if not merged["root_cause_analysis"].get("evidence_chain"):
            merged["root_cause_analysis"]["evidence_chain"] = self._safe_list(
                final_judgment.get("evidence_chain", [])
            )

        if not merged["impact_assessment"].get("business_impact"):
            merged["impact_assessment"]["business_impact"] = impact.get("business_impact", "")
        if not merged["impact_assessment"].get("affected_users"):
            merged["impact_assessment"]["affected_users"] = impact.get("affected_users", "")

        if not merged["recommendations"].get("immediate_actions"):
            merged["recommendations"]["immediate_actions"] = self._safe_list(
                debate_result.get("action_items", [])
            )
        if not merged["recommendations"].get("long_term_fixes"):
            merged["recommendations"]["long_term_fixes"] = self._safe_list(fix.get("steps", []))
        if not merged["recommendations"].get("prevention_measures"):
            merged["recommendations"]["prevention_measures"] = self._safe_list(
                risk.get("mitigation_suggestions", [])
            )

        if not merged["appendix"].get("debate_summary"):
            merged["appendix"]["debate_summary"] = (
                f"共执行 {debate_result.get('round_control', {}).get('executed_rounds', 0)} 轮辩论，"
                f"置信度 {debate_result.get('confidence', 0) * 100:.1f}%"
            )
        interface_mapping = assets.get("interface_mapping", {}) if isinstance(assets, dict) else {}
        merged["appendix"]["responsibility_mapping"] = {
            "matched": interface_mapping.get("matched", False),
            "domain": interface_mapping.get("domain"),
            "aggregate": interface_mapping.get("aggregate"),
            "owner_team": interface_mapping.get("owner_team"),
            "owner": interface_mapping.get("owner"),
            "matched_endpoint": interface_mapping.get("matched_endpoint"),
            "db_tables": interface_mapping.get("db_tables", []),
            "code_artifacts": interface_mapping.get("code_artifacts", []),
            "design_ref": interface_mapping.get("design_ref"),
            "guidance": interface_mapping.get("guidance", []),
        }

        return merged

    @staticmethod
    def _safe_dict(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _safe_list(value: Any) -> List[Any]:
        return value if isinstance(value, list) else []
    
    def _get_default_report_structure(self) -> Dict[str, Any]:
        """获取默认报告结构"""
        return {
            "executive_summary": {
                "title": "故障分析报告",
                "severity": "待定",
                "root_cause_summary": "待分析",
                "resolution_status": "进行中"
            },
            "incident_overview": {
                "description": "",
                "timeline": [],
                "affected_services": []
            },
            "root_cause_analysis": {
                "primary_cause": "",
                "contributing_factors": [],
                "evidence_chain": []
            },
            "impact_assessment": {
                "business_impact": "",
                "technical_impact": "",
                "affected_users": "",
                "duration": ""
            },
            "recommendations": {
                "immediate_actions": [],
                "long_term_fixes": [],
                "prevention_measures": []
            },
            "lessons_learned": [],
            "appendix": {
                "related_assets": [],
                "debate_summary": "",
                "responsibility_mapping": {},
            }
        }
    
    def _format_as_markdown(
        self,
        report_content: Dict[str, Any],
        incident: Dict[str, Any],
        debate_result: Dict[str, Any],
        assets: Dict[str, Any],
    ) -> str:
        """格式化为 Markdown"""
        exec_summary = report_content.get("executive_summary", {})
        overview = report_content.get("incident_overview", {})
        root_cause = report_content.get("root_cause_analysis", {})
        impact = report_content.get("impact_assessment", {})
        recommendations = report_content.get("recommendations", {})
        
        responsibility = (report_content.get("appendix", {}) or {}).get("responsibility_mapping", {})
        md = f"""# 故障分析报告

## 执行摘要

**标题**: {exec_summary.get('title', incident.get('title', '未知'))}

**严重程度**: {exec_summary.get('severity', '未知')}

**根因摘要**: {exec_summary.get('root_cause_summary', '待分析')}

**解决状态**: {exec_summary.get('resolution_status', '进行中')}

**生成时间**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC

---

## 1. 故障概述

### 1.1 故障描述
{overview.get('description', incident.get('description', '无描述'))}

### 1.2 受影响服务
{self._format_list(overview.get('affected_services', [incident.get('service_name', '未知')]))}

### 1.3 时间线
{self._format_timeline(overview.get('timeline', []))}

---

## 2. 根因分析

### 2.1 主要原因
{root_cause.get('primary_cause', '待分析')}

### 2.2 促成因素
{self._format_list(root_cause.get('contributing_factors', []))}

### 2.3 证据链
{self._format_evidence_chain(root_cause.get('evidence_chain', []))}

---

## 3. 影响评估

### 3.1 业务影响
{impact.get('business_impact', '待评估')}

### 3.2 技术影响
{impact.get('technical_impact', '待评估')}

### 3.3 受影响用户
{impact.get('affected_users', '待评估')}

### 3.4 故障持续时间
{impact.get('duration', '待评估')}

---

## 4. 修复建议

### 4.1 立即行动
{self._format_action_items(recommendations.get('immediate_actions', []))}

### 4.2 长期修复
{self._format_list(recommendations.get('long_term_fixes', []))}

### 4.3 预防措施
{self._format_list(recommendations.get('prevention_measures', []))}

---

## 5. 经验教训
{self._format_list(report_content.get('lessons_learned', []))}

---

## 6. 附录

### 6.1 相关资产
{self._format_assets(report_content.get('appendix', {}).get('related_assets', []))}

### 6.2 AI 辩论摘要
{report_content.get('appendix', {}).get('debate_summary', '无')}

### 6.3 责任田映射
{self._format_responsibility_mapping_markdown(responsibility, assets)}

### 6.4 置信度
{debate_result.get('confidence', 0) * 100:.1f}%

---

*本报告由 SRE Debate Platform 自动生成*
"""
        return md
    
    def _format_as_html(
        self,
        report_content: Dict[str, Any],
        incident: Dict[str, Any],
        debate_result: Dict[str, Any],
        assets: Dict[str, Any],
    ) -> str:
        """格式化为 HTML"""
        _ = assets
        exec_summary = report_content.get("executive_summary", {})
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>故障分析报告 - {incident.get('title', '未知')}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1677ff;
            border-bottom: 2px solid #1677ff;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #333;
            margin-top: 30px;
        }}
        .severity {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: bold;
        }}
        .severity-critical {{ background: #ff4d4f; color: white; }}
        .severity-high {{ background: #faad14; color: white; }}
        .severity-medium {{ background: #fa8c16; color: white; }}
        .severity-low {{ background: #52c41a; color: white; }}
        .section {{
            margin: 20px 0;
            padding: 15px;
            background: #fafafa;
            border-radius: 4px;
        }}
        .evidence-chain {{
            border-left: 3px solid #1677ff;
            padding-left: 15px;
        }}
        .action-item {{
            background: #e6f7ff;
            padding: 10px;
            margin: 5px 0;
            border-radius: 4px;
        }}
        .footer {{
            margin-top: 40px;
            text-align: center;
            color: #999;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>故障分析报告</h1>
        
        <div class="section">
            <h2>执行摘要</h2>
            <p><strong>标题:</strong> {exec_summary.get('title', incident.get('title', '未知'))}</p>
            <p><strong>严重程度:</strong> 
                <span class="severity severity-{exec_summary.get('severity', 'low')}">
                    {exec_summary.get('severity', '未知')}
                </span>
            </p>
            <p><strong>根因摘要:</strong> {exec_summary.get('root_cause_summary', '待分析')}</p>
            <p><strong>生成时间:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        </div>
        
        <div class="section">
            <h2>根因分析</h2>
            <p>{report_content.get('root_cause_analysis', {}).get('primary_cause', '待分析')}</p>
        </div>
        
        <div class="section">
            <h2>修复建议</h2>
            {self._format_actions_html(report_content.get('recommendations', {}).get('immediate_actions', []))}
        </div>
        
        <div class="section">
            <h2>置信度</h2>
            <p>{debate_result.get('confidence', 0) * 100:.1f}%</p>
        </div>
        
        <div class="footer">
            <p>本报告由 SRE Debate Platform 自动生成</p>
        </div>
    </div>
</body>
</html>"""
        return html
    
    def _format_as_json(
        self,
        report_content: Dict[str, Any],
        incident: Dict[str, Any],
        debate_result: Dict[str, Any],
        assets: Dict[str, Any],
    ) -> str:
        """格式化为 JSON"""
        report = {
            "report_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "incident_id": incident.get("id"),
                "confidence": debate_result.get("confidence", 0),
                "generator": "SRE Debate Platform"
            },
            "assets_summary": {
                "runtime_assets_count": len(assets.get("runtime_assets", [])) if isinstance(assets, dict) else 0,
                "dev_assets_count": len(assets.get("dev_assets", [])) if isinstance(assets, dict) else 0,
                "design_assets_count": len(assets.get("design_assets", [])) if isinstance(assets, dict) else 0,
                "interface_mapping": (assets.get("interface_mapping", {}) if isinstance(assets, dict) else {}),
            },
            **report_content
        }
        return json.dumps(report, ensure_ascii=False, indent=2)
    
    def _format_list(self, items: List[str]) -> str:
        """格式化列表"""
        if not items:
            return "- 无"
        return "\n".join(f"- {item}" for item in items)
    
    def _format_timeline(self, timeline: List[Any]) -> str:
        """格式化时间线"""
        if not timeline:
            return "无时间线信息"
        lines = []
        for item in timeline:
            if isinstance(item, dict):
                time = item.get("time", "未知时间")
                event = item.get("event", "未知事件")
            else:
                time = "未知时间"
                event = str(item)
            lines.append(f"- **{time}**: {event}")
        return "\n".join(lines)
    
    def _format_evidence_chain(self, chain: List[Any]) -> str:
        """格式化证据链"""
        if not chain:
            return "无证据链"
        lines = []
        for i, evidence in enumerate(chain, 1):
            if isinstance(evidence, dict):
                step = evidence.get("step", i)
                desc = evidence.get("description", "无描述")
                location = evidence.get("code_location", "")
                strength = evidence.get("strength", "medium")
            else:
                step = i
                desc = str(evidence)
                location = ""
                strength = "medium"
            lines.append(f"{step}. **{desc}**")
            if location:
                lines.append(f"   - 位置: `{location}`")
            lines.append(f"   - 强度: {strength}")
        return "\n".join(lines)
    
    def _format_action_items(self, items: List[Any]) -> str:
        """格式化行动项"""
        if not items:
            return "无行动项"
        lines = []
        for item in items:
            if isinstance(item, dict):
                priority = item.get("priority", "-")
                action = item.get("action", "未知行动")
                owner = item.get("owner", "未分配")
            else:
                priority = "-"
                action = str(item)
                owner = "未分配"
            lines.append(f"{priority}. {action} (负责人: {owner})")
        return "\n".join(lines)
    
    def _format_actions_html(self, items: List[Any]) -> str:
        """格式化行动项 HTML"""
        if not items:
            return "<p>无行动项</p>"
        html = ""
        for item in items:
            action = item.get("action", "未知行动") if isinstance(item, dict) else str(item)
            html += f'<div class="action-item">{action}</div>'
        return html

    def _format_responsibility_mapping_markdown(self, mapping: Dict[str, Any], assets: Dict[str, Any]) -> str:
        mapping = mapping if isinstance(mapping, dict) else {}
        interface_mapping = assets.get("interface_mapping", {}) if isinstance(assets, dict) else {}
        merged = {**interface_mapping, **mapping}
        matched = "是" if merged.get("matched") else "否"
        endpoint = merged.get("matched_endpoint") or {}
        endpoint_text = "-"
        if isinstance(endpoint, dict):
            endpoint_text = f"{endpoint.get('method', '-')} {endpoint.get('path', '-')}"
        code_items = merged.get("code_artifacts") or []
        db_tables = merged.get("db_tables") or []
        guidance = merged.get("guidance") or []
        lines = [
            f"- 命中: {matched}",
            f"- 领域: {merged.get('domain') or '-'}",
            f"- 聚合根: {merged.get('aggregate') or '-'}",
            f"- 责任团队: {merged.get('owner_team') or '-'}",
            f"- 负责人: {merged.get('owner') or '-'}",
            f"- 命中接口: {endpoint_text}",
            f"- 代码资产数: {len(code_items)}",
            f"- 数据表: {', '.join(db_tables) if db_tables else '-'}",
        ]
        if guidance:
            lines.append("- 未命中补充建议:")
            lines.extend([f"  - {str(item)}" for item in guidance[:5]])
        return "\n".join(lines)
    
    def _format_assets(self, assets: List[Any]) -> str:
        """格式化资产列表"""
        if not assets:
            return "无相关资产"
        lines = []
        for asset in assets:
            if isinstance(asset, dict):
                name = asset.get("name", "未知")
                type_ = asset.get("type", "未知类型")
            else:
                name = str(asset)
                type_ = "未知类型"
            lines.append(f"- {name} ({type_})")
        return "\n".join(lines)
    
    async def _save_report(
        self,
        content: str,
        incident_id: str,
        format: str
    ) -> str:
        """保存报告到文件"""
        ext = {"markdown": "md", "html": "html", "json": "json"}.get(format, "md")
        filename = f"report_{incident_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
        filepath = os.path.join(self.reports_path, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info("report_saved", path=filepath)
        return filepath

    async def _emit_event(
        self,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        event: Dict[str, Any],
    ) -> None:
        if not event_callback:
            return
        try:
            maybe_coro = event_callback(event)
            if hasattr(maybe_coro, "__await__"):
                await maybe_coro
        except Exception as e:
            logger.warning("report_event_emit_failed", error=str(e))


# 全局实例
report_generation_service = ReportGenerationService()
