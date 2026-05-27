"""
电商后端工具集 (@tool装饰函数)

低风险 (全自动):
  check_inventory(sku, region)
  get_order_details(order_id)
  track_shipment(tracking_number)
  check_payment_status(order_id)
  search_knowledge_base(query)
  check_return_eligibility(order_id, item_id)
  find_promotions(product_ids, customer_tier)
  get_customer_orders(customer_id, limit)
  check_warranty_status(product_id, purchase_date)

中风险 (条件性interrupt):
  update_shipping_address(order_id, new_address)  → >200或跨国需审批
  update_order_quantity(order_id, item_id, qty)   → >500需审批
  send_return_label(order_id, item_id)            → 全自动
  issue_store_credit(customer_id, amount, reason) → >50需审批
  retry_payment(order_id)                         → 全自动

高风险 (始终interrupt):
  issue_refund(order_id, amount, method, reason)
  cancel_order(order_id, reason)
  process_exchange(order_id, original_item, new_item)
  apply_compensation(customer_id, type, value, reason)
  override_eligibility(order_id, policy_exception_reason)
"""
