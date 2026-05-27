"""
状态Schema定义

定义LangGraph StateGraph所需的所有状态类型:
- ConversationState: 顶层监督者状态
- AgentSubgraphState: 子图共享基础状态
- 各子图扩展状态 (PreSales/InSales/AfterSales/Complaint/General)
- 子图输出类型 (normal/clarification/fallback/escalate)
"""
