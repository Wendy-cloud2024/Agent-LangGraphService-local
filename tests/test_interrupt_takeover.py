"""
测试: Supervisor 中断协议 + Session Takeover

测试分类:
  Part A - 中断协议 (无需 API):
    A1. escalation.py 工具函数单元测试
    A2. 售前子图 escalation_monitor
    A3. 售中子图 escalation_monitor
    A4. 售后子图 escalation_monitor
    A5. 投诉子图 escalation_monitor
    A6. 通用子图 emotion_monitor
    A7. context_wrapper 超时/错误边界
    A8. subgraph_output_router 升级信号路由

  Part B - Session Takeover (无需 API):
    B1. escalate_to_human 普通转接模式
    B2. escalate_to_human 接管模式
    B3. escalate_to_human 接管持久性 (session_takeover 已为 True 时)
    B4. orchestrator_gate 接管状态检查
    B5. human_review 接管决策
    B6. route_after_human_review 接管路由

  Part C - 端到端生命周期 (需要 API):
    C1. 完整接管生命周期: 激活 → 持久化 → 释放 → 恢复

运行方式:
  全部测试:  python tests/test_interrupt_takeover.py
  仅纯逻辑:  python tests/test_interrupt_takeover.py --no-api
"""

import os
import sys
import time

# 修复 Windows 终端编码
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# ======================================================================
# 测试基础设施
# ======================================================================

_passed = 0
_failed = 0
_errors = []


class FakeMsg:
    """伪造消息对象"""
    def __init__(self, content, type_="human"):
        self.content = content
        self.type = type_


def assert_eq(name, actual, expected):
    global _passed, _failed
    if actual == expected:
        _passed += 1
    else:
        _failed += 1
        msg = f"  FAIL: {name} -> expected={expected!r}, got={actual!r}"
        print(msg)
        _errors.append(msg)


def assert_true(name, value):
    assert_eq(name, value, True)


def assert_false(name, value):
    assert_eq(name, value, False)


def assert_is_none(name, value):
    global _passed, _failed
    if value is None:
        _passed += 1
    else:
        _failed += 1
        msg = f"  FAIL: {name} -> expected=None, got={value!r}"
        print(msg)
        _errors.append(msg)


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def subsection(title):
    print(f"\n--- {title} ---")


# ======================================================================
# Part A: 中断协议测试 (无需 API)
# ======================================================================

