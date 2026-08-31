# -*- coding: utf-8 -*-
"""邮箱功能测试脚本。

用法:
    python -m tests.email_test                      # 默认 tempmail
    python -m tests.email_test --backend mailtm     # 指定后端
    python -m tests.email_test --backend yyds --api-key YOUR_KEY

日志会自动携带 task_id，一次请求的全部关键信息
（邮箱地址、密码、收件 subject/code）可通过 task_id grep 追踪。
"""
from __future__ import annotations

import argparse

from email_tools.email import create_email_backend, Backend


def email_test(
    name: str | Backend | None = None,
    api_key: str | None = None,
    timeout: float = 360.0,
) -> None:
    """创建邮箱、等待验证码的完整流程测试。

    Args:
        name:    后端名称（yyds / tempmail / mailtm）
        api_key: YYDS 后端需要的 API Key
        timeout: 等待验证码的超时秒数
    """
    kwargs = {}
    if api_key is not None:
        kwargs["api_key"] = api_key

    backend = create_email_backend(name, **kwargs)

    # 打印 task_id，方便 grep
    print(f"=== task_id: {backend.task_id} ===")

    address = backend.create()
    print(f"邮箱地址: {address}")

    code = backend.wait_for_code(timeout=timeout)
    if code:
        print(f"验证码: {code}")
    else:
        print(f"收到邮件但未提取到验证码，请从日志中查找 | task_id={backend.task_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="邮箱后端测试")
    parser.add_argument(
        "--backend",
        choices=["yyds", "tempmail", "mailtm"],
        default="tempmail",
        help="邮箱后端（默认 yyds）",
    )
    parser.add_argument("--api-key", default=None, help="YYDS API Key")
    parser.add_argument("--timeout", type=float, default=360.0, help="等待验证码超时秒数")

    args = parser.parse_args()
    email_test(name=args.backend, api_key=args.api_key, timeout=args.timeout)


if __name__ == "__main__":
    main()
