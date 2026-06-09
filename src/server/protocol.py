"""WebSocket 消息协议 — Pydantic 模型定义

客户端 → 服务端: ChatMessage, HumanDecision, ApprovalDecision, EndTakeover, GetStatus
服务端 → 客户端: NodeProgress, ChatResponse, HumanReviewRequest, ApprovalRequest, StatusResponse, ErrorEvent
"""

from typing import Literal, Any
from pydantic import BaseModel, Field


# ==================== 客户端 → 服务端 ====================

class ChatMessage(BaseModel):
    """客户发送聊天消息"""
    type: Literal["chat"] = "chat"
    content: str


class HumanDecision(BaseModel):
    """人工审核决策"""
    type: Literal["human_decision"] = "human_decision"
    decision: Literal["approve", "edit", "reject_regenerate", "reject_reclassify", "takeover"]
    feedback: str = ""
    edited_response: str = ""


class ApprovalDecision(BaseModel):
    """投诉审批决策"""
    type: Literal["approval"] = "approval"
    approved: bool
    note: str = ""


class EndTakeover(BaseModel):
    """结束接管模式"""
    type: Literal["end_takeover"] = "end_takeover"


class GetStatus(BaseModel):
    """查询会话状态"""
    type: Literal["get_status"] = "get_status"


# 联合类型（用于解析）
ClientMessage = ChatMessage | HumanDecision | ApprovalDecision | EndTakeover | GetStatus


# ==================== 服务端 → 客户端 ====================

class ResponseMetadata(BaseModel):
    """Agent 元数据"""
    intent_labels: list[dict] = Field(default_factory=list)
    emotion: str = ""
    urgency: str = ""
    routing_reason: str = ""
    active_agents: list[str] = Field(default_factory=list)
    risk_level: str = ""
    quality_score: float = 0.0
    resolution_status: str = ""
    session_takeover: bool = False


class NodeProgress(BaseModel):
    """节点执行进度"""
    type: Literal["node_progress"] = "node_progress"
    node: str
    tags: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """最终回复"""
    type: Literal["chat_response"] = "chat_response"
    content: str
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata)


class HumanReviewRequest(BaseModel):
    """人工审核中断请求"""
    type: Literal["human_review_request"] = "human_review_request"
    review_info: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    """投诉审批中断请求"""
    type: Literal["approval_request"] = "approval_request"
    approval_info: dict[str, Any] = Field(default_factory=dict)


class StatusResponse(BaseModel):
    """会话状态响应"""
    type: Literal["status_response"] = "status_response"
    takeover: bool = False
    resolution_status: str = ""
    message_count: int = 0
    pending_nodes: list[str] = Field(default_factory=list)


class ErrorEvent(BaseModel):
    """错误消息"""
    type: Literal["error"] = "error"
    message: str


# 联合类型
ServerEvent = NodeProgress | ChatResponse | HumanReviewRequest | ApprovalRequest | StatusResponse | ErrorEvent


# ==================== 辅助函数 ====================

def parse_client_message(data: dict) -> ClientMessage:
    """根据 type 字段解析客户端消息"""
    msg_type = data.get("type", "")
    parsers = {
        "chat": ChatMessage,
        "human_decision": HumanDecision,
        "approval": ApprovalDecision,
        "end_takeover": EndTakeover,
        "get_status": GetStatus,
    }
    parser = parsers.get(msg_type)
    if parser is None:
        raise ValueError(f"未知消息类型: {msg_type}")
    return parser(**data)
