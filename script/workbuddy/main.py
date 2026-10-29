#!/usr/bin/env python3
"""
new Env('WorkBuddy签到');
cron: 36 3 * * *
"""

"""
WorkBuddy(CodeBuddy)自动签到脚本

该脚本用于自动执行WorkBuddy的每日签到任务，包括：
- 读取账号配置信息
- 查询今日签到状态
- 执行签到操作
- 令牌过期时自动刷新并回写配置
- 推送执行结果

Author: Assistant
Date: 2026-08-03
"""

import logging
import sys
from pathlib import Path
from typing import Any

# 项目根目录: 供 notification 模块导入
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
# script 目录: 供 _shared 共享基础设施包导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _shared import (
    apply_startup_jitter,
    build_summary,
    get_default_config_path,
    load_platform_accounts,
    run_accounts,
    save_account_fields,
    send_summary_notification,
    setup_logger,
)
from api import WorkBuddyAPI

from notification import NotificationSound


class WorkBuddyTasks:
    """WorkBuddy签到任务自动化执行类"""

    def __init__(self, config_path: str = None):
        """
        初始化任务执行器

        Args:
            config_path (str): 配置文件的完整路径，如果为None则使用项目根目录下的config/token.json
        """
        if config_path is None:
            self.config_path = get_default_config_path()
        else:
            self.config_path = Path(config_path)

        self.logger = setup_logger('workbuddy')
        self.accounts: list[dict[str, Any]] = load_platform_accounts('workbuddy', self.config_path)
        self.account_results: list[dict[str, Any]] = []

    def _save_refreshed_token(self, account_index: int, api: WorkBuddyAPI):
        """
        令牌刷新后回写配置文件，避免下次执行仍使用过期令牌

        Args:
            account_index (int): 账号在配置数组中的下标
            api (WorkBuddyAPI): 持有最新令牌的API实例
        """
        updates = {'access_token': api.access_token}
        if api.refresh_token:
            updates['refresh_token'] = api.refresh_token
        if api.domain:
            updates['domain'] = api.domain

        if save_account_fields('workbuddy', account_index, updates, self.config_path):
            self.logger.info("💾 新令牌已写回配置文件")
        else:
            self.logger.warning("⚠️ 回写令牌失败")

    def process_account(self, account_index: int, account_info: dict[str, Any]) -> dict[str, Any]:
        """
        处理单个账号的签到任务

        Args:
            account_index (int): 账号在配置数组中的下标
            account_info (Dict[str, Any]): 账号信息字典

        Returns:
            Dict[str, Any]: 处理结果
        """
        account_name = account_info.get('account_name') or account_info.get('email') or '未命名账号'
        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(f"开始处理账号: {account_name}")
        self.logger.info(f"{'=' * 60}")

        result = {
            'account_name': account_name,
            'success': False,
            'message': '',
            'already_checked': False,
            'credit': None,
            'streak_days': None,
            'status_info': {}
        }

        try:
            access_token = account_info.get('access_token')
            if not access_token:
                error_msg = "账号配置中缺少 access_token"
                self.logger.error(f"❌ {account_name}: {error_msg}")
                result['message'] = error_msg
                return result

            api = WorkBuddyAPI(
                access_token=access_token,
                refresh_token=account_info.get('refresh_token'),
                uid=account_info.get('uid'),
                enterprise_id=account_info.get('enterprise_id'),
                domain=account_info.get('domain'),
                user_agent=account_info.get('user_agent'),
            )

            # 查询签到状态
            self.logger.info(f"{account_name} - 查询签到状态")
            status = api.get_checkin_status()

            if not status['success']:
                error_msg = status.get('error', '查询签到状态失败')
                if status.get('error_type') == 'token_expired':
                    result['message'] = f'{error_msg}，请重新导入账号'
                    self.logger.error(f"❌ {account_name} {result['message']}")
                else:
                    result['message'] = error_msg
                    self.logger.error(f"❌ {account_name} {error_msg}")
                return result

            result['status_info'] = status
            self.logger.info(
                f"📊 连签天数: {status.get('streak_days', 0)} 天 | "
                f"每日积分: {status.get('daily_credit', 0)}"
            )

            # 活动未开启
            if not status.get('active', True):
                result['success'] = True
                result['message'] = '签到活动未开启或不适用'
                self.logger.info(f"ℹ️ {account_name} 签到活动未开启")
                return result

            # 今日已签到
            if status.get('today_checked_in'):
                result['success'] = True
                result['already_checked'] = True
                result['message'] = '今日已签到'
                result['credit'] = status.get('today_credit')
                result['streak_days'] = status.get('streak_days')
                self.logger.info(f"✅ {account_name} 今日已签到")
                return result

            # 执行签到
            self.logger.info(f"{account_name} - 执行签到")
            checkin = api.daily_checkin()

            if checkin['success']:
                result['success'] = True
                result['message'] = checkin.get('message') or '签到成功'
                result['credit'] = checkin.get('credit')
                result['streak_days'] = checkin.get('streak_days')

                self.logger.info(f"✅ {account_name} 签到成功")
                if checkin.get('credit') is not None:
                    self.logger.info(f"🎁 获得积分: {checkin['credit']}")
                if checkin.get('streak_days') is not None:
                    self.logger.info(f"🔥 连签天数: {checkin['streak_days']} 天")
                if checkin.get('is_streak_day'):
                    self.logger.info("🎉 触发连签奖励")
            else:
                # 签到失败后复查状态，可能是并发导致的"已签到"
                latest = api.get_checkin_status()
                if latest['success'] and latest.get('today_checked_in'):
                    result['success'] = True
                    result['already_checked'] = True
                    result['message'] = '今日已签到'
                    result['streak_days'] = latest.get('streak_days')
                    self.logger.info(f"✅ {account_name} 今日已签到")
                else:
                    result['message'] = checkin.get('error', '签到失败')
                    self.logger.error(f"❌ {account_name} 签到失败: {result['message']}")

            # 令牌被刷新过则回写配置
            if api.token_refreshed:
                self._save_refreshed_token(account_index, api)

        except Exception as e:
            error_msg = f"处理账号时发生异常: {str(e)}"
            self.logger.exception(f"❌ {error_msg}")
            result['message'] = error_msg

        return result

    def run(self):
        """执行所有账号的签到任务"""
        # 启动随机抖动，错开请求高峰
        apply_startup_jitter('WORKBUDDY_JITTER_MAX', 600)

        self.logger.info("=" * 60)
        self.logger.info("WorkBuddy自动签到任务开始")
        self.logger.info("=" * 60)

        if not self.accounts:
            self.logger.warning("没有需要处理的账号")
            return

        self.account_results = run_accounts(self.accounts, self.process_account)

        # 打印执行结果统计
        summary = build_summary(self.account_results)
        self.logger.info("\n" + "=" * 60)
        self.logger.info("执行结果统计")
        self.logger.info("=" * 60)
        self.logger.info(f"总账号数: {summary['total']}")
        self.logger.info(f"签到成功: {summary['success'] - summary['already_checked']}")
        self.logger.info(f"今日已签: {summary['already_checked']}")
        self.logger.info(f"签到失败: {summary['failed']}")

        self.logger.info("\n详细结果:")
        for r in self.account_results:
            status = "✅ 成功" if r['success'] else "❌ 失败"
            self.logger.info(f"  {r['account_name']}: {status} - {r['message']}")
        self.logger.info("=" * 60)

        # 推送汇总通知
        send_summary_notification(
            'WorkBuddy',
            self.account_results,
            sound=NotificationSound.BIRDSONG,
        )


def main():
    """主函数"""
    logger = logging.getLogger('workbuddy')
    try:
        tasks = WorkBuddyTasks()
        tasks.run()

    except FileNotFoundError as e:
        logger.error("❌ 错误: %s", e)
        logger.error("请确保配置文件存在并包含 workbuddy 账号信息")
        sys.exit(1)
    except Exception as e:
        logger.error("❌ 发生未知错误: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
