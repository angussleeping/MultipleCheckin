#!/usr/bin/env python3
"""
统一日志配置 + 敏感字段脱敏

所有平台脚本应使用 setup_logger(platform_name) 获取 logger,
避免各自重复实现 console handler、formatter 等样板代码。
"""

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union

# _shared 包内模块使用 logging.getLogger(__name__),logger 名为 '_shared.xxx'
SHARED_PARENT_LOGGER = '_shared'


class SensitiveDataFilter(logging.Filter):
    """
    日志脱敏过滤器

    对 cookie/token/authorization/phone 等敏感字段值进行打码,
    保留前后各 4 位以便排查问题。
    """

    # 匹配 "key=value" / "key: value" / "key\":\"value\"" 形式
    SENSITIVE_KEYS = (
        r'cookie', r'token', r'access_token', r'refresh_token',
        r'authorization', r'set-cookie', r'phone', r'mobile',
        r'password', r'secret', r'sckey', r'sendkey', r'pushkey',
        r'access_token', r'openid', r'session',
    )

    # 形如 cookie=xxx / token: xxx / "token": "xxx"
    _PATTERN = re.compile(
        r'(?P<key>' + '|'.join(SENSITIVE_KEYS) + r')'
        r'(?P<sep>["\']?\s*[:=]\s*["\']?)'
        r'(?P<value>(?:Bearer\s+)?[A-Za-z0-9\-_\.=+/]{8,})',
        re.IGNORECASE,
    )

    # 独立匹配 Bearer token(不与具体 key 关联的情况)
    _BEARER_PATTERN = re.compile(r'\bBearer\s+([A-Za-z0-9\-_\.=+/]{8,})\b', re.IGNORECASE)

    @classmethod
    def _mask(cls, value: str) -> str:
        if len(value) <= 8:
            return '****'
        return f'{value[:4]}****{value[-4:]}'

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        def _replace(m: re.Match) -> str:
            return f"{m.group('key')}{m.group('sep')}{self._mask(m.group('value'))}"

        masked = self._PATTERN.sub(_replace, msg)
        # 再扫一遍独立的 Bearer token
        masked = self._BEARER_PATTERN.sub(lambda m: f'Bearer {self._mask(m.group(1))}', masked)
        if masked != msg:
            record.msg = masked
            record.args = ()
        return True


def _ensure_file_handler(
    logger: logging.Logger,
    log_file: Union[str, Path],
    level: int,
    formatter: logging.Formatter,
    enable_mask: bool,
) -> logging.Handler:
    """为 logger 挂载(或复用)指定路径的轮转文件 handler,并返回该 handler"""
    log_path = Path(log_file).expanduser().resolve()
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path:
            return handler

    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8',
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    if enable_mask:
        file_handler.addFilter(SensitiveDataFilter())
    logger.addHandler(file_handler)
    return file_handler


def setup_logger(
    name: str,
    level: int = logging.INFO,
    fmt: Optional[str] = None,
    enable_mask: bool = True,
    log_file: Optional[Union[str, Path]] = None,
) -> logging.Logger:
    """
    创建统一格式的 logger

    Args:
        name: logger 名称(通常为平台名,如 'workbuddy')
        level: 日志级别
        fmt: 自定义格式,默认 '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        enable_mask: 是否启用敏感字段脱敏(默认启用)
        log_file: 可选的本地日志文件路径(轮转写入,单文件最大 2MB,保留 3 个备份)

    Returns:
        配置好的 logger,自动添加 console handler 与脱敏 filter
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt or '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # 避免重复添加 handler(同一 logger 多次 setup 时)
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        if enable_mask:
            console_handler.addFilter(SensitiveDataFilter())
        logger.addHandler(console_handler)
        logger.propagate = False

    file_handler = None
    if log_file is not None:
        file_handler = _ensure_file_handler(logger, log_file, level, formatter, enable_mask)

    # '_shared.xxx' 与平台 logger 无父子关系且根 logger 无 handler,
    # 不同步的话 _shared 包内模块的日志会被静默丢弃
    shared_logger = logging.getLogger(SHARED_PARENT_LOGGER)
    if not shared_logger.handlers:
        shared_logger.setLevel(level)
        for handler in logger.handlers:
            shared_logger.addHandler(handler)
        shared_logger.propagate = False
    elif file_handler is not None and file_handler not in shared_logger.handlers:
        shared_logger.addHandler(file_handler)

    return logger
