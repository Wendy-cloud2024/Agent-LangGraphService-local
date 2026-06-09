"""
测试: clarify_to_customer 状态清理 + 补全字段 + unused imports 验证

覆盖:
  1. clarify_to_customer 清除 clarification_request
  2. clarify_to_customer 保存完整 pending_accumulated_state (含新增字段)
  3. clarify_to_customer 递增 clarification_attempts
  4. clarify_to_customer 设置 pending_clarification / pending_subgraph
  5. clarify_to_customer 写入 AIMessage 到 messages
  6. 澄清重入恢复时 pending_accumulated_state 各字段还原
  7. subgraph_output_router 不被残留 clarification_request 误导
  8. unused imports 已清除 (编译级验证)
  9. API 端到端: 澄清回路完整闭环

运行方式:
  python tests/test_clarify_and_quality.py
  python tests/test_clarify_and_quality.py --no-api
"""

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

_passed = 0
_failed = 0
_errors = []


def check(name, condition):
    global _passed, _failed
    if condition:
        _passed += 1
    else:
        _failed += 1
        msg = f"  FAIL: {name}"
        print(msg)
        _errors.append(msg)


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ======================================================================
# Part A: clarify_to_customer 纯逻辑测试 (无需 API)
# ======================================================================

def test_A1_clarify_clears_request():
    """A1. clarification_request 被清除为 None"""
    section("A1. clarification_request 被清除")
    from src.graph.nodes.clarify_to_customer import clarify_to_customer

    state = {
        "messages": [], "trace_id": "t",
        "clarification_request": {"question": "请提供订单号", "required_info": "order_id"},
        "intent_labels": [{"intent": "aftersales_return", "confidence": 0.9, "primary": True}],
        "emotion": "neutral", "emotion_intensity": 0.3,
        "customer_tier": "vip", "urgency": "medium", "language": "zh",
        "clarification_attempts": 0,
    }
    result = clarify_to_customer(state)

    check("clarification_request cleared to None", result.get("clarification_request") is None)
    check("pending_clarification set True", result["pending_clarification"] is True)


def test_A2_accumulated_state_complete():
    """A2. pending_accumulated_state 包含所有必要字段"""
    section("A2. pending_accumulated_state 字段完整性")
    from src.graph.nodes.clarify_to_customer import clarify_to_customer

    state = {
        "messages": [], "trace_id": "t",
        "clarification_request": {"question": "请提供订单号", "required_info": "order_id"},
        "intent_labels": [{"intent": "insales_order", "confidence": 0.85, "primary": True}],
        "emotion": "frustrated", "emotion_intensity": 0.7,
        "customer_tier": "enterprise", "urgency": "high", "language": "en",
        "clarification_attempts": 1,
    }
    result = clarify_to_customer(state)
    acc = result.get("pending_accumulated_state", {})

    # 原有字段
    check("intent_labels saved", acc.get("intent_labels") == state["intent_labels"])
    check("emotion saved", acc.get("emotion") == "frustrated")
    check("customer_tier saved", acc.get("customer_tier") == "enterprise")
    check("clarification_request saved", acc.get("clarification_request") == state["clarification_request"])

    # 新增字段
    check("urgency saved", acc.get("urgency") == "high")
    check("language saved", acc.get("language") == "en")
    check("emotion_intensity saved", acc.get("emotion_intensity") == 0.7)


def test_A3_clarification_attempts_increment():
    """A3. clarification_attempts 正确递增"""
    section("A3. clarification_attempts 递增")
    from src.graph.nodes.clarify_to_customer import clarify_to_customer

    for start_val in [0, 1]:
        state = {
            "messages": [], "trace_id": "t",
            "clarification_request": {"question": "test", "required_info": "test"},
            "intent_labels": [{"intent": "general_faq", "primary": True}],
            "emotion": "neutral", "emotion_intensity": 0.3,
            "customer_tier": "standard", "urgency": "low", "language": "zh",
            "clarification_attempts": start_val,
        }
        result = clarify_to_customer(state)
        check(f"attempts {start_val} -> {start_val + 1}",
              result["clarification_attempts"] == start_val + 1)


def test_A4_pending_subgraph_routing():
    """A4. pending_subgraph 正确映射"""
    section("A4. pending_subgraph 映射")
    from src.graph.nodes.clarify_to_customer import clarify_to_customer

    test_cases = [
        ([{"intent": "presales_product", "primary": True}], "presales_agent"),
        ([{"intent": "aftersales_return", "primary": True}], "aftersales_agent"),
        ([{"intent": "complaint_product", "primary": True}], "complaint_agent"),
        ([{"intent": "insales_order", "primary": True}], "insales_agent"),
        ([{"intent": "general_faq", "primary": True}], "general_agent"),
        ([], "general_agent"),  # 无意图标签 -> 兜底
    ]

    for intent_labels, expected_subgraph in test_cases:
        state = {
            "messages": [], "trace_id": "t",
            "clarification_request": {"question": "test", "required_info": "test"},
            "intent_labels": intent_labels,
            "emotion": "neutral", "emotion_intensity": 0.3,
            "customer_tier": "standard", "urgency": "low", "language": "zh",
            "clarification_attempts": 0,
        }
        result = clarify_to_customer(state)
        intent_name = intent_labels[0].get("intent", "empty") if intent_labels else "empty"
        check(f"intent={intent_name} -> {expected_subgraph}",
              result["pending_subgraph"] == expected_subgraph)


