# -*- coding: utf-8 -*-
"""Tempmail.lol 邮箱后端 — 免费，无需认证。

环境变量兜底：
  EMAIL_TIMEOUT  — 超时秒数
  EMAIL_INTERVAL — 轮询间隔
  EMAIL_DEBUG    — 调试开关
"""
from __future__ import annotations

import httpx

from .backend import EmailBackend, env_float, env_bool
from .extractor import extract_verification_code

DEFAULT_BASE_URL = "https://api.tempmail.lol"


class TempmailBackend(EmailBackend):
    """Tempmail.lol 适配器，免费临时邮箱。"""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        interval: float | None = None,
        debug: bool | None = None,
        task_id: str | None = None,
    ):
        super().__init__(task_id=task_id)

        self.base_url = DEFAULT_BASE_URL
        self.default_timeout = env_float(timeout, "EMAIL_TIMEOUT", 90.0)
        self.default_interval = env_float(interval, "EMAIL_INTERVAL", 3.0)
        self.debug = env_bool(debug, "EMAIL_DEBUG", False)

        self._addr: str = ""
        self._token: str = ""
        self._created: bool = False

        self._logger.info("Tempmail init | timeout=%.0fs | interval=%.1fs",
                          self.default_timeout, self.default_interval)

    @property
    def _address(self) -> str:
        return self._addr

    def create(self) -> str:
        if self._created:
            raise RuntimeError("Inbox already created")

        url = f"{self.base_url}/v2/inbox/create"
        resp = httpx.post(url, timeout=15)
        self._logger.info("API POST %s | status=%d | resp=%s", url, resp.status_code, resp.text[:80])

        if resp.status_code != 201:
            self._logger.error("create failed | status=%d | resp=%s", resp.status_code, resp.text[:200])
            raise RuntimeError(f"Tempmail create failed: {resp.status_code} {resp.text[:200]}")

        data = resp.json()
        self._addr = data["address"]
        self._token = data["token"]
        self._created = True

        self._logger.info("inbox created | address=%s | token=%s", self._addr, self._token)
        return self._addr

    def get_emails(self) -> list[dict]:
        if not self._created:
            raise RuntimeError("Call create() first")

        url = f"{self.base_url}/v2/inbox"
        resp = httpx.get(url, params={"token": self._token}, timeout=15)
        self._logger.info("API GET %s | status=%d | resp=%s", url, resp.status_code, resp.text[:80])

        if resp.status_code != 200:
            self._logger.warning("get_emails failed | status=%d | address=%s", resp.status_code, self._addr)
            return []

        emails = resp.json().get("emails", [])
        self._logger.info("get_emails | count=%d | address=%s", len(emails), self._addr)
        return emails

    def _email_id(self, email: dict) -> str:
        return f"{email.get('from', '')}:{email.get('subject', '')}:{email.get('date', '')}"

    def _extract_from_email(self, email: dict) -> str | None:
        subject = email.get("subject", "") or ""
        body = email.get("body", "") or ""

        self._logger.info("extract | subject=%s | body=%s", subject, body)

        text = f"{subject} {body}"
        code = extract_verification_code(text, subject)

        if code:
            self._logger.info("code=%s | subject=%s", code, subject)
            return code

        self._logger.warning("code=NOT_FOUND | subject=%s | body=%s", subject, body)
        return None
