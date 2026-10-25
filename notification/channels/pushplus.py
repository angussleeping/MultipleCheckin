# -*- coding: utf-8 -*-
"""PushPlus 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载PushPlus配置"""
    return {
        'token': get_value('pushplus', 'token', 'PUSHPLUS_TOKEN', ''),
        'topic': get_value('pushplus', 'topic', 'PUSHPLUS_TOPIC', ''),
    }


def is_enabled(config) -> bool:
    """检查PushPlus推送是否已启用"""
    return bool(config.get('token'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送PushPlus推送"""
    if not is_enabled(config):
        logger.warning("PushPlus推送未启用")
        return False

    token = config['token']
    topic = config.get('topic')

    data = {
        "token": token,
        "title": title,
        "content": content.replace("\n", "<br>"),
        "template": "html"
    }
    if topic:
        data['topic'] = topic

    url = "http://www.pushplus.plus/send"

    try:
        logger.info("正在发送PushPlus推送")
        response = requests.post(url, json=data, timeout=timeout)
        if response.json().get("code") == 200:
            logger.info("✅ PushPlus推送成功")
            return True
        else:
            logger.error(f"❌ PushPlus推送失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ PushPlus推送异常: {e}")
        return False