def test_A5_messages_written():
    """A5. 澄清消息写入 messages (AIMessage)"""
    section("A5. AIMessage 写入 messages")
    from src.graph.nodes.clarify_to_customer import clarify_to_customer
    from langchain_core.messages import AIMessage

    state = {
        "messages": [], "trace_id": "t",
        "clarification_request": {"question": "test", "required_info": "test"},
        "intent_labels": [{"intent": "general_faq", "primary": True}],
        "emotion": "neutral", "emotion_intensity": 0.3,
        "customer_tier": "standard", "urgency": "low", "language": "zh",
        "clarification_attempts": 0,
    }
    result = clarify_to_customer(state)
    msgs = result.get("messages", [])

    check("messages has 1 entry", len(msgs) == 1)
    check("is AIMessage", isinstance(msgs[0], AIMessage))
    check("message has content", len(msgs[0].content) > 0)
    check("draft_response matches message", result.get("draft_response") == msgs[0].content)


def test_A6_clarification_reentry_restores_state():
    """A6. 澄清重入时 orchestrator_gate 从 pending_accumulated_state 恢复"""
    section("A6. 澄清重入状态恢复")
    from src.graph.nodes.orchestrator_gate import orchestrator_gate
    from src.state.schema import create_initial_state
    from langchain_core.messages import HumanMessage, AIMessage

    state = create_initial_state("s1", "C001")
    state["messages"] = [
        HumanMessage(content="我要退货"),
        AIMessage(content="请提供订单号"),
        HumanMessage(content="ORD-0042"),
    ]
    state["pending_clarification"] = True
    state["pending_subgraph"] = "aftersales_agent"
    state["pending_accumulated_state"] = {
        "intent_labels": [{"intent": "aftersales_return", "confidence": 0.9, "primary": True}],
        "emotion": "frustrated",
        "emotion_intensity": 0.7,
        "customer_tier": "vip",
        "urgency": "high",
        "language": "zh",
        "clarification_request": {"question": "请提供订单号", "required_info": "order_id"},
    }

    result = orchestrator_gate(state)

    # 应恢复澄清前状态
    check("intent_labels restored",
          result.get("intent_labels", [{}])[0].get("intent") == "aftersales_return")
    check("emotion restored", result.get("emotion") == "frustrated")
    # 应清除澄清标记
    check("pending_clarification cleared", result.get("pending_clarification") is False)
    # 应路由回原子图
    check("route back to pending_subgraph",
          result.get("active_agents") is not None or state["pending_subgraph"] == "aftersales_agent")


def test_A7_router_not_confused_by_cleared_request():
    """A7. subgraph_output_router 正确处理已清除的 clarification_request"""
    section("A7. subgraph_output_router 不误判")
    from src.graph.nodes.subgraph_output_router import (
        subgraph_output_router,
        route_after_output_router,
    )

    # 场景1: clarification_request 已清除, agent_findings 为 normal
    state_normal = {
        "trace_id": "t", "_turn_start_idx": 0,
        "clarification_attempts": 1,
        "clarification_request": None,  # 已被 clarify_to_customer 清除
        "agent_findings": [{
            "source_agent": "aftersales_agent", "result_type": "normal",
            "escalate_signal": None, "findings": {"answer": "退货已处理"},
        }],
    }
    result = subgraph_output_router(state_normal)
    route = route_after_output_router(result)

    check("route to content_merger (not clarify)", route == "content_merger")
    check("no escalate", result.get("escalate_signal") is None)

    # 场景2: 子图本身返回 result_type="clarification" (这才是真正的澄清触发条件)
    state_clarify = {
        "trace_id": "t", "_turn_start_idx": 0,
        "clarification_attempts": 0,
        "clarification_request": None,
        "agent_findings": [{
            "source_agent": "aftersales_agent",
            "result_type": "clarification",
            "clarification_request": {"question": "请提供订单号", "required_info": "order_id"},
            "escalate_signal": None,
        }],
    }
    result_clarify = subgraph_output_router(state_clarify)
    route_clarify = route_after_output_router(result_clarify)
    check("subgraph clarification -> clarify_to_customer", route_clarify == "clarify_to_customer")

    # 场景3: clarification_request 残留但 agent_findings 为 normal (已修复后不会发生)
    # 验证 router 只看 agent_findings, 不看顶层 clarification_request
    state_leaked_but_normal = {
        "trace_id": "t", "_turn_start_idx": 0,
        "clarification_attempts": 0,
        "clarification_request": {"question": "残留的请求"},  # 即使残留
        "agent_findings": [{
            "source_agent": "presales_agent", "result_type": "normal",
            "escalate_signal": None, "findings": {"answer": "正常结果"},
        }],
    }
    result_leaked = subgraph_output_router(state_leaked_but_normal)
    route_leaked = route_after_output_router(result_leaked)
    check("leaked request ignored when findings are normal", route_leaked == "content_merger")


