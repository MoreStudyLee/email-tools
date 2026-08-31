# -*- coding: utf-8 -*-
"""YYDS 邮箱后端 — 需要 API Key。

环境变量兜底：
  YYDS_API_KEY   — X-API-Key 认证密钥（必填）
  EMAIL_TIMEOUT  — 超时秒数
  EMAIL_INTERVAL — 轮询间隔
  EMAIL_DEBUG    — 调试开关
"""
from __future__ import annotations

import secrets
import string
import warnings

import httpx

from .backend import EmailBackend, env_str, env_float, env_bool
from .extractor import extract_verification_code

warnings.filterwarnings("ignore", message="Using verify=False.*")

DEFAULT_API_BASE = "https://maliapi.215.im/v1"


class YYDSBackend(EmailBackend):
    """YYDS Mail 适配器，通过 X-API-Key 认证。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float | None = None,
        interval: float | None = None,
        debug: bool | None = None,
        task_id: str | None = None,
    ):
        super().__init__(task_id=task_id)

        self.api_key = env_str(api_key, "YYDS_API_KEY", "")
        self.api_base = DEFAULT_API_BASE
        self.default_timeout = env_float(timeout, "EMAIL_TIMEOUT", 120.0)
        self.default_interval = env_float(interval, "EMAIL_INTERVAL", 3.0)
        self.debug = env_bool(debug, "EMAIL_DEBUG", False)

        self._addr: str = ""
        self._token: str = ""
        self._created: bool = False

        self._logger.info("YYDS init | api_key=%s | timeout=%.0fs | interval=%.1fs",
                          self.api_key, self.default_timeout, self.default_interval)

    @property
    def _address(self) -> str:
        return self._addr

    def _headers(self, json_body: bool = False) -> dict[str, str]:
        h: dict[str, str] = {}
        if json_body:
            h["Content-Type"] = "application/json"
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        elif self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _get_domains(self) -> list[dict]:
        url = f"{self.api_base}/domains"
        resp = httpx.get(url, headers=self._headers(), timeout=20, verify=False)
        self._logger.info("API GET %s | status=%d | resp=%s", url, resp.status_code, resp.text[:80])
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", []) if data.get("success") else []

    def _pick_domain(self) -> str:
        domains = self._get_domains()
        if not domains:
            raise RuntimeError("YYDS 没有可用域名")
        pool = [d for d in domains if d.get("isVerified") and not d.get("isPublic")] \
               or [d for d in domains if d.get("isVerified")] \
               or domains
        item = pool[0]
        domain = str(item) if isinstance(item, str) else str(item.get("domain") or item.get("name") or "")
        self._logger.info("pick domain | domain=%s | pool_size=%d", domain, len(pool))
        return domain

    def create(self) -> str:
        if self._created:
            raise RuntimeError("Inbox already created")
        if not self.api_key:
            raise RuntimeError("YYDS 需要 api_key（入参或 YYDS_API_KEY 环境变量）")

        domain = self._pick_domain()
        username = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))
        address = f"{username}@{domain}"
        payload = {"address": address, "domain": domain}

        url = f"{self.api_base}/accounts"
        resp = httpx.post(url, json=payload, headers=self._headers(json_body=True), timeout=20, verify=False)
        self._logger.info("API POST %s | status=%d | resp=%s", url, resp.status_code, resp.text[:80])
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            self._logger.error("create failed | resp=%s", data)
            raise RuntimeError(f"YYDS 创建邮箱失败: {data}")

        result = data.get("data", {})
        self._addr = result.get("address") or address
        self._token = result.get("token") or ""

        # 响应不含 token 时单独获取
        if not self._token and self._addr:
            url2 = f"{self.api_base}/token"
            t = httpx.post(url2, json={"address": self._addr}, headers=self._headers(json_body=True), timeout=20, verify=False)
            self._logger.info("API POST %s | status=%d | resp=%s", url2, t.status_code, t.text[:80])
            t.raise_for_status()
            td = t.json()
            if td.get("success"):
                self._token = td.get("data", {}).get("token", "")

        if not self._token:
            self._logger.error("token failed | address=%s", self._addr)
            raise RuntimeError("YYDS 获取 token 失败")

        self._created = True
        self._logger.info("inbox created | address=%s | token=%s | api_key=%s",
                          self._addr, self._token, self.api_key)
        return self._addr

    def get_emails(self) -> list[dict]:
        if not self._created:
            raise RuntimeError("Call create() first")
        url = f"{self.api_base}/messages"
        resp = httpx.get(url, params={"address": self._addr}, headers=self._headers(), timeout=20, verify=False)
        self._logger.info("API GET %s | status=%d | resp=%s", url, resp.status_code, resp.text[:80])
        resp.raise_for_status()
        data = resp.json()
        emails = data.get("data", {}).get("messages", []) if data.get("success") else []
        self._logger.info("get_emails | count=%d | address=%s", len(emails), self._addr)
        return emails

    def _get_message_detail(self, message_id: str) -> dict:
        url = f"{self.api_base}/messages/{message_id}"
        resp = httpx.get(url, headers=self._headers(), timeout=20, verify=False)
        self._logger.info("API GET %s | status=%d | resp=%s", url, resp.status_code, resp.text[:80])
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}) if data.get("success") else {}

    def _email_id(self, email: dict) -> str:
        mid = email.get("id") or email.get("messageId", "")
        return mid or f"{email.get('from', '')}:{email.get('subject', '')}:{email.get('date', '')}"

    def _extract_from_email(self, email: dict) -> str | None:
        subject = str(email.get("subject", ""))
        body = str(email.get("text", "")) or str(email.get("body", "")) or str(email.get("intro", ""))

        # 正文过短时拉详情
        mid = email.get("id") or email.get("messageId", "")
        if mid and len(body) < 20:
            try:
                detail = self._get_message_detail(mid)
                body = " ".join(str(detail.get(k) or "") for k in ("subject", "text", "html", "body", "intro", "content"))
                subject = str(detail.get("subject", "")) or subject
            except Exception as exc:
                self._logger.warning("detail fetch error | mid=%s | %s", mid, exc)

        self._logger.info("extract | subject=%s | body=%s | mid=%s", subject, body, mid or "none")

        code = extract_verification_code(body, subject)
        if code and not str(code).isdigit():
            self._logger.info("code=%s | subject=%s", code, subject)
            return str(code)

        self._logger.warning("code=NOT_FOUND | subject=%s", subject)
        return None
