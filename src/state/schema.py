"""
状态Schema定义

定义LangGraph StateGraph所需的所有状态类型:
- ConversationState: 顶层监督者状态
- AgentSubgraphState: 子图共享基础状态
- 各子图扩展状态 (PreSales/InSales/AfterSales/Complaint/General)
- 子图输出类型 (normal/clarification/fallback/escalate)
"""

import operator
from typing import TypedDict, Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ==================== 顶层监督者状态 ====================
class ConversationState(TypedDict):
    """顶层监督者状态 - 贯穿整个对话生命周期"""
    # --- 核心对话 ---
    messages: Annotated[list[BaseMessage], add_messages]     # 对话消息列表
    session_id: str                                          # 会话ID
    thread_id: str                                           # 线程ID（LangGraph用）

    # --- 客户上下文 ---
    customer_id: str                                         # 客户ID
    customer_tier: str                                       # 客户等级: standard/vip/enterprise
    customer_profile: dict                                   # 客户画像

    # --- 多维标签向量 ---
    intent_labels: list[dict]                                # [{intent, confidence, primary}, ...]
    emotion: str                                             # 情感类别
    emotion_intensity: float                                 # 情感强度 0-1
    urgency: str                                             # 紧急程度: low/medium/high/critical
    language: str                                            # 检测到的语言

    # --- 多模态 ---
    media_safety_passed: bool                                # 图片安全审核是否通过
    media_lightweight_description: str                       # 入口提取的通用图片描述

    # --- 安全筛查 ---
    safety_screen_passed: bool                               # 安全审核是否通过
    sensitive_word_hit: bool                                 # 是否命中敏感词

    # --- 路由 ---
    active_agents: list[str]                                 # 激活的子图列表
    routing_reason: str                                      # 路由原因说明

    # --- 澄清回路 ---
    pending_clarification: bool                              # 是否有待处理的澄清
    pending_clarification_intent: str                        # 澄清关联的意图
    pending_subgraph: str                                    # 待恢复的子图名称
    pending_accumulated_state: dict                          # 澄清前的累积状态
    clarification_attempts: int                              # 澄清尝试次数（最多2次）
    clarification_request: dict                              # 澄清请求内容

    # --- Supervisor中断协议 ---
    escalate_signal: str | None                              # "to_complaint"|"to_human"|None
    interrupted_subgraph_results: list[dict]                 # 被中断子图已产出的部分结果

    # --- 子图结果（reducers聚合）---
    agent_findings: Annotated[list[dict], operator.add]      # 子图产出的发现
    tool_calls_made: Annotated[list[dict], operator.add]     # 工具调用记录
    knowledge_retrieved: Annotated[list[dict], operator.add] # 知识库检索结果

    # --- 降级标记 ---
    is_fallback: bool                                        # 是否为降级结果
    fallback_reason: str                                     # 降级原因

    # --- 响应生成 ---
    merged_content: str                                      # content_merger输出
    draft_response: str                                      # tone_adapter输出
    response_sources: list[str]                              # 回答引用来源
    response_confidence: float                               # 回答置信度

    # --- 质量与安全 ---
    risk_level: str                                          # 风险等级: low/medium/high/critical
    requires_human_review: bool                              # 是否需要人工审核
    human_review_reason: str                                 # 人工审核原因
    safety_flags: list[str]                                  # 安全标记
    quality_score: float                                     # 质量评分 0-1
    auto_correction_attempts: int                            # 自动修正次数（最多1次）
    human_review_rounds: int                                 # 人工审核轮次（最多2轮）
    human_decision: str                                      # 人工决策: approve/edit/reject_regenerate/reject_reclassify/takeover
    human_feedback: str                                      # 人工反馈内容

    # --- 策略版本 ---
    strategy_version: str                                    # 策略版本
    prompt_variant: str                                      # prompt变体

    # --- 解决跟踪 ---
    resolution_status: str                                   # 解决状态
    resolution_attempts: int                                 # 解决尝试次数
    max_resolution_attempts: int                             # 最大尝试次数

    # --- 观测埋点 ---
    trace_events: Annotated[list[dict], operator.add]        # 观测事件列表
    trace_id: str                                            # 追踪ID

    # --- 会话接管 ---
    session_takeover: bool                                   # 是否被人工客服接管

    # --- 元数据 ---
    created_at: str                                          # 创建时间
    updated_at: str                                          # 更新时间
    tags: list[str]                                          # 标签
    checkpoint_backup: dict                                  # 检查点备份