def test_A1_escalation_utils():
    """A1. escalation.py 工具函数"""
    section("A1. escalation.py 工具函数")
    from src.utils.escalation import (
        detect_complaint_keywords,
        detect_emotion_escalation,
        check_tool_failures,
        evaluate_escalation,
    )

    # --- detect_complaint_keywords ---
    subsection("detect_complaint_keywords")

    # 正常文本不触发
    assert_false(
        "normal text no trigger",
        detect_complaint_keywords([FakeMsg("hello"), FakeMsg("reply", "ai")]),
    )

    # 包含投诉关键词触发
    assert_true(
        "complaint keyword triggers",
        detect_complaint_keywords([
            FakeMsg("hello"), FakeMsg("reply", "ai"),
            FakeMsg("我要投诉你们！"),
        ]),
    )

    # 多个关键词
    for kw in ["骗子", "315", "曝光", "举报", "假货", "欺诈"]:
        assert_true(
            f"keyword '{kw}' triggers",
            detect_complaint_keywords([FakeMsg(f"你{kw}吧")]),
        )

    # 非 human 消息不检查
    assert_false(
        "ai message ignored",
        detect_complaint_keywords([FakeMsg("投诉", "ai")]),
    )

    # --- detect_emotion_escalation ---
    subsection("detect_emotion_escalation")

    assert_true("angry 0.95", detect_emotion_escalation("angry", 0.95))
    assert_true("frustrated 0.92", detect_emotion_escalation("frustrated", 0.92))
    assert_false("neutral 0.95", detect_emotion_escalation("neutral", 0.95))
    assert_false("angry 0.5", detect_emotion_escalation("angry", 0.5))
    assert_false("happy 0.95", detect_emotion_escalation("happy", 0.95))

    # --- check_tool_failures ---
    subsection("check_tool_failures")

    assert_eq("empty list", check_tool_failures([]), 0)
    assert_eq("all success", check_tool_failures([{"status": "completed"}]), 0)
    assert_eq("2 failures", check_tool_failures([{"status": "failed"}, {"status": "failed"}]), 2)
    assert_eq("success then 2 failures", check_tool_failures([
        {"status": "completed"}, {"status": "failed"}, {"status": "failed"},
    ]), 2)
    assert_eq("failure success failure", check_tool_failures([
        {"status": "failed"}, {"status": "completed"}, {"status": "failed"},
    ]), 1)

    # --- evaluate_escalation ---
    subsection("evaluate_escalation")

    # 正常情况 -> None
    state_normal = {
        "trace_id": "t", "messages": [], "emotion": "neutral",
        "emotion_intensity": 0.3, "tool_calls_made": [],
    }
    assert_is_none("normal -> None", evaluate_escalation(state_normal))

    # 工具失败 -> to_human (优先级1)
    state_tools = {
        "trace_id": "t", "messages": [], "emotion": "neutral",
        "emotion_intensity": 0.3,
        "tool_calls_made": [{"status": "failed"}, {"status": "failed"}],
    }
    assert_eq("tool failures -> to_human", evaluate_escalation(state_tools), "to_human")

    # 投诉关键词 -> to_complaint (优先级2)
    state_kw = {
        "trace_id": "t", "messages": [FakeMsg("我要投诉")],
        "emotion": "neutral", "emotion_intensity": 0.3,
        "tool_calls_made": [],
    }
    assert_eq("complaint keyword -> to_complaint", evaluate_escalation(state_kw), "to_complaint")

    # 极端情绪 -> to_complaint (优先级3)
    state_emotion = {
        "trace_id": "t", "messages": [], "emotion": "angry",
        "emotion_intensity": 0.95, "tool_calls_made": [],
    }
    assert_eq("extreme emotion -> to_complaint", evaluate_escalation(state_emotion), "to_complaint")

    # 子图上下文: 退款被拒 + 情绪
    state_ctx = {
        "trace_id": "t", "messages": [], "emotion": "disappointed",
        "emotion_intensity": 0.7, "tool_calls_made": [],
    }
    assert_eq("refund denied -> to_complaint",
              evaluate_escalation(state_ctx, {"refund_denied": True}), "to_complaint")

    # 子图上下文: 订单严重问题 + 情绪
    state_ctx2 = {
        "trace_id": "t", "messages": [], "emotion": "angry",
        "emotion_intensity": 0.7, "tool_calls_made": [],
    }
    assert_eq("order severe -> to_complaint",
              evaluate_escalation(state_ctx2, {"order_severe_issue": True}), "to_complaint")

    # 优先级: 工具失败 > 关键词
    state_priority = {
        "trace_id": "t", "messages": [FakeMsg("投诉")],
        "emotion": "angry", "emotion_intensity": 0.95,
        "tool_calls_made": [{"status": "failed"}, {"status": "failed"}],
    }
    assert_eq("priority: tool failure > keywords",
              evaluate_escalation(state_priority), "to_human")


def test_A2_presales_escalation_monitor():
    """A2. 售前子图 escalation_monitor"""
    section("A2. 售前子图 escalation_monitor")
    from src.graph.subgraphs.presales.graph import escalation_monitor

    # 正常情况 -> None
    state = {
        "trace_id": "t", "messages": [], "emotion": "neutral",
        "emotion_intensity": 0.3, "tool_calls_made": [],
        "_findings": {"answer": "product info"},
    }
    result = escalation_monitor(state)
    assert_is_none("presales normal -> None", result["escalate_signal"])
    assert_eq("presales source_agent", result["agent_findings"][0]["source_agent"], "presales_agent")

    # 投诉关键词 -> to_complaint
    state_kw = {**state, "messages": [FakeMsg("你们是骗子，我要投诉")]}
    result_kw = escalation_monitor(state_kw)
    assert_eq("presales complaint keyword", result_kw["escalate_signal"], "to_complaint")

    # 极端情绪 -> to_complaint
    state_emotion = {**state, "emotion": "angry", "emotion_intensity": 0.95}
    result_emotion = escalation_monitor(state_emotion)
    assert_eq("presales extreme emotion", result_emotion["escalate_signal"], "to_complaint")


