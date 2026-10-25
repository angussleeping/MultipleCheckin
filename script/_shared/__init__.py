#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享基础设施包

提供多平台签到脚本的通用能力:
- logging: 统一日志格式 + 敏感字段脱敏
- http_client: 带超时/重试的 requests Session 工厂
- config: 配置文件加载与原子写回
- runner: 多账号调度(启动抖动 + 账号间隔)
- report: 结果汇总与推送
"""

from .logging import setup_logger, SensitiveDataFilter
from .http_client import create_session, request_with_retry, post_and_parse
from .config import load_platform_accounts, save_account_fields, load_json_config
from .runner import run_accounts, apply_startup_jitter
from .report import build_summary, send_summary_notification

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
