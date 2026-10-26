"""飞书机器人 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载飞书配置"""
    return {
        'key': get_value('feishu', 'key', 'FSKEY', ''),
    }


def is_enabled(config) -> bool:
    """检查飞书推送是否已启用"""
    return bool(config.get('key'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送飞书机器人推送"""
    if not is_enabled(config):
        logger.warning("飞书推送未启用")
        return False

    key = config['key']
    url = f"https://open.feishu.cn/open-apis/bot/v2/hook/{key}"
    data = {
        "msg_type": "text",
        "content": {
            "text": f"{title}\n\n{content}"
        }
    }

    try:
        logger.info("正在发送飞书推送")
        response = requests.post(url, json=data, timeout=timeout)
        if response.json().get("StatusCode") == 0:
            logger.info("✅ 飞书推送成功")
            return True
        else:
            logger.error(f"❌ 飞书推送失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ 飞书推送异常: {e}")
        return False
