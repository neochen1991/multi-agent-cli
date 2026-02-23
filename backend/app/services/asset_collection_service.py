"""
资产采集服务
Asset Collection Service

负责采集三态资产：运行态、开发态、设计态
"""

import os
import asyncio
import json
import subprocess
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional
from pathlib import Path
import time

import structlog

from app.models.asset import (
    RuntimeAsset,
    DevAsset,
    DesignAsset,
    RuntimeAssetType,
    DevAssetType,
    DesignAssetType,
    DomainModel,
    AggregateRoot,
)
from app.core.autogen_client import autogen_client
from app.core.json_utils import extract_json_dict
from app.config import settings

logger = structlog.get_logger()


class AssetCollectionService:
    """资产采集服务"""
    
    def __init__(self):
        self.code_repos_path = os.getenv("CODE_REPOS_PATH", "/tmp/repos")
        self.design_docs_path = os.getenv("DESIGN_DOCS_PATH", "/tmp/design_docs")
    
    # ==================== 运行态资产采集 ====================
    
    async def collect_runtime_assets(
        self,
        log_content: Optional[str] = None,
        log_file_path: Optional[str] = None,
        metrics_data: Optional[Dict[str, Any]] = None,
        trace_data: Optional[Dict[str, Any]] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> List[RuntimeAsset]:
        """
        采集运行态资产
        
        Args:
            log_content: 日志内容
            log_file_path: 日志文件路径
            metrics_data: 指标数据
            trace_data: 链路追踪数据
            
        Returns:
            采集到的运行态资产列表
        """
        assets = []
        
        # 采集日志资产
        if log_content:
            asset = await self._collect_log_asset(log_content, event_callback=event_callback)
            if asset:
                assets.append(asset)
        
        if log_file_path and os.path.exists(log_file_path):
            asset = await self._collect_log_file_asset(log_file_path, event_callback=event_callback)
            if asset:
                assets.append(asset)
        
        # 采集指标资产
        if metrics_data:
            asset = await self._collect_metrics_asset(metrics_data)
            if asset:
                assets.append(asset)
        
        # 采集链路追踪资产
        if trace_data:
            asset = await self._collect_trace_asset(trace_data)
            if asset:
                assets.append(asset)
        
        logger.info("runtime_assets_collected", count=len(assets))
        return assets
    
    async def _collect_log_asset(
        self,
        log_content: str,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Optional[RuntimeAsset]:
        """采集日志资产"""
        try:
            # 使用 AutoGen 多 Agent 分析日志
            parsed_data = await self._parse_log_with_ai(
                log_content,
                event_callback=event_callback,
            )
            
            asset = RuntimeAsset(
                id=f"rt_log_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                type=RuntimeAssetType.LOG,
                source="application_log",
                raw_content=log_content,
                parsed_data=parsed_data,
                timestamp=datetime.utcnow()
            )
            return asset
        except Exception as e:
            logger.error("log_asset_collection_failed", error=str(e))
            return None
    
    async def _collect_log_file_asset(
        self,
        file_path: str,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Optional[RuntimeAsset]:
        """从文件采集日志资产"""
        try:
            with open(file_path, 'r') as f:
                log_content = f.read()
            return await self._collect_log_asset(log_content, event_callback=event_callback)
        except Exception as e:
            logger.error("log_file_collection_failed", error=str(e), file_path=file_path)
            return None
    
    async def _collect_metrics_asset(self, metrics_data: Dict[str, Any]) -> Optional[RuntimeAsset]:
        """采集指标资产"""
        try:
            asset = RuntimeAsset(
                id=f"rt_metric_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                type=RuntimeAssetType.METRIC,
                source="monitoring_system",
                parsed_data=metrics_data,
                timestamp=datetime.utcnow()
            )
            return asset
        except Exception as e:
            logger.error("metrics_asset_collection_failed", error=str(e))
            return None
    
    async def _collect_trace_asset(self, trace_data: Dict[str, Any]) -> Optional[RuntimeAsset]:
        """采集链路追踪资产"""
        try:
            asset = RuntimeAsset(
                id=f"rt_trace_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                type=RuntimeAssetType.TRACE,
                source="tracing_system",
                parsed_data=trace_data,
                timestamp=datetime.utcnow()
            )
            return asset
        except Exception as e:
            logger.error("trace_asset_collection_failed", error=str(e))
            return None
    
    async def _parse_log_with_ai(
        self,
        log_content: str,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """使用 AutoGen 多 Agent 解析日志"""
        try:
            # 创建会话
            session = await autogen_client.create_session(
                title="日志解析分析"
            )
            
            # 构建提示
            prompt = f"""请分析以下应用日志，提取关键信息：

```
{log_content[:5000]}
```

请提取以下信息并以 JSON 格式返回：
1. exception_type: 异常类型（如果有）
2. exception_message: 异常消息
3. stack_trace: 堆栈跟踪关键信息（类名、方法名、文件名、行号）
4. error_level: 日志级别（ERROR/WARN/INFO等）
5. timestamp: 日志时间戳
6. service_name: 服务名称（如果能识别）
7. key_classes: 涉及的关键类
8. key_methods: 涉及的关键方法

返回格式：
{{
    "exception_type": "...",
    "exception_message": "...",
    "stack_trace": [...],
    "error_level": "...",
    "timestamp": "...",
    "service_name": "...",
    "key_classes": [...],
    "key_methods": [...]
}}"""

            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_started",
                    "phase": "asset_analysis",
                    "stage": "runtime_log_parse",
                    "session_id": session.id,
                    "model": settings.default_model_config.get("name"),
                    "prompt_preview": prompt[:800],
                },
            )
            started_at = time.perf_counter()
            # 调用 LLM
            call_timeout = max(12, min(settings.llm_total_timeout, 35))
            result = await asyncio.wait_for(
                autogen_client.send_prompt(
                    session_id=session.id,
                    parts=[{"type": "text", "text": prompt}],
                    model=settings.default_model_config,
                    max_tokens=700,
                    trace_callback=event_callback,
                    trace_context={
                        "phase": "asset_analysis",
                        "stage": "runtime_log_parse",
                    },
                ),
                timeout=call_timeout,
            )
            
            # 解析结果
            if result and "content" in result:
                parsed = extract_json_dict(result["content"])
                await self._emit_event(
                    event_callback,
                    {
                        "type": "autogen_call_completed",
                        "phase": "asset_analysis",
                        "stage": "runtime_log_parse",
                        "session_id": session.id,
                        "model": settings.default_model_config.get("name"),
                        "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                        "response_preview": result.get("content", "")[:1000],
                        "parsed": bool(parsed),
                    },
                )
                if parsed:
                    return parsed

            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_completed",
                    "phase": "asset_analysis",
                    "stage": "runtime_log_parse",
                    "session_id": session.id,
                    "model": settings.default_model_config.get("name"),
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "response_preview": (result or {}).get("content", "")[:1000] if isinstance(result, dict) else "",
                    "parsed": False,
                },
            )
            return {}
            
        except Exception as e:
            error_text = str(e).strip() or e.__class__.__name__
            logger.error("ai_log_parse_failed", error=error_text)
            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_failed",
                    "phase": "asset_analysis",
                    "stage": "runtime_log_parse",
                    "session_id": session.id if "session" in locals() else None,
                    "model": settings.default_model_config.get("name"),
                    "prompt_preview": prompt[:800] if "prompt" in locals() else "",
                    "error": error_text,
                },
            )
            raise RuntimeError(f"运行态日志 LLM 解析失败: {error_text}") from e
    
    # ==================== 开发态资产采集 ====================
    
    async def collect_dev_assets(
        self,
        repo_url: Optional[str] = None,
        repo_path: Optional[str] = None,
        target_classes: Optional[List[str]] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> List[DevAsset]:
        """
        采集开发态资产
        
        Args:
            repo_url: Git 仓库 URL
            repo_path: 本地仓库路径
            target_classes: 目标类名列表
            
        Returns:
            采集到的开发态资产列表
        """
        assets = []
        
        # 确定仓库路径
        if repo_url and not repo_path:
            repo_path = await self._clone_repo(repo_url)
        
        if not repo_path or not os.path.exists(repo_path):
            logger.warning("repo_path_not_found", path=repo_path)
            return assets
        
        # 采集代码资产
        if target_classes:
            for class_name in target_classes:
                asset = await self._collect_class_asset(
                    repo_path,
                    class_name,
                    event_callback=event_callback,
                )
                if asset:
                    assets.append(asset)
        else:
            # 采集所有代码资产
            assets.extend(await self._collect_all_code_assets(repo_path))
        
        logger.info("dev_assets_collected", count=len(assets))
        return assets
    
    async def _clone_repo(self, repo_url: str) -> Optional[str]:
        """克隆 Git 仓库"""
        try:
            repo_name = repo_url.split("/")[-1].replace(".git", "")
            repo_path = os.path.join(self.code_repos_path, repo_name)
            
            if os.path.exists(repo_path):
                # 已存在，拉取最新代码
                subprocess.run(
                    ["git", "pull"],
                    cwd=repo_path,
                    check=True,
                    capture_output=True
                )
            else:
                # 克隆仓库
                os.makedirs(self.code_repos_path, exist_ok=True)
                subprocess.run(
                    ["git", "clone", repo_url, repo_path],
                    check=True,
                    capture_output=True
                )
            
            return repo_path
        except Exception as e:
            logger.error("repo_clone_failed", error=str(e), repo_url=repo_url)
            return None
    
    async def _collect_class_asset(
        self,
        repo_path: str,
        class_name: str,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Optional[DevAsset]:
        """采集指定类的代码资产"""
        try:
            # 搜索类文件
            class_file = await self._find_class_file(repo_path, class_name)
            if not class_file:
                return None
            
            # 读取文件内容
            with open(class_file, 'r') as f:
                content = f.read()
            
            # 使用 AI 解析代码结构
            parsed_data = await self._parse_code_with_ai(
                content,
                class_name,
                event_callback=event_callback,
            )
            
            asset = DevAsset(
                id=f"dev_code_{class_name.lower()}",
                type=DevAssetType.CODE,
                name=os.path.basename(class_file),
                path=class_file,
                language=self._detect_language(class_file),
                content=content,
                parsed_data=parsed_data,
            )
            return asset
        except Exception as e:
            logger.error("class_asset_collection_failed", error=str(e), class_name=class_name)
            return None
    
    async def _find_class_file(self, repo_path: str, class_name: str) -> Optional[str]:
        """查找类文件"""
        # Java 类文件
        java_file = os.path.join(repo_path, f"**/{class_name}.java")
        matches = list(Path(repo_path).glob(f"**/{class_name}.java"))
        if matches:
            return str(matches[0])
        
        # Python 类文件
        matches = list(Path(repo_path).glob(f"**/{class_name.lower()}.py"))
        if matches:
            return str(matches[0])
        
        return None
    
    async def _parse_code_with_ai(
        self,
        code_content: str,
        class_name: str,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """使用 AutoGen 多 Agent 解析代码结构"""
        try:
            session = await autogen_client.create_session(
                title=f"代码结构分析 - {class_name}"
            )
            
            prompt = f"""请分析以下代码，提取结构信息：

```java
{code_content[:8000]}
```

请提取以下信息并以 JSON 格式返回：
1. class_name: 类名
2. package: 包名
3. is_service: 是否是 Service 类
4. is_controller: 是否是 Controller 类
5. is_repository: 是否是 Repository 类
6. dependencies: 依赖的其他类
7. methods: 方法列表（名称、参数、返回类型）
8. fields: 字段列表
9. annotations: 注解列表

返回格式：
{{
    "class_name": "...",
    "package": "...",
    "is_service": true/false,
    "is_controller": true/false,
    "is_repository": true/false,
    "dependencies": [...],
    "methods": [...],
    "fields": [...],
    "annotations": [...]
}}"""

            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_started",
                    "phase": "asset_analysis",
                    "stage": "dev_code_parse",
                    "session_id": session.id,
                    "model": settings.default_model_config.get("name"),
                    "target": class_name,
                    "prompt_preview": prompt[:800],
                },
            )
            started_at = time.perf_counter()
            call_timeout = max(20, min(settings.llm_timeout, 90))
            result = await asyncio.wait_for(
                autogen_client.send_prompt(
                    session_id=session.id,
                    parts=[{"type": "text", "text": prompt}],
                    model=settings.default_model_config,
                    max_tokens=800,
                    trace_callback=event_callback,
                    trace_context={
                        "phase": "asset_analysis",
                        "stage": "dev_code_parse",
                        "target": class_name,
                    },
                ),
                timeout=call_timeout,
            )
            
            if result and "content" in result:
                parsed = extract_json_dict(result["content"])
                await self._emit_event(
                    event_callback,
                    {
                        "type": "autogen_call_completed",
                        "phase": "asset_analysis",
                        "stage": "dev_code_parse",
                        "session_id": session.id,
                        "model": settings.default_model_config.get("name"),
                        "target": class_name,
                        "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                        "response_preview": result.get("content", "")[:1000],
                        "parsed": bool(parsed),
                    },
                )
                if parsed:
                    return parsed

            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_completed",
                    "phase": "asset_analysis",
                    "stage": "dev_code_parse",
                    "session_id": session.id,
                    "model": settings.default_model_config.get("name"),
                    "target": class_name,
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "response_preview": (result or {}).get("content", "")[:1000] if isinstance(result, dict) else "",
                    "parsed": False,
                },
            )
            return {}
            
        except Exception as e:
            error_text = str(e).strip() or e.__class__.__name__
            logger.error("ai_code_parse_failed", error=error_text)
            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_failed",
                    "phase": "asset_analysis",
                    "stage": "dev_code_parse",
                    "session_id": session.id if "session" in locals() else None,
                    "target": class_name,
                    "model": settings.default_model_config.get("name"),
                    "prompt_preview": prompt[:800] if "prompt" in locals() else "",
                    "error": error_text,
                },
            )
            raise RuntimeError(f"开发态代码 LLM 解析失败: {error_text}") from e
    
    def _detect_language(self, file_path: str) -> str:
        """检测编程语言"""
        ext = os.path.splitext(file_path)[1].lower()
        language_map = {
            ".java": "java",
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".go": "go",
            ".rs": "rust",
        }
        return language_map.get(ext, "unknown")
    
    async def _collect_all_code_assets(self, repo_path: str) -> List[DevAsset]:
        """采集所有代码资产"""
        assets = []
        # 采集主要 Java 文件
        for java_file in Path(repo_path).glob("**/*.java"):
            if "test" in str(java_file).lower():
                continue
            try:
                with open(java_file, 'r') as f:
                    content = f.read()
                
                asset = DevAsset(
                    id=f"dev_{java_file.stem}",
                    type=DevAssetType.CODE,
                    name=java_file.name,
                    path=str(java_file),
                    language="java",
                    content=content,
                )
                assets.append(asset)
                
                # 限制数量
                if len(assets) >= 50:
                    break
            except Exception:
                continue
        
        return assets
    
    # ==================== 设计态资产采集 ====================
    
    async def collect_design_assets(
        self,
        domain_name: Optional[str] = None,
        design_docs_path: Optional[str] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> List[DesignAsset]:
        """
        采集设计态资产
        
        Args:
            domain_name: 领域名称
            design_docs_path: 设计文档路径
            
        Returns:
            采集到的设计态资产列表
        """
        assets = []
        
        docs_path = design_docs_path or self.design_docs_path
        
        if not os.path.exists(docs_path):
            logger.warning("design_docs_path_not_found", path=docs_path)
            return assets
        
        # 采集 DDD 文档
        ddd_assets = await self._collect_ddd_docs(
            docs_path,
            domain_name,
            event_callback=event_callback,
        )
        assets.extend(ddd_assets)
        
        # 采集 API 规范
        api_assets = await self._collect_api_specs(docs_path)
        assets.extend(api_assets)
        
        # 采集数据库设计
        db_assets = await self._collect_db_schemas(docs_path)
        assets.extend(db_assets)
        
        logger.info("design_assets_collected", count=len(assets))
        return assets
    
    async def _collect_ddd_docs(
        self,
        docs_path: str,
        domain_name: Optional[str] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> List[DesignAsset]:
        """采集 DDD 文档"""
        assets = []
        
        # 查找 DDD 文档
        ddd_patterns = ["**/ddd*.md", "**/*领域*.md", "**/*domain*.md"]
        for pattern in ddd_patterns:
            for doc_file in Path(docs_path).glob(pattern):
                try:
                    with open(doc_file, 'r') as f:
                        content = f.read()
                    
                    # 使用 AI 解析 DDD 文档
                    parsed_data = await self._parse_ddd_doc_with_ai(
                        content,
                        event_callback=event_callback,
                    )
                    
                    asset = DesignAsset(
                        id=f"des_ddd_{doc_file.stem}",
                        type=DesignAssetType.DDD_DOCUMENT,
                        name=doc_file.name,
                        content=content,
                        parsed_data=parsed_data,
                        domain=parsed_data.get("domain_name"),
                    )
                    assets.append(asset)
                except Exception as e:
                    logger.error("ddd_doc_collection_failed", error=str(e))
        
        return assets
    
    async def _parse_ddd_doc_with_ai(
        self,
        doc_content: str,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """使用 AutoGen 多 Agent 解析 DDD 文档"""
        try:
            session = await autogen_client.create_session(
                title="DDD 文档解析"
            )
            
            prompt = f"""请分析以下 DDD 领域设计文档，提取关键信息：

```
{doc_content[:8000]}
```

请提取以下信息并以 JSON 格式返回：
1. domain_name: 领域名称
2. aggregates: 聚合列表
3. entities: 实体列表
4. value_objects: 值对象列表
5. domain_services: 领域服务列表
6. repositories: 仓储列表
7. bounded_context: 限界上下文
8. owner_team: 责任团队

返回格式：
{{
    "domain_name": "...",
    "aggregates": [...],
    "entities": [...],
    "value_objects": [...",
    "domain_services": [...],
    "repositories": [...],
    "bounded_context": "...",
    "owner_team": "..."
}}"""

            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_started",
                    "phase": "asset_analysis",
                    "stage": "design_ddd_parse",
                    "session_id": session.id,
                    "model": settings.default_model_config.get("name"),
                    "prompt_preview": prompt[:800],
                },
            )
            started_at = time.perf_counter()
            call_timeout = max(20, min(settings.llm_timeout, 90))
            result = await asyncio.wait_for(
                autogen_client.send_prompt(
                    session_id=session.id,
                    parts=[{"type": "text", "text": prompt}],
                    model=settings.default_model_config,
                    max_tokens=800,
                    trace_callback=event_callback,
                    trace_context={
                        "phase": "asset_analysis",
                        "stage": "design_ddd_parse",
                    },
                ),
                timeout=call_timeout,
            )
            
            if result and "content" in result:
                parsed = extract_json_dict(result["content"])
                await self._emit_event(
                    event_callback,
                    {
                        "type": "autogen_call_completed",
                        "phase": "asset_analysis",
                        "stage": "design_ddd_parse",
                        "session_id": session.id,
                        "model": settings.default_model_config.get("name"),
                        "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                        "response_preview": result.get("content", "")[:1000],
                        "parsed": bool(parsed),
                    },
                )
                if parsed:
                    return parsed

            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_completed",
                    "phase": "asset_analysis",
                    "stage": "design_ddd_parse",
                    "session_id": session.id,
                    "model": settings.default_model_config.get("name"),
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "response_preview": (result or {}).get("content", "")[:1000] if isinstance(result, dict) else "",
                    "parsed": False,
                },
            )
            return {}
            
        except Exception as e:
            error_text = str(e).strip() or e.__class__.__name__
            logger.error("ai_ddd_parse_failed", error=error_text)
            await self._emit_event(
                event_callback,
                {
                    "type": "autogen_call_failed",
                    "phase": "asset_analysis",
                    "stage": "design_ddd_parse",
                    "session_id": session.id if "session" in locals() else None,
                    "model": settings.default_model_config.get("name"),
                    "prompt_preview": prompt[:800] if "prompt" in locals() else "",
                    "error": error_text,
                },
            )
            raise RuntimeError(f"设计态 DDD 文档 LLM 解析失败: {error_text}") from e
    
    async def _collect_api_specs(self, docs_path: str) -> List[DesignAsset]:
        """采集 API 规范"""
        assets = []

        patterns = [
            "**/*api*.json",
            "**/*api*.yaml",
            "**/*api*.yml",
            "**/*openapi*.json",
            "**/*openapi*.yaml",
            "**/*openapi*.yml",
            "**/*swagger*.json",
            "**/*swagger*.yaml",
            "**/*swagger*.yml",
        ]
        seen = set()
        for pattern in patterns:
            for api_file in Path(docs_path).glob(pattern):
                if not api_file.is_file():
                    continue
                key = str(api_file.resolve())
                if key in seen:
                    continue
                seen.add(key)
                try:
                    with open(api_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    asset = DesignAsset(
                        id=f"des_api_{api_file.stem}",
                        type=DesignAssetType.API_SPEC,
                        name=api_file.name,
                        content=content,
                    )
                    assets.append(asset)
                except Exception as e:
                    logger.error("api_spec_collection_failed", error=str(e), file=str(api_file))

        return assets
    
    async def _collect_db_schemas(self, docs_path: str) -> List[DesignAsset]:
        """采集数据库设计"""
        assets = []

        keywords = ("db", "database", "schema", "table", "ddl")
        extensions = ("sql", "md", "json", "yaml", "yml")
        seen = set()

        for ext in extensions:
            for db_file in Path(docs_path).glob(f"**/*.{ext}"):
                if not db_file.is_file():
                    continue
                name_lower = db_file.name.lower()
                if not any(keyword in name_lower for keyword in keywords):
                    continue

                key = str(db_file.resolve())
                if key in seen:
                    continue
                seen.add(key)

                try:
                    with open(db_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    asset = DesignAsset(
                        id=f"des_db_{db_file.stem}",
                        type=DesignAssetType.DB_SCHEMA,
                        name=db_file.name,
                        content=content,
                    )
                    assets.append(asset)
                except Exception as e:
                    logger.error("db_schema_collection_failed", error=str(e), file=str(db_file))

        return assets
    
    # ==================== 综合采集 ====================
    
    async def collect_all_assets(
        self,
        log_content: Optional[str] = None,
        repo_url: Optional[str] = None,
        target_classes: Optional[List[str]] = None,
        domain_name: Optional[str] = None,
    ) -> Dict[str, List]:
        """
        综合采集所有三态资产
        
        Args:
            log_content: 日志内容
            repo_url: Git 仓库 URL
            target_classes: 目标类名列表
            domain_name: 领域名称
            
        Returns:
            包含三态资产的字典
        """
        runtime_assets = await self.collect_runtime_assets(log_content=log_content)
        
        dev_assets = await self.collect_dev_assets(
            repo_url=repo_url,
            target_classes=target_classes
        )
        
        design_assets = await self.collect_design_assets(domain_name=domain_name)
        
        return {
            "runtime_assets": runtime_assets,
            "dev_assets": dev_assets,
            "design_assets": design_assets,
        }

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
            logger.warning("asset_event_emit_failed", error=str(e))


# 全局实例
asset_collection_service = AssetCollectionService()
