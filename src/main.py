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

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from langchain_core.messages import HumanMessage

from src.graph.supervisor import compile_supervisor_graph
from src.state.schema import create_initial_state
from src.utils.observability import generate_trace_id
from src.tools.result_logger import log_invoke_result, log_execution_path
from src.graph.nodes.escalate_to_human import release_takeover

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# 模块级单例：只编译一次图，避免每次对话重复编译
_app = None


def _get_app():
    global _app
    if _app is None:
        _app = compile_supervisor_graph()
    return _app


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
    app = _get_app()

    # 创建线程ID
    if not thread_id:
        thread_id = str(uuid.uuid4())

    trace_id = generate_trace_id()

    # 加载客户画像 (Layer 4 记忆)
    from src.memory.customer_store import get_customer_store
    store = get_customer_store()
    customer_profile = store.load(customer_id)
    # 如果画像中有等级且未显式指定，使用画像中的等级
    if customer_tier == "standard" and customer_profile.get("tier"):
        customer_tier = customer_profile["tier"]

    # 创建初始状态
    initial_state = create_initial_state(
        session_id=thread_id,
        customer_id=customer_id,
        customer_tier=customer_tier,
    )
    initial_state["customer_profile"] = customer_profile
    initial_state["trace_id"] = trace_id
    initial_state["messages"] = [HumanMessage(content=message)]

    # 运行图
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = app.invoke(initial_state, config)
        log_invoke_result(result)
        log_execution_path(result)
        return result
    except Exception as e:
        logger.error(f"对话执行失败: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


def interactive_mode():
    """交互式对话模式

    支持两种模式:
      - 正常模式: 客户与 AI 对话
      - 接管模式: 人工客服接管后，所有消息直达人工

    特殊命令:
      - /end_takeover: 人工客服结束接管，恢复 AI 处理
      - /status: 查看当前会话状态
      - quit/exit: 退出程序
    """
    print("=" * 60)
    print("  电商智能客服Agent - 交互模式")
    print("  输入 'quit' 或 'exit' 退出")
    print("  输入 '/status' 查看会话状态")
    print("=" * 60)

    customer_id = input("请输入客户ID (默认: C001): ").strip() or "C001"
    customer_tier = input("请输入客户等级 (standard/vip/enterprise, 默认: standard): ").strip() or "standard"

    thread_id = str(uuid.uuid4())
    print(f"\n会话ID: {thread_id}")
    print("-" * 40)

    app = _get_app()
    first_turn = True
    session_takeover = False  # 本地追踪接管状态

    while True:
        # 根据接管状态显示不同的提示符
        if session_takeover:
            try:
                message = input("\n[接管模式] 人工客服> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break
        else:
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

        config = {"configurable": {"thread_id": thread_id}}

        # ============================================================
        # 特殊命令处理
        # ============================================================

        # /end_takeover: 人工客服结束接管
        if message == "/end_takeover":
            if session_takeover:
                result = release_takeover(app, config)
                if result is not None:
                    session_takeover = False
                    print("\n[系统] 接管已释放，AI 将恢复自动处理。")
                    print(f"客服: 已为您处理完毕，如果您还有其他问题，欢迎随时咨询。")
                else:
                    print("\n[系统] 释放接管失败，请重试。")
            else:
                print("\n[系统] 当前不在接管模式。")
            continue

        # /status: 查看当前会话状态
        if message == "/status":
            snapshot = app.get_state(config)
            values = snapshot.values
            takeover = values.get("session_takeover", False)
            status = values.get("resolution_status", "")
            msg_count = len(values.get("messages", []))
            findings = len(values.get("agent_findings", []))
            print(f"\n[会话状态]")
            print(f"  接管模式: {'是' if takeover else '否'}")
            print(f"  解决状态: {status}")
            print(f"  消息数量: {msg_count}")
            print(f"  子图结果: {findings}")
            if snapshot.next:
                print(f"  待执行节点: {snapshot.next}")
            continue

        trace_id = generate_trace_id()

        if first_turn:
            # 首轮: 需要完整的初始状态（尚无checkpoint）
            from src.memory.customer_store import get_customer_store
            store = get_customer_store()
            customer_profile = store.load(customer_id)

            initial_state = create_initial_state(
                session_id=thread_id,
                customer_id=customer_id,
                customer_tier=customer_tier,
            )
            initial_state["customer_profile"] = customer_profile
            initial_state["trace_id"] = trace_id
            initial_state["messages"] = [HumanMessage(content=message)]
            first_turn = False
        else:
            # 后续轮: 仅传入新消息，让checkpoint保留对话历史和状态
            # 关键修复: 不再调用 create_initial_state() 覆盖全量状态
            #   - messages 通过 add_messages reducer 自动追加
            #   - 标量字段 (pending_clarification, session_takeover等) 从checkpoint保留
            #   - reducer字段 (agent_findings等) 通过 orchestrator_gate 的 _turn_start_idx 管理
            initial_state = {
                "messages": [HumanMessage(content=message)],
                "trace_id": trace_id,
            }

        try:
            result = app.invoke(initial_state, config)
            log_invoke_result(result)
            log_execution_path(result)

            # 检测接管状态变化
            new_takeover = result.get("session_takeover", False)
            if new_takeover and not session_takeover:
                session_takeover = True
                print("\n[系统] 人工客服已接管此会话。")
                print("  输入 /end_takeover 结束接管")
                print("  人工客服可直接输入回复内容")

            # 显示回复
            draft = result.get("draft_response", "") or result.get("merged_content", "")
            if draft:
                print(f"\n客服: {draft}")
            else:
                print("\n客服: 抱歉，我暂时无法处理您的请求。")

            status = result.get("resolution_status", "")
            if status == "escalated":
                if session_takeover:
                    print("  [已进入人工接管模式]")
                else:
                    print("  [已转接人工客服]")
            elif status == "clarifying":
                print("  [等待您提供更多信息]")

        except Exception as e:
            logger.error(f"对话执行失败: {e}", exc_info=True)
            print(f"\n[系统错误]: {e}")


if __name__ == "__main__":
    interactive_mode()
