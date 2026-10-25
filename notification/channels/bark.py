# -*- coding: utf-8 -*-
"""Bark 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载Bark配置"""
    return {
        'push': get_value('bark', 'push', 'BARK_PUSH', ''),
        'icon': get_value('bark', 'icon', 'BARK_ICON', ''),
        'sound': get_value('bark', 'sound', 'BARK_SOUND', 'birdsong'),
        'group': get_value('bark', 'group', 'BARK_GROUP', ''),
        'level': get_value('bark', 'level', 'BARK_LEVEL', ''),
        'url': get_value('bark', 'url', 'BARK_URL', ''),
    }


def is_enabled(config) -> bool:
    """检查Bark推送是否已启用"""
    return bool(config.get('push'))


def send(config, title, content, timeout, logger, level=None, sound=None, group=None, url=None) -> bool:
    """
    发送Bark推送

    Args:
        config: Bark配置
        title (str): 推送标题
        content (str): 推送内容
        timeout (int): 请求超时时间
        logger: 日志记录器
        level (Optional[str]): 推送级别
        sound (Optional[str]): 推送声音
        group (Optional[str]): 推送分组
        url (Optional[str]): 跳转链接

    Returns:
        bool: 推送是否成功
    """
    if not is_enabled(config):
        logger.warning("Bark推送未启用")
        return False

    bark_push = config.get('push')
    base_url = config.get('url', 'https://api.day.app').rstrip('/')

    url_path = f"{base_url}/{bark_push}" if not bark_push.startswith('http') else bark_push

    data = {
        "title": title,
        "body": content,
        "sound": sound or config.get('sound'),
        "group": group or config.get('group'),
        "level": level or config.get('level'),
        "url": url or config.get('url'),
        "icon": config.get('icon')
    }
    # 移除None值的键
    data = {k: v for k, v in data.items() if v is not None}

    try:
        logger.info("正在发送Bark推送")
        response = requests.post(url_path, json=data, timeout=timeout)
        if response.json().get('code') == 200:
            logger.info("✅ Bark推送成功")
            return True
        else:
            logger.error(f"❌ Bark推送失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Bark推送异常: {e}")
        return False