# ==================== 子图共享基础状态 ====================
class AgentSubgraphState(TypedDict):
    """子图共享基础状态 - 由supervisor注入上下文后传入子图"""
    # 从supervisor注入的上下文
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    thread_id: str
    customer_id: str
    customer_tier: str
    customer_profile: dict
    intent_labels: list[dict]
    emotion: str
    emotion_intensity: float
    urgency: str
    language: str
    media_lightweight_description: str

    # supervisor注入的相关历史
    relevant_history: list[dict]

    # 子图输出 → 向监督者传递（写入 agent_findings 由 reducer 聚合）
    agent_findings: Annotated[list[dict], operator.add]   # [{source_agent, result_type, findings, clarification_request, escalate_signal, ...}]
    result_type: str                          # normal/clarification/fallback
    clarification_request: dict | None        # 澄清请求
    fallback_reason: str | None               # 降级原因
    fallback_message: str | None              # 降级预置话术
    escalate_signal: str | None               # 升级信号

    # 子图内部工具调用
    tool_calls_made: Annotated[list[dict], operator.add]

    # 观测
    trace_events: Annotated[list[dict], operator.add]
    trace_id: str


# ==================== 子图输出Schema（控制回传给监督者的字段）====================
class SubgraphOutput(TypedDict):
    """子图向监督者回传的字段，避免 session_id 等标量字段冲突"""
    agent_findings: Annotated[list[dict], operator.add]
    tool_calls_made: Annotated[list[dict], operator.add]
    trace_events: Annotated[list[dict], operator.add]


# ==================== 售前子图状态 ====================
class PreSalesState(AgentSubgraphState):
    """售前子图扩展状态"""
    product_info: dict | None                 # 查询到的商品信息
    inventory_result: dict | None             # 库存查询结果
    recommendations: list[dict]               # 推荐结果
    promotions: list[dict]                    # 匹配的优惠活动
    knowledge_results: list[dict]             # 知识库检索结果


# ==================== 售中子图状态 ====================
class InSalesState(AgentSubgraphState):
    """售中子图扩展状态"""
    order_info: dict | None                   # 订单信息
    logistics_info: dict | None               # 物流信息
    payment_info: dict | None                 # 支付信息
    action_plan: dict | None                  # 操作计划
    tool_execution_result: dict | None        # 工具执行结果


# ==================== 售后子图状态 ====================
class AfterSalesState(AgentSubgraphState):
    """售后子图扩展状态"""
    issue_type: str                           # 问题类型: return/exchange/refund/warranty
    order_info: dict | None                   # 订单信息
    eligibility_result: dict | None           # 资格检查结果
    evidence_collected: list[dict]            # 收集的证据
    resolution_plan: dict | None              # 解决方案
    tool_execution_result: dict | None        # 工具执行结果


# ==================== 投诉子图状态 ====================
class ComplaintState(AgentSubgraphState):
    """投诉子图扩展状态"""
    complaint_type: str                       # 投诉类型: product/service/logistics
    complaint_severity: str                   # 严重程度: low/medium/high/critical
    context_gathered: dict | None             # 收集的上下文
    empathy_response: str                     # 同理心回复
    resolution_plan: dict | None              # 解决方案
    approval_result: dict | None              # 审批结果


# ==================== 通用子图状态 ====================
class GeneralState(AgentSubgraphState):
    """通用子图扩展状态"""
    faq_result: dict | None                   # FAQ匹配结果
    policy_result: dict | None                # 政策检索结果
    emotion_escalate: bool                    # 是否检测到情绪升级
    _findings: dict                           # general_respond → emotion_monitor 内部传递


# ==================== 子图输出类型常量 ====================
RESULT_TYPE_NORMAL = "normal"
RESULT_TYPE_CLARIFICATION = "clarification"
RESULT_TYPE_FALLBACK = "fallback"

ESCALATE_TO_COMPLAINT = "to_complaint"
ESCALATE_TO_HUMAN = "to_human"


def create_initial_state(session_id: str, customer_id: str,
                         customer_tier: str = "standard") -> ConversationState:
    """创建初始对话状态"""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    return ConversationState(
        messages=[],
        session_id=session_id,
        thread_id=session_id,
        customer_id=customer_id,
        customer_tier=customer_tier,
        customer_profile={},
        intent_labels=[],
        emotion="neutral",
        emotion_intensity=0.0,
        urgency="low",
        language="zh",
        media_safety_passed=True,
        media_lightweight_description="",
        safety_screen_passed=True,
        sensitive_word_hit=False,
        active_agents=[],
        routing_reason="",
        pending_clarification=False,
        pending_clarification_intent="",
        pending_subgraph="",
        pending_accumulated_state={},
        clarification_attempts=0,
        clarification_request={},
        escalate_signal=None,
        interrupted_subgraph_results=[],
        agent_findings=[],
        tool_calls_made=[],
        knowledge_retrieved=[],
        is_fallback=False,
        fallback_reason="",
        merged_content="",
        draft_response="",
        response_sources=[],
        response_confidence=0.0,
        risk_level="low",
        requires_human_review=False,
        human_review_reason="",
        safety_flags=[],
        quality_score=0.0,
        auto_correction_attempts=0,
        human_review_rounds=0,
        human_decision="",
        human_feedback="",
        strategy_version="v1",
        prompt_variant="default",
        resolution_status="pending",
        resolution_attempts=0,
        max_resolution_attempts=3,
        trace_events=[],
        trace_id="",
        session_takeover=False,
        created_at=now,
        updated_at=now,
        tags=[],
        checkpoint_backup={},
    )
