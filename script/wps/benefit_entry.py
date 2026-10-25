#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPS 福利中心入口发现

从多个营销渠道收集活动入口链接，解析去重后按优先级选中「天天领福利」入口。
独立成模块以降低 daily_benefits.py 体积，由 DailyBenefitsAPI.get_benefit_portal 委托调用。
"""

from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

# 入口判定依据活动链接 query 中的 position 参数，福利中心固定为 pc_nvc_activity_fuli。
# 选中优先级：position 精确命中 > position 含 fuli > 标题命中。
TARGET_POSITIONS = ("pc_nvc_activity_fuli",)
TARGET_TITLES = {"福利中心", "天天领福利"}


def discover_benefit_portal(
    market_activity_getter: Callable[[Dict[str, Any]], Dict[str, Any]],
    channels: List[Dict[str, Any]],
    logger,
) -> Dict[str, Any]:
    """
    跨多个营销渠道发现并选中「天天领福利」活动入口

    Args:
        market_activity_getter: 按渠道 payload 查询市场活动的可调用对象
        channels: 营销渠道 payload 列表，靠前的渠道优先级更高
        logger: 日志器（需支持 extra={"step": ...} 上下文）

    Returns:
        成功时为解析后的入口信息，失败时为 {"success": False, "error": ...}
    """
    raw_candidates: List[Dict[str, str]] = []
    channel_errors: List[str] = []
    auth_expired = False

    for channel_payload in channels:
        channel_code = channel_payload.get("channel_code", "")
        market_result = market_activity_getter(channel_payload)
        if not market_result["success"]:
            channel_errors.append(f"{channel_code}: {market_result.get('error', '未知错误')}")
            if market_result.get("error_type") == "token_expired":
                auth_expired = True
            continue
        _collect_portal_candidates(market_result["data"], raw_candidates)

    parsed_candidates = _parse_portal_candidates(raw_candidates)
    logger.info(
        "入口发现：收集到 %s 个链接，去重后 %s 个入口",
        len(raw_candidates),
        len(parsed_candidates),
        extra={"step": "入口发现"}
    )

    if not parsed_candidates:
        failure = {"success": False, "error": "未找到福利中心活动入口"}
        if auth_expired:
            failure["error_type"] = "token_expired"
        elif channel_errors:
            failure["error"] = (
                f"未找到福利中心活动入口（渠道请求失败: {'; '.join(channel_errors)}）"
            )
        return failure

    selected = _select_benefit_portal(parsed_candidates)
    if selected is None:
        found_positions = sorted({
            candidate.get("position", "")
            for candidate in parsed_candidates
            if candidate.get("position")
        })
        return {
            "success": False,
            "error": (
                "未匹配到福利中心入口（期望 position=pc_nvc_activity_fuli）"
                f"，实际发现: {', '.join(found_positions) or '无 position'}"
            )
        }
    return selected


def _parse_portal_candidates(raw_candidates: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """解析候选链接并按 activity/page 去重，附带 position/title。"""
    parsed: List[Dict[str, Any]] = []
    seen: set = set()
    for candidate in raw_candidates:
        portal_info = _parse_portal_link(candidate["link"])
        if not portal_info["success"]:
            continue

        dedup_key = (portal_info["activity_number"], portal_info["page_number"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        portal_info["title"] = candidate.get("title", "")
        portal_info["pic"] = candidate.get("pic", "")
        portal_info["position"] = portal_info.get("filter_params", {}).get("position", "")
        parsed.append(portal_info)
    return parsed


def _select_benefit_portal(parsed_candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """按 position 精确命中 > position 含 fuli > 标题命中 的顺序选中福利入口。"""
    for candidate in parsed_candidates:
        if candidate.get("position") in TARGET_POSITIONS:
            return candidate

    for candidate in parsed_candidates:
        if "fuli" in (candidate.get("position") or ""):
            return candidate

    for candidate in parsed_candidates:
        if candidate.get("title") in TARGET_TITLES:
            return candidate

    return None


def _collect_portal_candidates(node: Any, candidates: List[Dict[str, str]]) -> None:
    """递归收集包含 portal 链接的活动入口（不再要求节点带 title）"""
    if isinstance(node, dict):
        link = node.get("link")
        if isinstance(link, str) and "/rubik2/portal/" in link:
            title = node.get("title")
            candidates.append({
                "title": title if isinstance(title, str) else "",
                "link": link,
                "pic": node.get("pic") or node.get("img") or ""
            })

        for value in node.values():
            _collect_portal_candidates(value, candidates)

    elif isinstance(node, list):
        for item in node:
            _collect_portal_candidates(item, candidates)


def _parse_portal_link(link: str) -> Dict[str, Any]:
    """解析活动 portal 链接"""
    try:
        parsed = urlparse(link)
        path_parts = [part for part in parsed.path.split("/") if part]
        portal_index = path_parts.index("portal")

        activity_number = path_parts[portal_index + 1]
        page_number = path_parts[portal_index + 2]

        query_params = parse_qs(parsed.query)
        filter_params = {
            key: values[0]
            for key, values in query_params.items()
            if values
        }

        return {
            "success": True,
            "link": link,
            "activity_number": activity_number,
            "page_number": page_number,
            "filter_params": filter_params
        }
    except (ValueError, IndexError) as exc:
        return {
            "success": False,
            "error": f"活动链接解析失败: {exc}"
        }