def test_A3_insales_escalation_monitor():
    """A3. 售中子图 escalation_monitor"""
    section("A3. 售中子图 escalation_monitor")
    from src.graph.subgraphs.insales.graph import escalation_monitor

    # 正常情况 -> None
    state = {
        "trace_id": "t", "messages": [], "emotion": "neutral",
        "emotion_intensity": 0.3, "tool_calls_made": [],
        "_findings": {"answer": "order status"},
        "order_info": {"status": "shipped"},
    }
    result = escalation_monitor(state)
    assert_is_none("insales normal -> None", result["escalate_signal"])

    # 订单严重问题 + 愤怒 -> to_complaint
    state_severe = {**state, "emotion": "angry", "emotion_intensity": 0.8,
                    "order_info": {"status": "cancelled"}}
    result_severe = escalation_monitor(state_severe)
    assert_eq("insales cancelled + angry", result_severe["escalate_signal"], "to_complaint")

    # 订单正常但愤怒不够 -> None
    state_mild = {**state, "emotion": "angry", "emotion_intensity": 0.4,
                  "order_info": {"status": "cancelled"}}
    result_mild = escalation_monitor(state_mild)
    assert_is_none("insales cancelled + mild anger -> None", result_mild["escalate_signal"])


def test_A4_aftersales_escalation_monitor():
    """A4. 售后子图 escalation_monitor"""
    section("A4. 售后子图 escalation_monitor")
    from src.graph.subgraphs.aftersales.graph import escalation_monitor

    # 正常 -> None
    state = {
        "trace_id": "t", "messages": [], "emotion": "neutral",
        "emotion_intensity": 0.3, "tool_calls_made": [],
        "_findings": {"answer": "return processed", "eligible": True},
    }
    result = escalation_monitor(state)
    assert_is_none("aftersales normal -> None", result["escalate_signal"])

    # 退款被拒 + 失望 -> to_complaint
    state_denied = {**state, "emotion": "disappointed", "emotion_intensity": 0.7,
                    "_findings": {"answer": "denied", "eligible": False}}
    result_denied = escalation_monitor(state_denied)
    assert_eq("aftersales refund denied", result_denied["escalate_signal"], "to_complaint")

    # 退款通过但极端愤怒 -> to_complaint
    state_angry = {**state, "emotion": "angry", "emotion_intensity": 0.95}
    result_angry = escalation_monitor(state_angry)
    assert_eq("aftersales extreme emotion", result_angry["escalate_signal"], "to_complaint")


def test_A5_complaint_escalation_monitor():
    """A5. 投诉子图 escalation_monitor (仅工具失败)"""
    section("A5. 投诉子图 escalation_monitor")
    from src.graph.subgraphs.complaint.graph import escalation_monitor

    # 正常 -> None
    state = {
        "trace_id": "t", "messages": [], "emotion": "angry",
        "emotion_intensity": 0.95, "tool_calls_made": [],
        "agent_findings": [{"findings": {"answer": "complaint handled"}, "source_agent": "complaint_agent"}],
    }
    result = escalation_monitor(state)
    assert_is_none("complaint normal -> None", result["escalate_signal"])

    # 工具失败 -> to_human
    state_fail = {**state, "tool_calls_made": [
        {"status": "failed"}, {"status": "failed"},
    ]}
    result_fail = escalation_monitor(state_fail)
    assert_eq("complaint tool failure -> to_human", result_fail["escalate_signal"], "to_human")

    # 投诉子图即使有极端情绪也不触发 to_complaint (已在投诉流程中)
    state_extreme = {**state, "emotion": "furious", "emotion_intensity": 0.99}
    result_extreme = escalation_monitor(state_extreme)
    assert_is_none("complaint extreme emotion -> None (not to_complaint)",
                   result_extreme["escalate_signal"])


