"""页面巡检与自动拉起 RCA 服务。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from time import perf_counter
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

import httpx
import structlog

from app.config import settings
from app.core.task_queue import task_queue
from app.models.incident import IncidentCreate as IncidentCreateModel, IncidentSeverity, IncidentStatus, IncidentUpdate
from app.models.monitoring import MonitorStatus, MonitorTarget, MonitorTargetCreate, MonitorTargetUpdate, PageMonitorFinding
from app.services.debate_service import debate_service
from app.services.incident_service import incident_service
from app.services.knowledge_service import knowledge_service
from app.storage.sqlite_store import sqlite_store

logger = structlog.get_logger()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _from_iso(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    with suppress(Exception):
        return datetime.fromisoformat(text)
    return None


class PageMonitoringService:
    """管理页面巡检任务并自动触发故障分析。"""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task[Any]] = None
        self._stop_event = asyncio.Event()
        self._running = False
        self._last_loop_at: Optional[datetime] = None
        self._loop_lock = asyncio.Lock()
        # 中文注释：全局串行巡检锁。无论是定时轮询还是手动“立即感知”，都必须排队执行，
        # 避免多个页面或同一页面同时触发 Playwright/HTTP 巡检导致并发抖动。
        self._scan_serial_lock = asyncio.Lock()

    async def start(self) -> None:
        """启动巡检循环。"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="page-monitor-loop")
        logger.info("page_monitor_started")

    async def stop(self) -> None:
        """停止巡检循环。"""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        task = self._task
        self._task = None
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        logger.info("page_monitor_stopped")

    async def status(self) -> MonitorStatus:
        """返回巡检服务状态。"""
        targets = await self.list_targets(enabled_only=True)
        return MonitorStatus(
            running=self._running,
            tick_seconds=max(5, int(settings.PAGE_MONITOR_TICK_SECONDS or 15)),
            active_targets=len(targets),
            last_loop_at=self._last_loop_at,
        )

    async def list_targets(self, *, enabled_only: bool = False) -> List[MonitorTarget]:
        """列出巡检目标。"""
        sql = "SELECT payload_json FROM monitor_targets ORDER BY updated_at DESC"
        params: List[Any] = []
        if enabled_only:
            sql = "SELECT payload_json FROM monitor_targets WHERE enabled=1 ORDER BY updated_at DESC"
        rows = await sqlite_store.fetchall(sql, params)
        return [self._row_to_target(row["payload_json"]) for row in rows]

    async def get_target(self, target_id: str) -> Optional[MonitorTarget]:
        """获取单个巡检目标。"""
        row = await sqlite_store.fetchone("SELECT payload_json FROM monitor_targets WHERE id=?", [target_id])
        if not row:
            return None
        return self._row_to_target(row["payload_json"])

    async def create_target(self, payload: MonitorTargetCreate) -> MonitorTarget:
        """创建巡检目标。"""
        now = _utcnow()
        target = MonitorTarget(
            id=f"mon_{uuid4().hex[:10]}",
            name=payload.name.strip(),
            url=payload.url.strip(),
            enabled=bool(payload.enabled),
            check_interval_sec=int(payload.check_interval_sec),
            timeout_sec=int(payload.timeout_sec),
            cooldown_sec=int(payload.cooldown_sec),
            service_name=payload.service_name.strip(),
            environment=payload.environment.strip() or "prod",
            severity=str(payload.severity or "high").strip().lower(),
            # 中文注释：Cookie 按原始 Header 文本保存，供需要登录态的页面巡检时直接透传。
            cookie_header=str(payload.cookie_header or "").strip(),
            tags=[str(item).strip() for item in (payload.tags or []) if str(item).strip()],
            metadata=dict(payload.metadata or {}),
            created_at=now,
            updated_at=now,
        )
        await self._save_target(target)
        return target

    async def update_target(self, target_id: str, payload: MonitorTargetUpdate) -> Optional[MonitorTarget]:
        """更新巡检目标。"""
        current = await self.get_target(target_id)
        if not current:
            return None
        updates = payload.model_dump(exclude_unset=True)
        merged = current.model_dump()
        for key, value in updates.items():
            merged[key] = value
        merged["updated_at"] = _utcnow()
        target = MonitorTarget(**merged)
        await self._save_target(target)
        return target

    async def delete_target(self, target_id: str) -> bool:
        """删除巡检目标。"""
        existing = await self.get_target(target_id)
        if not existing:
            return False
        await sqlite_store.execute("DELETE FROM monitor_targets WHERE id=?", [target_id])
        return True

    async def scan_target_once(self, target_id: str) -> Optional[PageMonitorFinding]:
        """手动触发单目标巡检。"""
        target = await self.get_target(target_id)
        if not target:
            return None
        finding = await self._scan_target_serialized(target, trigger="manual")
        await self._record_finding(finding)
        if finding.has_error:
            await self._handle_anomaly(target, finding)
        return finding

    async def list_events(self, target_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        """查询巡检事件。"""
        rows = await sqlite_store.fetchall(
            "SELECT payload_json FROM monitor_scan_events WHERE target_id=? ORDER BY id DESC LIMIT ?",
            [target_id, max(1, min(200, int(limit or 50)))],
        )
        items: List[Dict[str, Any]] = []
        for row in rows:
            items.append(sqlite_store.loads_json(row["payload_json"], default={}) or {})
        return items

    async def _loop(self) -> None:
        """巡检主循环。"""
        tick = max(5, int(settings.PAGE_MONITOR_TICK_SECONDS or 15))
        while not self._stop_event.is_set():
            self._last_loop_at = _utcnow()
            await self._run_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=tick)
            except asyncio.TimeoutError:
                continue

    async def _run_once(self) -> None:
        """执行一轮巡检。"""
        if not self._running:
            return
        async with self._loop_lock:
            targets = await self.list_targets(enabled_only=True)
            if not targets:
                return
            for target in targets:
                if not self._should_check(target):
                    continue
                finding = await self._scan_target_serialized(target, trigger="loop")
                await self._record_finding(finding)
                if finding.has_error:
                    await self._handle_anomaly(target, finding)
                target.last_checked_at = finding.checked_at
                target.updated_at = _utcnow()
                await self._save_target(target)

    async def _scan_target_serialized(self, target: MonitorTarget, *, trigger: str) -> PageMonitorFinding:
        """串行执行单目标巡检，统一为所有入口提供排队门禁。"""
        queued_at = perf_counter()
        async with self._scan_serial_lock:
            wait_ms = round((perf_counter() - queued_at) * 1000, 2)
            # 中文注释：显式记录排队耗时，便于定位“为什么感知慢/按钮转圈久”。
            logger.info(
                "page_monitor_scan_started",
                target_id=target.id,
                target_name=target.name,
                trigger=trigger,
                queue_wait_ms=wait_ms,
            )
            finding = await self._scan_target(target)
            logger.info(
                "page_monitor_scan_completed",
                target_id=target.id,
                target_name=target.name,
                trigger=trigger,
                has_error=finding.has_error,
            )
            return finding

    def _should_check(self, target: MonitorTarget) -> bool:
        """判断目标是否到达巡检时间。"""
        if not target.enabled:
            return False
        now = _utcnow()
        last_checked = target.last_checked_at
        if not last_checked:
            return True
        return (now - last_checked).total_seconds() >= int(target.check_interval_sec or 60)

    async def _scan_target(self, target: MonitorTarget) -> PageMonitorFinding:
        """巡检单个页面。"""
        checked_at = _utcnow()
        playwright_result = await self._scan_with_playwright(target)
        if playwright_result is None:
            playwright_result = await self._scan_with_http(target)

        frontend_errors = list(playwright_result.get("frontend_errors") or [])
        api_errors = list(playwright_result.get("api_errors") or [])
        browser_error = str(playwright_result.get("browser_error") or "").strip()
        summary = str(playwright_result.get("summary") or "").strip()
        observed_query_apis = list(playwright_result.get("observed_query_apis") or [])
        triggered_actions = list(playwright_result.get("triggered_actions") or [])
        replay_api_errors = list(playwright_result.get("replay_api_errors") or [])
        has_error = bool(frontend_errors or api_errors or browser_error)
        if not summary:
            if has_error:
                summary = (
                    f"页面感知检测到异常（前端报错{len(frontend_errors)}条，"
                    f"接口异常{len(api_errors)}条，回放异常{len(replay_api_errors)}条）"
                )
            else:
                summary = (
                    f"页面感知正常（识别查询接口{len(observed_query_apis)}个，"
                    f"触发交互{len(triggered_actions)}次）"
                )
        return PageMonitorFinding(
            target_id=target.id,
            target_name=target.name,
            url=target.url,
            checked_at=checked_at,
            has_error=has_error,
            frontend_errors=frontend_errors[:10],
            api_errors=api_errors[:20],
            browser_error=browser_error[:500],
            summary=summary[:300],
            raw=dict(playwright_result or {}),
        )

    async def _scan_with_playwright(self, target: MonitorTarget) -> Optional[Dict[str, Any]]:
        """使用 Playwright 巡检页面，采集前端异常与接口失败。"""
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return None

        frontend_errors: List[str] = []
        api_errors: List[str] = []
        replay_api_errors: List[str] = []
        observed_query_api_map: Dict[str, Dict[str, Any]] = {}
        triggered_actions: List[str] = []
        browser_error = ""
        replay_started = {"value": False}

        def _record_response(resp: Any) -> None:
            """记录页面接口响应与异常。"""
            status = int(getattr(resp, "status", 0) or 0)
            request = getattr(resp, "request", None)
            method = str(getattr(request, "method", "") or "").upper()
            url = str(getattr(resp, "url", "") or "")
            resource_type = str(getattr(request, "resource_type", "") or "").lower()
            phase = "replay" if replay_started.get("value") else "initial"
            if resource_type in {"xhr", "fetch"} and self._is_query_api_candidate(method=method, url=url):
                api_key = self._api_fingerprint(method=method, url=url)
                observed_query_api_map[api_key] = {
                    "method": method,
                    "url": self._strip_url_for_display(url),
                    "phase": phase,
                    "status": status,
                }
            if status >= 400 and resource_type in {"xhr", "fetch", "document"}:
                msg = f"{status} {method} {url}"
                api_errors.append(msg)
                if phase == "replay":
                    replay_api_errors.append(msg)

        def _record_request_failed(req: Any) -> None:
            """记录接口请求失败事件。"""
            resource_type = str(getattr(req, "resource_type", "") or "").lower()
            if resource_type not in {"xhr", "fetch", "document"}:
                return
            method = str(getattr(req, "method", "") or "").upper()
            url = str(getattr(req, "url", "") or "")
            failure = str(getattr(req, "failure", "") or "")
            msg = f"failed {method} {url} {failure}".strip()
            api_errors.append(msg)
            if replay_started.get("value"):
                replay_api_errors.append(msg)
            if self._is_query_api_candidate(method=method, url=url):
                api_key = self._api_fingerprint(method=method, url=url)
                observed_query_api_map[api_key] = {
                    "method": method,
                    "url": self._strip_url_for_display(url),
                    "phase": "replay" if replay_started.get("value") else "initial",
                    "status": "failed",
                }

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                request_headers = self._build_request_headers(target)
                context = await browser.new_context(
                    ignore_https_errors=True,
                    extra_http_headers=request_headers or None,
                )
                page = await context.new_page()

                # 中文注释：采集 pageerror 和 console.error，覆盖前端运行时异常。
                page.on("pageerror", lambda exc: frontend_errors.append(str(exc)))
                page.on(
                    "console",
                    lambda msg: frontend_errors.append(f"console:{msg.type} {msg.text}")
                    if str(msg.type or "").lower() == "error"
                    else None,
                )
                # 中文注释：统一记录接口响应，可同时用于“接口报错监控”和“查询接口清单识别”。
                page.on("response", _record_response)
                page.on("requestfailed", _record_request_failed)

                await page.goto(
                    target.url,
                    wait_until="networkidle",
                    timeout=max(5, int(target.timeout_sec or 20)) * 1000,
                )
                await page.wait_for_timeout(800)
                # 中文注释：进入“回放阶段”后自动点击查询类控件，主动触发页面查询请求用于二次观测。
                replay_started["value"] = True
                triggered_actions = await self._trigger_query_actions(page)
                if triggered_actions:
                    await page.wait_for_timeout(900)
                await context.close()
                await browser.close()
        except Exception as exc:
            browser_error = str(exc)

        has_error = bool(frontend_errors or api_errors or browser_error)
        observed_query_apis = list(observed_query_api_map.values())
        return {
            "checker": "playwright",
            "has_error": has_error,
            "frontend_errors": frontend_errors,
            "api_errors": api_errors,
            "replay_api_errors": replay_api_errors,
            "observed_query_apis": observed_query_apis,
            "triggered_actions": triggered_actions,
            "browser_error": browser_error,
            "summary": (
                f"Playwright 页面感知发现异常（查询接口{len(observed_query_apis)}个，"
                f"触发交互{len(triggered_actions)}次，回放异常{len(replay_api_errors)}条）"
                if has_error
                else (
                    f"Playwright 页面感知正常（查询接口{len(observed_query_apis)}个，"
                    f"触发交互{len(triggered_actions)}次）"
                )
            ),
        }

    async def _scan_with_http(self, target: MonitorTarget) -> Dict[str, Any]:
        """当浏览器巡检不可用时降级为 HTTP 探测。"""
        api_errors: List[str] = []
        browser_error = ""
        try:
            timeout = httpx.Timeout(timeout=max(5, int(target.timeout_sec or 20)))
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                request_headers = self._build_request_headers(target)
                resp = await client.get(target.url, headers=request_headers or None)
                if int(resp.status_code or 0) >= 400:
                    api_errors.append(f"{resp.status_code} GET {target.url}")
        except Exception as exc:
            browser_error = str(exc)
        has_error = bool(api_errors or browser_error)
        return {
            "checker": "http",
            "has_error": has_error,
            "frontend_errors": [],
            "api_errors": api_errors,
            "browser_error": browser_error,
            "summary": "HTTP 巡检发现异常" if has_error else "HTTP 巡检正常",
        }

    async def _record_finding(self, finding: PageMonitorFinding) -> None:
        """持久化巡检事件。"""
        payload = finding.model_dump(mode="json")
        await sqlite_store.execute(
            """
            INSERT INTO monitor_scan_events(target_id, created_at, status, payload_json)
            VALUES(?, ?, ?, ?)
            """,
            [
                finding.target_id,
                finding.checked_at.isoformat(),
                "error" if finding.has_error else "ok",
                sqlite_store.dumps_json(payload),
            ],
        )

    async def _handle_anomaly(self, target: MonitorTarget, finding: PageMonitorFinding) -> None:
        """异常命中后自动创建故障并拉起 RCA。"""
        now = _utcnow()
        if target.last_triggered_at:
            elapsed = (now - target.last_triggered_at).total_seconds()
            if elapsed < int(target.cooldown_sec or 300):
                logger.info(
                    "page_monitor_cooldown_skip",
                    target_id=target.id,
                    target_name=target.name,
                    elapsed=elapsed,
                )
                return

        query = " ".join(
            [
                target.name,
                target.url,
                *finding.frontend_errors[:2],
                *finding.api_errors[:3],
            ]
        ).strip()
        kb_items = await knowledge_service.search_reference_entries(query=query, limit=3)
        kb_summaries = [f"{item.get('title')}: {item.get('summary')}" for item in kb_items]
        kb_text = "\n".join(kb_summaries)

        desc_lines = [
            f"监控目标：{target.name}",
            f"页面地址：{target.url}",
            f"异常摘要：{finding.summary}",
        ]
        if finding.frontend_errors:
            desc_lines.append("前端报错：")
            desc_lines.extend([f"- {line}" for line in finding.frontend_errors[:5]])
        if finding.api_errors:
            desc_lines.append("接口异常：")
            desc_lines.extend([f"- {line}" for line in finding.api_errors[:8]])
        raw_query_apis = list((finding.raw or {}).get("observed_query_apis") or [])
        if raw_query_apis:
            desc_lines.append("识别到的查询接口：")
            for item in raw_query_apis[:8]:
                method = str((item or {}).get("method") or "").upper()
                api_url = str((item or {}).get("url") or "")
                phase = str((item or {}).get("phase") or "")
                status = str((item or {}).get("status") or "")
                desc_lines.append(f"- [{phase}] {status} {method} {api_url}".strip())
        if kb_text:
            desc_lines.append("知识库建议：")
            desc_lines.extend([f"- {line}" for line in kb_summaries[:3]])
        description = "\n".join(desc_lines)[:4000]

        incident = await incident_service.create_incident(
            IncidentCreateModel(
                title=f"[AutoMonitor] {target.name} 页面异常",
                description=description,
                source="monitor",
                severity=IncidentSeverity(str(target.severity or "high")),
                service_name=target.service_name or target.name,
                environment=target.environment or "prod",
                log_content="\n".join([*finding.frontend_errors, *finding.api_errors])[:50000],
                exception_stack=finding.browser_error[:50000] if finding.browser_error else "",
                metadata={
                    "monitor_target_id": target.id,
                    "monitor_target_name": target.name,
                    "monitor_url": target.url,
                    "monitor_finding": finding.model_dump(mode="json"),
                    "knowledge_recommendations": kb_items,
                },
            )
        )
        session = await debate_service.create_session(
            incident,
            max_rounds=max(1, int(settings.PAGE_MONITOR_AUTO_MAX_ROUNDS or 1)),
            analysis_depth_mode=str(settings.PAGE_MONITOR_AUTO_ANALYSIS_DEPTH_MODE or "standard"),
            execution_mode=str(settings.PAGE_MONITOR_AUTO_EXECUTION_MODE or "quick"),
        )
        await incident_service.update_incident(
            incident.id,
            IncidentUpdate(
                status=IncidentStatus.ANALYZING,
                debate_session_id=session.id,
                fix_suggestion=("\n".join(kb_summaries[:3]) or None),
            ),
        )

        async def _run() -> Dict[str, Any]:
            result = await debate_service.execute_debate(session.id, retry_failed_only=False)
            await incident_service.update_incident(
                incident.id,
                IncidentUpdate(
                    status=IncidentStatus.RESOLVED,
                    debate_session_id=session.id,
                    root_cause=result.root_cause,
                    fix_suggestion=result.fix_recommendation.summary if result.fix_recommendation else None,
                    impact_analysis=result.impact_analysis.model_dump() if result.impact_analysis else None,
                ),
            )
            return {"incident_id": incident.id, "session_id": session.id, "confidence": float(result.confidence or 0.0)}

        task_id = task_queue.submit(_run, timeout_seconds=max(60, int(settings.DEBATE_TIMEOUT or 600)))
        target.last_triggered_at = now
        target.updated_at = now
        await self._save_target(target)
        logger.info(
            "page_monitor_triggered_incident",
            target_id=target.id,
            incident_id=incident.id,
            session_id=session.id,
            task_id=task_id,
            kb_matches=len(kb_items),
        )

    async def _save_target(self, target: MonitorTarget) -> None:
        """保存巡检目标。"""
        payload = target.model_dump(mode="json")
        await sqlite_store.execute(
            """
            INSERT INTO monitor_targets(
                id, name, url, enabled, check_interval_sec, timeout_sec, cooldown_sec,
                last_checked_at, last_triggered_at, created_at, updated_at, payload_json
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                url=excluded.url,
                enabled=excluded.enabled,
                check_interval_sec=excluded.check_interval_sec,
                timeout_sec=excluded.timeout_sec,
                cooldown_sec=excluded.cooldown_sec,
                last_checked_at=excluded.last_checked_at,
                last_triggered_at=excluded.last_triggered_at,
                updated_at=excluded.updated_at,
                payload_json=excluded.payload_json
            """,
            [
                target.id,
                target.name,
                target.url,
                1 if target.enabled else 0,
                int(target.check_interval_sec),
                int(target.timeout_sec),
                int(target.cooldown_sec),
                target.last_checked_at.isoformat() if target.last_checked_at else "",
                target.last_triggered_at.isoformat() if target.last_triggered_at else "",
                target.created_at.isoformat(),
                target.updated_at.isoformat(),
                sqlite_store.dumps_json(payload),
            ],
        )

    @staticmethod
    def _build_request_headers(target: MonitorTarget) -> Dict[str, str]:
        """构建巡检请求头。"""
        headers: Dict[str, str] = {}
        cookie_header = str(getattr(target, "cookie_header", "") or "").strip()
        if cookie_header:
            # 中文注释：统一使用 Cookie 头透传登录态，Playwright 与 HTTP 降级逻辑共用同一份配置。
            headers["Cookie"] = cookie_header
        return headers

    @staticmethod
    def _api_fingerprint(*, method: str, url: str) -> str:
        """生成接口指纹，便于接口去重。"""
        parsed = urlparse(str(url or ""))
        return f"{str(method or '').upper()} {parsed.path or '/'}"

    @staticmethod
    def _strip_url_for_display(url: str) -> str:
        """对 URL 做脱敏与裁剪，避免 query 参数泄漏敏感值。"""
        parsed = urlparse(str(url or ""))
        if not parsed.query:
            return str(url or "")
        query_keys = list(parse_qs(parsed.query).keys())
        query_hint = "&".join([f"{key}=*" for key in query_keys[:8]])
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_hint}"

    @staticmethod
    def _is_query_api_candidate(*, method: str, url: str) -> bool:
        """判断接口是否属于查询类请求。"""
        method_up = str(method or "").upper()
        parsed = urlparse(str(url or ""))
        path = str(parsed.path or "").lower()
        query = str(parsed.query or "").lower()
        if method_up == "GET":
            return True
        # 中文注释：POST 也可能是“查询接口”（如 /search、/query），按关键词识别以覆盖常见后端风格。
        keywords = ("query", "search", "list", "page", "find", "lookup", "filter")
        if any(token in path for token in keywords):
            return True
        if any(token in query for token in keywords):
            return True
        return False

    async def _trigger_query_actions(self, page: Any) -> List[str]:
        """自动触发页面查询操作，扩大接口观测覆盖。"""
        action_labels: List[str] = []
        selectors = [
            "button:has-text('查询')",
            "button:has-text('搜索')",
            "button:has-text('查找')",
            "[role='button']:has-text('查询')",
            "[role='button']:has-text('搜索')",
            "[aria-label*='查询']",
            "[aria-label*='搜索']",
            "[data-testid*='search']",
            "[data-testid*='query']",
            "input[type='search']",
        ]
        max_actions = 5
        for selector in selectors:
            if len(action_labels) >= max_actions:
                break
            with suppress(Exception):
                locator = page.locator(selector)
                count = await locator.count()
                if count <= 0:
                    continue
                for idx in range(min(count, 2)):
                    if len(action_labels) >= max_actions:
                        break
                    item = locator.nth(idx)
                    if not await item.is_visible():
                        continue
                    if selector.startswith("input"):
                        # 中文注释：搜索输入框优先触发回车，尽量避免输入新值污染业务状态。
                        await item.focus(timeout=1200)
                        await page.keyboard.press("Enter")
                        action_labels.append(f"enter:{selector}")
                    else:
                        label = (await item.inner_text(timeout=800)).strip() if hasattr(item, "inner_text") else ""
                        if re.search(r"(删除|移除|取消|清空)", label):
                            continue
                        await item.click(timeout=1500)
                        action_labels.append(f"click:{label or selector}")
                    await page.wait_for_timeout(500)
        return action_labels[:max_actions]

    @staticmethod
    def _row_to_target(raw: Any) -> MonitorTarget:
        payload = sqlite_store.loads_json(raw, default={}) or {}
        target = MonitorTarget(**payload)
        target.last_checked_at = _from_iso(payload.get("last_checked_at"))
        target.last_triggered_at = _from_iso(payload.get("last_triggered_at"))
        target.created_at = _from_iso(payload.get("created_at")) or _utcnow()
        target.updated_at = _from_iso(payload.get("updated_at")) or target.created_at
        return target



page_monitoring_service = PageMonitoringService()
