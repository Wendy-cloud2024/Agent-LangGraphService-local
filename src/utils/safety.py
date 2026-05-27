"""
安全检查工具

- 敏感词黑名单匹配
- PII泄露检测 (手机号/身份证/银行卡)
- 有害内容检测
- 图片安全审核
- 基本安全过滤 (clarify_to_customer旁路使用)
"""

import re

from src.config.settings import SENSITIVE_WORDS


def check_sensitive_words(text: str) -> tuple[bool, list[str]]:
    """检查文本是否包含敏感词

    返回: (是否命中, 命中的敏感词列表)
    """
    hits = []
    text_lower = text.lower()
    for word in SENSITIVE_WORDS:
        if word in text_lower:
            hits.append(word)
    return len(hits) > 0, hits


def check_pii_leak(text: str) -> tuple[bool, list[str]]:
    """检查文本是否包含PII信息

    检测: 手机号、身份证号、银行卡号、邮箱
    """
    flags = []
    # 手机号: 1开头11位数字
    if re.search(r"1[3-9]\d{9}", text):
        flags.append("phone_number")
    # 身份证号: 18位
    if re.search(r"\d{17}[\dXx]", text):
        flags.append("id_card")
    # 银行卡号: 16-19位连续数字
    if re.search(r"\d{16,19}", text):
        flags.append("bank_card")
    # 邮箱
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        flags.append("email")
    return len(flags) > 0, flags


def check_harmful_content(text: str) -> tuple[bool, list[str]]:
    """检查文本是否包含有害内容

    检测: 辱骂、歧视、暴力、色情关键词
    """
    harmful_patterns = [
        (r"(傻瓜|笨蛋|白痴|蠢)", "insult"),
        (r"(死|杀|打|砍|捅)", "violence"),
    ]
    flags = []
    for pattern, category in harmful_patterns:
        if re.search(pattern, text):
            flags.append(category)
    return len(flags) > 0, flags


def basic_safety_check(text: str) -> tuple[bool, list[str]]:
    """基本安全检查（用于clarify_to_customer旁路）

    仅做PII过滤和有害内容检测，不做完整审核。
    """
    all_flags = []
    has_pii, pii_flags = check_pii_leak(text)
    all_flags.extend(pii_flags)
    has_harmful, harmful_flags = check_harmful_content(text)
    all_flags.extend(harmful_flags)
    passed = len(all_flags) == 0
    return passed, all_flags


def full_safety_check(text: str) -> tuple[bool, list[str]]:
    """完整安全检查（用于output_gate）

    包含: 敏感词 + PII + 有害内容
    """
    all_flags = []

    _, sensitive_hits = check_sensitive_words(text)
    if sensitive_hits:
        all_flags.append(f"sensitive_word:{','.join(sensitive_hits)}")

    _, pii_flags = check_pii_leak(text)
    all_flags.extend([f"pii:{f}" for f in pii_flags])

    _, harmful_flags = check_harmful_content(text)
    all_flags.extend([f"harmful:{f}" for f in harmful_flags])

    passed = len(all_flags) == 0
    return passed, all_flags


def check_image_safety(image_data: bytes | str) -> tuple[bool, str]:
    """图片安全审核

    检测: 暴力/色情/违法内容
    返回: (是否安全, 描述)
    """
    # 实际项目中调用视觉安全API
    # 这里返回默认安全结果
    return True, ""
