"""
故障事件仓储模块

本模块提供故障事件的数据持久化层。

核心功能：
1. 故障事件的 CRUD 操作
2. 支持内存存储和文件存储两种后端

存储后端：
- InMemoryIncidentRepository: 内存存储，适合测试
- FileIncidentRepository: 文件存储，适合单机部署

存储结构：
- {LOCAL_STORE_DIR}/incidents.json

使用场景：
- IncidentService 通过此模块持久化故障数据
- 支持按配置选择存储后端

Incident Repository
"""

from abc import ABC, abstractmethod
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings
from app.models.incident import Incident


class IncidentRepository(ABC):
    """
    故障事件仓储接口

    定义故障事件持久化的标准接口。
    实现类需提供 CRUD 操作。

    方法：
    - create: 创建故障事件
    - get: 按 ID 获取故障事件
    - update: 更新故障事件
    - delete: 删除故障事件
    - list_all: 列出所有故障事件
    """

    @abstractmethod
    async def create(self, incident: Incident) -> Incident:
        """
        创建故障事件

        Args:
            incident: 故障事件对象

        Returns:
            Incident: 创建的故障事件
        """
        pass

    @abstractmethod
    async def get(self, incident_id: str) -> Optional[Incident]:
        """
        按 ID 获取故障事件

        Args:
            incident_id: 故障事件 ID

        Returns:
            Optional[Incident]: 故障事件对象，不存在则返回 None
        """
        pass

    @abstractmethod
    async def update(self, incident: Incident) -> Incident:
        """
        更新故障事件

        Args:
            incident: 更新后的故障事件对象

        Returns:
            Incident: 更新后的故障事件
        """
        pass

    @abstractmethod
    async def delete(self, incident_id: str) -> bool:
        """
        删除故障事件

        Args:
            incident_id: 故障事件 ID

        Returns:
            bool: 是否删除成功
        """
        pass

    @abstractmethod
    async def list_all(self) -> List[Incident]:
        """
        列出所有故障事件

        Returns:
            List[Incident]: 故障事件列表
        """
        pass


class InMemoryIncidentRepository(IncidentRepository):
    """
    基于内存的故障事件仓储

    适合测试环境或无需持久化的场景。
    数据仅在进程生命周期内有效。

    属性：
    - _incidents: 故障事件字典（ID -> Incident）
    """

    def __init__(self):
        """
        初始化内存仓储

        创建空的故障事件字典。
        """
        self._incidents: Dict[str, Incident] = {}

    async def create(self, incident: Incident) -> Incident:
        """
        创建故障事件（内存存储）

        Args:
            incident: 故障事件对象

        Returns:
            Incident: 创建的故障事件
        """
        self._incidents[incident.id] = incident
        return incident

    async def get(self, incident_id: str) -> Optional[Incident]:
        """
        按 ID 获取故障事件

        Args:
            incident_id: 故障事件 ID

        Returns:
            Optional[Incident]: 故障事件对象
        """
        return self._incidents.get(incident_id)

    async def update(self, incident: Incident) -> Incident:
        """
        更新故障事件

        Args:
            incident: 更新后的故障事件对象

        Returns:
            Incident: 更新后的故障事件
        """
        self._incidents[incident.id] = incident
        return incident

    async def delete(self, incident_id: str) -> bool:
        """
        删除故障事件

        Args:
            incident_id: 故障事件 ID

        Returns:
            bool: 是否删除成功
        """
        if incident_id in self._incidents:
            del self._incidents[incident_id]
            return True
        return False

    async def list_all(self) -> List[Incident]:
        """
        列出所有故障事件

        Returns:
            List[Incident]: 故障事件列表
        """
        return list(self._incidents.values())


class FileIncidentRepository(IncidentRepository):
    """
    基于本地 JSON 文件的故障事件仓储

    适合单机部署，支持持久化。
    使用原子写入保证数据安全。

    存储路径：
    - {LOCAL_STORE_DIR}/incidents.json

    属性：
    - _file: 数据文件路径
    - _lock: 异步锁，保证并发安全
    - _incidents: 故障事件字典（内存缓存）
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化文件仓储

        创建存储目录，并从磁盘加载已有数据。

        Args:
            base_dir: 基础存储目录，未提供则使用配置值
        """
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "incidents.json"
        self._lock = asyncio.Lock()
        self._incidents: Dict[str, Incident] = {}
        self._load_from_disk()

    async def create(self, incident: Incident) -> Incident:
        """
        创建故障事件（持久化）

        Args:
            incident: 故障事件对象

        Returns:
            Incident: 创建的故障事件
        """
        async with self._lock:
            self._incidents[incident.id] = incident
            self._persist_to_disk()
        return incident

    async def get(self, incident_id: str) -> Optional[Incident]:
        """
        按 ID 获取故障事件

        Args:
            incident_id: 故障事件 ID

        Returns:
            Optional[Incident]: 故障事件对象
        """
        async with self._lock:
            return self._incidents.get(incident_id)

    async def update(self, incident: Incident) -> Incident:
        """
        更新故障事件（持久化）

        Args:
            incident: 更新后的故障事件对象

        Returns:
            Incident: 更新后的故障事件
        """
        async with self._lock:
            self._incidents[incident.id] = incident
            self._persist_to_disk()
        return incident

    async def delete(self, incident_id: str) -> bool:
        """
        删除故障事件（持久化）

        Args:
            incident_id: 故障事件 ID

        Returns:
            bool: 是否删除成功
        """
        async with self._lock:
            if incident_id not in self._incidents:
                return False
            del self._incidents[incident_id]
            self._persist_to_disk()
        return True

    async def list_all(self) -> List[Incident]:
        """
        列出所有故障事件

        Returns:
            List[Incident]: 故障事件列表
        """
        async with self._lock:
            return list(self._incidents.values())

    def _load_from_disk(self) -> None:
        """
        从磁盘加载数据

        启动时从 JSON 文件恢复故障事件数据。
        无效记录会被跳过。
        """
        if not self._file.exists():
            return
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            rows = payload.get("incidents", []) if isinstance(payload, dict) else []
            loaded: Dict[str, Incident] = {}
            for row in rows:
                try:
                    item = Incident.model_validate(row)
                    loaded[item.id] = item
                except Exception:
                    continue
            self._incidents = loaded
        except Exception:
            self._incidents = {}

    def _persist_to_disk(self) -> None:
        """
        持久化到磁盘

        使用临时文件原子写入，避免进程中断导致数据损坏。
        """
        payload = {
            "schema_version": 1,
            "incidents": [item.model_dump(mode="json") for item in self._incidents.values()],
        }
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)