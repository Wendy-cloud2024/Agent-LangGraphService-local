"""内存会话注册表 — 管理 thread_id → 会话信息的映射"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import WebSocket


@dataclass
class Session:
    """一个活跃的对话会话"""
    thread_id: str
    customer_id: str
    customer_tier: str = "standard"
    first_turn: bool = True
    session_takeover: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    websocket: WebSocket | None = None


class SessionManager:
    """线程安全的会话管理器"""

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, thread_id: str, customer_id: str, customer_tier: str = "standard") -> Session:
        """创建新会话"""
        with self._lock:
            session = Session(
                thread_id=thread_id,
                customer_id=customer_id,
                customer_tier=customer_tier,
            )
            self._sessions[thread_id] = session
            return session

    def get(self, thread_id: str) -> Session | None:
        """获取会话"""
        with self._lock:
            return self._sessions.get(thread_id)

    def list_sessions(self) -> list[Session]:
        """列出所有活跃会话"""
        with self._lock:
            return list(self._sessions.values())

    def remove(self, thread_id: str) -> bool:
        """移除会话"""
        with self._lock:
            return self._sessions.pop(thread_id, None) is not None

    def set_websocket(self, thread_id: str, ws: WebSocket | None):
        """绑定/解绑 WebSocket 连接"""
        with self._lock:
            session = self._sessions.get(thread_id)
            if session:
                session.websocket = ws


# 全局单例
session_manager = SessionManager()
