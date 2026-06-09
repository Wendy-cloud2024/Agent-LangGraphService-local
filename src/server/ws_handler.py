"""WebSocket 处理器 — 实时对话 + 人工审核交互

核心设计: 主循环统一接收消息，通过 _waiting_for 字段判断当前期待的输入类型。
这样避免了嵌套 receive_json 导致的消息竞争问题。
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.server.session_manager import session_manager
from src.server.graph_manager import graph_manager
from src.server.protocol import parse_client_message

logger = logging.getLogger(__name__)
router = APIRouter()

# 会话当前期待的消息类型
_WAITING_NONE = "none"
_WAITING_HUMAN_DECISION = "human_decision"
_WAITING_APPROVAL = "approval"


@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """WebSocket 端点 — 统一主循环处理所有消息"""
    session = session_manager.get(thread_id)
    if not session:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "message": f"会话 {thread_id} 不存在，请先通过 POST /api/sessions 创建",
        })
        await websocket.close()
        return

    await websocket.accept()
    session_manager.set_websocket(thread_id, websocket)
    logger.info(f"WebSocket 连接建立: {thread_id}")

    # 当前期待的消息类型（用于人工审核流程）
    waiting_for = _WAITING_NONE

    try:
        while True:
            raw = await websocket.receive_json()
            logger.info(f"[{thread_id}] 收到消息: {raw.get('type', '?')}")

            try:
                msg = parse_client_message(raw)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": f"消息格式错误: {e}"})
                continue

            # ---- 按期待类型分发 ----
            if waiting_for == _WAITING_HUMAN_DECISION:
                if msg.type == "human_decision":
                    waiting_for = await _handle_human_decision(websocket, session, msg)
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "当前等待人工审核决策，请先处理审核请求",
                    })
                continue

            elif waiting_for == _WAITING_APPROVAL:
                if msg.type == "approval":
                    waiting_for = await _handle_approval(websocket, session, msg)
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "当前等待投诉审批决策，请先处理审批请求",
                    })
                continue

            # ---- 正常消息分发 ----
            if msg.type == "chat":
                waiting_for = await _handle_chat(websocket, session, msg.content)

            elif msg.type == "human_decision":
                # 没有在等待但收到了 decision（可能前端重发），直接处理
                waiting_for = await _handle_human_decision(websocket, session, msg)

            elif msg.type == "approval":
                waiting_for = await _handle_approval(websocket, session, msg)

            elif msg.type == "end_takeover":
                await _handle_end_takeover(websocket, session)
                waiting_for = _WAITING_NONE

            elif msg.type == "get_status":
                state = graph_manager.get_session_state(thread_id)
                await websocket.send_json({"type": "status_response", **state})

    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: {thread_id}")
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}", exc_info=True)
    finally:
        session_manager.set_websocket(thread_id, None)


async def _handle_chat(websocket: WebSocket, session, content: str) -> str:
    """处理客户消息。返回下一步期待的消息类型。"""
    await websocket.send_json({
        "type": "node_progress",
        "node": "__thinking__",
        "tags": {"message": "正在处理您的消息..."},
    })

    # 在线程池中同步执行图（避免阻塞事件循环）
    events = await asyncio.to_thread(
        graph_manager.invoke_turn,
        session.thread_id,
        session.customer_id,
        session.customer_tier,
        content,
        session.first_turn,
    )
    session.first_turn = False

    # 逐条发送事件，检测中断
    result = _WAITING_NONE
    for event in events:
        await websocket.send_json(event)

        if event["type"] == "human_review_request":
            logger.info(f"[{session.thread_id}] 触发人工审核中断，等待决策")
            result = _WAITING_HUMAN_DECISION
            break

        elif event["type"] == "approval_request":
            logger.info(f"[{session.thread_id}] 触发投诉审批中断，等待审批")
            result = _WAITING_APPROVAL
            break

    # 更新接管状态
    state = graph_manager.get_session_state(session.thread_id)
    session.session_takeover = state["takeover"]

    return result


async def _handle_human_decision(websocket: WebSocket, session, decision) -> str:
    """处理人工审核决策。返回下一步期待的消息类型。"""
    resume_value = {
        "decision": decision.decision,
        "feedback": decision.feedback,
        "edited_response": decision.edited_response,
    }
    logger.info(f"[{session.thread_id}] 人工审核决策: {decision.decision}")

    # 在线程池中恢复中断
    events = await asyncio.to_thread(
        graph_manager.resume_interrupt,
        session.thread_id,
        resume_value,
    )

    # 发送后续事件
    result = _WAITING_NONE
    for event in events:
        await websocket.send_json(event)

        if event["type"] == "human_review_request":
            logger.info(f"[{session.thread_id}] 二次人工审核中断")
            result = _WAITING_HUMAN_DECISION
            break

        elif event["type"] == "approval_request":
            logger.info(f"[{session.thread_id}] 审核后触发审批中断")
            result = _WAITING_APPROVAL
            break

    # 更新接管状态
    if decision.decision == "takeover":
        session.session_takeover = True
    state = graph_manager.get_session_state(session.thread_id)
    session.session_takeover = state["takeover"]

    return result


async def _handle_approval(websocket: WebSocket, session, decision) -> str:
    """处理投诉审批决策。返回下一步期待的消息类型。"""
    resume_value = {
        "approved": decision.approved,
        "note": decision.note,
    }
    logger.info(f"[{session.thread_id}] 投诉审批: {'批准' if decision.approved else '拒绝'}")

    events = await asyncio.to_thread(
        graph_manager.resume_interrupt,
        session.thread_id,
        resume_value,
    )

    result = _WAITING_NONE
    for event in events:
        await websocket.send_json(event)

        if event["type"] == "human_review_request":
            logger.info(f"[{session.thread_id}] 审批后触发人工审核")
            result = _WAITING_HUMAN_DECISION
            break

        elif event["type"] == "approval_request":
            logger.info(f"[{session.thread_id}] 二次审批中断")
            result = _WAITING_APPROVAL
            break

    return result


async def _handle_end_takeover(websocket: WebSocket, session):
    """处理结束接管"""
    result = await asyncio.to_thread(
        graph_manager.do_release_takeover,
        session.thread_id,
    )
    await websocket.send_json(result)
    if result.get("type") == "status_response":
        session.session_takeover = False
