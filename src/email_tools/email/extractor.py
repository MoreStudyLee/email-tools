# -*- coding: utf-8 -*-
"""统一验证码提取器。

支持常见验证码格式：
  - ABC-DEF（3+3 带横杠）
  - 6 位字母数字（如 XAI0X1）
  - 关键词引导的 4-8 位字母数字

明确拒绝纯数字（如 333333），避免从 HTML/CSS 误抓。
"""
from __future__ import annotations

import re
from typing import Optional


# 常见英文词黑名单，避免误匹配
_DENY_WORDS = {
    "CODE", "CODES", "VERIFY", "VERIF", "OTP",
    "XAI", "EMAIL", "LOGIN", "TOKEN",
    "HTTPS", "HTTP", "WWW",
}


def extract_verification_code(text: str, subject: str = "") -> Optional[str]:
    """从邮件正文 + 标题中提取验证码。

    匹配优先级（从高到低）：
      1. 标题前缀: "LSQ-OPU xAI"
      2. ABC-DEF 格式（3+3 带横杠）
      3. 关键词引导的 4-8 位字母数字
      4. "XXXXXX is your code" 句式
      5. 独立的 6 位字母数字（含字母）

    Args:
        text:    邮件正文。
        subject: 邮件标题。

    Returns:
        提取到的验证码字符串，未找到则返回 None。
    """
    subject = subject or ""
    text = text or ""
    blob = subject + "\n" + text
    if not blob.strip():
        return None

    # 1) 标题前缀匹配: "LSQ-OPU xAI"
    m = re.search(r"(?i)^\s*([A-Z0-9]{3}-[A-Z0-9]{3})\s+xAI", subject)
    if m:
        return m.group(1).upper()

    # 2) ABC-DEF 格式（非纯数字）
    m = re.search(r"(?<![A-Z0-9])([A-Z0-9]{3}-[A-Z0-9]{3})(?![A-Z0-9])", blob, flags=re.I)
    if m:
        code = m.group(1).upper()
        if not code.replace("-", "").isdigit():
            return code

    # 3) 关键词引导的 4-8 位字母数字
    m = re.search(
        r"(?i)(?:your\s+code\s+is|code\s+is|verification\s+code|verify\s+code|otp|验证码|code)"
        r"\s*[:=\-]?\s*([A-Z0-9]{3}-[A-Z0-9]{3}|[A-Z0-9]{4,8})",
        blob,
    )
    if m:
        code = m.group(1).upper()
        if not code.isdigit() and code not in _DENY_WORDS and not code.startswith("HTTP"):
            return code

    # 4) "XXXXXX is your code" 句式
    m = re.search(
        r"(?i)\b([A-Z0-9]{3}-[A-Z0-9]{3}|[A-Z0-9]{6})\b\s+is\s+your\s+code",
        blob,
    )
    if m:
        code = m.group(1).upper()
        if not code.isdigit() and code not in _DENY_WORDS:
            return code

    # 5) 独立的 6 位字母数字（必须含字母）
    for m in re.finditer(r"(?i)\b([A-Z0-9]{6})\b", blob):
        code = m.group(1).upper()
        if code.isdigit() or code in _DENY_WORDS:
            continue
        if code.lower() in {"ffffff", "000000", "abcdef"}:
            continue
        if any(ch.isalpha() for ch in code):
            return code

    return None
