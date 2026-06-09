"""WebSocket 处理器 — 实时对话 + 人工审核交互"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.server.session_manager import session_manager
from src.server.graph_manager import graph_manager
from src.server.protocol import parse_client_message, HumanDecision, ApprovalDecision

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """WebSocket 端点 — 处理实时对话和人工审核交互"""
    session = session_manager.get(thread_id)
    if not session:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": f"会话 {thread_id} 不存在，请先通过 POST /api/sessions 创建"})
        await websocket.close()
        return

    await websocket.accept()
    session_manager.set_websocket(thread_id, websocket)
    logger.info(f"WebSocket 连接建立: {thread_id}")

    try:
        while True:
            # 接收客户端消息
            raw = await websocket.receive_json()
            try:
                msg = parse_client_message(raw)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": f"消息格式错误: {e}"})
                continue

            # ---- chat 消息 ----
            if msg.type == "chat":
                await _handle_chat(websocket, session, msg.content)

            # ---- human_decision ----
            elif msg.type == "human_decision":
                await _handle_human_decision(websocket, session, msg)

            # ---- approval ----
            elif msg.type == "approval":
                await _handle_approval(websocket, session, msg)

            # ---- end_takeover ----
            elif msg.type == "end_takeover":
                await _handle_end_takeover(websocket, session)

            # ---- get_status ----
            elif msg.type == "get_status":
                state = graph_manager.get_session_state(thread_id)
                await websocket.send_json({"type": "status_response", **state})

    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: {thread_id}")
    finally:
        session_manager.set_websocket(thread_id, None)


async def _handle_chat(websocket: WebSocket, session, content: str):
    """处理客户消息：调用图 → 发送进度 → 处理中断"""
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

    # 逐条发送事件
    for event in events:
        await websocket.send_json(event)

        # 如果是中断请求，等待客户端决策后恢复
        if event["type"] == "human_review_request":
            # 等待人工审核决策
            raw_decision = await websocket.receive_json()
            try:
                decision = parse_client_message(raw_decision)
                if decision.type == "human_decision":
                    await _handle_human_decision(websocket, session, decision)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": f"决策消息格式错误: {e}"})
            break  # 中断处理后不再发送后续事件（resume 会重新发送）

        elif event["type"] == "approval_request":
            raw_decision = await websocket.receive_json()
            try:
                decision = parse_client_message(raw_decision)
                if decision.type == "approval":
                    await _handle_approval(websocket, session, decision)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": f"审批消息格式错误: {e}"})
            break

    # 更新接管状态
    state = graph_manager.get_session_state(session.thread_id)
    if state["takeover"] and not session.session_takeover:
        session.session_takeover = True


async def _handle_human_decision(websocket: WebSocket, session, decision: HumanDecision):
    """处理人工审核决策：构建 resume_value 并恢复图"""
    resume_value = {
        "decision": decision.decision,
        "feedback": decision.feedback,
        "edited_response": decision.edited_response,
    }

    # 在线程池中恢复中断
    events = await asyncio.to_thread(
        graph_manager.resume_interrupt,
        session.thread_id,
        resume_value,
    )

    # 发送后续事件
    for event in events:
        await websocket.send_json(event)

        # 可能触发二次中断（人工审核最多2轮）
        if event["type"] == "human_review_request":
            raw_decision = await websocket.receive_json()
            try:
                d2 = parse_client_message(raw_decision)
                if d2.type == "human_decision":
                    await _handle_human_decision(websocket, session, d2)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": f"二次审核决策格式错误: {e}"})
            break

        elif event["type"] == "approval_request":
            raw_decision = await websocket.receive_json()
            try:
                d2 = parse_client_message(raw_decision)
                if d2.type == "approval":
                    await _handle_approval(websocket, session, d2)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": f"审批决策格式错误: {e}"})
            break

    # 更新接管状态
    if decision.decision == "takeover":
        session.session_takeover = True
    state = graph_manager.get_session_state(session.thread_id)
    session.session_takeover = state["takeover"]


async def _handle_approval(websocket: WebSocket, session, decision: ApprovalDecision):
    """处理投诉审批决策"""
    resume_value = {
        "approved": decision.approved,
        "note": decision.note,
    }

    events = await asyncio.to_thread(
        graph_manager.resume_interrupt,
        session.thread_id,
        resume_value,
    )

    for event in events:
        await websocket.send_json(event)

        if event["type"] == "human_review_request":
            raw_decision = await websocket.receive_json()
            try:
                d2 = parse_client_message(raw_decision)
                if d2.type == "human_decision":
                    await _handle_human_decision(websocket, session, d2)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": f"审核决策格式错误: {e}"})
            break


async def _handle_end_takeover(websocket: WebSocket, session):
    """处理结束接管"""
    result = await asyncio.to_thread(
        graph_manager.do_release_takeover,
        session.thread_id,
    )
    await websocket.send_json(result)
    if result.get("type") == "status_response":
        session.session_takeover = False
