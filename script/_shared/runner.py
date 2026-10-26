#!/usr/bin/env python3
"""
多账号任务调度

统一实现: 启动随机抖动、账号间随机延迟、单账号异常隔离。
"""

import logging
import os
import random
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


def apply_startup_jitter(env_var: str, default_max: int = 600) -> float:
    """
    启动随机抖动,错开请求高峰

    Args:
        env_var: 控制最大抖动秒数的环境变量名(如 'WORKBUDDY_JITTER_MAX'),
                 设为 '0' 时关闭
        default_max: 未设置环境变量时的默认上限

    Returns:
        实际休眠的秒数
    """
    max_seconds = int(os.environ.get(env_var, str(default_max)))
    if max_seconds <= 0:
        return 0.0

    delay = random.uniform(0, max_seconds)
    logger.info('随机延迟 %.0f 秒后开始(可通过环境变量 %s 调整)', delay, env_var)
    time.sleep(delay)
    return delay


def run_accounts(
    accounts: list[dict[str, Any]],
    handler: Callable[[int, dict[str, Any]], dict[str, Any]],
    *,
    interval_range: tuple = (5, 10),
) -> list[dict[str, Any]]:
    """
    顺序执行多账号任务,自动添加账号间随机延迟并隔离异常

    Args:
        accounts: 账号配置列表
        handler: 单账号处理函数,签名为 (index, account_info) -> result dict,
                 result 至少包含 'account_name', 'success', 'message' 字段
        interval_range: 账号间随机延迟秒数区间

    Returns:
        所有账号的处理结果列表
    """
    results: list[dict[str, Any]] = []
    total = len(accounts)

    for idx, account in enumerate(accounts):
        try:
            result = handler(idx, account)
        except Exception as e:
            logger.exception('账号 #%d 处理发生未捕获异常', idx)
            name = account.get('account_name') or account.get('email') or f'账号#{idx}'
            result = {
                'account_name': name,
                'success': False,
                'message': f'未捕获异常: {e}',
            }
        results.append(result)

        if idx < total - 1:
            delay = random.uniform(*interval_range)
            logger.info('等待 %.1f 秒后处理下一个账号...', delay)
            time.sleep(delay)

    return results
