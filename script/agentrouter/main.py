#!/usr/bin/env python3
"""
new Env('AgentRouter签到');
cron: 20 9 * * *
"""

"""
Agent Router（ps.air-outer.com）每日签到脚本

签到原理：该站点没有独立签到入口，额度在**登录时**发放（官方 FAQ：「签到领 $25 额度」
需要退出后重新登录才会到账）。脚本因此每天完整重走一次 GitHub OAuth 登录：

    站点 /api/oauth/state -> GitHub 授权换 code -> 站点 /api/oauth/github 登录 -> 额度到账

GitHub 登录态由配置提供（github_session），不读取任何浏览器数据。
GitHub 回调域名为 agentrouter.org（境内不通），脚本只从其跳转地址中提取 code，
随后统一用配置中的 base_url（默认 https://ps.air-outer.com）完成登录。

配置示例（config/token.json 的 agentrouter 节点）：
{
  "agentrouter": {
    "accounts": [
      {
        "account_name": "erma0",
        "github_session": "GitHub 登录后的 user_session 值"
      }
    ]
  }
}

Author: Assistant
Date: 2026-09-10
"""

import sys
from pathlib import Path
from typing import Any

# 路径布局:项目根目录(notification)、script/ 目录(_shared)、脚本所在目录(api 等 sibling 模块)
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(script_dir.parent))
sys.path.insert(0, str(script_dir))

from _shared import (
    apply_startup_jitter,
    get_default_config_path,
    load_platform_accounts,
    run_accounts,
    send_summary_notification,
    setup_logger,
)
from api import DEFAULT_BASE_URL, AgentRouterAPI

from notification import NotificationSound

logger = setup_logger('agentrouter')


class AgentRouterTasks:
    """Agent Router 签到任务执行类"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            self.config_path = get_default_config_path()
        else:
            self.config_path = Path(config_path)

        self.logger = logger
        self.accounts: list[dict[str, Any]] = load_platform_accounts(
            'agentrouter', self.config_path, required_fields=['github_session'])
        self.account_results: list[dict[str, Any]] = []

    def _build_api(self, account_info: dict[str, Any]) -> AgentRouterAPI:
        return AgentRouterAPI(
            base_url=account_info.get('base_url') or DEFAULT_BASE_URL,
            github_session=account_info.get('github_session') or '',
            user_id=account_info.get('user_id') or '',
            proxy=account_info.get('proxy') or '',
            verify=account_info.get('verify'),
        )

    def _describe_user(self, api: AgentRouterAPI, session) -> dict[str, Any]:
        """查询登录后的账号信息，返回额度摘要"""
        info = api.get_user_self(session)
        if not info.get('success'):
            return {'success': False, 'error': info.get('error')}

        user = info.get('user') or {}
        quota = user.get('quota')
        summary = {
            'success': True,
            'display_name': user.get('display_name') or user.get('username') or '',
            'quota': quota,
            'used_quota': user.get('used_quota'),
            'quota_usd': api.quota_to_usd(quota),
        }
        return summary

    def process_account(self, account_index: int, account_info: dict[str, Any]) -> dict[str, Any]:
        """
        处理单个账号的签到（即重新登录）

        Args:
            account_index (int): 账号下标
            account_info (Dict[str, Any]): 账号配置

        Returns:
            Dict[str, Any]: 处理结果
        """
        account_name = account_info.get('account_name') or f'账号{account_index + 1}'
        self.logger.info(f"\n{'=' * 60}\n开始处理账号: {account_name}\n{'=' * 60}")

        result: dict[str, Any] = {
            'account_name': account_name,
            'success': False,
            'message': '',
            'token_error': False,
            'quota_usd': None,
            'checked_in': None,
        }

        api = self._build_api(account_info)
        self.logger.info(f'{account_name} - 站点: {api.base_url}')

        # 登录即签到：重走一次 GitHub OAuth 登录，服务端在登录流程中发放额度
        self.logger.info(f'{account_name} - 通过 GitHub OAuth 重新登录以触发签到')
        login = api.login_by_github()

        if not login.get('success'):
            result['message'] = login.get('error', '登录失败')
            result['token_error'] = login.get('error_type') in ('missing_credential', 'auth_failed')
            self.logger.error(f"❌ {account_name}: {result['message']}")
            return result

        summary = self._describe_user(api, login['session'])
        # checked_in 为服务端下发的「今日已签到」标记：同日重复登录仍为 true 且不重复
        # 发放额度，仅它以真值计为签到成功，其余情况如实标失败以便人工确认
        checked_in = bool(login.get('checked_in'))
        result['checked_in'] = checked_in
        result['mode'] = login.get('mode', '')
        result['success'] = checked_in
        result['message'] = ('登录成功，今日已签到' if checked_in
                             else '登录成功但未标记签到到账（今日已签到或额度未发放），请人工确认')
        if summary.get('success'):
            result['quota_usd'] = summary.get('quota_usd')
            result['display_name'] = summary.get('display_name')
            result['message'] += f"（当前余额 ${summary.get('quota_usd')}）"
        else:
            self.logger.warning(f"⚠️ {account_name}: 签到已完成，但查询余额失败"
                                f"（{summary.get('error')}）")
        self.logger.info(f"✅ {account_name}: {result['message']}")
        return result

    def run(self, dry_run: bool = False):
        """执行所有账号的签到"""
        if not self.accounts:
            self.logger.error('没有可处理的账号，请检查配置')
            return

        if dry_run:
            self.logger.info('[dry-run] 仅校验配置，不执行登录')
            for index, account in enumerate(self.accounts):
                name = account.get('account_name') or f'账号{index + 1}'
                has_github = bool(account.get('github_session'))
                self.logger.info(f'{name}: GitHub登录态={has_github}')
            return

        # 启动随机抖动，错开请求高峰
        apply_startup_jitter('AGENTROUTER_JITTER_MAX', 600)

        self.account_results = run_accounts(self.accounts, self.process_account)
        self._send_notification()

    def _send_notification(self):
        """汇总并发送推送通知"""
        if not self.account_results:
            return

        send_summary_notification(
            'AgentRouter',
            self.account_results,
            title='AgentRouter签到结果通知',
            sound=NotificationSound.BIRDSONG,
        )


def main():
    dry_run = '--dry-run' in sys.argv
    try:
        AgentRouterTasks().run(dry_run=dry_run)
    except (FileNotFoundError, ValueError) as exc:
        logger.error(f'❌ 错误: {exc}')
        sys.exit(1)
    except Exception as exc:
        logger.exception(f'❌ 发生未知错误: {exc}')
        sys.exit(1)


if __name__ == '__main__':
    main()
