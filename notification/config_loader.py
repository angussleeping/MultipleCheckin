# -*- coding: utf-8 -*-
"""通知配置加载：文件 > 环境变量 > 默认值"""

import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger("NotificationManager")


def load_config_from_file() -> Dict:
    """从JSON文件中加载配置"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'notification.json'
    )
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"❌ 配置文件 {config_path} 格式错误")
                return {}
    return {}


def get_config_value(file_config: Dict, service: str, key: str, env_var: str, default: Any = None) -> Any:
    """
    获取配置值，优先级: 文件 > 环境变量 > 默认值
    """
    # 1. 从文件配置中获取
    service_config = file_config.get(service, {})
    value = service_config.get(key)

    # 如果值是字符串，去除首尾空格
    if isinstance(value, str):
        value = value.strip()

    # 文件中有非空值，则直接返回
    if value is not None and value != '':
        return value

    # 2. 从环境变量中获取
    env_value = os.environ.get(env_var, '').strip()
    if env_value:
        # 对布尔类型的环境变量进行特殊处理
        if isinstance(default, bool):
            return env_value.lower() == 'true'
        return env_value

    # 3. 返回默认值
    return default
