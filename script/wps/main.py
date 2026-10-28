#!/usr/bin/env python3
"""
new Env('WPS签到抽奖');
cron: 18 4 * * *
"""

"""
WPS 多页面任务入口脚本

当前统一执行以下活动页面：
- 任务中心
- 天天领福利

Author: Assistant
Date: 2026-03-11
"""

import random
import sys
import time
from pathlib import Path
from typing import Any

# 获取项目根目录,并将根目录与 script/ 目录加入 sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "script"))

from _shared import (
    apply_startup_jitter,
    build_summary,
    load_platform_accounts,
    run_accounts,
    send_summary_notification,
    setup_logger,
)
from daily_benefits import DailyBenefitsTasks
from logging_utils import (
    log_account_end,
    log_account_start,
    log_banner,
    log_page_switch,
    log_startup,
)
from task_center import WPSTaskCenterPage

from notification import NotificationSound


class WPSMultiPageRunner:
    """WPS 多页面任务统一入口"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            self.config_path = project_root / "config" / "token.json"
        else:
            self.config_path = Path(config_path)

        self.logger = setup_logger("wps")
        self.accounts: list[dict[str, Any]] = load_platform_accounts("wps", self.config_path)
        self.account_results: list[dict[str, Any]] = []
        self.page_tasks: list[tuple[str, type]] = [
            ("任务中心", WPSTaskCenterPage),
            ("天天领福利", DailyBenefitsTasks),
        ]
        self.page_runners: list[tuple[str, Any]] = []

    @staticmethod
    def _is_auth_expired_result(page_result: dict[str, Any]) -> bool:
        """判断页面结果是否为登录态失效。"""
        if page_result.get("auth_expired"):
            return True

        message = str(page_result.get("message", ""))
        keywords = ("Token已过期", "ErrNotLogin", "userNotLogin", "未登录", "请重新登录")
        return any(keyword in message for keyword in keywords)

    def _process_account(self, account_index: int, account_info: dict[str, Any]) -> dict[str, Any]:
        """处理单个账号的所有页面任务"""
        account_name = account_info.get("account_name", "未命名账号")
        account_result: dict[str, Any] = {
            "account_name": account_name,
            "success": True,
            "message": "",
            "pages": []
        }

        log_account_start(self.logger, account_name)

        for page_index, (page_name, page_runner) in enumerate(self.page_runners):
            log_page_switch(self.logger, page_name)
            try:
                page_result = page_runner.process_account(account_info)
            except Exception as exc:
                page_result = {
                    "account_name": account_name,
                    "success": False,
                    "message": f"{page_name}执行异常: {exc}"
                }
                self.logger.exception("%s 页面执行失败", page_name)

            account_result["pages"].append({
                "page_name": page_name,
                "result": page_result
            })

            # 页面执行器提供 build_notification_lines 时,收集详情行用于推送展示
            builder = getattr(page_runner, "build_notification_lines", None)
            if callable(builder):
                try:
                    account_result.setdefault("details", []).extend(builder(page_result))
                except Exception:
                    self.logger.exception("构造 %s 推送详情行失败", page_name)

            if not page_result.get("success", False):
                account_result["success"] = False

            if self._is_auth_expired_result(page_result):
                self.logger.warning("[%s] 登录态已失效，停止执行该账号后续页面任务", account_name)
                break

            if page_index < len(self.page_runners) - 1:
                delay = random.uniform(1, 2)
                self.logger.info("")
                time.sleep(delay)

        account_result["message"] = " | ".join(
            f"{page_item['page_name']}: {page_item['result'].get('message', '')}"
            for page_item in account_result["pages"]
        )
        log_account_end(self.logger, account_name, account_result["success"])
        return account_result

    def run(self) -> None:
        """按账号顺序执行所有页面任务。"""
        log_startup(self.logger, len(self.accounts))
        self.logger.info("")

        if not self.accounts:
            self.logger.warning("没有需要处理的账号")
            return

        apply_startup_jitter("WPS_JITTER_MAX", 600)

        self.page_runners = [
            (
                page_name,
                task_class(config_path=str(self.config_path), enable_notification=False, load_accounts=False)
            )
            for page_name, task_class in self.page_tasks
        ]

        self.account_results = run_accounts(
            self.accounts,
            self._process_account,
            interval_range=(3, 6),
        )

        self._print_summary()
        self._send_notification()

    def _print_summary(self) -> None:
        """打印账号级页面汇总结果。"""
        self.logger.info("")
        log_banner(self.logger, "多页面任务执行结果统计")

        summary = build_summary(self.account_results)

        self.logger.info("总账号数: %s", summary["total"])
        self.logger.info("执行成功: %s", summary["success"])
        self.logger.info("执行失败: %s", summary["failed"])

        for item in self.account_results:
            status = "✅ 成功" if item["success"] else "❌ 失败"
            self.logger.info("%s: %s", item["account_name"], status)
            for page_item in item.get("pages", []):
                page_result = page_item["result"]
                self.logger.info(
                    "  - %s: %s",
                    page_item["page_name"],
                    page_result.get("message", "")
                )

        self.logger.info("%s", "=" * 60)

    def _send_notification(self) -> None:
        """统一发送所有页面的汇总通知。"""
        if not self.account_results:
            return

        summary = build_summary(self.account_results)
        send_summary_notification(
            "WPS多页面任务",
            self.account_results,
            title="WPS多页面任务结果通知",
            summary=summary,
            sound=NotificationSound.BIRDSONG,
        )


def main() -> None:
    """主函数"""
    logger = setup_logger("wps")
    try:
        WPSMultiPageRunner().run()
    except FileNotFoundError as exc:
        logger.error("❌ 错误: %s", exc)
        logger.error("请确保配置文件存在并包含 WPS 账号信息")
        sys.exit(1)
    except Exception as exc:
        logger.exception("❌ 发生未知错误: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
