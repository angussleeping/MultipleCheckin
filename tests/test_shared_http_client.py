#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_shared.http_client 单元测试"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'script'))

from _shared.http_client import DEFAULT_TIMEOUT, create_session, request_with_retry


class TestCreateSession:
    def test_returns_session(self):
        s = create_session()
        assert isinstance(s, requests.Session)

    def test_default_headers_applied(self):
        s = create_session(default_headers={'User-Agent': 'test-ua'})
        assert s.headers['User-Agent'] == 'test-ua'

    def test_retry_adapter_mounted(self):
        s = create_session()
        adapter = s.get_adapter('https://example.com')
        assert adapter.max_retries.total == 3

    def test_custom_retries(self):
        s = create_session(retries=5)
        adapter = s.get_adapter('https://example.com')
        assert adapter.max_retries.total == 5


class TestRequestWithRetry:
    def test_uses_default_timeout(self):
        s = create_session()
        with patch.object(s, 'request', return_value=object()) as mock_req:
            request_with_retry(s, 'GET', 'https://example.com')
            _, kwargs = mock_req.call_args
            assert kwargs['timeout'] == DEFAULT_TIMEOUT

    def test_explicit_timeout_overrides_default(self):
        s = create_session()
        with patch.object(s, 'request', return_value=object()) as mock_req:
            request_with_retry(s, 'GET', 'https://example.com', timeout=(1, 5))
            _, kwargs = mock_req.call_args
            assert kwargs['timeout'] == (1, 5)

    def test_method_and_url_passed(self):
        s = create_session()
        with patch.object(s, 'request', return_value=object()) as mock_req:
            request_with_retry(s, 'POST', 'https://api.example.com/x', json={'a': 1})
            args, kwargs = mock_req.call_args
            assert args[0] == 'POST'
            assert args[1] == 'https://api.example.com/x'
            assert kwargs['json'] == {'a': 1}
