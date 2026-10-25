#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_shared.config 单元测试"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'script'))

from _shared.config import (
    load_json_config,
    load_platform_accounts,
    save_account_fields,
)


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """创建临时配置文件"""
    data = {
        'workbuddy': {
            'accounts': [
                {'account_name': 'a1', 'access_token': 'token_1'},
                {'account_name': 'a2', 'access_token': 'token_2'},
            ]
        },
        'wps': {'accounts': []},
    }
    path = tmp_path / 'token.json'
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


class TestLoadJsonConfig:
    def test_loads_valid_file(self, config_file):
        data = load_json_config(config_file)
        assert 'workbuddy' in data

    def test_raises_when_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_json_config(tmp_path / 'nonexistent.json')

    def test_raises_on_invalid_json(self, tmp_path):
        bad = tmp_path / 'bad.json'
        bad.write_text('{not json}', encoding='utf-8')
        with pytest.raises(json.JSONDecodeError):
            load_json_config(bad)


class TestLoadPlatformAccounts:
    def test_returns_accounts(self, config_file):
        accounts = load_platform_accounts('workbuddy', config_file)
        assert len(accounts) == 2
        assert accounts[0]['account_name'] == 'a1'

    def test_returns_empty_for_missing_platform(self, config_file):
        accounts = load_platform_accounts('nonexistent_platform', config_file)
        assert accounts == []

    def test_warns_on_missing_required_fields(self, config_file, caplog):
        with caplog.at_level('WARNING'):
            load_platform_accounts('workbuddy', config_file, required_fields=['refresh_token'])
        assert '缺少字段' in caplog.text or 'missing' in caplog.text.lower()


class TestSaveAccountFields:
    def test_updates_account_fields(self, config_file):
        ok = save_account_fields('workbuddy', 0, {'access_token': 'new_token'}, config_file)
        assert ok

        data = json.loads(config_file.read_text(encoding='utf-8'))
        assert data['workbuddy']['accounts'][0]['access_token'] == 'token_1'.replace('token_1', 'new_token')
        # 其他账号不受影响
        assert data['workbuddy']['accounts'][1]['access_token'] == 'token_2'

    def test_out_of_range_index_returns_false(self, config_file):
        ok = save_account_fields('workbuddy', 99, {'x': 'y'}, config_file)
        assert not ok

    def test_atomic_write_no_tmp_file_left(self, config_file):
        save_account_fields('workbuddy', 0, {'access_token': 'x'}, config_file)
        tmp = config_file.with_suffix('.json.tmp')
        assert not tmp.exists()
