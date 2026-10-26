#!/usr/bin/env python3
"""
共享基础设施包

提供多平台签到脚本的通用能力:
- logging: 统一日志格式 + 敏感字段脱敏
- http_client: 带超时/重试的 requests Session 工厂
- config: 配置文件加载与原子写回
- runner: 多账号调度(启动抖动 + 账号间隔)
- report: 结果汇总与推送
"""

from .config import load_json_config, load_platform_accounts, save_account_fields
from .http_client import create_session, post_and_parse, request_with_retry
from .logging import SensitiveDataFilter, setup_logger
from .report import build_summary, send_summary_notification
from .runner import apply_startup_jitter, run_accounts

__all__ = [
    'setup_logger',
    'SensitiveDataFilter',
    'create_session',
    'request_with_retry',
    'post_and_parse',
    'load_platform_accounts',
    'save_account_fields',
    'load_json_config',
    'run_accounts',
    'apply_startup_jitter',
    'build_summary',
    'send_summary_notification',
]
