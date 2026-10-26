#!/usr/bin/env python3
"""WPS 脚本日志辅助工具。

logger 的创建统一使用 _shared.setup_logger,
本模块仅保留 WPS 页面脚本特有的上下文绑定与阶段化输出辅助函数。
"""

import logging
from collections.abc import Mapping, MutableMapping
from typing import Any, Optional


class ContextAdapter(logging.LoggerAdapter):
    """支持层层叠加上下文的日志适配器。

    绑定的上下文会以 `[值]` 前缀形式拼入消息文本，
    保证在未渲染 extra 字段的默认日志格式下同样可见。
    """

    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple[str, MutableMapping[str, Any]]:
        extra: Mapping[str, Any] = kwargs.get("extra", {})
        merged_extra = dict(self.extra)
        merged_extra.update(extra)
        kwargs["extra"] = merged_extra

        if merged_extra:
            prefix = "".join(f"[{value}]" for value in merged_extra.values() if value)
            if prefix:
                msg = f"{prefix} {msg}"
        return msg, kwargs


def bind_logger(logger: logging.Logger | ContextAdapter, **context: Any) -> ContextAdapter:
    """为日志器绑定上下文。"""
    if isinstance(logger, ContextAdapter):
        merged_context = dict(logger.extra)
        merged_context.update(context)
        return ContextAdapter(logger.logger, merged_context)
    return ContextAdapter(logger, context)


def log_banner(logger: logging.Logger | ContextAdapter, title: str) -> None:
    """输出较明显的标题分隔。"""
    line = "═" * 38
    logger.info(line)
    logger.info(title)
    logger.info(line)


def log_account_start(logger: logging.Logger | ContextAdapter, account_name: str) -> None:
    """输出账号开始日志。"""
    line = "━" * 32
    logger.info(line)
    logger.info("👤 账号：%s", account_name)
    logger.info(line)


def log_account_end(
    logger: logging.Logger | ContextAdapter,
    account_name: str,
    success: bool = True,
    wait_seconds: Optional[float] = None
) -> None:
    """输出账号结束日志。"""
    icon = "✅" if success else "❌"
    if wait_seconds is not None:
        logger.info("%s %s 完成，等待 %.1fs", icon, account_name, wait_seconds)
        return
    logger.info("%s %s 完成", icon, account_name)


def log_page_switch(logger: logging.Logger | ContextAdapter, page_name: str) -> None:
    """输出页面切换日志。"""
    logger.info("📄 页面：%s", page_name)


def log_startup(logger: logging.Logger | ContextAdapter, total_accounts: int) -> None:
    """输出启动摘要。"""
    logger.info("📦 WPS 任务启动，共 %s 个账号", total_accounts)


def log_task_result(logger: logging.Logger | ContextAdapter, label: str, result: str) -> None:
    """输出简洁任务结果行。"""
    logger.info("  %-10s → %s", label, result)
