#!/usr/bin/env python3
"""
统一配置加载与原子写回

读取 config/token.json 中指定平台的账号配置;
支持把更新后的字段(如刷新后的 token)原子写回配置。
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


CONFIG_FILE_ENV = 'CHECKIN_CONFIG_FILE'
CONFIG_DIR_ENV = 'CHECKIN_CONFIG_DIR'


def get_project_root() -> Path:
    """返回项目根目录(script/_shared 的上上级)"""
    return Path(__file__).resolve().parent.parent.parent


def get_default_config_path() -> Path:
    """
    返回默认配置文件路径

    优先级:
    1. 环境变量 CHECKIN_CONFIG_FILE(完整文件路径)
    2. 环境变量 CHECKIN_CONFIG_DIR(目录,自动拼接 token.json)
    3. 项目根目录 config/token.json

    面板部署时把 token.json 放到仓库外的固定目录并设置上述变量,
    重新拉取仓库就不会覆盖本地配置。
    """
    override_file = os.environ.get(CONFIG_FILE_ENV, '').strip()
    if override_file:
        return Path(override_file).expanduser()
    override_dir = os.environ.get(CONFIG_DIR_ENV, '').strip()
    if override_dir:
        return Path(override_dir).expanduser() / 'token.json'
    return get_project_root() / 'config' / 'token.json'


def load_json_config(config_path: Optional[Path] = None) -> dict[str, Any]:
    """
    加载 JSON 配置文件,失败时抛出明确异常

    Args:
        config_path: 配置文件路径,None 时使用默认 token.json

    Raises:
        FileNotFoundError: 配置文件不存在
        json.JSONDecodeError: 配置格式错误
    """
    path = Path(config_path) if config_path else get_default_config_path()
    if not path.exists():
        raise FileNotFoundError(f'配置文件不存在: {path}')

    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_platform_accounts(
    platform: str,
    config_path: Optional[Path] = None,
    *,
    required_fields: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """
    加载指定平台的账号列表

    Args:
        platform: 平台节点名,如 'workbuddy' / 'trae' / 'wps'
        config_path: 配置文件路径
        required_fields: 每个账号必填字段;缺失时仅告警不阻断

    Returns:
        账号字典列表
    """
    data = load_json_config(config_path)
    accounts = data.get(platform, {}).get('accounts', []) or []

    if not accounts:
        logger.warning('配置文件中未找到 %s 账号配置', platform)
        return accounts

    if required_fields:
        for idx, acc in enumerate(accounts):
            missing = [f for f in required_fields if not acc.get(f)]
            if missing:
                name = acc.get('account_name') or acc.get('email') or f'账号#{idx}'
                logger.warning('%s 缺少字段: %s', name, ', '.join(missing))

    logger.info('已加载 %s 平台账号 %d 个', platform, len(accounts))
    return accounts


def save_account_fields(
    platform: str,
    account_index: int,
    updates: dict[str, Any],
    config_path: Optional[Path] = None,
) -> bool:
    """
    原子写回指定账号的字段(用于 token 刷新后持久化)

    通过 临时文件 + os.replace 保证写盘原子性,避免进程中断导致配置损坏。

    Args:
        platform: 平台节点名
        account_index: 账号在 accounts 数组中的下标
        updates: 需要更新的字段键值对
        config_path: 配置文件路径

    Returns:
        写回是否成功
    """
    path = Path(config_path) if config_path else get_default_config_path()

    try:
        data = load_json_config(path)
        accounts = data.get(platform, {}).get('accounts', [])
        if account_index >= len(accounts):
            logger.warning('%s 账号下标 %d 越界,跳过写回', platform, account_index)
            return False

        accounts[account_index].update(updates)

        tmp_path = path.with_suffix(path.suffix + '.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

        logger.info('%s[%d] 配置已原子写回: %s', platform, account_index, ', '.join(updates.keys()))
        return True
    except Exception as e:
        logger.warning('写回 %s[%d] 配置失败: %s', platform, account_index, e)
        return False
