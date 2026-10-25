#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
青龙面板通知推送模块

支持的推送方式：
- Bark 推送
- Server酱 推送
- Server酱 Turbo 推送
- Cool Push 推送
- Qmsg酱 推送
- Telegram 推送
- 飞书 推送
- 钉钉 推送
- 企业微信群机器人 推送
- 企业微信应用消息 推送
- PushPlus 推送
- Gotify 推送
- Ntfy 推送
- PushDeer 推送

配置参数说明（需要在青龙面板的 config.sh 中设置或通过环境变量设置）：
详见各平台对应的配置说明

使用示例：
    from notification import send_notification, NotificationLevel, NotificationSound

    # 基础推送（自动使用所有已配置的平台）
    send_notification("测试标题", "测试内容")

    # 自定义级别和声音
    send_notification(
        "重要通知",
        "这是一条重要消息",
        level=NotificationLevel.TIME_SENSITIVE,
        sound=NotificationSound.ALARM
    )

Author: Assistant
Date: 2025-12-08
参考项目:https://github.com/Sitoi/dailycheckin 的推送相关内容
"""

from .constants import NotificationLevel, NotificationSound
from .manager import NotificationManager, notification_manager, send_notification

__all__ = [
    "NotificationManager",
    "NotificationLevel",
    "NotificationSound",
    "send_notification",
    "notification_manager",
]


if __name__ == "__main__":
    """测试推送功能"""
    import sys
    import logging

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 检查是否有任何推送方式被启用
    if not any([
        notification_manager.is_bark_enabled(),
        notification_manager.is_server_enabled(),
        notification_manager.is_coolpush_enabled(),
        notification_manager.is_qmsg_enabled(),
        notification_manager.is_telegram_enabled(),
        notification_manager.is_feishu_enabled(),
        notification_manager.is_dingtalk_enabled(),
        notification_manager.is_qywx_robot_enabled(),
        notification_manager.is_qywx_app_enabled(),
        notification_manager.is_pushplus_enabled(),
        notification_manager.is_gotify_enabled(),
        notification_manager.is_ntfy_enabled(),
        notification_manager.is_pushdeer_enabled(),
    ]):
        print("❌ 未配置任何推送方式，请检查环境变量")
        sys.exit(1)

    print("🧪 开始测试推送...\n")

    # 测试1: 基础推送
    print("测试1: 基础推送")
    send_notification("📱 青龙面板测试", "这是一条测试推送消息")
    print("基础推送已发送\n")

    # 测试2: 自定义级别和声音 (主要对Bark有效)
    print("测试2: 自定义推送（时效性通知 + 警报声）")
    send_notification(
        "🔔 重要通知",
        "这是一条时效性通知，部分平台（如Bark）会特殊处理",
        level=NotificationLevel.TIME_SENSITIVE,
        sound=NotificationSound.ALARM
    )
    print("自定义推送已发送\n")

    # 测试3: 任务摘要
    print("测试3: 任务摘要")
    task_title = "✅ 上海云媒体任务 - 部分成功"
    task_content = """📊 执行统计:
✅ 成功: 3 个账号
❌ 失败: 1 个账号
📈 总计: 4 个账号

📝 详情: 部分账号token已过期"""
    send_notification(task_title, task_content)
    print("任务摘要已发送\n")

    # 测试4: 错误通知
    print("测试4: 错误通知")
    error_title = "❌ 什么值得买任务 - 执行错误"
    error_content = """💥 发生错误:
👤 账号: 测试账号1
❌ 错误: 网络连接超时"""
    send_notification(error_title, error_content)
    print("错误通知已发送\n")

    print("🎉 测试完成")
