"""
售后Agent子图 (最复杂)

节点:
  1. issue_identify       → 分类问题类型 (破损/错发/质量/不满意)
  2. order_fetch          → 并行获取订单+购买历史
  3. eligibility_checker  → 资格校验 (退货窗口/物品状态/保修/客户历史)
  4. evidence_collector   → 证据收集 (照片/描述)
  5. resolution_planner   → 确定方案 (退款/换货/维修/店铺积分)
  6. tool_executor        → 执行操作 (退款/换货=interrupt, 标签/积分=条件性)
  7. aftersales_respond   → 编译回复

专项视觉工具: detect_product_damage(image), ocr_product_label(image)

输出类型: normal | clarification (证据不足时)
工具审批: issue_refund/process_exchange → 始终interrupt
         issue_store_credit → 金额>50需interrupt
         send_return_label → 全自动
"""
