"""
电商智能客服Agent - 主入口

基于LangGraph构建的多Agent电商客服系统。
支持售前/售中/售后/投诉/通用五大场景，
具备人工审核、澄清回路、降级策略等完整功能。
"""

import os
import sys
import uuid
import logging

# 确保src目录在Python路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage

from src.graph.supervisor import compile_supervisor_graph
from src.state.schema import create_initial_state
from src.utils.observability import generate_trace_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_conversation(
    customer_id: str,
    message: str,
    thread_id: str | None = None,
    customer_tier: str = "standard",
) -> dict:
    """运行一次对话

    参数:
        customer_id: 客户ID
        message: 客户消息
        thread_id: 线程ID（用于持续对话）
        customer_tier: 客户等级

    返回: 最终状态
    """
    # 编译图
    app = compile_supervisor_graph()

    # 创建线程ID
    if not thread_id:
        thread_id = str(uuid.uuid4())

    trace_id = generate_trace_id()

    # 创建初始状态
    initial_state = create_initial_state(
        session_id=thread_id,
        customer_id=customer_id,
        customer_tier=customer_tier,
    )
    initial_state["trace_id"] = trace_id
    initial_state["messages"] = [HumanMessage(content=message)]

    # 运行图
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = app.invoke(initial_state, config)
        return result
    except Exception as e:
        logger.error(f"对话执行失败: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


def interactive_mode():
    """交互式对话模式"""
    print("=" * 60)
    print("  电商智能客服Agent - 交互模式")
    print("  输入 'quit' 或 'exit' 退出")
    print("=" * 60)

    customer_id = input("请输入客户ID (默认: C001): ").strip() or "C001"
    customer_tier = input("请输入客户等级 (standard/vip/enterprise, 默认: standard): ").strip() or "standard"

    thread_id = str(uuid.uuid4())
    print(f"\n会话ID: {thread_id}")
    print("-" * 40)

    app = compile_supervisor_graph()

    while True:
        try:
            message = input("\n客户: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if message.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

        if not message:
            continue

        trace_id = generate_trace_id()
        initial_state = create_initial_state(
            session_id=thread_id,
            customer_id=customer_id,
            customer_tier=customer_tier,
        )
        initial_state["trace_id"] = trace_id
        initial_state["messages"] = [HumanMessage(content=message)]

        config = {"configurable": {"thread_id": thread_id}}

        try:
            result = app.invoke(initial_state, config)
            draft = result.get("draft_response", "") or result.get("merged_content", "")
            if draft:
                print(f"\n客服: {draft}")
            else:
                print("\n客服: 抱歉，我暂时无法处理您的请求。")

            status = result.get("resolution_status", "")
            if status == "escalated":
                print("  [已转接人工客服]")
            elif status == "clarifying":
                print("  [等待您提供更多信息]")

        except Exception as e:
            logger.error(f"对话执行失败: {e}", exc_info=True)
            print(f"\n[系统错误]: {e}")


if __name__ == "__main__":
    interactive_mode()
