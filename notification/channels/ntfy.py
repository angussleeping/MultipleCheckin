"""Ntfy 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载Ntfy配置"""
    return {
        'url': get_value('ntfy', 'url', 'NTFY_URL', 'https://ntfy.sh'),
        'topic': get_value('ntfy', 'topic', 'NTFY_TOPIC', ''),
        'priority': get_value('ntfy', 'priority', 'NTFY_PRIORITY', '3'),
    }


def is_enabled(config) -> bool:
    """检查Ntfy推送是否已启用"""
    return bool(config.get('topic'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送Ntfy推送"""
    if not is_enabled(config):
        logger.warning("Ntfy推送未启用")
        return False

    base_url = config.get('url', 'https://ntfy.sh')
    topic = config['topic']
    priority = config.get('priority', '3')

    url = f"{base_url}/{topic}"
    headers = {
        'Title': title.encode('utf-8'),
        'Priority': priority,
        'Tags': 'tada'
    }

    try:
        logger.info("正在发送Ntfy推送")
        response = requests.post(url, data=content.encode('utf-8'), headers=headers, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ Ntfy推送成功")
        return True
    except Exception as e:
        logger.error(f"❌ Ntfy推送异常: {e}")
        return False
