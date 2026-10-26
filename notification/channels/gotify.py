"""Gotify 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载Gotify配置"""
    return {
        'url': get_value('gotify', 'url', 'GOTIFY_URL', ''),
        'token': get_value('gotify', 'token', 'GOTIFY_TOKEN', ''),
        'priority': get_value('gotify', 'priority', 'GOTIFY_PRIORITY', '3'),
    }


def is_enabled(config) -> bool:
    """检查Gotify推送是否已启用"""
    return bool(config.get('url') and config.get('token'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送Gotify推送"""
    if not is_enabled(config):
        logger.warning("Gotify推送未启用")
        return False

    base_url = config['url']
    token = config['token']
    priority = config.get('priority', '3')

    url = f"{base_url}/message?token={token}"
    data = {
        "title": title,
        "message": content,
        "priority": int(priority)
    }

    try:
        logger.info("正在发送Gotify推送")
        response = requests.post(url, json=data, timeout=timeout)
        if response.json().get("id"):
            logger.info("✅ Gotify推送成功")
            return True
        else:
            logger.error(f"❌ Gotify推送失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Gotify推送异常: {e}")
        return False
