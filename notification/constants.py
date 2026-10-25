# -*- coding: utf-8 -*-
"""推送级别与推送声音常量"""


# 推送级别常量
class NotificationLevel:
    """推送级别常量"""
    ACTIVE = "active"           # 默认级别，立即亮屏显示通知
    TIME_SENSITIVE = "timeSensitive"  # 时效性通知，即使在专注模式下也会显示
    PASSIVE = "passive"         # 被动通知，不会立即显示，需要用户主动查看


# 推送声音常量
class NotificationSound:
    """推送声音常量"""
    ALARM = "alarm"
    ANTICIPATE = "anticipate"
    BELL = "bell"
    BIRDSONG = "birdsong"      # 默认
    BLOOM = "bloom"
    CALYPSO = "calypso"
    CHIME = "chime"
    CHOO = "choo"
    DESCENT = "descent"
    ELECTRONIC = "electronic"
    FANFARE = "fanfare"
    GLASS = "glass"
    GOTOSLEEP = "gotosleep"
    HEALTHNOTIFICATION = "healthnotification"
    HORN = "horn"
    LADDER = "ladder"
    MAILSENT = "mailsent"
    MINUET = "minuet"
    MULTIWAYINVITATION = "multiwayinvitation"
    NEWMAIL = "newmail"
    NEWSFLASH = "newsflash"
    NOIR = "noir"
    PAYMENTSUCCESS = "paymentsuccess"
    SHAKE = "shake"
    SHERWOODFOREST = "sherwoodforest"
    SILENCE = "silence"
    SPELL = "spell"
    SUSPENSE = "suspense"
    TELEGRAPH = "telegraph"
    TIPTOES = "tiptoes"
    TYPEWRITERS = "typewriters"
    UPDATE = "update"
