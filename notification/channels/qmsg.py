"""Qmsg酱 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载Qmsg酱配置"""
    return {
        'key': get_value('qmsg', 'key', 'QMSG_KEY', ''),
        'type': get_value('qmsg', 'type', 'QMSG_TYPE', 'private'),
    }


def is_enabled(config) -> bool:
    """检查Qmsg酱推送是否已启用"""
    return bool(config.get('key'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送Qmsg酱推送"""
    if not is_enabled(config):
        logger.warning("Qmsg酱推送未启用")
        return False

    key = config.get('key')
    qmsg_type = config.get('type', 'private')
    url = f"https://qmsg.zendee.cn/{qmsg_type}/{key}"
    params = {'msg': content}

    try:
        logger.info("正在发送Qmsg酱推送")
        response = requests.get(url, params=params, timeout=timeout)
        if response.json().get("success"):
            logger.info("✅ Qmsg酱推送成功")
            return True
        else:
            logger.error(f"❌ Qmsg酱推送失败: {response.json().get('reason')}")
            return False
    except Exception as e:
        logger.error(f"❌ Qmsg酱推送异常: {e}")
        return False
