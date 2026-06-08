"""
测试: 多子图并行执行 (LangGraph Send API)

测试覆盖:
  1. route_by_labels 单意图 -> str
  2. route_by_labels 特殊路由 -> str
  3. route_by_labels 多意图 -> list[Send]
  4. 单意图端到端 (API)
  5. 多意图端到端 - 并行执行 (API)
  6. 并行结果通过 subgraph_output_router 正确聚合
  7. 并行中一个子图 escalate，另一个正常
  8. 并行中一个子图 fallback，另一个正常

运行方式:
  python tests/test_parallel_execution.py
  python tests/test_parallel_execution.py --no-api  (跳过API测试)
"""

import os
import sys
import time
import uuid

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
# Test 1-3: route_by_labels 纯逻辑测试 (无需 API)
# ======================================================================

def test_route_by_labels():
    from langgraph.types import Send
    from src.graph.nodes.orchestrator_gate import route_by_labels

    # --- Test 1: 单意图 -> str ---
    section("Test 1: route_by_labels 单意图返回 str")
    for agents, expected in [
        (["presales_agent"], "presales_agent"),
        (["insales_agent"], "insales_agent"),
        (["general_agent"], "general_agent"),
        (["complaint_agent"], "complaint_agent"),
        (["aftersales_agent"], "aftersales_agent"),
    ]:
        r = route_by_labels({"active_agents": agents})
        check(f"{agents[0]} -> str", isinstance(r, str) and r == expected)

    r_empty = route_by_labels({"active_agents": []})
    check("empty -> general_agent", r_empty == "general_agent")

    # --- Test 2: 特殊路由 -> str ---
    section("Test 2: route_by_labels 特殊路由返回 str")

    r_esc = route_by_labels({"active_agents": ["escalate_to_human"]})
    check("escalate_to_human -> str", isinstance(r_esc, str) and r_esc == "escalate_to_human")

    r_sig = route_by_labels({"active_agents": [], "escalate_signal": "to_human"})
    check("signal to_human -> str", isinstance(r_sig, str) and r_sig == "escalate_to_human")

    r_sig2 = route_by_labels({"active_agents": [], "escalate_signal": "to_complaint"})
    check("signal to_complaint -> str", isinstance(r_sig2, str) and r_sig2 == "complaint_agent")

    r_clarify = route_by_labels({
        "active_agents": [], "pending_clarification": True,
        "pending_subgraph": "aftersales_agent",
    })
    check("clarification -> str", isinstance(r_clarify, str) and r_clarify == "aftersales_agent")

    # --- Test 3: 多意图 -> list[Send] ---
    section("Test 3: route_by_labels 多意图返回 list[Send]")

    for agents, count in [
        (["presales_agent", "general_agent"], 2),
        (["insales_agent", "aftersales_agent"], 2),
        (["presales_agent", "insales_agent", "general_agent"], 3),
    ]:
        r = route_by_labels({"active_agents": agents})
        check(
            f"{agents} -> {count} Send",
            isinstance(r, list) and len(r) == count and all(isinstance(s, Send) for s in r),
        )
        if isinstance(r, list):
            targets = [s.node for s in r]
            check(f"  targets match: {targets}", set(targets) == set(agents))

    # 验证 Send 携带 state 副本
    state_multi = {
        "active_agents": ["presales_agent", "general_agent"],
        "customer_id": "C_TEST",
        "messages": ["test"],
    }
    r_multi = route_by_labels(state_multi)
    for s in r_multi:
        check("Send.arg is dict", isinstance(s.arg, dict))
        check("Send.arg has customer_id", s.arg.get("customer_id") == "C_TEST")


# ======================================================================
# Test 6-8: subgraph_output_router 并行结果处理 (无需 API)
# ======================================================================

