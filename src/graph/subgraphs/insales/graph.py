"""
售中Agent子图

节点:
  1. order_identify       → 提取订单号 (支持从图片OCR提取)
  2. order_fetch          → 并行查询订单+支付+物流 (@tool)
  3. order_analyze        → 分析状态/修改资格
  4. action_planner       → 规划操作 (追踪/修改/支付)
  5. tool_executor        → 执行工具 (带审批门控, 高风险interrupt)
  6. insales_respond      → 编译回复

并行执行: 订单详情+支付状态+物流信息 (Send API)
专项视觉工具: ocr_shipping_label(image)

输出类型: normal | clarification (无订单号时)
"""
