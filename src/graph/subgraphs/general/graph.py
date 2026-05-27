"""
通用Agent子图 (最简单 + 降级fallback目标)

节点:
  1. faq_matcher     → FAQ匹配
  2. policy_search   → RAG搜索店铺政策
  3. general_respond → 编译通用回复
  4. emotion_monitor → 情绪监控 (检测升级信号)

特殊职责:
- 当其他子图超时/异常时, supervisor降级到此子图使用预置话术
- emotion_monitor检测到情绪恶化 → 发出escalate_to_complaint信号

输出类型: normal | escalate
"""