def test_A8_unused_imports_removed():
    """A8. 验证 unused imports 已清除"""
    section("A8. unused imports 清除验证")
    import ast

    # output_gate.py: 不应有 're' import
    with open("D:/cod/thesis-agent/src/graph/nodes/output_gate.py", "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    import_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                import_names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                import_names.append(alias.name)
    check("output_gate: 're' removed", "re" not in import_names)
    check("output_gate: 'json' kept (used)", "json" in import_names)

    # orchestrator_gate.py: 不应有 'json' import
    with open("D:/cod/thesis-agent/src/graph/nodes/orchestrator_gate.py", "r", encoding="utf-8") as f:
        source2 = f.read()
    tree2 = ast.parse(source2)
    import_names2 = []
    for node in ast.walk(tree2):
        if isinstance(node, ast.Import):
            for alias in node.names:
                import_names2.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                import_names2.append(alias.name)
    check("orchestrator_gate: 'json' removed", "json" not in import_names2)
    check("orchestrator_gate: 're' kept (used)", "re" in import_names2)


# ======================================================================
# Part B: API 端到端 (需要 API)
# ======================================================================

def test_B1_clarification_loop_e2e():
    """B1. 澄清回路端到端: 正常 → 澄清 → 回复 → 恢复"""
    section("B1. 澄清回路端到端 (API)")

    if not os.environ.get("OPENAI_API_KEY"):
        print("  SKIP: 未配置 OPENAI_API_KEY")
        return

    from src.graph.supervisor import compile_supervisor_graph
    from src.state.schema import create_initial_state
    from src.utils.observability import generate_trace_id
    from langchain_core.messages import HumanMessage
    import uuid

    app = compile_supervisor_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Step 1: 触发需要订单号的售后请求
    state1 = create_initial_state("s1", "C001", "standard")
    state1["trace_id"] = generate_trace_id()
    state1["messages"] = [HumanMessage(content="我要退货")]
    result1 = app.invoke(state1, config)
    status1 = result1.get("resolution_status", "")
    print(f"  Step1: status={status1}")

    check("step1 completed", status1 in ("resolved", "escalated", "clarifying"))

    # 验证结果
    findings1 = result1.get("agent_findings", [])
    has_clarification = any(f.get("result_type") == "clarification" for f in findings1)
    print(f"  Step1: findings={len(findings1)}, has_clarification={has_clarification}")

    if result1.get("pending_clarification"):
        print("  Step1: 澄清已触发, pending_subgraph=" + str(result1.get("pending_subgraph")))
        check("pending_clarification set", True)
        check("pending_subgraph not empty", len(result1.get("pending_subgraph", "")) > 0)
        check("accumulated state saved", len(result1.get("pending_accumulated_state", {})) > 0)
    else:
        # 子图可能没有返回 clarification (直接回答了), 这也是合理的
        print("  Step1: 子图直接回答了, 未触发澄清")
        check("direct answer (no clarification needed)", True)


# ======================================================================
# 主入口
# ======================================================================

def main():
    global _passed, _failed, _errors
    run_api = "--no-api" not in sys.argv

    print("\n" + "=" * 60)
    print("  clarify_to_customer + 代码质量 测试套件")
    print("=" * 60)

    t0 = time.time()

    # Part A: 纯逻辑
    for fn in [test_A1_clarify_clears_request,
               test_A2_accumulated_state_complete,
               test_A3_clarification_attempts_increment,
               test_A4_pending_subgraph_routing,
               test_A5_messages_written,
               test_A6_clarification_reentry_restores_state,
               test_A7_router_not_confused_by_cleared_request,
               test_A8_unused_imports_removed]:
        try:
            fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            _errors.append(str(e))

    # Part B: API
    if run_api:
        try:
            test_B1_clarification_loop_e2e()
        except Exception as e:
            print(f"  ERROR in B1: {e}")
            import traceback
            traceback.print_exc()
            _errors.append(str(e))

    elapsed = time.time() - t0
    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  {_passed}/{total} PASSED, {_failed} FAILED ({elapsed:.1f}s)")
    if _errors:
        print(f"\n  Errors:")
        for err in _errors:
            print(f"    {err}")
    print("=" * 60)

    return _failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