def test_A6_general_emotion_monitor():
    """A6. 通用子图 emotion_monitor"""
    section("A6. 通用子图 emotion_monitor")
    from src.graph.subgraphs.general.graph import emotion_monitor

    # 正常 -> None
    state = {
        "trace_id": "t", "messages": [], "emotion": "neutral",
        "emotion_intensity": 0.3, "tool_calls_made": [],
        "result_type": "normal", "_findings": {"answer": "faq answer"},
    }
    result = emotion_monitor(state)
    assert_is_none("general normal -> None", result["escalate_signal"])
    assert_eq("general source_agent", result["agent_findings"][0]["source_agent"], "general_agent")

    # 投诉关键词 -> to_complaint
    state_kw = {**state, "messages": [FakeMsg("我要举报你们")]}
    result_kw = emotion_monitor(state_kw)
    assert_eq("general complaint keyword", result_kw["escalate_signal"], "to_complaint")

    # 极端愤怒 -> to_complaint
    state_angry = {**state, "emotion": "angry", "emotion_intensity": 0.95}
    result_angry = emotion_monitor(state_angry)
    assert_eq("general extreme emotion", result_angry["escalate_signal"], "to_complaint")


def test_A7_context_wrapper_protection():
    """A7. context_wrapper 超时/错误边界"""
    section("A7. context_wrapper 超时/错误边界")
    from src.graph.nodes.context_wrapper import (
        _create_fallback_result,
        _create_escalate_to_human_result,
    )
    from src.utils.observability import TraceTimer

    timer = TraceTimer()
    timer.start()

    # fallback 结果: 普通子图
    fb = _create_fallback_result("presales_agent", "test-trace", timer, "timeout", 30000)
    assert_true("fallback is_fallback", fb["is_fallback"])
    assert_eq("fallback result_type", fb["agent_findings"][0]["result_type"], "fallback")
    assert_is_none("fallback no escalate_signal", fb["agent_findings"][0]["escalate_signal"])
    assert_true("fallback has message", len(fb["agent_findings"][0]["findings"]["answer"]) > 0)

    # fallback: 不同子图有不同消息
    fb_insales = _create_fallback_result("insales_agent", "test-trace", timer, "error", 1000)
    assert_true("insales fallback", fb_insales["is_fallback"])
    assert_true("insales different msg",
                fb_insales["agent_findings"][0]["findings"]["answer"] != fb["agent_findings"][0]["findings"]["answer"])

    # escalate_to_human: 投诉子图不降级
    es = _create_escalate_to_human_result("complaint_agent", "test-trace", timer, "timeout", 30000)
    assert_eq("complaint escalate signal", es["escalate_signal"], "to_human")
    assert_eq("complaint finding signal", es["agent_findings"][0]["escalate_signal"], "to_human")
    assert_false("complaint no fallback", "is_fallback" in es)


def test_A8_subgraph_output_router_escalation():
    """A8. subgraph_output_router 升级信号路由"""
    section("A8. subgraph_output_router 升级信号路由")
    from src.graph.nodes.subgraph_output_router import (
        subgraph_output_router,
        route_after_output_router,
    )

    # to_complaint -> complaint_agent
    state = {
        "trace_id": "t", "_turn_start_idx": 0,
        "clarification_attempts": 0,
        "agent_findings": [{"escalate_signal": "to_complaint", "result_type": "normal"}],
    }
    router = subgraph_output_router(state)
    assert_eq("router signal", router["escalate_signal"], "to_complaint")
    assert_eq("route to complaint", route_after_output_router(router), "complaint_agent")

    # to_human -> escalate_to_human
    state2 = {**state, "agent_findings": [{"escalate_signal": "to_human", "result_type": "normal"}]}
    router2 = subgraph_output_router(state2)
    assert_eq("route to human", route_after_output_router(router2), "escalate_to_human")

    # 正常 -> content_merger
    state3 = {**state, "agent_findings": [{"escalate_signal": None, "result_type": "normal"}]}
    router3 = subgraph_output_router(state3)
    assert_eq("route normal", route_after_output_router(router3), "content_merger")

    # fallback 标记
    state4 = {**state, "agent_findings": [{"escalate_signal": None, "result_type": "fallback"}]}
    router4 = subgraph_output_router(state4)
    assert_true("fallback flag", router4.get("is_fallback", False))
    assert_eq("fallback route", route_after_output_router(router4), "content_merger")

    # 中断时保存其他子图结果
    state5 = {
        "trace_id": "t", "_turn_start_idx": 0,
        "clarification_attempts": 0,
        "agent_findings": [
            {"escalate_signal": "to_complaint", "result_type": "normal", "source": "general"},
            {"escalate_signal": None, "result_type": "normal", "source": "presales"},
        ],
    }
    router5 = subgraph_output_router(state5)
    assert_eq("interrupted results saved", len(router5["interrupted_subgraph_results"]), 1)


