"""REST API 路由 — 客户列表、会话 CRUD、状态查询"""

import uuid
import logging

from fastapi import APIRouter, HTTPException

from src.server.session_manager import session_manager, Session
from src.server.graph_manager import graph_manager
from src.db import queries as db

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 客户 ====================

@router.get("/customers")
def list_customers():
    """列出所有客户"""
    customers = []
    for cid in ("C001", "C002", "C003", "C004", "C005"):
        c = db.get_customer(cid)
        if c:
            customers.append(c)
    return customers


@router.get("/customers/{customer_id}")
def get_customer(customer_id: str):
    """获取单个客户详情"""
    c = db.get_customer(customer_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"客户 {customer_id} 不存在")
    return c


# ==================== 会话 ====================

class CreateSessionRequest:
    """创建会话请求体"""
    __slots__ = ("customer_id", "customer_tier")

    def __init__(self, customer_id: str, customer_tier: str = "standard"):
        self.customer_id = customer_id
        self.customer_tier = customer_tier


@router.post("/sessions")
def create_session(body: dict):
    """创建新会话，返回 thread_id"""
    customer_id = body.get("customer_id", "")
    customer_tier = body.get("customer_tier", "standard")

    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id 必填")

    # 验证客户存在
    c = db.get_customer(customer_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"客户 {customer_id} 不存在")

    # 使用画像中的 tier（如果有的话）
    from src.memory.customer_store import get_customer_store
    store = get_customer_store()
    profile = store.load(customer_id)
    if customer_tier == "standard" and profile.get("tier"):
        customer_tier = profile["tier"]

    thread_id = str(uuid.uuid4())
    session = session_manager.create(thread_id, customer_id, customer_tier)
    return {
        "thread_id": thread_id,
        "customer_id": customer_id,
        "customer_tier": customer_tier,
        "customer_name": c.get("name", ""),
    }


@router.get("/sessions")
def list_sessions():
    """列出所有活跃会话"""
    sessions = session_manager.list_sessions()
    result = []
    for s in sessions:
        result.append({
            "thread_id": s.thread_id,
            "customer_id": s.customer_id,
            "customer_tier": s.customer_tier,
            "first_turn": s.first_turn,
            "session_takeover": s.session_takeover,
            "created_at": s.created_at,
        })
    return result


@router.get("/sessions/{thread_id}/status")
def get_session_status(thread_id: str):
    """获取会话状态快照"""
    session = session_manager.get(thread_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话 {thread_id} 不存在")
    return graph_manager.get_session_state(thread_id)


@router.post("/sessions/{thread_id}/end")
def end_session(thread_id: str):
    """结束会话"""
    removed = session_manager.remove(thread_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"会话 {thread_id} 不存在")
    return {"status": "ended", "thread_id": thread_id}
