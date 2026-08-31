# -*- coding: utf-8 -*-
"""统一日志：按天轮转文件 + 控制台。"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(_BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = TimedRotatingFileHandler(
    os.path.join(LOG_DIR, "app.log"),
    when="midnight",
    backupCount=30,
    encoding="utf-8",
)
_file_handler.setFormatter(_formatter)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)

_root = logging.getLogger(__name__)
_root.setLevel(logging.DEBUG)
_root.addHandler(_file_handler)
_root.addHandler(_console_handler)


def get_logger(name: str) -> logging.Logger:
    """获取子 logger，name 会拼接在当前模块下。"""
    return _root.getChild(name)