# ======================================================================
# Part B: Session Takeover 测试 (无需 API)
# ======================================================================

def test_B1_escalate_normal():
    """B1. escalate_to_human 普通转接模式"""
    section("B1. escalate_to_human 普通转接")
    from src.graph.nodes.escalate_to_human import escalate_to_human

    state = {
        "messages": [], "trace_events": [], "customer_id": "C001",
        "customer_tier": "standard", "emotion": "neutral",
        "merged_content": "AI tried this",
    }
    result = escalate_to_human(state)

    assert_false("normal: not takeover", result["session_takeover"])
    assert_eq("normal: status escalated", result["resolution_status"], "escalated")
    assert_true("normal: has draft_response", len(result.get("draft_response", "")) > 0)
    assert_true("normal: has AIMessage", len(result.get("messages", [])) > 0)
    assert_false("normal: no takeover in msg",
                 "接管" in result.get("draft_response", ""))


def test_B2_escalate_takeover():
    """B2. escalate_to_human 接管模式"""
    section("B2. escalate_to_human 接管模式")
    from src.graph.nodes.escalate_to_human import escalate_to_human, TAKEOVER_CUSTOMER_MSG

    state = {
        "messages": [], "trace_events": [], "customer_id": "C001",
        "customer_tier": "vip", "emotion": "angry",
        "human_decision": "takeover",
        "merged_content": "AI attempted",
        "human_feedback": "wrong approach",
    }
    result = escalate_to_human(state)

    assert_true("takeover: flag set", result["session_takeover"])
    assert_eq("takeover: msg matches", result["draft_response"], TAKEOVER_CUSTOMER_MSG)
    assert_true("takeover: has feedback in summary",
                "wrong approach" in result.get("merged_content", ""))


def test_B3_escalate_takeover_persistence():
    """B3. escalate_to_human 接管持久性"""
    section("B3. escalate_to_human 接管持久性")
    from src.graph.nodes.escalate_to_human import escalate_to_human

    # 模拟: session_takeover 已为 True (来自 checkpoint)，human_decision 可能不是 takeover
    state_persisted = {
        "messages": [], "trace_events": [], "customer_id": "C001",
        "customer_tier": "standard", "emotion": "neutral",
        "session_takeover": True,
        "merged_content": "",
    }
    result = escalate_to_human(state_persisted)

    # 接管状态应该保持
    assert_true("persisted: takeover kept", result["session_takeover"])
    # 应该使用后续消息而非首次接管通知
    assert_true("persisted: shorter msg",
                "转由人工" in result.get("draft_response", ""))


def test_B4_orchestrator_takeover_check():
    """B4. orchestrator_gate 接管状态检查"""
    section("B4. orchestrator_gate 接管状态检查")
    from src.graph.nodes.orchestrator_gate import orchestrator_gate
    from src.state.schema import create_initial_state
    from langchain_core.messages import HumanMessage

    # session_takeover=True -> 直达 escalate_to_human
    state = create_initial_state("s1", "C001")
    state["session_takeover"] = True
    state["messages"] = [HumanMessage(content="任何消息")]
    result = orchestrator_gate(state)

    assert_eq("takeover route", result["active_agents"], ["escalate_to_human"])
    assert_true("takeover reason", "接管" in result.get("routing_reason", ""))

    # session_takeover=False -> 正常流程
    state2 = create_initial_state("s2", "C001")
    state2["messages"] = [HumanMessage(content="人工客服")]
    result2 = orchestrator_gate(state2)

    # 转人工快捷通道（不是接管）
    assert_eq("shortcut route", result2["active_agents"], ["escalate_to_human"])
    assert_false("shortcut not takeover reason",
                 "接管" in result2.get("routing_reason", ""))


