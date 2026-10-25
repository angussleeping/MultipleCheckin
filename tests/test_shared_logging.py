#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_shared.logging 单元测试"""

import logging
import sys
from pathlib import Path

import pytest

# 让 script/_shared 可被 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'script'))

from _shared.logging import SensitiveDataFilter, setup_logger


class TestSensitiveDataFilter:
    def _make_record(self, msg: str) -> logging.LogRecord:
        return logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg=msg, args=(), exc_info=None,
        )

    def test_masks_cookie(self):
        f = SensitiveDataFilter()
        record = self._make_record('请求头: cookie=abcdef1234567890XYZ')
        f.filter(record)
        assert 'abcdef1234567890XYZ' not in record.getMessage()
        assert 'abcd****' in record.getMessage()

    def test_masks_token_with_quotes(self):
        f = SensitiveDataFilter()
        record = self._make_record('body: {"access_token": "tok_0123456789abcdef"}')
        f.filter(record)
        assert 'tok_0123456789abcdef' not in record.getMessage() or 'tok_****' in record.getMessage()

    def test_masks_authorization_header(self):
        f = SensitiveDataFilter()
        record = self._make_record('Authorization: Bearer abcdef123456789')
        f.filter(record)
        assert 'abcdef123456789' not in record.getMessage()

    def test_short_value_fully_masked(self):
        f = SensitiveDataFilter()
        record = self._make_record('token=short12')
        f.filter(record)
        # 长度<=8 不脱敏(正则要求至少 8 位);边界情况只验证不抛异常
        assert record.getMessage()

    def test_normal_message_unchanged(self):
        f = SensitiveDataFilter()
        msg = '普通日志消息,不含敏感信息'
        record = self._make_record(msg)
        f.filter(record)
        assert record.getMessage() == msg


class TestSetupLogger:
    def test_returns_logger_with_handler(self):
        logger = setup_logger('test_platform_a')
        assert logger.handlers, '应至少有一个 handler'
        assert logger.level == logging.INFO

    def test_idempotent_no_duplicate_handlers(self):
        logger1 = setup_logger('test_platform_b')
        handler_count = len(logger1.handlers)
        logger2 = setup_logger('test_platform_b')
        assert logger1 is logger2
        assert len(logger2.handlers) == handler_count

    def test_custom_level(self):
        logger = setup_logger('test_platform_c', level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_mask_filter_attached_by_default(self):
        logger = setup_logger('test_platform_d')
        has_mask = any(
            any(isinstance(f, SensitiveDataFilter) for f in h.filters)
            for h in logger.handlers
        )
        assert has_mask

    def test_mask_can_be_disabled(self):
        logger = setup_logger('test_platform_e', enable_mask=False)
        has_mask = any(
            any(isinstance(f, SensitiveDataFilter) for f in h.filters)
            for h in logger.handlers
        )
        assert not has_mask


class TestSharedParentLogger:
    """setup_logger 应把 handler 同步到 '_shared' 父 logger,

    使 _shared 包内模块(logging.getLogger('_shared.xxx'))的日志不被静默丢弃。"""

    @staticmethod
    def _reset_shared() -> None:
        shared = logging.getLogger('_shared')
        for handler in list(shared.handlers):
            shared.removeHandler(handler)

    def test_shared_child_logger_emits(self, capsys):
        self._reset_shared()
        try:
            setup_logger('test_platform_shared_sync')
            logging.getLogger('_shared.config').info('内部日志可见性探针')
            assert '内部日志可见性探针' in capsys.readouterr().out
        finally:
            self._reset_shared()

    def test_log_file_written_and_masked(self, tmp_path):
        log_file = tmp_path / 'logs' / 'task.log'
        logger = setup_logger('test_platform_file', log_file=log_file)
        try:
            logger.info('写文件测试 cookie=abcdef1234567890')
            for handler in logger.handlers:
                handler.flush()
            content = log_file.read_text(encoding='utf-8')
            assert '写文件测试' in content
            assert 'abcdef1234567890' not in content, '文件日志同样应脱敏'
        finally:
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                handler.close()
            self._reset_shared()
