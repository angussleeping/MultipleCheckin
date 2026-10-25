# -*- coding: utf-8 -*-
"""企业微信推送渠道（群机器人 + 应用消息）"""

import requests


def load_config(get_value) -> dict:
    """加载企业微信配置"""
    return {
        'key': get_value('qywx', 'key', 'QYWX_KEY', ''),
        'corpid': get_value('qywx', 'corpid', 'QYWX_CORPID', ''),
        'agentid': get_value('qywx', 'agentid', 'QYWX_AGENTID', ''),
        'corpsecret': get_value('qywx', 'corpsecret', 'QYWX_CORPSECRET', ''),
        'touser': get_value('qywx', 'touser', 'QYWX_TOUSER', ''),
        'media_id': get_value('qywx', 'media_id', 'QYWX_MEDIA_ID', ''),
        'origin': get_value('qywx', 'origin', 'QYWX_ORIGIN', ''),
    }


def is_robot_enabled(config) -> bool:
    """检查企业微信群机器人推送是否已启用"""
    return bool(config.get('key'))


def is_app_enabled(config) -> bool:
    """检查企业微信应用消息推送是否已启用"""
    return bool(
        config.get('corpid') and
        config.get('agentid') and
        config.get('corpsecret') and
        config.get('touser')
    )


def send_robot(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送企业微信群机器人推送"""
    if not is_robot_enabled(config):
        logger.warning("企业微信群机器人推送未启用")
        return False

    key = config['key']
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    data = {"msgtype": "text", "text": {"content": content}}

    try:
        logger.info("正在发送企业微信群机器人推送")
        response = requests.post(url, json=data, timeout=timeout)
        if response.json().get("errcode") == 0:
            logger.info("✅ 企业微信群机器人推送成功")
            return True
        else:
            logger.error(f"❌ 企业微信群机器推送失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ 企业微信群机器人推送异常: {e}")
        return False


def send_app(config, title, content, timeout, logger, **kwargs) -> bool:
    """发送企业微信应用消息推送"""
    if not is_app_enabled(config):
        logger.warning("企业微信应用消息推送未启用")
        return False

    corpid = config['corpid']
    corpsecret = config['corpsecret']
    agentid = config['agentid']
    touser = config['touser']
    media_id = config.get('media_id')

    try:
        # 获取 access_token
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}"
        token_res = requests.get(token_url, timeout=timeout).json()
        access_token = token_res.get('access_token')
        if not access_token:
            logger.error(f"❌ 企业微信应用消息获取token失败: {token_res.get('errmsg')}")
            return False

        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"

        if media_id:
            data = {
                "touser": touser,
                "msgtype": "mpnews",
                "agentid": agentid,
                "mpnews": {
                    "articles": [{
                        "title": title,
                        "thumb_media_id": media_id,
                        "content": content.replace("\n", "<br>"),
                        "digest": content
                    }]
                }
            }
        else:
            data = {
                "touser": touser,
                "msgtype": "textcard",
                "agentid": agentid,
                "textcard": {
                    "title": title,
                    "description": content,
                    "url": "https://github.com/ZaiZaiCat/ZaiZaiCat-Checkin",
                    "btntxt": "详情"
                }
            }

        logger.info("正在发送企业微信应用消息推送")
        response = requests.post(send_url, json=data, timeout=timeout)
        if response.json().get("errcode") == 0:
            logger.info("✅ 企业微信应用消息推送成功")
            return True
        else:
            logger.error(f"❌ 企业微信应用消息推送失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ 企业微信应用消息推送异常: {e}")
        return False
