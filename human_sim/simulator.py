"""
人工服务模拟器

模拟 interrupt 中断 → 人工处理 → 恢复执行的完整闭环:
  - human_review (supervisor层): 高风险回复审核，5种决策
  - approval_gate (complaint子图): 投诉补偿审批

测试场景:
  输入 "人工客服"             → 直接触发 escalate_to_human (不经过 interrupt)
  输入 "我要投诉，东西太差了"  → 可能触发投诉审批 (approval_gate interrupt)
  任何消息如果 output_gate 评高风险 → 触发人工审核 (human_review interrupt)
"""

import os
import sys
import uuid

# 确保 src 目录可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from src.graph.supervisor import compile_supervisor_graph
from src.state.schema import create_initial_state
from src.utils.observability import generate_trace_id
from src.graph.nodes.escalate_to_human import release_takeover

# ── 单例图 ──────────────────────────────────────────────
_app = None


def get_app():
    global _app
    if _app is None:
        _app = compile_supervisor_graph()
    return _app


# ── 显示工具 ────────────────────────────────────────────

def box(title: str = "", width: int = 50):
    if title:
        pad = width - len(title) - 2
        left = pad // 2
        right = pad - left
        print(f"\n{'=' * left} {title} {'=' * right}")
    else:
        print("=" * width)


