"""
专项视觉工具集 (@tool装饰函数)

各子图内部调用的专项图像分析工具:

售前: visual_product_match(image)     → 客户拍照匹配SKU
售中: ocr_shipping_label(image)       → 解析物流面单运单号/条码
售后: detect_product_damage(image)    → 判断破损程度/保修范围
售后: ocr_product_label(image)        → 读取商品标签/成分表/批号
投诉: detect_quality_issue(image)     → 识别质量问题(色差/做工缺陷)

注意: orchestrator_gate仅做通用图片描述和安全检查,
      专项识别下沉到各子图内部通过这些工具完成。
"""
