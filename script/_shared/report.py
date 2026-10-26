#!/usr/bin/env python3
"""
执行结果汇总与推送

统一生成可读的任务执行报告,并通过 notification 模块推送。
"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def build_summary(
    results: list[dict[str, Any]],
    *,
    extra_stats: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    构建执行结果统计

    Args:
        results: run_accounts 返回的结果列表
        extra_stats: 附加统计字段(如 'already_checked')

    Returns:
        {
            'total': int,
            'success': int,
            'failed': int,
            'already_checked': int,
            'extras': {...},
        }
    """
    total = len(results)
    success = sum(1 for r in results if r.get('success'))
    already = sum(1 for r in results if r.get('already_checked'))
    summary = {
        'total': total,
        'success': success,
        'failed': total - success,
        'already_checked': already,
        'extras': extra_stats or {},
    }
    return summary


def render_summary_text(
    platform_name: str,
    results: list[dict[str, Any]],
    summary: Optional[dict[str, Any]] = None,
) -> str:
    """
    把结果渲染为推送文本
    """
    if summary is None:
        summary = build_summary(results)

    lines = [
        f'📊 总账号数: {summary["total"]}',
        f'✅ 签到成功: {summary["success"] - summary["already_checked"]}',
        f'📅 今日已签: {summary["already_checked"]}',
        f'❌ 签到失败: {summary["failed"]}',
    ]

    for key, value in summary.get('extras', {}).items():
        lines.append(f'{key}: {value}')

    lines.append('')
    lines.append('📋 详细结果:')

    for r in results:
        status = '✅' if r.get('success') else '❌'
        name = r.get('account_name') or '未命名账号'
        msg = r.get('message') or ''
        lines.append(f'{status} {name}: {msg}')

        details = []
        if r.get('credit') is not None:
            details.append(f'积分 +{r["credit"]}')
        if r.get('streak_days') is not None:
            details.append(f'连签 {r["streak_days"]} 天')
        if details:
            lines.append(f'    🎁 {" | ".join(details)}')

        # 平台自定义详情行(如抽奖奖品、任务统计),保留原有的缩进层级
        for extra_line in r.get('details') or []:
            lines.append(f'    {extra_line}')

    return '\n'.join(lines)


def send_summary_notification(
    platform_name: str,
    results: list[dict[str, Any]],
    *,
    title: Optional[str] = None,
    summary: Optional[dict[str, Any]] = None,
    **send_kwargs,
) -> bool:
    """
    发送任务汇总推送

    Args:
        platform_name: 平台显示名,用于默认标题
        results: 执行结果列表
        title: 自定义标题,默认 '{platform_name}签到结果通知'
        summary: 已构建的统计信息
        **send_kwargs: 透传给 notification.send_notification

    Returns:
        推送是否成功
    """
    if not results:
        logger.info('无结果,跳过推送')
        return False

    # 延迟到此处才 import,避免 _shared 被引入时立刻加载 notification 模块
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from notification import send_notification
    except ImportError:
        logger.exception('notification 模块导入失败')
        return False

    title = title or f'{platform_name}签到结果通知'
    content = render_summary_text(platform_name, results, summary)

    try:
        send_notification(title=title, content=content, **send_kwargs)
        logger.info('推送通知已发送')
        return True
    except Exception as e:
        logger.warning('发送推送通知失败: %s', e)
        return False
