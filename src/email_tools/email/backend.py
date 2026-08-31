# -*- coding: utf-8 -*-
"""邮箱后端基类、枚举与环境变量辅助。

模块职责：
  - Backend 枚举：后端选择，无别名兼容
  - EmailBackend 抽象基类 + 公共轮询逻辑
  - 环境变量回退辅助（入参 > 环境变量 > 默认值）
"""
from __future__ import annotations

import os
import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum

from .extractor import extract_verification_code
from ..common.logger import get_logger


# ── 环境变量回退辅助 ──────────────────────────────────


def env_str(value: str | None, env_key: str, default: str = "") -> str:
    """字符串：入参 > 环境变量 > 默认值。"""
    if value is not None:
        return str(value).strip()
    v = os.environ.get(env_key, "").strip()
    return v if v else default


def env_float(value: float | None, env_key: str, default: float) -> float:
    """浮点：入参 > 环境变量 > 默认值。"""
    if value is not None:
        return float(value)
    v = os.environ.get(env_key, "").strip()
    if v:
        try:
            return float(v)
        except ValueError:
            raise RuntimeError(f"环境变量 {env_key}='{v}' 不是有效浮点数")
    return default


def env_bool(value: bool | None, env_key: str, default: bool = False) -> bool:
    """布尔：入参 > 环境变量 > 默认值。"""
    if value is not None:
        return bool(value)
    v = os.environ.get(env_key, "").strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    return default


# ── 后端枚举 ──────────────────────────────────────────


class Backend(str, Enum):
    """邮箱后端选择。每个值即后端名称，无别名兼容。"""

    YYDS = "yyds"
    TEMPMAIL = "tempmail"
    MAILTM = "mailtm"


# ── 抽象基类 + 公共轮询 ──────────────────────────────


class EmailBackend(ABC):
    """一次性临时邮箱后端抽象接口。

    task_id 嵌入 logger name，日志中 grep task_id 即可追踪全链路。
    收到邮件即停止：有验证码返回 str，无验证码返回 None，超时无邮件抛 TimeoutError。
    """

    default_timeout: float = 120.0
    default_interval: float = 3.0
    debug: bool = False

    def __init__(self, *, task_id: str | None = None):
        self._task_id = task_id or uuid.uuid4().hex[:8]
        # task_id 嵌入 logger name → grep task_id 即追踪全链路
        self._logger = get_logger(f"{type(self).__name__}.{self._task_id}")
        self._logger.info("backend init | task_id=%s", self._task_id)

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def address(self) -> str:
        """当前邮箱地址。create() 前为空字符串。"""
        return self._address

    @property
    @abstractmethod
    def _address(self) -> str:
        ...

    @abstractmethod
    def create(self) -> str:
        """创建邮箱并返回地址。同一实例不可重复调用。"""
        ...

    @abstractmethod
    def get_emails(self) -> list[dict]:
        """拉取当前邮箱所有邮件列表。"""
        ...

    @abstractmethod
    def _email_id(self, email: dict) -> str:
        """为邮件生成唯一标识符，用于轮询去重。"""
        ...

    @abstractmethod
    def _extract_from_email(self, email: dict) -> str | None:
        """从单封邮件提取验证码，返回 None 表示未找到。"""
        ...

    def wait_for_code(self, timeout: float | None = None, interval: float | None = None) -> str | None:
        """轮询收件箱，收到邮件即停止。

        - 提取到验证码 → 返回验证码字符串
        - 收到邮件但未提取到验证码 → 返回 None（日志中已有 subject/intro/body）
        - 超时且无任何邮件 → 抛 TimeoutError
        """
        if not self.address:
            raise RuntimeError("Call create() first")

        effective_timeout = timeout or self.default_timeout
        effective_interval = interval or self.default_interval

        self._logger.info("wait_for_code start | address=%s | timeout=%.0fs | interval=%.1fs",
                          self.address, effective_timeout, effective_interval)

        deadline = time.time() + effective_timeout
        start_time = deadline - effective_timeout
        seen: set[str] = set()

        while True:
            elapsed = time.time() - start_time

            try:
                emails = self.get_emails()
            except Exception as exc:
                self._logger.warning("get_emails error | %s", exc)
                emails = []

            for email in emails:
                eid = self._email_id(email)
                if eid in seen:
                    continue
                seen.add(eid)

                subject = str(email.get("subject", ""))
                from_addr = str(email.get("from", ""))
                intro = str(email.get("intro", ""))
                body = str(email.get("body", "") or email.get("text", ""))

                code = self._extract_from_email(email)

                self._logger.info("email received | subject=%s | from=%s | intro=%s | body=%s | code=%s",
                                  subject, from_addr, intro, body, code or "NOT_FOUND")

                if code is not None:
                    self._logger.info("✓ code found | code=%s | elapsed=%.1fs | emails_seen=%d",
                                      code, elapsed, len(seen))
                    return code
                else:
                    self._logger.warning("⚠ code NOT found but email received | subject=%s | elapsed=%.1fs",
                                         subject, elapsed)
                    return None

            if time.time() >= deadline:
                self._logger.error("✗ timeout | address=%s | timeout=%.0fs | emails_seen=%d | no email",
                                   self.address, effective_timeout, len(seen))
                raise TimeoutError(
                    f"{type(self).__name__}: no email for {self.address} within "
                    f"{effective_timeout:.0f}s ({len(seen)} emails seen)")

            self._logger.debug("polling | elapsed=%.1fs | emails_seen=%d | address=%s",
                               elapsed, len(seen), self.address)
            time.sleep(effective_interval)