def test_B5_human_review_takeover():
    """B5. human_review 接管决策"""
    section("B5. human_review 接管决策")
    from src.graph.nodes.human_review import human_review

    # 超过审核轮次 -> 强制接管
    state_force = {
        "trace_id": "t", "human_review_rounds": 2,
        "draft_response": "test", "risk_level": "high",
        "quality_score": 0.3, "safety_flags": [],
        "human_review_reason": "test",
    }
    result_force = human_review(state_force)
    assert_eq("force takeover", result_force["human_decision"], "takeover")


def test_B6_route_after_human_review_takeover():
    """B6. route_after_human_review 接管路由"""
    section("B6. route_after_human_review 接管路由")
    from src.graph.nodes.human_review import route_after_human_review

    # takeover -> escalate_to_human
    assert_eq("takeover route",
              route_after_human_review({"human_decision": "takeover"}),
              "escalate_to_human")

    # approve -> output_gate
    assert_eq("approve route",
              route_after_human_review({"human_decision": "approve"}),
              "output_gate")

    # reject_regenerate -> content_merger
    assert_eq("reject_regenerate route",
              route_after_human_review({"human_decision": "reject_regenerate"}),
              "content_merger")

    # reject_reclassify -> orchestrator_gate
    assert_eq("reject_reclassify route",
              route_after_human_review({"human_decision": "reject_reclassify"}),
              "orchestrator_gate")


# ======================================================================
# Part C: 端到端生命周期 (需要 API)
# ======================================================================

def test_C1_full_takeover_lifecycle():
    """C1. 完整接管生命周期: 激活 -> 持久化 -> 释放 -> 恢复"""
    section("C1. 完整接管生命周期 (需要 API)")

    if not os.environ.get("OPENAI_API_KEY"):
        print("  SKIP: 未配置 OPENAI_API_KEY")
        return

    from src.graph.supervisor import compile_supervisor_graph
    from src.state.schema import create_initial_state
    from src.graph.nodes.escalate_to_human import release_takeover
    from src.utils.observability import generate_trace_id
    from langchain_core.messages import HumanMessage
    import uuid

    app = compile_supervisor_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # --- Step 1: 正常对话 ---
    print("  Step 1: 正常对话...")
    state1 = create_initial_state("s1", "C001", "standard")
    state1["trace_id"] = generate_trace_id()
    state1["messages"] = [HumanMessage(content="你好")]
    result1 = app.invoke(state1, config)
    assert_false("step1: not takeover", result1.get("session_takeover"))
    print(f"    takeover={result1.get('session_takeover')}, status={result1.get('resolution_status')}")

    # --- Step 2: 模拟 human_review 选择接管 ---
    print("  Step 2: 模拟接管激活...")
    app.update_state(
        config,
        {"session_takeover": True, "human_decision": "takeover"},
        as_node="human_review",
    )
    snapshot2 = app.get_state(config)
    assert_true("step2: takeover activated", snapshot2.values.get("session_takeover"))
    print(f"    takeover={snapshot2.values.get('session_takeover')}")

    # --- Step 3: 接管模式下的客户消息 ---
    print("  Step 3: 接管模式下发送消息...")
    state3 = {
        "messages": [HumanMessage(content="我的问题还没解决")],
        "trace_id": generate_trace_id(),
    }
    result3 = app.invoke(state3, config)
    assert_true("step3: takeover persists", result3.get("session_takeover"))
    assert_eq("step3: status escalated", result3.get("resolution_status"), "escalated")
    print(f"    takeover={result3.get('session_takeover')}, draft={result3.get('draft_response', '')[:50]}")

    # --- Step 4: 释放接管 ---
    print("  Step 4: 释放接管...")
    release_result = release_takeover(app, config)
    snapshot4 = app.get_state(config)
    assert_false("step4: takeover released", snapshot4.values.get("session_takeover"))
    print(f"    takeover={snapshot4.values.get('session_takeover')}")

    # --- Step 5: 恢复正常 AI 处理 ---
    print("  Step 5: 恢复正常对话...")
    state5 = {
        "messages": [HumanMessage(content="谢谢")],
        "trace_id": generate_trace_id(),
    }
    result5 = app.invoke(state5, config)
    assert_false("step5: takeover still false", result5.get("session_takeover"))
    print(f"    takeover={result5.get('session_takeover')}, status={result5.get('resolution_status')}")

    print("  完整生命周期验证通过!")


