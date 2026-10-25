#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_shared.runner 与 _shared.report 单元测试"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'script'))

from _shared.runner import apply_startup_jitter, run_accounts
from _shared.report import build_summary, render_summary_text, send_summary_notification


class TestApplyStartupJitter:
    def test_zero_disables(self):
        with patch.dict(os.environ, {'TEST_JITTER': '0'}):
            delay = apply_startup_jitter('TEST_JITTER', 600)
            assert delay == 0.0

    def test_sleeps_within_range(self):
        with patch.dict(os.environ, {'TEST_JITTER': '5'}), \
             patch('time.sleep') as mock_sleep:
            delay = apply_startup_jitter('TEST_JITTER', 600)
            assert 0 <= delay <= 5
            mock_sleep.assert_called_once()


class TestRunAccounts:
    def test_runs_all_accounts(self):
        accounts = [{'account_name': 'a'}, {'account_name': 'b'}]
        handler = lambda i, acc: {'account_name': acc['account_name'], 'success': True}
        with patch('time.sleep'):
            results = run_accounts(accounts, handler)
        assert len(results) == 2
        assert all(r['success'] for r in results)

    def test_continues_after_exception(self):
        accounts = [{'account_name': 'a'}, {'account_name': 'b'}, {'account_name': 'c'}]

        def handler(i, acc):
            if i == 1:
                raise RuntimeError('boom')
            return {'account_name': acc['account_name'], 'success': True}

        with patch('time.sleep'):
            results = run_accounts(accounts, handler)

        assert len(results) == 3
        assert results[0]['success']
        assert not results[1]['success']
        assert 'boom' in results[1]['message']
        assert results[2]['success']

    def test_no_sleep_after_last_account(self):
        accounts = [{'account_name': 'a'}]
        with patch('time.sleep') as mock_sleep:
            run_accounts(accounts, lambda i, a: {'account_name': 'a', 'success': True})
            mock_sleep.assert_not_called()


class TestBuildSummary:
    def test_counts_correctly(self):
        results = [
            {'account_name': 'a', 'success': True},
            {'account_name': 'b', 'success': True, 'already_checked': True},
            {'account_name': 'c', 'success': False},
        ]
        s = build_summary(results)
        assert s['total'] == 3
        assert s['success'] == 2
        assert s['already_checked'] == 1
        assert s['failed'] == 1


class TestRenderSummaryText:
    def test_includes_counts_and_details(self):
        results = [
            {'account_name': 'a', 'success': True, 'message': '签到成功',
             'credit': 10, 'streak_days': 3},
            {'account_name': 'b', 'success': False, 'message': 'token 过期'},
        ]
        text = render_summary_text('Test', results)
        assert '总账号数: 2' in text
        assert '签到失败: 1' in text
        assert '签到成功' in text
        assert '积分 +10' in text
        assert '连签 3 天' in text
        assert 'token 过期' in text

    def test_renders_custom_details_lines(self):
        results = [
            {'account_name': 'a', 'success': True, 'message': '任务完成',
             'details': ['[任务中心] 签到成功', '抽奖结果: 第1次: 5天会员']},
        ]
        text = render_summary_text('Test', results)
        assert '    [任务中心] 签到成功' in text
        assert '    抽奖结果: 第1次: 5天会员' in text


class TestSendSummaryNotification:
    def _results(self):
        return [{'account_name': 'a', 'success': True, 'message': 'ok'}]

    def _fake_notification(self, monkeypatch, send_notification):
        fake = types.ModuleType('notification')
        fake.send_notification = send_notification
        monkeypatch.setitem(sys.modules, 'notification', fake)

    def test_empty_results_returns_false_without_sending(self):
        assert send_summary_notification('Test', []) is False

    def test_import_failure_returns_false(self, monkeypatch):
        # sys.modules 中置 None 会使 import 抛出 ImportError
        monkeypatch.setitem(sys.modules, 'notification', None)
        assert send_summary_notification('Test', self._results()) is False

    def test_send_exception_returns_false(self, monkeypatch):
        def send_notification(**kwargs):
            raise RuntimeError('push failed')

        self._fake_notification(monkeypatch, send_notification)
        assert send_summary_notification('Test', self._results()) is False

    def test_success_returns_true_and_sends_content(self, monkeypatch):
        captured = {}

        def send_notification(**kwargs):
            captured.update(kwargs)

        self._fake_notification(monkeypatch, send_notification)
        assert send_summary_notification('Test', self._results()) is True
        assert captured['title'] == 'Test签到结果通知'
        assert '总账号数: 1' in captured['content']
