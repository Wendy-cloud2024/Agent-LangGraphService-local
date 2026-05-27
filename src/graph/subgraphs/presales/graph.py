"""
售前Agent子图

节点:
  1. product_lookup       → 识别商品 (支持图片匹配SKU)
  2. knowledge_search     → RAG检索商品信息/尺码指南
  3. inventory_check      → 实时库存查询 (@tool)
  4. recommendation_engine→ 尺码/颜色/搭配推荐
  5. promotion_matcher    → 匹配优惠活动 (@tool)
  6. presales_respond     → 编译售前回复

并行执行: knowledge_search + inventory_check + promotion_matcher (Send API fan-out)
专项视觉工具: visual_product_match(image)

输出类型: normal | clarification (商品不明确时)
"""
