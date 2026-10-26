"""钉钉机器人 推送渠道"""

import base64
import hashlib
import hmac
import time
from urllib.parse import quote_plus

import requests


def load_config(get_value) -> dict:
    """加载钉钉配置"""
    return {
        'access_token': get_value('dingtalk', 'access_token', 'DINGTALK_ACCESS_TOKEN', ''),
        'secret': get_value('dingtalk', 'secret', 'DINGTALK_SECRET', ''),
    }


def is_enabled(config) -> bool:
    """检查钉钉推送是否已启用"""
    return bool(config.get('access_token') and config.get('secret'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送钉钉机器人推送"""
    if not is_enabled(config):
        logger.warning("钉钉推送未启用")
        return False

    access_token = config['access_token']
    secret = config['secret']

    timestamp = str(round(time.time() * 1000))
    secret_enc = secret.encode('utf-8')
    string_to_sign = f'{timestamp}\n{secret}'
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(hmac_code))

    url = f"https://oapi.dingtalk.com/robot/send?access_token={access_token}&timestamp={timestamp}&sign={sign}"
    data = {
        "msgtype": "text",
        "text": {
            "content": f"{title}\n\n{content}"
        }
    }

    try:
        logger.info("正在发送钉钉推送")
        response = requests.post(url, json=data, timeout=timeout)
        if response.json().get("errcode") == 0:
            logger.info("✅ 钉钉推送成功")
            return True
        else:
            logger.error(f"❌ 钉钉推送失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ 钉钉推送异常: {e}")
        return False
