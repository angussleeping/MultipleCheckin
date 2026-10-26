"""Cool Push 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载CoolPush配置"""
    return {
        'skey': get_value('coolpush', 'skey', 'COOLPUSH_SKEY', ''),
        'qq': get_value('coolpush', 'qq', 'COOLPUSH_QQ', True),
        'wx': get_value('coolpush', 'wx', 'COOLPUSH_WX', False),
        'email': get_value('coolpush', 'email', 'COOLPUSH_EMAIL', False),
    }


def is_enabled(config) -> bool:
    """检查CoolPush推送是否已启用"""
    return bool(config.get('skey'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送CoolPush推送"""
    if not is_enabled(config):
        logger.warning("CoolPush推送未启")
        return False

    skey = config.get('skey')
    params = {'c': content, 't': title}

    try:
        logger.info("正在发送CoolPush推送")
        base_url = "https://push.xuthus.cc"
        if config.get('qq'):
            requests.post(f"{base_url}/send/{skey}", params=params, timeout=timeout)
        if config.get('wx'):
            requests.post(f"{base_url}/wx/{skey}", params=params, timeout=timeout)
        if config.get('email'):
            requests.post(f"{base_url}/email/{skey}", params=params, timeout=timeout)
        logger.info("✅ CoolPush推送已提交")
        return True
    except Exception as e:
        logger.error(f"❌ CoolPush推送异常: {e}")
        return False
