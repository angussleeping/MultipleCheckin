# -*- coding: utf-8 -*-
"""Telegram 推送渠道"""

import requests


def load_config(get_value) -> dict:
    """加载Telegram配置"""
    return {
        'bot_token': get_value('telegram', 'bot_token', 'TG_BOT_TOKEN', ''),
        'user_id': get_value('telegram', 'user_id', 'TG_USER_ID', ''),
        'api_host': get_value('telegram', 'api_host', 'TG_API_HOST', ''),
        'proxy': get_value('telegram', 'proxy', 'TG_PROXY', ''),
    }


def is_enabled(config) -> bool:
    """检查Telegram推送是否已启用"""
    return bool(config.get('bot_token') and config.get('user_id'))


def send(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送Telegram推送"""
    if not is_enabled(config):
        logger.warning("Telegram推送未启用")
        return False

    bot_token = config['bot_token']
    user_id = config['user_id']
    api_host = config.get('api_host')
    proxy = config.get('proxy')

    message = f"<b>{title}</b>\n\n{content}"
    url = f"https://{api_host}/bot{bot_token}/sendMessage" if api_host else f"https://api.telegram.org/bot{bot_token}/sendMessage"

    data = {
        'chat_id': user_id,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': 'true'
    }
    proxies = {'http': proxy, 'https': proxy} if proxy else None

    try:
        logger.info("正在发送Telegram推送")
        response = requests.post(url, data=data, proxies=proxies, timeout=timeout)
        if response.json().get('ok'):
            logger.info("✅ Telegram推送成功")
            return True
        else:
            logger.error(f"❌ Telegram推送失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Telegram推送异常: {e}")
        return False
