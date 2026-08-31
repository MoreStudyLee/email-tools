# -*- coding: utf-8 -*-
"""mail.tm 邮箱后端 — 完全免费，无需认证。

环境变量兜底：
  EMAIL_TIMEOUT  — 超时秒数
  EMAIL_INTERVAL — 轮询间隔
  EMAIL_DEBUG    — 调试开关
"""
from __future__ import annotations

import secrets
import string

import httpx

from .backend import EmailBackend, env_float, env_bool
from .extractor import extract_verification_code

DEFAULT_BASE_URL = "https://api.mail.tm"


class MailtmBackend(EmailBackend):
    """mail.tm 适配器，免费临时邮箱，无需认证。"""

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
        self.default_timeout = env_float(timeout, "EMAIL_TIMEOUT", 120.0)
        self.default_interval = env_float(interval, "EMAIL_INTERVAL", 3.0)
        self.debug = env_bool(debug, "EMAIL_DEBUG", False)

        self._addr: str = ""
        self._password: str = ""
        self._token: str = ""
        self._created: bool = False

        self._logger.info("Mailtm init | timeout=%.0fs | interval=%.1fs",
                          self.default_timeout, self.default_interval)

    @property
    def _address(self) -> str:
        return self._addr

    def _get_domains(self) -> list[str]:
        url = f"{self.base_url}/domains"
        resp = httpx.get(url, timeout=15)
        self._logger.info("API GET %s | status=%d | resp=%s", url, resp.status_code, resp.text[:80])
        resp.raise_for_status()
        domains = [d["domain"] for d in resp.json().get("hydra:member", []) if d.get("domain")]
        self._logger.info("domains | count=%d | domains=%s", len(domains), domains[:5])
        return domains

    def create(self) -> str:
        if self._created:
            raise RuntimeError("Inbox already created")

        domains = self._get_domains()
        if not domains:
            raise RuntimeError("mail.tm 没有可用域名")

        domain = domains[0]
        username = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))
        self._addr = f"{username}@{domain}"
        self._password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

        # 创建账户
        url1 = f"{self.base_url}/accounts"
        resp = httpx.post(url1, json={"address": self._addr, "password": self._password}, timeout=15)
        self._logger.info("API POST %s | status=%d | resp=%s", url1, resp.status_code, resp.text[:80])
        resp.raise_for_status()

        # 获取 token
        url2 = f"{self.base_url}/token"
        token_resp = httpx.post(url2, json={"address": self._addr, "password": self._password}, timeout=15)
        self._logger.info("API POST %s | status=%d | resp=%s", url2, token_resp.status_code, token_resp.text[:80])
        token_resp.raise_for_status()
        self._token = token_resp.json().get("token", "")

        if not self._token:
            self._logger.error("token failed | address=%s | password=%s", self._addr, self._password)
            raise RuntimeError("mail.tm token 为空")

        self._created = True

        self._logger.info("inbox created | address=%s | password=%s | token=%s",
                          self._addr, self._password, self._token)
        return self._addr

    def get_emails(self) -> list[dict]:
        if not self._created:
            raise RuntimeError("Call create() first")

        url = f"{self.base_url}/messages"
        resp = httpx.get(url, headers={"Authorization": f"Bearer {self._token}"}, timeout=15)
        self._logger.info("API GET %s | status=%d | resp=%s", url, resp.status_code, resp.text[:80])

        if resp.status_code != 200:
            self._logger.warning("get_emails failed | status=%d | address=%s", resp.status_code, self._addr)
            return []

        emails = resp.json().get("hydra:member", [])
        self._logger.info("get_emails | count=%d | address=%s", len(emails), self._addr)
        return emails

    def _email_id(self, email: dict) -> str:
        return f"{email.get('from', '')}:{email.get('subject', '')}:{email.get('createdAt', '')}"

    def _extract_from_email(self, email: dict) -> str | None:
        subject = email.get("subject", "") or ""
        intro = email.get("intro", "") or ""

        self._logger.info("extract | subject=%s | intro=%s", subject, intro)

        text = f"{subject} {intro}"
        code = extract_verification_code(text, subject)

        if code:
            self._logger.info("code=%s | subject=%s", code, subject)
            return code

        self._logger.warning("code=NOT_FOUND | subject=%s | intro=%s", subject, intro)
        return None
