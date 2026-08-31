# email-tools

可切换后端的临时邮箱工具包。支持 3 个临时邮箱服务，统一接口创建邮箱、轮询收件箱、自动提取验证码。

- **YYDSBackend** (YYDS Mail) — 需要 API Key
- **TempmailBackend** (tempmail.lol) — 免费，无需认证
- **MailtmBackend** (mail.tm) — 免费，无需认证

## 特性

- **统一接口**：三个后端实现同一套 `create()` / `wait_for_code()` 抽象，切换后端只改一个参数
- **验证码自动提取**：内置正则提取器，支持常见验证码格式（见下文）
- **参数回退策略**：入参 > 环境变量 > 默认值，不依赖配置文件
- **全链路日志追踪**：`task_id` 嵌入 logger name，`grep task_id` 即可追踪一次请求的完整链路

## 安装

```bash
pip install -e .           # 开发安装
pip install -e ".[dev]"    # 含 pytest / respx 测试依赖
```

## 快速开始

```python
from email_tools.email import create_email_backend, Backend

# 按后端枚举创建
backend = create_email_backend(Backend.YYDS, api_key="xxx", task_id="my_task")

# 或按名称创建（字符串形式）
backend = create_email_backend("mailtm")

# 创建临时邮箱
address = backend.create()
print(address)

# 轮询等待验证码（收到邮件即停止）
code = backend.wait_for_code(timeout=90)
print(code)
```

不传 `name` 时读取环境变量 `EMAIL_BACKEND`（默认 `yyds`）。

## 后端

| 后端 | 名称 | 认证 | 默认超时 | 环境变量 |
|------|------|------|----------|----------|
| YYDS | `yyds` | API Key（必填） | 120s | `YYDS_API_KEY` |
| Tempmail.lol | `tempmail` | 免费，无需 | 90s | — |
| mail.tm | `mailtm` | 免费，无需 | 120s | — |

各后端接受的构造参数：

- `YYDS`：`api_key`、`timeout`、`interval`、`debug`、`task_id`
- `TEMPMAIL`：`timeout`、`interval`、`debug`、`task_id`
- `MAILTM`：`timeout`、`interval`、`debug`、`task_id`

## 接口

`EmailBackend` 抽象基类（[backend.py](src/email-tools/email/backend.py)）：

| 方法 | 说明 |
|------|------|
| `create()` | 创建邮箱并返回地址；同一实例不可重复调用 |
| `get_emails()` | 拉取当前邮箱所有邮件列表 |
| `wait_for_code(timeout, interval)` | 轮询收件箱，收到邮件即停止 |
| `task_id` | 属性，本次请求的追踪 ID |
| `address` | 属性，当前邮箱地址（`create()` 前为空） |

`wait_for_code()` 返回语义：

- 提取到验证码 → 返回验证码字符串
- 收到邮件但未提取到验证码 → 返回 `None`（日志中已记录 subject/intro/body）
- 超时且无任何邮件 → 抛 `TimeoutError`

## 验证码提取

统一提取器 [extractor.py](src/email-tools/email/extractor.py)，从标题 + 正文匹配，优先级从高到低：

1. 标题前缀 `ABC-DEF xAI` 格式
2. `ABC-DEF` 格式（3+3 带横杠，非纯数字）
3. 关键词引导的 4-8 位字母数字（`code is` / `verification code` / `otp` / `验证码` 等）
4. `XXXXXX is your code` 句式
5. 独立的 6 位字母数字（必须含字母）

明确拒绝纯数字（如 `333333`），避免从 HTML/CSS 误抓；内置常见英文词黑名单（`CODE` / `OTP` / `XAI` 等）。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EMAIL_BACKEND` | 默认后端名称 | `yyds` |
| `YYDS_API_KEY` | YYDS API Key（必填） | — |
| `EMAIL_TIMEOUT` | 等待验证码超时秒数 | 后端各自默认 |
| `EMAIL_INTERVAL` | 轮询间隔秒数 | `3.0` |
| `EMAIL_DEBUG` | 调试开关 | `False` |

优先级始终为 **入参 > 环境变量 > 默认值**。

## 日志追踪

日志写入 `logs/app.log`（按天轮转，保留 30 天），同时输出到控制台。每个后端实例的 logger name 包含 `task_id`，一次请求的邮箱地址、密码、收件 subject/code 等全部关键信息，均可通过 `grep task_id` 一键追踪。

## 测试

```bash
python -m tests.email_test                      # 默认 tempmail
python -m tests.email_test --backend mailtm     # 指定后端
python -m tests.email_test --backend yyds --api-key YOUR_KEY
python -m tests.email_test --backend mailtm --timeout 300
```

输出示例：

```
=== task_id: a1b2c3d4 ===
邮箱地址: xxxxx@domain.com
验证码: ABC-DEF
```

## 项目结构

```
email-tools/
├── pyproject.toml                  # 打包配置（hatchling）
├── src/
│   ├── logs/                       # 日志输出目录（自动创建）
│   └── email-tools/
│       ├── common/
│       │   └── logger.py           # 统一日志：按天轮转 + 控制台
│       └── email/
│           ├── backend.py          # 后端枚举、抽象基类、轮询逻辑、环境变量辅助
│           ├── extractor.py        # 验证码提取器
│           ├── yyds.py             # YYDS Mail 后端
│           ├── tempmail.py         # Tempmail.lol 后端
│           └── mailtm.py           # mail.tm 后端
└── tests/
    └── email_test.py               # 功能测试脚本
```

## 依赖

- Python >= 3.10
- `httpx>=0.24`
- 开发依赖：`pytest>=7.0`、`respx>=0.21`