# ======================================================================
# 主入口
# ======================================================================

def run_all(run_api=True):
    global _passed, _failed, _errors

    print("\n" + "=" * 60)
    print("  中断协议 + Session Takeover 测试套件")
    print("=" * 60)

    t0 = time.time()

    # Part A: 中断协议 (纯逻辑, 无需 API)
    try:
        test_A1_escalation_utils()
    except Exception as e:
        print(f"  ERROR in A1: {e}")
        _errors.append(str(e))

    try:
        test_A2_presales_escalation_monitor()
    except Exception as e:
        print(f"  ERROR in A2: {e}")
        _errors.append(str(e))

    try:
        test_A3_insales_escalation_monitor()
    except Exception as e:
        print(f"  ERROR in A3: {e}")
        _errors.append(str(e))

    try:
        test_A4_aftersales_escalation_monitor()
    except Exception as e:
        print(f"  ERROR in A4: {e}")
        _errors.append(str(e))

    try:
        test_A5_complaint_escalation_monitor()
    except Exception as e:
        print(f"  ERROR in A5: {e}")
        _errors.append(str(e))

    try:
        test_A6_general_emotion_monitor()
    except Exception as e:
        print(f"  ERROR in A6: {e}")
        _errors.append(str(e))

    try:
        test_A7_context_wrapper_protection()
    except Exception as e:
        print(f"  ERROR in A7: {e}")
        _errors.append(str(e))

    try:
        test_A8_subgraph_output_router_escalation()
    except Exception as e:
        print(f"  ERROR in A8: {e}")
        _errors.append(str(e))

    # Part B: Session Takeover (纯逻辑, 无需 API)
    try:
        test_B1_escalate_normal()
    except Exception as e:
        print(f"  ERROR in B1: {e}")
        _errors.append(str(e))

    try:
        test_B2_escalate_takeover()
    except Exception as e:
        print(f"  ERROR in B2: {e}")
        _errors.append(str(e))

    try:
        test_B3_escalate_takeover_persistence()
    except Exception as e:
        print(f"  ERROR in B3: {e}")
        _errors.append(str(e))

    try:
        test_B4_orchestrator_takeover_check()
    except Exception as e:
        print(f"  ERROR in B4: {e}")
        _errors.append(str(e))

    try:
        test_B5_human_review_takeover()
    except Exception as e:
        print(f"  ERROR in B5: {e}")
        _errors.append(str(e))

    try:
        test_B6_route_after_human_review_takeover()
    except Exception as e:
        print(f"  ERROR in B6: {e}")
        _errors.append(str(e))

    # Part C: 端到端 (需要 API)
    if run_api:
        try:
            test_C1_full_takeover_lifecycle()
        except Exception as e:
            print(f"  ERROR in C1: {e}")
            _errors.append(str(e))

    # 结果汇总
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    total = _passed + _failed
    print(f"  测试结果: {_passed}/{total} 通过, {_failed} 失败")
    print(f"  耗时: {elapsed:.1f}s")
    if _errors:
        print(f"\n  失败详情:")
        for err in _errors:
            print(f"    {err}")
    print("=" * 60)

    return _failed == 0


if __name__ == "__main__":
    no_api = "--no-api" in sys.argv
    success = run_all(run_api=not no_api)
    sys.exit(0 if success else 1)
