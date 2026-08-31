# -*- coding: utf-8 -*-
"""邮箱助手 — 可切换的临时邮箱后端。

三个后端实现：
  - YYDSBackend      (YYDS Mail)   — 需要 API Key
  - TempmailBackend  (tempmail.lol) — 免费，无需认证
  - MailtmBackend    (mail.tm)     — 免费，无需认证

参数策略：入参 > 环境变量 > 默认值。不依赖配置文件。

用法:
    from email_tools.email import create_email_backend, Backend

    backend = create_email_backend(Backend.YYDS, api_key="xxx", task_id="my_task")
    backend = create_email_backend("mailtm")

    address = backend.create()
    code = backend.wait_for_code(timeout=90)

日志追踪：
    task_id 嵌入 logger name，grep task_id 即可追踪全链路。
"""
from __future__ import annotations

from .backend import Backend, EmailBackend, env_str, env_float, env_bool
from .extractor import extract_verification_code
from .yyds import YYDSBackend
from .tempmail import TempmailBackend
from .mailtm import MailtmBackend

# ── 后端注册表 ──────────────────────────────────────

_BACKENDS: dict[Backend, type[EmailBackend]] = {
    Backend.YYDS: YYDSBackend,
    Backend.TEMPMAIL: TempmailBackend,
    Backend.MAILTM: MailtmBackend,
}


# ── 工厂函数 ────────────────────────────────────────


def create_email_backend(
    name: str | Backend | None = None,
    **kwargs,
) -> EmailBackend:
    """创建邮箱后端实例。

    kwargs 直接透传给对应后端构造器，各后端只接受自己需要的参数：
      YYDS:      api_key, timeout, interval, debug, task_id
      TEMPMAIL:  timeout, interval, debug, task_id
      MAILTM:    timeout, interval, debug, task_id
    """
    if name is None:
        name = env_str(None, "EMAIL_BACKEND", "yyds")
    if isinstance(name, str):
        try:
            name = Backend(name)
        except ValueError:
            raise RuntimeError(
                f"不支持的邮箱后端: {name}（可选: {', '.join(b.value for b in Backend)}）"
            )
    cls = _BACKENDS.get(name)
    if cls is None:
        raise RuntimeError(f"后端 {name} 尚未注册")
    return cls(**kwargs)


__all__ = [
    "Backend",
    "EmailBackend",
    "YYDSBackend",
    "TempmailBackend",
    "MailtmBackend",
    "create_email_backend",
    "extract_verification_code",
    "env_str",
    "env_float",
    "env_bool",
]