def stream_execution(app, input_data, config) -> list[str]:
    """执行图并打印经过的节点，返回节点名列表"""
    visited = []
    print("\n[执行路径]")
    try:
        for event in app.stream(input_data, config, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "__end__":
                    continue
                visited.append(node_name)

                tags = []
                for key in ("risk_level", "quality_score", "resolution_status",
                            "emotion", "urgency"):
                    val = node_output.get(key)
                    if val is None:
                        continue
                    if isinstance(val, float):
                        tags.append(f"{key}={val:.2f}")
                    else:
                        tags.append(f"{key}={val}")

                suffix = f"  ({', '.join(tags)})" if tags else ""
                print(f"  -> {node_name}{suffix}")
    except Exception as e:
        print(f"  [!] 流式执行异常: {e}")
    return visited


def show_result(app, config):
    """打印最终结果"""
    snapshot = app.get_state(config)
    values = snapshot.values

    draft = values.get("draft_response", "") or values.get("merged_content", "")
    status = values.get("resolution_status", "")
    takeover = values.get("session_takeover", False)

    print(f"\n[客服回复] {draft or '(无回复)'}")
    if takeover:
        print("  -> 人工接管模式已激活")
        print("  -> 输入 /end_takeover 结束接管")
    elif status == "escalated":
        print("  -> 已转接人工客服")
    elif status == "clarifying":
        print("  -> 等待客户提供更多信息")
    elif status == "resolved":
        print("  -> 已解决")

    # 显示执行路径摘要
    trace = values.get("trace_events", [])
    if trace:
        print("\n[完整路径]")
        for evt in trace:
            node = evt.get("node", "?")
            ms = evt.get("elapsed_ms", 0)
            detail = evt.get("detail", {})
            action = detail.get("action", "")
            suffix = f" ({action})" if action else ""
            print(f"  {node} ({ms:.0f}ms){suffix}")


# ── 中断处理 ────────────────────────────────────────────

def handle_human_review(app, config, review_info: dict):
    """处理 supervisor 层 human_review 中断"""
    box("人工审核请求")
    print(f"  待审核回复: {review_info.get('draft_response', '')[:300]}")
    print(f"  风险等级:   {review_info.get('risk_level', '')}")
    print(f"  质量评分:   {review_info.get('quality_score', 0)}")
    print(f"  安全标记:   {review_info.get('safety_flags', [])}")
    print(f"  审核原因:   {review_info.get('human_review_reason', '')}")
    print(f"  审核轮次:   {review_info.get('review_round', 0)} / 2")
    box()

    print("\n  1. approve            批准发送")
    print("  2. edit               编辑后发送")
    print("  3. reject_regenerate  拒绝，重新生成")
    print("  4. reject_reclassify  拒绝，重新分诊")
    print("  5. takeover           人工接管")

    mapping = {"1": "approve", "2": "edit", "3": "reject_regenerate",
               "4": "reject_reclassify", "5": "takeover"}
    choice = input("\n  选择 (1-5): ").strip()
    decision = mapping.get(choice, "approve")

    edited_response = ""
    feedback = ""
    if decision == "edit":
        print("  输入修改后的回复:")
        edited_response = input("  > ").strip()
    if decision in ("edit", "reject_regenerate"):
        feedback = input("  反馈意见 (可选): ").strip()

    resume_value = {
        "decision": decision,
        "feedback": feedback,
        "edited_response": edited_response,
    }

    print(f"\n  [决策: {decision}] 恢复执行...")
    stream_execution(app, Command(resume=resume_value), config)
    show_result(app, config)


def handle_approval_gate(app, config, approval_info: dict):
    """处理 complaint 子图 approval_gate 中断"""
    box("投诉审批请求")
    print(f"  投诉类型:  {approval_info.get('complaint_type', '')}")
    print(f"  严重程度:  {approval_info.get('severity', '')}")
    print(f"  补偿金额:  ¥{approval_info.get('compensation_value', 0)}")
    plan = approval_info.get("plan", {})
    if plan:
        print(f"  补偿方案:  {plan.get('resolution', '')}")
        print(f"  补偿方式:  {plan.get('compensation_type', '')}")
    box()

    approve = input("  批准此方案? (y/n): ").strip().lower() in ("y", "yes")
    note = input("  审批备注 (可选): ").strip()

    resume_value = {"approved": approve, "note": note}

    print(f"\n  [决策: {'批准' if approve else '拒绝'}] 恢复执行...")
    stream_execution(app, Command(resume=resume_value), config)
    show_result(app, config)


def check_and_handle_interrupt(app, config):
    """检查图是否被中断，如果是则分派到对应处理器"""
    snapshot = app.get_state(config)

    if not snapshot.next:
        return False  # 未中断，正常完成

    # 查找 interrupt 信息
    has_interrupt = False
    interrupt_value = None

    for task in snapshot.tasks:
        if task.interrupts:
            has_interrupt = True
            interrupt_value = task.interrupts[0].value
            break

    if not has_interrupt:
        print(f"\n[系统] 图暂停于 {snapshot.next}，但未检测到 interrupt")
        return True

    # 根据中断值结构判断类型
    if isinstance(interrupt_value, dict):
        if "draft_response" in interrupt_value or "risk_level" in interrupt_value:
            handle_human_review(app, config, interrupt_value)
        elif "plan" in interrupt_value or "severity" in interrupt_value:
            handle_approval_gate(app, config, interrupt_value)
        else:
            print(f"\n[系统] 未知中断，值: {interrupt_value}")
    else:
        print(f"\n[系统] 未知中断格式: {interrupt_value}")

    return True


# ── 主循环 ──────────────────────────────────────────────

def main():
    app = get_app()

    box("人工服务模拟器", 30)
    print("  测试 interrupt 中断 -> 人工处理 -> 恢复执行")
    print("  输入 quit / exit / q 退出")
    print("  输入 /end_takeover 结束人工接管")
    print("  输入 /status 查看会话状态")
    box("测试提示", 30)
    print('  "人工客服"              -> 直接触发转人工')
    print('  "我要投诉，东西太差了"   -> 可能触发投诉审批 interrupt')
    print('  任何消息 (高风险时)     -> 触发 human_review interrupt')
    print('  human_review 中选 "5"  -> 触发接管模式')
    box()

    customer_id = input("客户ID (默认 C001): ").strip() or "C001"
    tier = input("客户等级 (standard/vip/enterprise, 默认 standard): ").strip() or "standard"
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    session_takeover = False

    print(f"\n会话ID: {thread_id}")
    print("-" * 50)

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

        # /end_takeover: 人工客服结束接管
        if message == "/end_takeover":
            if session_takeover:
                result = release_takeover(app, config)
                if result is not None:
                    session_takeover = False
                    print("\n[系统] 接管已释放，AI 将恢复自动处理。")
                else:
                    print("\n[系统] 释放接管失败，请重试。")
            else:
                print("\n[系统] 当前不在接管模式。")
            continue

        # /status: 查看会话状态
        if message == "/status":
            snapshot = app.get_state(config)
            values = snapshot.values
            takeover = values.get("session_takeover", False)
            print(f"\n[会话状态] 接管={takeover}, 待执行={snapshot.next}")
            continue

        trace_id = generate_trace_id()
        state = create_initial_state(
            session_id=thread_id,
            customer_id=customer_id,
            customer_tier=tier,
        )
        state["trace_id"] = trace_id
        state["messages"] = [HumanMessage(content=message)]

        try:
            stream_execution(app, state, config)

            if check_and_handle_interrupt(app, config):
                pass  # 已由中断处理器处理
            else:
                show_result(app, config)

            # 检测接管状态
            snapshot = app.get_state(config)
            new_takeover = snapshot.values.get("session_takeover", False)
            if new_takeover and not session_takeover:
                session_takeover = True
                print("\n[系统] 人工接管模式已激活")
                print("  输入 /end_takeover 结束接管")

        except Exception as e:
            print(f"\n[错误] {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
