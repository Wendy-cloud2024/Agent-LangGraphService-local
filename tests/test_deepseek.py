"""
测试脚本 - 使用DeepSeek API测试各个模块
"""

import os
import sys

# 修复Windows终端编码
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置API密钥和base_url
os.environ["OPENAI_API_KEY"] = "sk-f3b2dd6ef609479d888367cf659a8527"
os.environ["LLM_BASE_URL"] = "https://api.deepseek.com"

import uuid
from langchain_core.messages import HumanMessage

from src.state.schema import create_initial_state
from src.utils.observability import generate_trace_id


def test_orchestrator_gate():
    """测试入口关卡节点"""
    print("=" * 60)
    print("测试1: orchestrator_gate - 意图分类和路由")
    print("=" * 60)

    from src.graph.nodes.orchestrator_gate import orchestrator_gate

    state = create_initial_state(
        session_id="test-001",
        customer_id="C001",
        customer_tier="standard",
    )
    state["trace_id"] = generate_trace_id()
    state["messages"] = [HumanMessage(content="我想退货，商品质量问题")]

    result = orchestrator_gate(state)

    print(f"  意图标签: {result.get('intent_labels', [])}")
    print(f"  情感: {result.get('emotion', '')} (强度: {result.get('emotion_intensity', 0)})")
    print(f"  路由到: {result.get('active_agents', [])}")
    print(f"  路由原因: {result.get('routing_reason', '')}")
    print(f"  安全审核: {result.get('safety_screen_passed', True)}")
    print()


def test_human_transfer():
    """测试转人工快捷通道"""
    print("=" * 60)
    print("测试2: 转人工快捷匹配")
    print("=" * 60)

    from src.graph.nodes.orchestrator_gate import orchestrator_gate

    state = create_initial_state(
        session_id="test-002",
        customer_id="C002",
        customer_tier="vip",
    )
    state["trace_id"] = generate_trace_id()
    state["messages"] = [HumanMessage(content="我要转人工客服")]

    result = orchestrator_gate(state)

    print(f"  路由到: {result.get('active_agents', [])}")
    print(f"  路由原因: {result.get('routing_reason', '')}")
    print()


def test_general_agent():
    """测试通用Agent子图"""
    print("=" * 60)
    print("测试3: 通用Agent子图 - FAQ匹配")
    print("=" * 60)

    from src.graph.subgraphs.general.graph import compile_general_subgraph

    subgraph = compile_general_subgraph()

    state = create_initial_state(
        session_id="test-003",
        customer_id="C003",
        customer_tier="standard",
    )
    state["trace_id"] = generate_trace_id()
    state["messages"] = [HumanMessage(content="你们的运费政策是什么？")]

    result = subgraph.invoke(state)

    findings = result.get("findings", {})
    print(f"  结果类型: {result.get('result_type', '')}")
    print(f"  回答: {findings.get('answer', '')[:200]}")
    print(f"  FAQ匹配: {findings.get('faq_matched', False)}")
    print(f"  政策匹配: {findings.get('policy_matched', False)}")
    print()


def test_presales_agent():
    """测试售前Agent子图"""
    print("=" * 60)
    print("测试4: 售前Agent子图 - 商品咨询")
    print("=" * 60)

    from src.graph.subgraphs.presales.graph import compile_presales_subgraph

    subgraph = compile_presales_subgraph()

    state = create_initial_state(
        session_id="test-004",
        customer_id="C004",
        customer_tier="vip",
    )
    state["trace_id"] = generate_trace_id()
    state["messages"] = [HumanMessage(content="我想了解一下你们有没有蓝牙耳机")]

    result = subgraph.invoke(state)

    findings = result.get("findings", {})
    print(f"  结果类型: {result.get('result_type', '')}")
    print(f"  回答: {findings.get('answer', '')[:200]}")
    print(f"  库存: {findings.get('in_stock', False)}")
    print(f"  优惠: {findings.get('promotions', [])}")
    print()


