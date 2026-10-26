"""青龙面板通知推送管理器"""

import logging
from functools import partial
from typing import Optional

from .channels import (
    bark,
    coolpush,
    dingtalk,
    feishu,
    gotify,
    ntfy,
    pushdeer,
    pushplus,
    qmsg,
    qywx,
    server,
    telegram,
)
from .config_loader import get_config_value, load_config_from_file


class NotificationManager:
    """青龙面板通知推送管理器"""

    def __init__(self):
        """初始化推送管理器"""
        self.logger = logging.getLogger("NotificationManager")
        self.config_from_file = load_config_from_file()

        get_value = partial(get_config_value, self.config_from_file)

        self.bark_config = bark.load_config(get_value)
        self.server_config = server.load_config(get_value)
        self.coolpush_config = coolpush.load_config(get_value)
        self.qmsg_config = qmsg.load_config(get_value)
        self.telegram_config = telegram.load_config(get_value)
        self.feishu_config = feishu.load_config(get_value)
        self.dingtalk_config = dingtalk.load_config(get_value)
        self.qywx_config = qywx.load_config(get_value)
        self.pushplus_config = pushplus.load_config(get_value)
        self.gotify_config = gotify.load_config(get_value)
        self.ntfy_config = ntfy.load_config(get_value)
        self.pushdeer_config = pushdeer.load_config(get_value)

    def is_bark_enabled(self) -> bool:
        """检查Bark推送是否已启用"""
        return bark.is_enabled(self.bark_config)

    def is_server_enabled(self) -> bool:
        """检查Server酱推送是否已启用"""
        return server.is_enabled(self.server_config)

    def is_coolpush_enabled(self) -> bool:
        """检查CoolPush推送是否已启用"""
        return coolpush.is_enabled(self.coolpush_config)

    def is_qmsg_enabled(self) -> bool:
        """检查Qmsg酱推送是否已启用"""
        return qmsg.is_enabled(self.qmsg_config)

    def is_telegram_enabled(self) -> bool:
        """检查Telegram推送是否已启用"""
        return telegram.is_enabled(self.telegram_config)

    def is_feishu_enabled(self) -> bool:
        """检查飞书推送是否已启用"""
        return feishu.is_enabled(self.feishu_config)

    def is_dingtalk_enabled(self) -> bool:
        """检查钉钉推送是否已启用"""
        return dingtalk.is_enabled(self.dingtalk_config)

    def is_qywx_robot_enabled(self) -> bool:
        """检查企业微信群机器人推送是否已启用"""
        return qywx.is_robot_enabled(self.qywx_config)

    def is_qywx_app_enabled(self) -> bool:
        """检查企业微信应用消息推送是否已启用"""
        return qywx.is_app_enabled(self.qywx_config)

    def is_pushplus_enabled(self) -> bool:
        """检查PushPlus推送是否已启用"""
        return pushplus.is_enabled(self.pushplus_config)

    def is_gotify_enabled(self) -> bool:
        """检查Gotify推送是否已启用"""
        return gotify.is_enabled(self.gotify_config)

    def is_ntfy_enabled(self) -> bool:
        """检查Ntfy推送是否已启用"""
        return ntfy.is_enabled(self.ntfy_config)

    def is_pushdeer_enabled(self) -> bool:
        """检查PushDeer推送是否已启用"""
        return pushdeer.is_enabled(self.pushdeer_config)

    def send(self, title: str, content: str, level: Optional[str] = None,
             sound: Optional[str] = None, group: Optional[str] = None,
             url: Optional[str] = None, timeout: int = 10):
        """
        统一发送所有已启用的通知

        Args:
            title (str): 推送标题
            content (str): 推送内容
            level (Optional[str]): 推送级别 (Bark专用)
            sound (Optional[str]): 推送声音 (Bark专用)
            group (Optional[str]): 推送分组 (Bark专用)
            url (Optional[str]): 跳转链接 (Bark专用)
            timeout (int): 请求超时时间
        """
        if self.is_bark_enabled():
            self.send_bark_notification(title, content, timeout, level, sound, group, url)
        if self.is_server_enabled():
            self.send_server_notification(title, content, timeout)
        if self.is_coolpush_enabled():
            self.send_coolpush_notification(title, content, timeout)
        if self.is_qmsg_enabled():
            self.send_qmsg_notification(content, timeout)
        if self.is_telegram_enabled():
            self.send_telegram_notification(title, content, timeout)
        if self.is_feishu_enabled():
            self.send_feishu_notification(title, content, timeout)
        if self.is_dingtalk_enabled():
            self.send_dingtalk_notification(title, content, timeout)
        if self.is_qywx_robot_enabled():
            self.send_qywx_robot_notification(content, timeout)
        if self.is_qywx_app_enabled():
            self.send_qywx_app_notification(title, content, timeout)
        if self.is_pushplus_enabled():
            self.send_pushplus_notification(title, content, timeout)
        if self.is_pushdeer_enabled():
            self.send_pushdeer_notification(title, content, timeout)
        if self.is_gotify_enabled():
            self.send_gotify_notification(title, content, timeout)
        if self.is_ntfy_enabled():
            self.send_ntfy_notification(title, content, timeout)

    def send_server_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送Server酱推送"""
        return server.send(self.server_config, title, content, timeout, self.logger)

    def send_coolpush_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送CoolPush推送"""
        return coolpush.send(self.coolpush_config, title, content, timeout, self.logger)

    def send_qmsg_notification(self, content: str, timeout: int = 10) -> bool:
        """发送Qmsg酱推送"""
        return qmsg.send(self.qmsg_config, "", content, timeout, self.logger)

    def send_telegram_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送Telegram推送"""
        return telegram.send(self.telegram_config, title, content, timeout, self.logger)

    def send_feishu_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送飞书机器人推送"""
        return feishu.send(self.feishu_config, title, content, timeout, self.logger)

    def send_dingtalk_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送钉钉机器人推送"""
        return dingtalk.send(self.dingtalk_config, title, content, timeout, self.logger)

    def send_qywx_robot_notification(self, content: str, timeout: int = 10) -> bool:
        """发送企业微信群机器人推送"""
        return qywx.send_robot(self.qywx_config, "", content, timeout, self.logger)

    def send_qywx_app_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送企业微信应用消息推送"""
        return qywx.send_app(self.qywx_config, title, content, timeout, self.logger)

    def send_pushplus_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送PushPlus推送"""
        return pushplus.send(self.pushplus_config, title, content, timeout, self.logger)

    def send_gotify_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送Gotify推送"""
        return gotify.send(self.gotify_config, title, content, timeout, self.logger)

    def send_ntfy_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送Ntfy推送"""
        return ntfy.send(self.ntfy_config, title, content, timeout, self.logger)

    def send_bark_notification(self, title: str, content: str, timeout: int = 10,
                               level: Optional[str] = None, sound: Optional[str] = None,
                               group: Optional[str] = None, url: Optional[str] = None) -> bool:
        """
        发送Bark推送

        Args:
            title (str): 推送标题
            content (str): 推送内容
            timeout (int): 请求超时时间
            level (Optional[str]): 推送级别
            sound (Optional[str]): 推送声音
            group (Optional[str]): 推送分组
            url (Optional[str]): 跳转链接

        Returns:
            bool: 推送是否成功
        """
        return bark.send(self.bark_config, title, content, timeout, self.logger,
                         level=level, sound=sound, group=group, url=url)

    def send_pushdeer_notification(self, title: str, content: str, timeout: int = 10) -> bool:
        """发送 PushDeer 推送"""
        return pushdeer.send(self.pushdeer_config, title, content, timeout, self.logger)


# 创建全局通知管理器实例
notification_manager = NotificationManager()


def send_notification(title: str, content: str, level: Optional[str] = None,
                     sound: Optional[str] = None, group: Optional[str] = None,
                     url: Optional[str] = None):
    """
    便捷函数：发送通知

    Args:
        title (str): 推送标题
        content (str): 推送内容
        level (Optional[str]): 推送级别 (Bark专用)
        sound (Optional[str]): 推送声音 (Bark专用)
        group (Optional[str]): 推送分组 (Bark专用)
        url (Optional[str]): 跳转链接 (Bark专用)
    """
    notification_manager.send(title, content, level=level, sound=sound, group=group, url=url)
