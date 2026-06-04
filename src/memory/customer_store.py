"""
客户画像存储 (Layer 4: 跨会话长期记忆)

使用 JSON 文件持久化客户画像，支持:
- load: 加载客户画像
- save: 保存客户画像
- update_from_interaction: 从对话状态自动提取并更新画像

后续可替换为数据库实现，接口不变。
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "customers"


class CustomerStore:
    """客户画像 JSON 文件存储"""

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load(self, customer_id: str) -> dict:
        """加载客户画像，优先从 SQLite，降级到 JSON 文件"""
        # 优先从 SQLite 数据库加载
        try:
            from src.db.queries import get_customer
            db_customer = get_customer(customer_id)
            if db_customer:
                profile = self._default_profile(customer_id)
                profile["name"] = db_customer.get("name", "")
                profile["height"] = db_customer.get("height")
                profile["weight"] = db_customer.get("weight")
                profile["gender"] = db_customer.get("gender", "")
                profile["phone"] = db_customer.get("phone", "")
                profile["address"] = db_customer.get("address", "")
                return profile
        except Exception as e:
            logger.debug("SQLite 客户查询降级到 JSON: %s", e)

        # 降级: 从 JSON 文件加载
        path = self.data_dir / f"{customer_id}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.error("加载客户画像失败 %s: %s", customer_id, e)
        return self._default_profile(customer_id)

    def save(self, customer_id: str, profile: dict):
        """保存客户画像"""
        path = self.data_dir / f"{customer_id}.json"
        profile["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            path.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError as e:
            logger.error("保存客户画像失败 %s: %s", customer_id, e)

    def update_from_interaction(self, customer_id: str, state: dict):
        """从一次对话的状态中提取信息，更新客户画像"""
        profile = self.load(customer_id)

        # 更新交互次数和最后交互时间
        profile["interaction_count"] = profile.get("interaction_count", 0) + 1
        profile["last_interaction"] = datetime.now(timezone.utc).isoformat()[:10]

        # 更新客户等级
        tier = state.get("customer_tier", "")
        if tier:
            profile["tier"] = tier

        # 提取本次对话的话题
        intent_labels = state.get("intent_labels", [])
        topics = [label.get("intent", "") for label in intent_labels if label.get("primary")]
        if topics:
            # 追加到频繁话题列表（去重，保留最近10个）
            frequent = profile.get("frequent_topics", [])
            for t in topics:
                if t in frequent:
                    frequent.remove(t)
                frequent.insert(0, t)
            profile["frequent_topics"] = frequent[:10]

        # 记录情感趋势
        emotion = state.get("emotion", "")
        if emotion and emotion != "neutral":
            profile["last_emotion"] = emotion

        # 记录售后/投诉历史
        findings = state.get("agent_findings", [])
        for f in findings:
            source = f.get("source_agent", "")
            if source == "complaint_agent":
                history = profile.get("issue_history", [])
                history.append({
                    "type": "complaint",
                    "severity": "high",
                    "date": profile["last_interaction"],
                    "resolved": state.get("resolution_status") == "resolved",
                })
                profile["issue_history"] = history[-5:]  # 保留最近5条
            elif source == "aftersales_agent":
                history = profile.get("issue_history", [])
                findings_data = f.get("findings", {})
                history.append({
                    "type": findings_data.get("issue_type", "aftersales"),
                    "date": profile["last_interaction"],
                    "resolved": state.get("resolution_status") == "resolved",
                })
                profile["issue_history"] = history[-5:]

        # 保存更新后的画像
        self.save(customer_id, profile)
        logger.info("客户画像已更新: %s (交互%d次)", customer_id, profile["interaction_count"])
        return profile

    def _default_profile(self, customer_id: str) -> dict:
        """返回默认客户画像"""
        return {
            "customer_id": customer_id,
            "tier": "standard",
            "name": "",
            "interaction_count": 0,
            "last_interaction": "",
            "frequent_topics": [],
            "recent_orders": [],
            "issue_history": [],
            "last_emotion": "neutral",
            "preferences": {
                "language": "zh",
                "contact_method": "online",
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


# 模块级单例
_store: CustomerStore | None = None


def get_customer_store() -> CustomerStore:
    """获取客户画像存储单例"""
    global _store
    if _store is None:
        _store = CustomerStore()
    return _store