def test_content_merger_and_tone():
    """测试内容融合和语气适配"""
    print("=" * 60)
    print("测试5: 内容融合 + 语气适配")
    print("=" * 60)

    from src.graph.nodes.content_merger import content_merger
    from src.graph.nodes.tone_adapter import tone_adapter

    state = create_initial_state(
        session_id="test-005",
        customer_id="C005",
        customer_tier="vip",
    )
    state["trace_id"] = generate_trace_id()
    state["agent_findings"] = [{
        "result_type": "normal",
        "source_agent": "presales_agent",
        "findings": {"answer": "我们有蓝牙耳机，价格299元，目前有库存。"},
    }]
    state["intent_labels"] = [{"intent": "presales_product", "confidence": 0.9, "primary": True}]
    state["emotion"] = "happy"
    state["emotion_intensity"] = 0.3

    # 内容融合
    merge_result = content_merger(state)
    state.update(merge_result)
    print(f"  融合内容: {state.get('merged_content', '')[:200]}")

    # 语气适配
    tone_result = tone_adapter(state)
    state.update(tone_result)
    print(f"  适配后回复: {state.get('draft_response', '')[:200]}")
    print()


def test_safety_check():
    """测试安全检查"""
    print("=" * 60)
    print("测试6: 安全检查工具")
    print("=" * 60)

    from src.utils.safety import (
        check_sensitive_words, check_pii_leak, full_safety_check
    )

    # 测试敏感词
    hit, words = check_sensitive_words("我要投诉你们！")
    print(f"  敏感词检测 '我要投诉你们': hit={hit}, words={words}")

    # 测试PII
    has_pii, flags = check_pii_leak("我的手机号是13800138000")
    print(f"  PII检测 '手机号13800138000': has_pii={has_pii}, flags={flags}")

    # 完整安全检查
    passed, flags = full_safety_check("你好，请问有什么可以帮助您的？")
    print(f"  安全检查 (正常文本): passed={passed}, flags={flags}")
    print()


def test_subgraph_output_router():
    """测试子图输出路由器"""
    print("=" * 60)
    print("测试7: 子图输出路由器")
    print("=" * 60)

    from src.graph.nodes.subgraph_output_router import subgraph_output_router

    # 测试正常结果
    state = create_initial_state(
        session_id="test-007",
        customer_id="C007",
        customer_tier="standard",
    )
    state["trace_id"] = generate_trace_id()
    state["agent_findings"] = [{
        "result_type": "normal",
        "findings": {"answer": "正常结果"},
        "escalate_signal": None,
    }]

    result = subgraph_output_router(state)
    print(f"  正常结果 → is_fallback={result.get('is_fallback', False)}")

    # 测试降级结果
    state["agent_findings"] = [{
        "result_type": "fallback",
        "fallback_reason": "timeout",
        "escalate_signal": None,
    }]
    result = subgraph_output_router(state)
    print(f"  降级结果 → is_fallback={result.get('is_fallback', False)}, reason={result.get('fallback_reason', '')}")

    # 测试升级信号
    state["agent_findings"] = [{
        "result_type": "normal",
        "escalate_signal": "to_complaint",
    }]
    result = subgraph_output_router(state)
    print(f"  升级信号 → escalate_signal={result.get('escalate_signal', '')}")
    print()


if __name__ == "__main__":
    print("\n开始测试 DeepSeek API 集成...\n")

    try:
        test_safety_check()
        test_subgraph_output_router()
        test_orchestrator_gate()
        test_human_transfer()
        test_content_merger_and_tone()
        test_general_agent()
        test_presales_agent()

        print("\n" + "=" * 60)
        print("所有测试完成!")
        print("=" * 60)
    except Exception as e:
        import traceback
        print(f"\n测试失败: {e}")
        traceback.print_exc()