def test_parallel_router():
    from src.graph.nodes.subgraph_output_router import (
        subgraph_output_router,
        route_after_output_router,
    )

    # --- Test 6: 两个正常结果聚合 ---
    section("Test 6: 并行结果正确聚合到 content_merger")
    multi_findings = [
        {
            "source_agent": "presales_agent", "result_type": "normal",
            "escalate_signal": None, "findings": {"answer": "T恤129元"},
        },
        {
            "source_agent": "general_agent", "result_type": "normal",
            "escalate_signal": None, "findings": {"answer": "退货7天无理由"},
        },
    ]
    state_router = {
        "trace_id": "t", "agent_findings": multi_findings,
        "_turn_start_idx": 0, "clarification_attempts": 0,
    }
    router_result = subgraph_output_router(state_router)
    route = route_after_output_router(router_result)
    check("route -> content_merger", route == "content_merger")
    check("no escalate", router_result.get("escalate_signal") is None)

    # --- Test 7: 并行中一个 escalate ---
    section("Test 7: 并行中一个子图 escalate 覆盖正常结果")
    escalate_findings = [
        {
            "source_agent": "general_agent", "result_type": "normal",
            "escalate_signal": "to_complaint", "findings": {"answer": "投诉"},
        },
        {
            "source_agent": "presales_agent", "result_type": "normal",
            "escalate_signal": None, "findings": {"answer": "商品信息"},
        },
    ]
    state_esc = {
        "trace_id": "t", "agent_findings": escalate_findings,
        "_turn_start_idx": 0, "clarification_attempts": 0,
    }
    esc_result = subgraph_output_router(state_esc)
    esc_route = route_after_output_router(esc_result)
    check("escalate signal detected", esc_result.get("escalate_signal") == "to_complaint")
    check("route -> complaint_agent", esc_route == "complaint_agent")
    check("interrupted results saved", len(esc_result.get("interrupted_subgraph_results", [])) >= 1)

    # --- Test 8: 并行中一个 fallback ---
    section("Test 8: 并行中一个子图 fallback，另一个正常")
    fallback_findings = [
        {
            "source_agent": "insales_agent", "result_type": "fallback",
            "escalate_signal": None, "fallback_reason": "timeout",
        },
        {
            "source_agent": "general_agent", "result_type": "normal",
            "escalate_signal": None, "findings": {"answer": "FAQ"},
        },
    ]
    state_fb = {
        "trace_id": "t", "agent_findings": fallback_findings,
        "_turn_start_idx": 0, "clarification_attempts": 0,
    }
    fb_result = subgraph_output_router(state_fb)
    fb_route = route_after_output_router(fb_result)
    check("fallback flagged", fb_result.get("is_fallback") == True)
    check("route -> content_merger", fb_route == "content_merger")


# ======================================================================
# Test 4-5: 端到端 (需要 API)
# ======================================================================

def test_e2e():
    from langchain_core.messages import HumanMessage
    from src.graph.supervisor import compile_supervisor_graph
    from src.state.schema import create_initial_state
    from src.utils.observability import generate_trace_id

    app = compile_supervisor_graph()

    # --- Test 4: 单意图 ---
    section("Test 4: 单意图端到端 (API)")
    thread = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread}}
    state = create_initial_state("s4", "C001", "standard")
    state["trace_id"] = generate_trace_id()
    state["messages"] = [HumanMessage(content="hello")]

    t0 = time.time()
    result = app.invoke(state, config)
    elapsed = time.time() - t0

    findings = result.get("agent_findings", [])
    sources = list(set(f.get("source_agent", "?") for f in findings))
    print(f"  agents={sources}, status={result.get('resolution_status')}, time={elapsed:.1f}s")
    check("single intent completed", result.get("resolution_status") in ("resolved", "escalated"))

    # --- Test 5: 多意图并行 ---
    section("Test 5: 多意图端到端 - 并行执行 (API)")
    thread = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread}}
    state = create_initial_state("s5", "C001", "standard")
    state["trace_id"] = generate_trace_id()
    state["messages"] = [HumanMessage(content="T恤多少钱？还有你们的退货政策是什么")]

    t0 = time.time()
    result = app.invoke(state, config)
    elapsed = time.time() - t0

    findings = result.get("agent_findings", [])
    sources = list(set(f.get("source_agent", "?") for f in findings))
    print(f"  agents={sources}, findings_count={len(findings)}, time={elapsed:.1f}s")

    check("graph completed", result.get("resolution_status") in ("resolved", "escalated"))
    check(">=2 agent findings", len(findings) >= 2)
    check(">=2 unique agents", len(sources) >= 2)

    # 打印各子图回复摘要
    for f in findings:
        agent = f.get("source_agent", "?")
        inner = f.get("findings", {})
        answer = inner.get("answer", "(no answer)")
        print(f"  [{agent}] {answer[:80]}...")


# ======================================================================
# 主入口
# ======================================================================

def main():
    global _passed, _failed, _errors

    print("\n" + "=" * 60)
    print("  多子图并行执行 (Send API) 测试套件")
    print("=" * 60)

    t0 = time.time()
    run_api = "--no-api" not in sys.argv

    # 纯逻辑测试
    try:
        test_route_by_labels()
    except Exception as e:
        print(f"  ERROR in test_route_by_labels: {e}")
        _errors.append(str(e))

    try:
        test_parallel_router()
    except Exception as e:
        print(f"  ERROR in test_parallel_router: {e}")
        _errors.append(str(e))

    # API 测试
    if run_api:
        if not os.environ.get("OPENAI_API_KEY"):
            print("\n  SKIP: 未配置 OPENAI_API_KEY")
        else:
            try:
                test_e2e()
            except Exception as e:
                print(f"  ERROR in test_e2e: {e}")
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
