# -*- coding: utf-8 -*-
"""PushDeer 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载PushDeer配置"""
    return {
        'pushkey': get_value('pushdeer', 'pushkey', 'PUSHDEER_PUSHKEY', ''),
        'url': get_value('pushdeer', 'url', 'PUSHDEER_URL', 'https://api2.pushdeer.com/message/push'),
        'type': get_value('pushdeer', 'type', 'PUSHDEER_TYPE', 'text'),
    }


def is_enabled(config) -> bool:
    """检查PushDeer推送是否已启用"""
    return bool(config.get('pushkey'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送 PushDeer 推送"""
    if not is_enabled(config):
        logger.warning("PushDeer 推送未启用")
        return False

    pushkey = config.get('pushkey')
    url = config.get('url', 'https://api2.pushdeer.com/message/push').rstrip('/')
    ptype = config.get('type', 'text')

    data = {
        'pushkey': pushkey,
        'text': title or '',
        'desp': content or '',
        'type': ptype
    }

    try:
        logger.info("正在发送 PushDeer 推送")
        response = requests.post(url, data=data, timeout=timeout)
        # 常见官方在线版返回 status_code 200 表示提交成功；进一步尝试解析 JSON
        if response.status_code == 200:
            try:
                j = response.json()
                # 新旧版本可能有不同字段，尽量通用判断
                if j.get('success') is True or j.get('code') == 0 or j.get('message'):
                    logger.info("✅ PushDeer 推送已提交")
                    return True
            except Exception:
                # 非 json 响应也视为提交成功
                logger.info("✅ PushDeer 推送已提交 (非JSON响应)")
                return True

            # 如果解析后没有明显成功字段，仍以 200 作为成功提交的标志
            logger.info("✅ PushDeer 推送已提交")
            return True
        else:
            logger.error(f"❌ PushDeer 推送失败: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ PushDeer 推送异常: {e}")
        return False
