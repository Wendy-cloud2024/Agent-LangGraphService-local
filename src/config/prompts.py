"""
Prompt模板库

按策略版本管理所有prompt模板:
- 意图分类prompt (orchestrator_gate)
- 情感检测prompt (orchestrator_gate)
- 语气适配prompt (tone_adapter, 按emotion/tier变体)
- 响应模板 (content_merger, 按优先级模板)
- 澄清追问模板 (clarify_to_customer)
- 降级话术 (fallback预置话术)
- 交接摘要模板 (escalate_to_human)

支持 strategy_version 切换不同prompt变体。
"""

from src.config.settings import INTENT_CATEGORIES, STRATEGY_VERSION


# ==================== 意图分类 Prompt ====================
INTENT_CLASSIFICATION_PROMPT = """你是一个电商客服意图分类器。
根据客户的消息和对话历史，判断客户的意图。

可选的意图类别:
{intent_categories}

请以JSON格式返回结果:
```json
{{
    "intent_labels": [
        {{"intent": "意图类别", "confidence": 0.95, "primary": true}},
        {{"intent": "次要意图", "confidence": 0.3, "primary": false}}
    ]
}}
```

注意:
- 必须返回至少一个primary=true的意图
- confidence范围0-1
- 可以返回多个意图（多标签分类）
- 优先选择最匹配的意图
"""

# ==================== 情感检测 Prompt ====================
EMOTION_DETECTION_PROMPT = """分析客户消息中的情感状态。

请以JSON格式返回:
```json
{{
    "emotion": "情感类别(neutral/happy/angry/sad/anxious/frustrated/confused)",
    "emotion_intensity": 0.5,
    "urgency": "紧急程度(low/medium/high/critical)"
}}
```

emotion_intensity范围0-1:
- 0-0.3: 平静
- 0.3-0.6: 轻微波动
- 0.6-0.9: 明显情绪
- 0.9-1.0: 极端情绪

考虑因素:
- 客户用词的情感倾向
- 标点符号的使用(!, !!, ???)
- 是否使用大写强调
- 重复表达
- 是否有威胁或最后通牒
"""

# ==================== 合并分类 Prompt (意图+情感, 单次LLM调用) ====================
COMBINED_CLASSIFICATION_PROMPT = """你是一个电商客服多维度分析器。
同时完成意图分类和情感检测。

可选的意图类别:
{intent_categories}

请以JSON格式返回:
```json
{{
    "intent_labels": [
        {{"intent": "意图类别", "confidence": 0.95, "primary": true}},
        {{"intent": "次要意图", "confidence": 0.3, "primary": false}}
    ],
    "emotion": "情感类别(neutral/happy/angry/sad/anxious/frustrated/confused)",
    "emotion_intensity": 0.5,
    "urgency": "紧急程度(low/medium/high/critical)"
}}
```

要求:
- 必须返回至少一个primary=true的意图
- confidence/emotion_intensity范围0-1
- emotion_intensity: 0-0.3平静, 0.3-0.6轻微波动, 0.6-0.9明显情绪, 0.9-1.0极端情绪
- 考虑用词情感倾向、标点符号、大写强调、重复表达等因素
"""

# ==================== 语气适配 Prompt ====================
TONE_ADAPTER_PROMPT = """你是一个电商客服语气适配器。
根据以下信息调整回复的语气:

- 客户情感: {emotion}
- 情感强度: {emotion_intensity}
- 客户等级: {customer_tier}
- 紧急程度: {urgency}

语气规则:
1. 愤怒/沮丧客户: 更有同理心，先道歉再解决问题，使用更温和的措辞
2. VIP客户: 更专业、尊重，使用敬语，提供优先处理信息
3. 企业客户: 更正式、简洁，侧重数据和结果
4. 焦虑客户: 更安抚性，提供明确的时间线和保证
5. 普通客户: 友好、专业、简洁

请调整以下回复的语气，保持核心信息不变:
{draft_response}

返回调整后的回复内容。"""

