"""Server酱 / Server酱 Turbo 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载Server酱配置"""
    return {
        'sckey': get_value('server', 'sckey', 'SCKEY', ''),
        'sendkey': get_value('server', 'sendkey', 'SENDKEY', ''),
    }


def is_enabled(config) -> bool:
    """检查Server酱推送是否已启用"""
    return bool(config.get('sckey') or config.get('sendkey'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送Server酱推送"""
    sckey = config.get('sckey')
    sendkey = config.get('sendkey')

    if not (sckey or sendkey):
        logger.warning("Server酱推送未启用")
        return False

    data = {'text': title, 'desp': content.replace("\n", "\n\n")}

    try:
        if sckey:
            logger.info("正在发送Server酱(SCKEY)推送")
            url = f"https://sc.ftqq.com/{sckey}.send"
            response = requests.post(url, data=data, timeout=timeout)
            if response.json().get("errno") == 0:
                logger.info("✅ Server酱(SCKEY)推送成功")
            else:
                logger.error(f"❌ Server酱(SCKEY)推送失败: {response.text}")

        if sendkey:
            logger.info("正在发送Server酱(SENDKEY)推送")
            url = f"https://sctapi.ftqq.com/{sendkey}.send"
            response = requests.post(url, data=data, timeout=timeout)
            if response.json().get("code") == 0:
                logger.info("✅ Server酱(SENDKEY)推送成功")
            else:
                logger.error(f"❌ Server酱(SENDKEY)推送失败: {response.text}")

        return True
    except Exception as e:
        logger.error(f"❌ Server酱推送异常: {e}")
        return False