# ==================== 内容融合模板 ====================
CONTENT_MERGER_PROMPT = """你是一个电商客服内容融合器。
将多个子图的结果融合为一条统一的客户回复。

子图结果（按优先级排序）:
{agent_findings}

客户信息:
- 意图: {intent_labels}
- 情感: {emotion}
- 等级: {customer_tier}

要求:
1. 按优先级排序: 投诉 > 售后 > 售中 > 售前 > 通用
2. 合并相关信息，避免重复
3. 保持逻辑清晰，分点回复
4. 使用简洁专业的语言
5. 如有操作结果，明确告知客户

返回融合后的回复内容。"""

# ==================== 澄清追问模板 ====================
CLARIFICATION_PROMPT = """根据以下澄清请求，生成一条友好的追问消息:

澄清问题: {question}
需要的信息: {required_info}

要求:
1. 语气友好，让客户感到被关注
2. 清楚说明需要客户提供什么信息
3. 如果可以，给出示例或提示
4. 不要过于正式

返回追问消息。"""

# ==================== 降级话术 ====================
FALLBACK_MESSAGES = {
    "timeout": "抱歉，系统正在处理中，请稍后再试。如果问题持续，可以回复'人工客服'转接人工服务。",
    "tool_error": "抱歉，暂时无法查询相关信息，请稍后再试或联系人工客服。",
    "unexpected": "抱歉，系统遇到了一些问题。您可以回复'人工客服'转接人工服务，我们会尽快为您解决。",
    "general": "抱歉，我暂时无法处理您的请求。请稍后再试或回复'人工客服'转接人工服务。",
}

# ==================== 交接摘要模板 ====================
ESCALATION_SUMMARY_PROMPT = """生成一份人工客服交接摘要:

对话上下文:
{conversation_summary}

客户信息:
- ID: {customer_id}
- 等级: {customer_tier}
- 情感: {emotion}

已处理的步骤:
{trace_summary}

AI已尝试的方案:
{attempted_solutions}

请生成一份简洁的交接摘要，包含:
1. 客户问题概述
2. 已尝试的解决方案
3. 需要人工处理的原因
4. 建议的处理方向
"""

# ==================== 路由决策 Prompt ====================
ROUTING_DECISION_PROMPT = """根据以下分析结果，决定需要路由到哪些子图:

意图标签: {intent_labels}
情感: {emotion} (强度: {emotion_intensity})
紧急度: {urgency}
敏感词命中: {sensitive_word_hit}
安全审核: {safety_screen_passed}

子图列表:
- presales_agent: 售前咨询（商品/推荐/库存）
- insales_agent: 售中服务（订单/物流/支付）
- aftersales_agent: 售后服务（退货/换货/退款/保修）
- complaint_agent: 投诉处理（最高优先级）
- general_agent: 通用服务（FAQ/政策/问候）

特殊规则:
- 敏感词命中 → complaint_agent
- 情感强度>0.9且负面 → complaint_agent
- 投诉相关意图 → complaint_agent
- 多个意图 → 可并行路由到多个子图

请以JSON格式返回:
```json
{{
    "active_agents": ["子图名称列表"],
    "routing_reason": "路由原因说明"
}}
```
"""

# ==================== 输出关卡评估 Prompt ====================
OUTPUT_GATE_PROMPT = """评估以下客服回复的质量和安全性:

回复内容:
{draft_response}

客户信息:
- 意图: {intent_labels}
- 情感: {emotion}

请评估:
1. 安全性: 是否包含PII泄露、内部信息、有害内容
2. 准确性: 信息是否准确、完整
3. 语气: 是否得体、专业
4. 策略合规: 是否符合客服策略

以JSON格式返回:
```json
{{
    "risk_level": "low/medium/high/critical",
    "quality_score": 0.85,
    "safety_flags": ["标记列表"],
    "issues": ["问题描述列表"]
}}
```
"""

# ==================== 多模态预处理 Prompt ====================
MULTIMODAL_DESCRIPTION_PROMPT = """描述这张图片的通用内容。
仅提供简洁的中文描述，例如"一张物流面单的照片"、"一件破损商品的照片"等。
不要进行详细的OCR或专项分析，仅做通用描述。

图片描述:"""
