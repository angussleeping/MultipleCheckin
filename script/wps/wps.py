#!/usr/bin/env python3
"""
new Env('WPS签到抽奖');
cron: 18 4 * * *
"""
"""
WPS 签到抽奖统一入口脚本
整合了原仓库三个独立脚本（main.py / task_center.py / daily_benefits.py）的全部功能，
通过 CLI 参数控制执行范围：
    python wps.py                     # 依次执行任务中心 + 天天领福利
    python wps.py --page task_center  # 只执行任务中心
    python wps.py --page daily_benefits  # 只执行天天领福利
Author: Angus (assisted by Trae)
Date: 2026-10-28
"""

import argparse
import base64
import json
import logging
import random
import string
import sys
import time
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

import requests
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

# ---------------------------------------------------------------------------
# 路径 & 共享模块导入（对齐 script/workbuddy、script/trae 的布局）
# ---------------------------------------------------------------------------
# 本文件位于 <project>/script/wps/ 目录
script_dir = Path(__file__).resolve().parent
script_root = script_dir.parent          # <project>/script/
project_root = script_dir.parent.parent  # <project>/
sys.path.insert(0, str(project_root))    # notification 在此
sys.path.insert(0, str(script_root))     # _shared 在此

from _shared import (
    apply_startup_jitter,
    build_summary,
    create_session,
    load_platform_accounts,
    request_with_retry,
    run_accounts,
    send_summary_notification,
    setup_logger,
)
from notification import NotificationSound


# ---------------------------------------------------------------------------
# 通用工具函数（从三个脚本中去重合并）
# ---------------------------------------------------------------------------
AUTH_EXPIRED_KEYWORDS = ("Token已过期", "ErrNotLogin", "userNotLogin", "未登录", "请重新登录")


def is_auth_expired(message) -> bool:
    """判断消息是否表示登录态失效（原三处重复定义合并为一处）。"""
    return any(keyword in str(message) for keyword in AUTH_EXPIRED_KEYWORDS)


def parse_cookies(cookie_str: str) -> dict[str, str]:
    """解析 Cookie 字符串为字典（WPSAPI / DailyBenefitsAPI 共用）。"""
    cookies: dict[str, str] = {}
    for item in cookie_str.split("; "):
        if "=" in item:
            key, value = item.split("=", 1)
            cookies[key] = value
    return cookies


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 日志辅助（原 logging_utils.py）
# ---------------------------------------------------------------------------
class ContextAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple[str, MutableMapping[str, Any]]:
        extra: Mapping[str, Any] = kwargs.get("extra", {})
        merged_extra = dict(self.extra)
        merged_extra.update(extra)
        kwargs["extra"] = merged_extra
        if merged_extra:
            prefix = "".join(f"[{value}]" for value in merged_extra.values() if value)
            if prefix:
                msg = f"{prefix} {msg}"
        return msg, kwargs


def bind_logger(logger, **context) -> ContextAdapter:
    if isinstance(logger, ContextAdapter):
        merged_context = dict(logger.extra)
        merged_context.update(context)
        return ContextAdapter(logger.logger, merged_context)
    return ContextAdapter(logger, context)


def log_banner(logger, title: str) -> None:
    line = "═" * 38
    logger.info(line)
    logger.info(title)
    logger.info(line)


def log_account_start(logger, account_name: str) -> None:
    line = "━" * 32
    logger.info(line)
    logger.info("👤 账号：%s", account_name)
    logger.info(line)


def log_account_end(logger, account_name: str, success: bool = True) -> None:
    icon = "✅" if success else "❌"
    logger.info("%s %s 完成", icon, account_name)


def log_page_switch(logger, page_name: str) -> None:
    logger.info("📄 页面：%s", page_name)


def log_startup(logger, total_accounts: int) -> None:
    logger.info("📦 WPS 任务启动，共 %s 个账号", total_accounts)


def log_task_result(logger, label: str, result: str) -> None:
    logger.info("  %-10s → %s", label, result)


# ---------------------------------------------------------------------------
# WPSEncryption / WPSAPI（原 api.py）
# ---------------------------------------------------------------------------
_wps_api_logger = setup_logger("wps.api", level=logging.WARNING)


class WPSEncryption:
    @staticmethod
    def generate_aes_key(length: int = 32) -> str:
        chars = string.ascii_lowercase + string.digits
        random_part = "".join(random.choice(chars) for _ in range(length - 10))
        timestamp_part = str(int(time.time()))
        return random_part + timestamp_part

    @staticmethod
    def aes_encrypt(plain_text: str, aes_key: str) -> str:
        key_bytes = aes_key.encode("utf-8")
        key_padded = key_bytes + b"\x00" * (32 - len(key_bytes))
        iv = aes_key[:16].encode("utf-8")
        cipher = AES.new(key_padded, AES.MODE_CBC, iv)
        plain_bytes = plain_text.encode("utf-8")
        padded_data = pad(plain_bytes, AES.block_size)
        encrypted = cipher.encrypt(padded_data)
        return base64.b64encode(encrypted).decode("utf-8")

    @staticmethod
    def rsa_encrypt(plain_text: str, public_key_pem: str) -> str:
        public_key = RSA.import_key(public_key_pem)
        cipher = PKCS1_v1_5.new(public_key)
        encrypted = cipher.encrypt(plain_text.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")


class WPSAPI:
    """WPS 任务中心 API（原 api.py 的 WPSAPI）"""

    def __init__(self, cookies: str, user_agent: Optional[str] = None):
        self.cookies = parse_cookies(cookies)
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        )
        self.base_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "pragma": "no-cache",
            "cache-control": "no-cache",
            "sec-ch-ua-platform": '"macOS"',
            "sec-ch-ua": '"Chromium";v="142", "Brave";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-gpc": "1",
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": "https://personal-act.wps.cn",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://personal-act.wps.cn/",
            "priority": "u=1, i",
        }
        self.encrypt_key_url = "https://personal-bus.wps.cn/sign_in/v1/encrypt/key"
        self.sign_in_url = "https://personal-bus.wps.cn/sign_in/v1/sign_in"
        self.lottery_url = "https://personal-act.wps.cn/activity-rubik/activity/component_action"
        self.user_info_url = "https://personal-act.wps.cn/activity-rubik/activity/page_info"
        self.encryption = WPSEncryption()
        self.session = create_session()

    # ----- 用户信息 -----
    def get_user_info(
        self,
        activity_number: str = "HD2025031821201822",
        page_number: str = "YM2025041617143388",
    ) -> dict:
        _wps_api_logger.info("正在获取用户个人信息...")
        try:
            headers = self.base_headers.copy()
            headers["referer"] = (
                f"https://personal-act.wps.cn/rubik2/portal/{activity_number}/{page_number}"
                "?cs_from=&mk_key=JkVKsOtv4aCLMdNdAKwUGoz9tfKeFZVKyjEe&position=mac_grzx_sign"
            )
            headers["sec-fetch-site"] = "same-origin"
            headers["sec-fetch-mode"] = "cors"
            headers["sec-fetch-dest"] = "empty"
            response = request_with_retry(
                self.session,
                "GET",
                self.user_info_url,
                headers=headers,
                cookies=self.cookies,
                params={"activity_number": activity_number, "page_number": page_number},
            )
            response.raise_for_status()
            result = response.json()
            if result.get("result") == "ok" and "data" in result:
                user_info = {
                    "success": True,
                    "lottery_times": 0,
                    "points": 0,
                    "advent_points": 0,
                    "lottery_component_number": "",
                    "lottery_component_node_id": "",
                    "points_component_number": "",
                    "points_component_node_id": "",
                    "raw_data": result,
                }
                for item in result.get("data", []):
                    item_type = item.get("type")
                    if item_type == 45 and "lottery_v2" in item:
                        lottery_v2 = item.get("lottery_v2", {})
                        for lottery_session in lottery_v2.get("lottery_list", []):
                            if lottery_session.get("session_status") == "IN_PROGRESS":
                                user_info["lottery_times"] = lottery_session.get("times", 0)
                                user_info["lottery_component_number"] = item.get("number", "")
                                user_info["lottery_component_node_id"] = item.get("component_node_id", "")
                                break
                    elif item_type == 36 and "task_center_user_info" in item:
                        task_center = item.get("task_center_user_info", {})
                        user_info["points"] = task_center.get("integral", 0)
                        user_info["advent_points"] = task_center.get("advent_integral", 0)
                        user_info["points_component_number"] = item.get("number", "")
                        user_info["points_component_node_id"] = item.get("component_node_id", "")
                return user_info
            return {"success": False, "error": result.get("msg", "未知错误")}
        except requests.exceptions.RequestException as exc:
            return {"success": False, "error": f"网络请求失败: {exc}"}
        except Exception as exc:
            return {"success": False, "error": f"未知错误: {exc}"}

    # ----- 加密 & 签到 -----
    def get_encrypt_key(self) -> dict:
        _wps_api_logger.info("正在获取RSA加密公钥...")
        try:
            response = request_with_retry(
                self.session, "GET", self.encrypt_key_url,
                headers=self.base_headers, cookies=self.cookies,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("result") == "ok" and "data" in result:
                return {"success": True, "public_key": result["data"]}
            return {"success": False, "error": result.get("msg", "未知错误")}
        except requests.exceptions.RequestException as exc:
            return {"success": False, "error": f"网络请求失败: {exc}"}
        except Exception as exc:
            return {"success": False, "error": f"未知错误: {exc}"}

    def generate_crypto_data(self, public_key_base64: str, user_id: int, platform: int = 64) -> dict:
        public_key_pem = base64.b64decode(public_key_base64).decode("utf-8")
        aes_key = self.encryption.generate_aes_key(32)
        plain_data = json.dumps({"user_id": user_id, "platform": platform}, separators=(",", ":"))
        encrypt_data = self.encryption.aes_encrypt(plain_data, aes_key)
        token = self.encryption.rsa_encrypt(aes_key, public_key_pem)
        return {"extra": encrypt_data, "token": token, "aesKey": aes_key}

    def sign_in(self, user_id: int) -> dict:
        _wps_api_logger.info("开始签到...")
        try:
            key_result = self.get_encrypt_key()
            if not key_result["success"]:
                return {"success": False, "error": f"获取公钥失败: {key_result['error']}"}
            crypto_result = self.generate_crypto_data(key_result["public_key"], user_id)
            headers = self.base_headers.copy()
            headers["token"] = crypto_result["token"]
            response = request_with_retry(
                self.session,
                "POST",
                self.sign_in_url,
                headers=headers,
                cookies=self.cookies,
                json={
                    "encrypt": True,
                    "extra": crypto_result["extra"],
                    "pay_origin": "pc_ucs_rwzx_sign",
                },
            )
            if response.status_code == 200:
                resp_data = response.json()
                if resp_data.get("result") == "ok":
                    return {"success": True, "data": resp_data.get("data", {})}
                error_msg = resp_data.get("msg", "未知错误")
                error_code = resp_data.get("code")
                ext_msg = resp_data.get("ext_msg", "")
                if error_code == 2000000 and ext_msg == "userNotLogin":
                    return {"success": False, "error": "Token已过期，请重新登录", "error_type": "token_expired"}
                if error_msg == "has sign":
                    return {"success": True, "already_signed": True, "data": resp_data.get("data", {}), "message": "今日已签到"}
                return {"success": False, "error": error_msg}
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except requests.exceptions.RequestException as exc:
            return {"success": False, "error": f"网络请求失败: {exc}"}
        except Exception as exc:
            return {"success": False, "error": f"未知错误: {exc}"}

    # ----- 抽奖 -----
    def lottery(
        self,
        activity_number: str = "HD2025031821201822",
        page_number: str = "YM2025041617143388",
        component_number: str = "ZJ2025092916515917",
        component_node_id: str = "FN1762346087mJlk",
        session_id: int = 2,
    ) -> dict:
        _wps_api_logger.info("正在执行抽奖...")
        try:
            headers = self.base_headers.copy()
            headers["referer"] = (
                f"https://personal-act.wps.cn/rubik2/portal/{activity_number}/{page_number}"
                "?cs_from=&mk_key=JkVKsOtv4aCLMdNdAKwUGoz9tfKeFZVKyjEe&position=mac_grzx_sign"
            )
            headers["sec-fetch-site"] = "same-origin"
            headers["sec-fetch-mode"] = "cors"
            headers["sec-fetch-dest"] = "empty"
            data = {
                "component_uniq_number": {
                    "activity_number": activity_number,
                    "page_number": page_number,
                    "component_number": component_number,
                    "component_node_id": component_node_id,
                    "filter_params": {
                        "cs_from": "",
                        "mk_key": "JkVKsOtv4aCLMdNdAKwUGoz9tfKeFZVKyjEe",
                        "position": "mac_grzx_sign",
                    },
                },
                "component_type": 45,
                "component_action": "lottery_v2.exec",
                "lottery_v2": {"session_id": session_id},
            }
            response = request_with_retry(
                self.session, "POST", self.lottery_url,
                headers=headers, cookies=self.cookies, json=data,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("result") == "ok" and "data" in result:
                lottery_v2 = result.get("data", {}).get("lottery_v2", {})
                if lottery_v2.get("success"):
                    return {
                        "success": True,
                        "prize_name": lottery_v2.get("reward_name", "未知"),
                        "reward_type": lottery_v2.get("reward_type", ""),
                        "order_id": lottery_v2.get("order_id", ""),
                        "reward_id": lottery_v2.get("reward_id", 0),
                        "img": lottery_v2.get("img", ""),
                        "data": lottery_v2,
                    }
                error_code = lottery_v2.get("error_code", 0)
                send_msg = lottery_v2.get("send_msg", "抽奖失败")
                return {"success": False, "error": send_msg, "error_code": error_code}
            error_msg = result.get("msg", "未知错误")
            error_code = result.get("code")
            ext_msg = result.get("ext_msg", "")
            if error_code == 2000000 and ext_msg == "userNotLogin":
                return {"success": False, "error": "Token已过期，请重新登录", "error_type": "token_expired"}
            return {"success": False, "error": error_msg}
        except requests.exceptions.RequestException as exc:
            return {"success": False, "error": f"网络请求失败: {exc}"}
        except Exception as exc:
            return {"success": False, "error": f"未知错误: {exc}"}


# ---------------------------------------------------------------------------
# benefit_entry（原 benefit_entry.py）
# ---------------------------------------------------------------------------
TARGET_POSITIONS = ("pc_nvc_activity_fuli",)
TARGET_TITLES = {"福利中心", "天天领福利"}


def discover_benefit_portal(
    market_activity_getter: Callable[[dict[str, Any]], dict[str, Any]],
    channels: list[dict[str, Any]],
    logger,
) -> dict[str, Any]:
    raw_candidates: list[dict[str, str]] = []
    channel_errors: list[str] = []
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
        len(raw_candidates), len(parsed_candidates),
        extra={"step": "入口发现"},
    )

    if not parsed_candidates:
        failure: dict[str, Any] = {"success": False, "error": "未找到福利中心活动入口"}
        if auth_expired:
            failure["error_type"] = "token_expired"
        elif channel_errors:
            failure["error"] = f"未找到福利中心活动入口（渠道请求失败: {'; '.join(channel_errors)}）"
        return failure

    selected = _select_benefit_portal(parsed_candidates)
    if selected is None:
        found_positions = sorted({
            c.get("position", "") for c in parsed_candidates if c.get("position")
        })
        return {
            "success": False,
            "error": (
                "未匹配到福利中心入口（期望 position=pc_nvc_activity_fuli）"
                f"，实际发现: {', '.join(found_positions) or '无 position'}"
            ),
        }
    return selected


def _parse_portal_candidates(raw_candidates: list[dict[str, str]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
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


def _select_benefit_portal(parsed_candidates: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
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


def _collect_portal_candidates(node: Any, candidates: list[dict[str, str]]) -> None:
    if isinstance(node, dict):
        link = node.get("link")
        if isinstance(link, str) and "/rubik2/portal/" in link:
            title = node.get("title")
            candidates.append({
                "title": title if isinstance(title, str) else "",
                "link": link,
                "pic": node.get("pic") or node.get("img") or "",
            })
        for value in node.values():
            _collect_portal_candidates(value, candidates)
    elif isinstance(node, list):
        for item in node:
            _collect_portal_candidates(item, candidates)


def _parse_portal_link(link: str) -> dict[str, Any]:
    try:
        parsed = urlparse(link)
        path_parts = [p for p in parsed.path.split("/") if p]
        portal_index = path_parts.index("portal")
        activity_number = path_parts[portal_index + 1]
        page_number = path_parts[portal_index + 2]
        query_params = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
        return {
            "success": True,
            "link": link,
            "activity_number": activity_number,
            "page_number": page_number,
            "filter_params": query_params,
        }
    except (ValueError, IndexError) as exc:
        return {"success": False, "error": f"活动链接解析失败: {exc}"}


# ---------------------------------------------------------------------------
# DailyBenefitsAPI（原 daily_benefits.py）
# ---------------------------------------------------------------------------
class DailyBenefitsAPI:
    """WPS 天天领福利活动接口封装"""

    MARKET_ACTIVITY_URL = "https://tiance.wps.cn/dce/exec/api/market/activity"
    PAGE_INFO_URL = "https://personal-act.wps.cn/activity-rubik/activity/page_info"
    COMPONENT_ACTION_URL = "https://personal-act.wps.cn/activity-rubik/activity/component_action"

    MARKET_ACTIVITY_CHANNELS = [
        {"channel_code": "AUTOPCHYZXYYHD3737", "platform": 8, "version": "0.0.0.0"},
        {"channel_code": "HYGW5004,GWHD5002", "version": "", "platform": 8, "device": 1, "hdid": "", "filter_info": {}},
    ]

    def __init__(self, cookies: str, user_agent: Optional[str] = None):
        self.cookies = parse_cookies(cookies)
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        )
        self.base_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json; charset=UTF-8",
            "sec-ch-ua-platform": '"macOS"',
            "sec-ch-ua": '"Not:A-Brand";v="99", "Brave";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-gpc": "1",
            "accept-language": "zh-CN,zh;q=0.7",
            "origin": "https://personal-act.wps.cn",
            "referer": "https://personal-act.wps.cn/",
            "priority": "u=1, i",
        }
        self.session = create_session()
        self.logger = bind_logger(setup_logger("wps.daily_benefits.api"), page=DailyBenefitsTasks.page_name)

    # ----- 通用 -----
    @staticmethod
    def _extract_error_message(result: dict[str, Any]) -> str:
        return result.get("msg") or result.get("message") or result.get("error") or "未知错误"

    @staticmethod
    def _normalize_server_time(server_time: Any) -> int:
        try:
            timestamp = int(server_time)
        except (TypeError, ValueError):
            return 0
        if timestamp > 10 ** 12:
            timestamp //= 1000
        return timestamp

    @classmethod
    def _resolve_sign_date(cls, item: dict[str, Any], sign_records: list[dict[str, Any]]) -> str:
        server_time = cls._normalize_server_time(item.get("server_time", 0))
        if server_time:
            return time.strftime("%Y-%m-%d", time.localtime(server_time))
        today = time.strftime("%Y-%m-%d")
        if any(r.get("sign_date") == today for r in sign_records):
            return today
        if sign_records:
            return sign_records[0].get("sign_date", today)
        return today

    @staticmethod
    def _count_signed_days(sign_records: list[dict[str, Any]]) -> int:
        return sum(1 for r in sign_records if r.get("sign_status") == "signed")

    def _build_failure_result(self, payload: dict[str, Any], default_error: str = "未知错误") -> dict[str, Any]:
        error_message = self._extract_error_message(payload) or default_error
        result: dict[str, Any] = {"success": False, "error": error_message}
        if payload.get("code") == 2000000 or payload.get("ext_msg") == "userNotLogin" or is_auth_expired(error_message):
            result["error_type"] = "token_expired"
        return result

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        request_headers = self.base_headers.copy()
        if headers:
            request_headers.update(headers)
        try:
            response = request_with_retry(
                self.session, method, url,
                headers=request_headers, cookies=self.cookies, params=params, json=json_data,
            )
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except requests.exceptions.RequestException as exc:
            return {"success": False, "error": f"网络请求失败: {exc}"}
        except ValueError as exc:
            return {"success": False, "error": f"响应解析失败: {exc}"}

    # ----- 入口 & 页面 -----
    def get_market_activity(self, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        request_payload = payload if payload is not None else self.MARKET_ACTIVITY_CHANNELS[0]
        result = self._request(
            "POST", self.MARKET_ACTIVITY_URL,
            headers={"sec-fetch-site": "same-site", "sec-fetch-mode": "cors", "sec-fetch-dest": "empty"},
            json_data=request_payload,
        )
        if not result["success"]:
            return result
        payload_data = result["data"]
        if payload_data.get("result") != "ok":
            return self._build_failure_result(payload_data)
        return {"success": True, "data": payload_data}

    def get_benefit_portal(self) -> dict[str, Any]:
        return discover_benefit_portal(self.get_market_activity, self.MARKET_ACTIVITY_CHANNELS, self.logger)

    def get_page_info(self, portal_info: dict[str, Any]) -> dict[str, Any]:
        self.logger.info("获取页面活动信息", extra={"step": "页面信息"})
        result = self._request(
            "GET", self.PAGE_INFO_URL,
            headers={
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": portal_info["link"],
            },
            params={
                "activity_number": portal_info["activity_number"],
                "page_number": portal_info["page_number"],
                "filter_params": json.dumps(
                    portal_info.get("filter_params", {}), ensure_ascii=False, separators=(",", ":")
                ),
            },
        )
        if not result["success"]:
            return result
        payload = result["data"]
        if payload.get("result") != "ok":
            return self._build_failure_result(payload)
        return {"success": True, "data": payload}

    # ----- 会员免费试用 -----
    def get_member_trial_info(self, page_info: dict[str, Any]) -> dict[str, Any]:
        data_list = page_info.get("data", [])
        fallback_item: Optional[dict[str, Any]] = None
        for item in data_list:
            if not isinstance(item, dict):
                continue
            divide_prize = item.get("divide_prize")
            if not isinstance(divide_prize, dict):
                continue
            details = divide_prize.get("divide_prize_details") or []
            if not details:
                continue
            if fallback_item is None:
                fallback_item = item
            if any("会员" in str(detail.get("title", "")) for detail in details):
                return {
                    "success": True,
                    "component_number": item.get("number", ""),
                    "component_node_id": item.get("component_node_id", ""),
                    "remain_times": divide_prize.get("remain_times", 0),
                    "latest_result": divide_prize.get("latest_result", ""),
                    "join_reach_limit": divide_prize.get("join_reach_limit", False),
                    "details": details,
                    "raw_data": divide_prize,
                }
        if fallback_item is not None:
            divide_prize = fallback_item.get("divide_prize", {})
            return {
                "success": True,
                "component_number": fallback_item.get("number", ""),
                "component_node_id": fallback_item.get("component_node_id", ""),
                "remain_times": divide_prize.get("remain_times", 0),
                "latest_result": divide_prize.get("latest_result", ""),
                "join_reach_limit": divide_prize.get("join_reach_limit", False),
                "details": divide_prize.get("divide_prize_details") or [],
                "raw_data": divide_prize,
            }
        return {"success": False, "error": "未找到会员免费试用模块"}

    def sign_up_member_trial(
        self, portal_info: dict[str, Any], component_number: str,
        component_node_id: str, cycle_id: str, session_id: str,
    ) -> dict[str, Any]:
        csrf_token = self.cookies.get("act_csrf_token") or self.cookies.get("csrf")
        if not csrf_token:
            return {"success": False, "error": "Cookie 中缺少 act_csrf_token/csrf，无法提交试用申请"}
        payload = {
            "component_uniq_number": {
                "activity_number": portal_info["activity_number"],
                "page_number": portal_info["page_number"],
                "component_number": component_number,
                "component_node_id": component_node_id,
                "filter_params": {},
            },
            "component_type": 32,
            "component_action": "divide_prize.sign_up",
            "divide_prize": {"cycle_id": cycle_id, "session_id": session_id},
        }
        result = self._request(
            "POST", self.COMPONENT_ACTION_URL,
            headers={
                "Content-Type": "application/json",
                "x-act-csrf-token": csrf_token,
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": (
                    f"https://personal-act.wps.cn/rubik2/portal/"
                    f"{portal_info['activity_number']}/{portal_info['page_number']}"
                ),
            },
            json_data=payload,
        )
        if not result["success"]:
            return result
        payload_data = result["data"]
        if payload_data.get("result") != "ok":
            return self._build_failure_result(payload_data)
        divide_prize = payload_data.get("data", {}).get("divide_prize", {})
        if divide_prize.get("success"):
            return {"success": True, "reason": divide_prize.get("reason", ""), "data": divide_prize}
        failure_result = {
            "success": False,
            "error": divide_prize.get("reason") or "试用申请失败",
            "data": divide_prize,
        }
        if is_auth_expired(failure_result["error"]):
            failure_result["error_type"] = "token_expired"
        return failure_result

    # ----- 打卡免费领会员 -----
    def get_fragment_collect_info(self, page_info: dict[str, Any]) -> dict[str, Any]:
        data_list = page_info.get("data", [])
        fallback_item: Optional[dict[str, Any]] = None
        for item in data_list:
            if not isinstance(item, dict):
                continue
            fragment_collect = item.get("fragment_collect")
            if not isinstance(fragment_collect, dict):
                continue
            sign_records = fragment_collect.get("sign_records") or []
            if not sign_records:
                continue
            if fallback_item is None:
                fallback_item = item
            sign_date = self._resolve_sign_date(item, sign_records)
            today_record = next((r for r in sign_records if r.get("sign_date") == sign_date), None)
            sign_series_id = fragment_collect.get("sign_series_id", "")
            if item.get("type") == 42 or today_record is not None:
                return {
                    "success": True,
                    "component_number": item.get("number", ""),
                    "component_node_id": item.get("component_node_id", ""),
                    "sign_date": sign_date,
                    "sign_series_id": sign_series_id,
                    "is_new_sign_series": not bool(sign_series_id),
                    "is_signed": (today_record or {}).get("sign_status") == "signed",
                    "today_record": today_record or {},
                    "signed_days": self._count_signed_days(sign_records),
                    "sign_records": sign_records,
                    "raw_data": fragment_collect,
                }
        if fallback_item is not None:
            fragment_collect = fallback_item.get("fragment_collect", {})
            sign_records = fragment_collect.get("sign_records") or []
            sign_date = self._resolve_sign_date(fallback_item, sign_records)
            today_record = next((r for r in sign_records if r.get("sign_date") == sign_date), None)
            sign_series_id = fragment_collect.get("sign_series_id", "")
            return {
                "success": True,
                "component_number": fallback_item.get("number", ""),
                "component_node_id": fallback_item.get("component_node_id", ""),
                "sign_date": sign_date,
                "sign_series_id": sign_series_id,
                "is_new_sign_series": not bool(sign_series_id),
                "is_signed": (today_record or {}).get("sign_status") == "signed",
                "today_record": today_record or {},
                "signed_days": self._count_signed_days(sign_records),
                "sign_records": sign_records,
                "raw_data": fragment_collect,
            }
        return {"success": False, "error": "未找到打卡免费领会员模块"}

    def sign_in_fragment_collect(
        self, portal_info: dict[str, Any], component_number: str,
        component_node_id: str, sign_date: str, sign_series_id: str, is_new_sign_series: bool,
    ) -> dict[str, Any]:
        csrf_token = self.cookies.get("act_csrf_token") or self.cookies.get("csrf")
        if not csrf_token:
            return {"success": False, "error": "Cookie 中缺少 act_csrf_token/csrf，无法执行打卡签到"}
        payload = {
            "component_uniq_number": {
                "activity_number": portal_info["activity_number"],
                "page_number": portal_info["page_number"],
                "component_number": component_number,
                "component_node_id": component_node_id,
                "filter_params": portal_info.get("filter_params", {}),
            },
            "component_type": 42,
            "component_action": "fragment_collect.sign_in",
            "fragment_collect": {
                "sign_date": sign_date,
                "series_id": sign_series_id,
                "is_new_sign_series": is_new_sign_series,
            },
        }
        result = self._request(
            "POST", self.COMPONENT_ACTION_URL,
            headers={
                "Content-Type": "application/json",
                "x-act-csrf-token": csrf_token,
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": portal_info["link"],
            },
            json_data=payload,
        )
        if not result["success"]:
            return result
        payload_data = result["data"]
        if payload_data.get("result") != "ok":
            return self._build_failure_result(payload_data)
        fragment_collect = payload_data.get("data", {}).get("fragment_collect", {})
        if fragment_collect.get("success"):
            return {"success": True, "reason": fragment_collect.get("reason", ""), "data": fragment_collect}
        failure_result = {
            "success": False,
            "error": fragment_collect.get("reason") or "打卡签到失败",
            "data": fragment_collect,
        }
        if is_auth_expired(failure_result["error"]):
            failure_result["error_type"] = "token_expired"
        return failure_result

    # ----- 天天抽奖 -----
    @staticmethod
    def _pick_lottery_session(lottery_list: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        for session in lottery_list:
            if (
                session.get("session_status") == "IN_PROGRESS"
                and session.get("stock_status") in {"IN_STOCK", "", None}
            ):
                return session
        for session in lottery_list:
            if session.get("session_status") == "IN_PROGRESS":
                return session
        return lottery_list[0] if lottery_list else None

    def get_daily_lottery_info(self, page_info: dict[str, Any]) -> dict[str, Any]:
        data_list = page_info.get("data", [])
        fallback_item: Optional[dict[str, Any]] = None
        fallback_session: Optional[dict[str, Any]] = None
        for item in data_list:
            if not isinstance(item, dict):
                continue
            lottery_v2 = item.get("lottery_v2")
            if not isinstance(lottery_v2, dict):
                continue
            lottery_list = lottery_v2.get("lottery_list") or []
            if not lottery_list:
                continue
            selected_session = self._pick_lottery_session(lottery_list)
            if selected_session is None:
                continue
            if fallback_item is None:
                fallback_item = item
                fallback_session = selected_session
            if selected_session.get("session_status") == "IN_PROGRESS":
                sign_day = safe_int(selected_session.get("times", 0))
                return {
                    "success": True,
                    "component_number": item.get("number", ""),
                    "component_node_id": item.get("component_node_id", ""),
                    "session_id": selected_session.get("session_id"),
                    "session_name": selected_session.get("session_name", ""),
                    "remain_times": sign_day,
                    "sign_day": sign_day,
                    "stock_status": selected_session.get("stock_status", ""),
                    "share_times": lottery_v2.get("share_times", False),
                    "share_times_count": lottery_v2.get("share_times_count", 0),
                    "lottery_reward_list": selected_session.get("lottery_reward_list", []),
                    "raw_data": lottery_v2,
                }
        if fallback_item is not None and fallback_session is not None:
            lottery_v2 = fallback_item.get("lottery_v2", {})
            sign_day = safe_int(fallback_session.get("times", 0))
            return {
                "success": True,
                "component_number": fallback_item.get("number", ""),
                "component_node_id": fallback_item.get("component_node_id", ""),
                "session_id": fallback_session.get("session_id"),
                "session_name": fallback_session.get("session_name", ""),
                "remain_times": 0,
                "sign_day": sign_day,
                "stock_status": fallback_session.get("stock_status", ""),
                "share_times": lottery_v2.get("share_times", False),
                "share_times_count": lottery_v2.get("share_times_count", 0),
                "lottery_reward_list": fallback_session.get("lottery_reward_list", []),
                "raw_data": lottery_v2,
            }
        return {"success": False, "error": "未找到天天抽奖模块"}

    def exec_daily_lottery(
        self, portal_info: dict[str, Any], component_number: str,
        component_node_id: str, session_id: Any,
    ) -> dict[str, Any]:
        csrf_token = self.cookies.get("act_csrf_token") or self.cookies.get("csrf")
        if not csrf_token:
            return {"success": False, "error": "Cookie 中缺少 act_csrf_token/csrf，无法执行抽奖"}
        payload = {
            "component_uniq_number": {
                "activity_number": portal_info["activity_number"],
                "page_number": portal_info["page_number"],
                "component_number": component_number,
                "component_node_id": component_node_id,
                "filter_params": portal_info.get("filter_params", {}),
            },
            "component_type": 45,
            "component_action": "lottery_v2.exec",
            "lottery_v2": {"session_id": session_id},
        }
        result = self._request(
            "POST", self.COMPONENT_ACTION_URL,
            headers={
                "Content-Type": "application/json",
                "x-act-csrf-token": csrf_token,
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": portal_info["link"],
            },
            json_data=payload,
        )
        if not result["success"]:
            return result
        payload_data = result["data"]
        if payload_data.get("result") != "ok":
            return self._build_failure_result(payload_data)
        lottery_v2 = payload_data.get("data", {}).get("lottery_v2", {})
        if lottery_v2.get("success"):
            return {
                "success": True,
                "reward_name": lottery_v2.get("reward_name", "未知奖品"),
                "reward_type": lottery_v2.get("reward_type", ""),
                "reward_id": lottery_v2.get("reward_id", 0),
                "order_id": lottery_v2.get("order_id", ""),
                "img": lottery_v2.get("img", ""),
                "data": lottery_v2,
            }
        failure_result = {
            "success": False,
            "error": lottery_v2.get("send_msg") or "抽奖失败",
            "error_code": lottery_v2.get("error_code", 0),
            "data": lottery_v2,
        }
        if is_auth_expired(failure_result["error"]):
            failure_result["error_type"] = "token_expired"
        return failure_result

    # ----- 第7天奖励 -----
    def receive_daily_lottery_reward(
        self, portal_info: dict[str, Any], component_number: str,
        component_node_id: str, sign_series_id: str,
    ) -> dict[str, Any]:
        csrf_token = self.cookies.get("act_csrf_token") or self.cookies.get("csrf")
        if not csrf_token:
            return {"success": False, "error": "Cookie 中缺少 act_csrf_token/csrf，无法领取第7天奖励"}
        payload = {
            "component_uniq_number": {
                "activity_number": portal_info["activity_number"],
                "page_number": portal_info["page_number"],
                "component_number": component_number,
                "component_node_id": component_node_id,
                "filter_params": portal_info.get("filter_params", {}),
            },
            "component_type": 42,
            "component_action": "fragment_collect.receive",
            "fragment_collect": {"series_id": sign_series_id},
        }
        result = self._request(
            "POST", self.COMPONENT_ACTION_URL,
            headers={
                "Content-Type": "application/json",
                "x-act-csrf-token": csrf_token,
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": portal_info["link"],
            },
            json_data=payload,
        )
        if not result["success"]:
            return result
        payload_data = result["data"]
        if payload_data.get("result") != "ok":
            return self._build_failure_result(payload_data)
        action_data = payload_data.get("data", {}).get("fragment_collect", {})
        if not action_data:
            action_data = payload_data.get("data", {}).get("lottery_v2", {})
        if action_data.get("success"):
            return {
                "success": True,
                "reason": action_data.get("reason", ""),
                "reward_name": action_data.get("reward_name", ""),
                "data": action_data,
            }
        error_message = (
            action_data.get("reason")
            or action_data.get("send_msg")
            or action_data.get("message")
            or "领取第7天奖励失败"
        )
        failure_result: dict[str, Any] = {
            "success": False,
            "error": error_message,
            "data": action_data,
            "payload_summary": {
                "component_type": payload["component_type"],
                "component_action": payload["component_action"],
                "component_number": component_number,
                "component_node_id": component_node_id,
                "sign_series_id": sign_series_id,
            },
        }
        if is_auth_expired(failure_result["error"]):
            failure_result["error_type"] = "token_expired"
        return failure_result


# ---------------------------------------------------------------------------
# DailyBenefitsTasks（原 daily_benefits.py）
# ---------------------------------------------------------------------------
class DailyBenefitsTasks:
    """天天领福利活动任务执行器"""

    page_name = "天天领福利"

    def __init__(
        self,
        config_path: str = None,
        enable_notification: bool = True,
        load_accounts: bool = True,
    ):
        if config_path is None:
            self.config_path = project_root / "config" / "token.json"
        else:
            self.config_path = Path(config_path)
        self.enable_notification = enable_notification
        self.logger = bind_logger(setup_logger("wps.daily_benefits"), page=self.page_name)
        self.accounts: list[dict[str, Any]] = []
        self.account_results: list[dict[str, Any]] = []
        if load_accounts:
            self._init_accounts()

    def _setup_logger(self):
        return self.logger

    @staticmethod
    def _is_broken_series_error(message: str) -> bool:
        text = str(message).lower()
        return "not in series" in text or "series records" in text

    def _init_accounts(self) -> None:
        self.accounts = load_platform_accounts("wps", self.config_path)

    @staticmethod
    def _sync_free_member_checkin_state(free_member_checkin: dict[str, Any], fragment_result: dict[str, Any]) -> None:
        today_record = fragment_result.get("today_record", {})
        free_member_checkin["sign_date"] = fragment_result.get("sign_date", "")
        free_member_checkin["sign_status"] = today_record.get("sign_status", "")
        free_member_checkin["reward_title"] = today_record.get("reward_title", "")
        free_member_checkin["signed_days"] = fragment_result.get("signed_days", 0)
        free_member_checkin["sign_series_id"] = fragment_result.get("sign_series_id", "")

    @staticmethod
    def _build_free_member_checkin_message(free_member_checkin: dict[str, Any], *, signed_now: bool = False) -> str:
        sign_date = free_member_checkin.get("sign_date", "")
        signed_days = free_member_checkin.get("signed_days", 0)
        reward_title = free_member_checkin.get("reward_title", "")
        sign_status = free_member_checkin.get("sign_status", "")
        if sign_status == "signed":
            day_text = f"连续第 {signed_days} 天" if signed_days else sign_date
            reward_text = f"，奖励: {reward_title}" if reward_title else ""
            if signed_now:
                return f"打卡免费领会员签到成功，{day_text}（{sign_date}）{reward_text}"
            return f"打卡免费领会员今日已签到，{day_text}（{sign_date}）{reward_text}"
        return f"打卡免费领会员待签到（{sign_date}）"

    @staticmethod
    def _summarize_lottery_item(index: int, item: dict[str, Any]) -> dict[str, Any]:
        lottery_v2 = item.get("lottery_v2") or {}
        lottery_list = lottery_v2.get("lottery_list") or []
        return {
            "index": index,
            "type": item.get("type"),
            "number": item.get("number", ""),
            "component_node_id": item.get("component_node_id", ""),
            "sessions": [
                {
                    "session_id": s.get("session_id", ""),
                    "session_name": s.get("session_name", ""),
                    "session_status": s.get("session_status", ""),
                    "stock_status": s.get("stock_status", ""),
                    "times": s.get("times", 0),
                    "reward_names": [r.get("reward_name", "") for r in s.get("lottery_reward_list", []) if r.get("reward_name")],
                }
                for s in lottery_list if isinstance(s, dict)
            ],
            "share_times": lottery_v2.get("share_times", False),
            "share_times_count": lottery_v2.get("share_times_count", 0),
        }

    @staticmethod
    def _summarize_fragment_item(index: int, item: dict[str, Any]) -> dict[str, Any]:
        fragment_collect = item.get("fragment_collect") or {}
        sign_records = fragment_collect.get("sign_records") or []
        return {
            "index": index,
            "type": item.get("type"),
            "number": item.get("number", ""),
            "component_node_id": item.get("component_node_id", ""),
            "sign_series_id": fragment_collect.get("sign_series_id", ""),
            "signed_days_from_records": DailyBenefitsAPI._count_signed_days(sign_records),
            "sign_records": [
                {
                    "sign_date": r.get("sign_date", ""),
                    "sign_status": r.get("sign_status", ""),
                    "reward_title": r.get("reward_title", ""),
                }
                for r in sign_records if isinstance(r, dict)
            ],
        }

    @classmethod
    def _build_page_diagnostics(
        cls, page_info: dict[str, Any],
        fragment_result: Optional[dict[str, Any]] = None,
        lottery_result: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        data_list = page_info.get("data", [])
        if not isinstance(data_list, list):
            data_list = []
        lottery_items = [
            cls._summarize_lottery_item(i, item)
            for i, item in enumerate(data_list)
            if isinstance(item, dict) and isinstance(item.get("lottery_v2"), dict)
        ]
        fragment_items = [
            cls._summarize_fragment_item(i, item)
            for i, item in enumerate(data_list)
            if isinstance(item, dict) and isinstance(item.get("fragment_collect"), dict)
        ]
        item_43 = data_list[43] if len(data_list) > 43 and isinstance(data_list[43], dict) else {}
        return {
            "data_count": len(data_list),
            "item_43": {
                "keys": list(item_43.keys()) if item_43 else [],
                "lottery_v2": cls._summarize_lottery_item(43, item_43) if item_43.get("lottery_v2") else {},
                "fragment_collect": cls._summarize_fragment_item(43, item_43) if item_43.get("fragment_collect") else {},
            },
            "fragment_result": {
                k: fragment_result.get(k) for k in ["success", "sign_date", "sign_series_id", "is_new_sign_series", "is_signed", "signed_days"]
            } if fragment_result else {},
            "lottery_result": {
                k: lottery_result.get(k) for k in ["success", "session_id", "session_name", "remain_times", "sign_day", "stock_status"]
            } if lottery_result else {},
            "fragment_items": fragment_items,
            "lottery_items": lottery_items,
        }

    @staticmethod
    def _format_diagnostics(diagnostics: dict[str, Any]) -> str:
        return json.dumps(diagnostics, ensure_ascii=False, default=str, separators=(",", ":"))

    # ----- 子流程 -----
    def _process_member_trial(self, api, portal_result, page_info, account_name, result):
        trial_logger = bind_logger(self.logger, account=account_name, step="会员试用")
        member_trial_result = api.get_member_trial_info(page_info)
        if not member_trial_result["success"]:
            message = member_trial_result["error"]
            result["member_trial"]["message"] = message
            return {"success": False, "message": message}

        details = member_trial_result["details"]
        remain_times = member_trial_result["remain_times"]
        join_reach_limit = member_trial_result["join_reach_limit"]
        candidates = [d for d in details if not d.get("has_join")]

        result["member_trial"]["remain_times"] = remain_times
        result["member_trial"]["candidates"] = [
            {
                "title": d.get("title", ""),
                "session_id": d.get("session_id", ""),
                "cycle_id": d.get("cycle_id", ""),
                "has_join": d.get("has_join", False),
                "stock": d.get("stock", 0),
            }
            for d in details
        ]

        if join_reach_limit:
            message = "会员免费试用今日申请次数已达上限"
            result["member_trial"]["message"] = message
            return {"success": True, "message": message}
        if remain_times <= 0:
            message = "会员免费试用无剩余申请次数"
            result["member_trial"]["message"] = message
            return {"success": True, "message": message}
        if not candidates:
            message = "会员免费试用已全部申请，无需重复提交"
            result["member_trial"]["message"] = message
            return {"success": True, "message": message}

        selected_candidates = candidates[:remain_times]
        trial_logger.info("剩余申请次数=%s，本次准备申请=%s 项", remain_times, len(selected_candidates))

        for index, candidate in enumerate(selected_candidates, start=1):
            if index > 1:
                time.sleep(random.uniform(1, 2))
            trial_logger.info("正在申请第 %s 项: %s", index, candidate.get("title", "未知试用"))
            sign_up_result = api.sign_up_member_trial(
                portal_info=portal_result,
                component_number=member_trial_result["component_number"],
                component_node_id=member_trial_result["component_node_id"],
                cycle_id=candidate["cycle_id"],
                session_id=candidate["session_id"],
            )
            attempt = {
                "title": candidate.get("title", ""),
                "session_id": candidate.get("session_id", ""),
                "cycle_id": candidate.get("cycle_id", ""),
                "success": sign_up_result["success"],
                "message": sign_up_result.get("reason") or sign_up_result.get("error") or "申请成功",
            }
            result["member_trial"]["attempts"].append(attempt)
            if sign_up_result["success"]:
                trial_logger.info("%s 申请成功", attempt["title"])
            else:
                trial_logger.error("%s 申请失败: %s", attempt["title"], attempt["message"])
                if sign_up_result.get("error_type") == "token_expired" or is_auth_expired(attempt["message"]):
                    result["auth_expired"] = True
                    result["member_trial"]["message"] = "Token已过期，请重新登录"
                    return {"success": False, "message": "Token已过期，请重新登录"}

        success_count = sum(1 for a in result["member_trial"]["attempts"] if a["success"])
        total_attempts = len(result["member_trial"]["attempts"])
        if total_attempts == 0:
            message, success = "未执行会员免费试用申请", True
        elif success_count == total_attempts:
            message, success = f"会员免费试用申请完成，成功 {success_count} 项", True
        elif success_count > 0:
            message, success = f"会员免费试用申请部分成功，成功 {success_count}/{total_attempts} 项", True
        else:
            message, success = f"会员免费试用申请失败，共尝试 {total_attempts} 项", False
        result["member_trial"]["message"] = message
        return {"success": success, "message": message}

    def _process_fragment_collect_sign_in(self, api, portal_result, page_info, account_name, result):
        checkin_logger = bind_logger(self.logger, account=account_name, step="打卡签到")
        fragment_result = api.get_fragment_collect_info(page_info)
        if not fragment_result["success"]:
            message = fragment_result["error"]
            result["free_member_checkin"]["message"] = message
            return {"success": False, "message": message, "refresh_page_info": False}

        self._sync_free_member_checkin_state(result["free_member_checkin"], fragment_result)
        if fragment_result["is_signed"]:
            message = self._build_free_member_checkin_message(result["free_member_checkin"])
            result["free_member_checkin"]["message"] = message
            return {"success": True, "message": message, "refresh_page_info": False, "signed_now": False}

        checkin_logger.info(
            "开始执行打卡签到，日期=%s, series_id=%s, is_new=%s",
            fragment_result["sign_date"], fragment_result.get("sign_series_id", ""),
            fragment_result.get("is_new_sign_series", True),
        )
        sign_in_result = api.sign_in_fragment_collect(
            portal_info=portal_result,
            component_number=fragment_result["component_number"],
            component_node_id=fragment_result["component_node_id"],
            sign_date=fragment_result["sign_date"],
            sign_series_id=fragment_result.get("sign_series_id", ""),
            is_new_sign_series=fragment_result.get("is_new_sign_series", True),
        )

        if not sign_in_result["success"] and self._is_broken_series_error(sign_in_result.get("error", "")):
            checkin_logger.info("检测到旧 series 已过期（%s），自动重新开启签到", sign_in_result.get("error", ""))
            result["free_member_checkin"]["restarted_series"] = True
            sign_in_result = api.sign_in_fragment_collect(
                portal_info=portal_result,
                component_number=fragment_result["component_number"],
                component_node_id=fragment_result["component_node_id"],
                sign_date="",
                sign_series_id=fragment_result.get("sign_series_id", ""),
                is_new_sign_series=True,
            )

        if sign_in_result["success"]:
            message = "打卡免费领会员签到成功，正在刷新签到状态"
            result["free_member_checkin"]["message"] = message
            return {"success": True, "message": message, "refresh_page_info": True, "signed_now": True}

        message = sign_in_result.get("error", "打卡签到失败")
        if sign_in_result.get("error_type") == "token_expired" or is_auth_expired(message):
            result["auth_expired"] = True
            message = "Token已过期，请重新登录"
        checkin_logger.info("打卡失败响应诊断: %s", self._format_diagnostics({
            "message": message,
            "response_data": sign_in_result.get("data", {}),
            "page_state": self._build_page_diagnostics(page_info, fragment_result=fragment_result),
        }))
        result["free_member_checkin"]["message"] = message
        return {"success": False, "message": message, "refresh_page_info": False}

    def _claim_daily_lottery_reward_if_ready(
        self, api, portal_result, page_info, account_name, result,
        *, force_claim: bool = False, fragment_result=None, include_skip_message: bool = False,
    ):
        claim_logger = bind_logger(self.logger, account=account_name, step="第7天奖励")
        reward_claim = result["daily_lottery"].setdefault("reward_claim", {"attempted": False, "success": False, "message": ""})
        lottery_result = api.get_daily_lottery_info(page_info)
        if not lottery_result["success"]:
            message = f"第7天奖励状态解析失败: {lottery_result['error']}"
            reward_claim["message"] = message
            return {"success": False, "message": message, "claimed": False}
        if fragment_result is None:
            fragment_result = api.get_fragment_collect_info(page_info)
        if not fragment_result["success"]:
            message = f"第7天奖励签到状态解析失败: {fragment_result['error']}"
            reward_claim["message"] = message
            return {"success": False, "message": message, "claimed": False}

        result["daily_lottery"]["sign_day"] = lottery_result.get("sign_day", 0)
        sign_day = lottery_result.get("sign_day", 0)
        if not force_claim and sign_day != 7:
            message = ""
            if include_skip_message and sign_day > 0:
                message = f"当前签到第 {sign_day} 天，未到第 7 天领取条件"
            return {"success": True, "message": message, "claimed": False}

        reward_claim["attempted"] = True
        claim_logger.info("当前签到第 7 天，开始领取奖励")
        receive_result = api.receive_daily_lottery_reward(
            portal_info=portal_result,
            component_number=fragment_result["component_number"],
            component_node_id=fragment_result["component_node_id"],
            sign_series_id=fragment_result.get("sign_series_id", ""),
        )
        if receive_result["success"]:
            reward_name = receive_result.get("reward_name", "")
            message = receive_result.get("reason") or (f"第7天奖励领取成功: {reward_name}" if reward_name else "第7天奖励领取成功")
            reward_claim["success"] = True
            reward_claim["message"] = message
            return {"success": True, "message": message, "claimed": True}

        message = receive_result.get("error", "第7天奖励领取失败")
        if receive_result.get("error_type") == "token_expired" or is_auth_expired(message):
            result["auth_expired"] = True
            message = "Token已过期，请重新登录"
        claim_logger.info("第7天奖励领取失败诊断: %s", self._format_diagnostics({
            "message": message,
            "response_data": receive_result.get("data", {}),
            "payload_summary": receive_result.get("payload_summary", {}),
        }))
        reward_claim["success"] = False
        reward_claim["message"] = message
        return {"success": False, "message": message, "claimed": False}

    def _process_daily_lottery_reward_claim(self, api, portal_result, account_name, result):
        claim_logger = bind_logger(self.logger, account=account_name, step="第7天奖励")
        reward_claim = result["daily_lottery"].setdefault("reward_claim", {"attempted": False, "success": False, "message": ""})

        refreshed_page_info_result = api.get_page_info(portal_result)
        if not refreshed_page_info_result["success"]:
            message = f"刷新签到天数失败: {refreshed_page_info_result['error']}"
            reward_claim["message"] = message
            return {"success": False, "message": message}

        refreshed_lottery_result = api.get_daily_lottery_info(refreshed_page_info_result["data"])
        if not refreshed_lottery_result["success"]:
            message = f"刷新后的签到天数解析失败: {refreshed_lottery_result['error']}"
            reward_claim["message"] = message
            return {"success": False, "message": message}
        refreshed_fragment_result = api.get_fragment_collect_info(refreshed_page_info_result["data"])
        if not refreshed_fragment_result["success"]:
            message = f"刷新后的领取组件解析失败: {refreshed_fragment_result['error']}"
            reward_claim["message"] = message
            return {"success": False, "message": message}

        sign_day = refreshed_lottery_result.get("sign_day", 0)
        result["daily_lottery"]["sign_day"] = sign_day
        signed_days = safe_int(refreshed_fragment_result.get("signed_days", 0))
        if signed_days < 7:
            if signed_days <= 0:
                return {"success": True, "message": ""}
            return {"success": True, "message": f"当前签到第 {signed_days} 天，未到第 7 天领取条件"}

        reward_claim["attempted"] = True
        claim_logger.info("当前签到第 7 天，开始领取奖励")
        receive_result = api.receive_daily_lottery_reward(
            portal_info=portal_result,
            component_number=refreshed_fragment_result["component_number"],
            component_node_id=refreshed_fragment_result["component_node_id"],
            sign_series_id=refreshed_fragment_result.get("sign_series_id", ""),
        )
        if receive_result["success"]:
            reward_name = receive_result.get("reward_name", "")
            message = receive_result.get("reason") or (f"第7天奖励领取成功: {reward_name}" if reward_name else "第7天奖励领取成功")
            reward_claim["success"] = True
            reward_claim["message"] = message
            return {"success": True, "message": message}

        message = receive_result.get("error", "第7天奖励领取失败")
        if receive_result.get("error_type") == "token_expired" or is_auth_expired(message):
            result["auth_expired"] = True
            message = "Token已过期，请重新登录"
        claim_logger.info("第7天奖励领取失败诊断: %s", self._format_diagnostics({
            "message": message,
            "response_data": receive_result.get("data", {}),
            "payload_summary": receive_result.get("payload_summary", {}),
        }))
        reward_claim["success"] = False
        reward_claim["message"] = message
        return {"success": False, "message": message}

    def _process_daily_lottery(self, api, portal_result, page_info, account_name, result):
        lottery_logger = bind_logger(self.logger, account=account_name, step="天天抽奖")
        daily_lottery_result = api.get_daily_lottery_info(page_info)
        if not daily_lottery_result["success"]:
            message = daily_lottery_result["error"]
            result["daily_lottery"]["message"] = message
            return {"success": False, "message": message}

        remain_times = daily_lottery_result["remain_times"]
        session_id = daily_lottery_result["session_id"]
        result["daily_lottery"].update({
            "remain_times": remain_times,
            "session_id": session_id,
            "session_name": daily_lottery_result.get("session_name", ""),
            "stock_status": daily_lottery_result.get("stock_status", ""),
            "sign_day": daily_lottery_result.get("sign_day", 0),
            "reward_pool": [r.get("reward_name", "") for r in daily_lottery_result.get("lottery_reward_list", []) if r.get("reward_name")],
        })

        if remain_times <= 0:
            message = "天天抽奖无剩余次数"
            result["daily_lottery"]["message"] = message
            return {"success": True, "message": message}

        lottery_logger.info("剩余抽奖次数=%s，开始执行抽奖", remain_times)
        for index in range(1, remain_times + 1):
            if index > 1:
                delay = random.uniform(1, 2)
                lottery_logger.info("等待 %.1f 秒后继续抽奖", delay)
                time.sleep(delay)
            lottery_exec_result = api.exec_daily_lottery(
                portal_info=portal_result,
                component_number=daily_lottery_result["component_number"],
                component_node_id=daily_lottery_result["component_node_id"],
                session_id=session_id,
            )
            attempt = {
                "index": index,
                "success": lottery_exec_result["success"],
                "reward_name": lottery_exec_result.get("reward_name", ""),
                "reward_type": lottery_exec_result.get("reward_type", ""),
                "message": lottery_exec_result.get("error") or lottery_exec_result.get("reward_name") or "抽奖成功",
            }
            result["daily_lottery"]["attempts"].append(attempt)
            if lottery_exec_result["success"]:
                lottery_logger.info("第 %s 次抽奖成功: %s", index, attempt["reward_name"])
            else:
                lottery_logger.error("第 %s 次抽奖失败: %s", index, attempt["message"])
                if lottery_exec_result.get("error_type") == "token_expired" or is_auth_expired(attempt["message"]):
                    result["auth_expired"] = True
                    result["daily_lottery"]["message"] = "Token已过期，请重新登录"
                    return {"success": False, "message": "Token已过期，请重新登录"}
                break

        success_count = sum(1 for a in result["daily_lottery"]["attempts"] if a["success"])
        total_attempts = len(result["daily_lottery"]["attempts"])
        if total_attempts == 0:
            message, success = "未执行天天抽奖", True
        elif success_count == total_attempts:
            message, success = f"天天抽奖完成，成功 {success_count} 次", True
        elif success_count > 0:
            message, success = f"天天抽奖部分成功，成功 {success_count}/{total_attempts} 次", True
        else:
            message, success = f"天天抽奖失败，共尝试 {total_attempts} 次", False

        if success_count > 0:
            reward_claim_status = self._process_daily_lottery_reward_claim(
                api=api, portal_result=portal_result, account_name=account_name, result=result,
            )
            if reward_claim_status["message"]:
                message = f"{message}，{reward_claim_status['message']}"
            success = success and reward_claim_status["success"]

        result["daily_lottery"]["message"] = message
        return {"success": success, "message": message}

    # ----- 主流程 -----
    def process_account(self, account_info: dict[str, Any]) -> dict[str, Any]:
        account_name = account_info.get("account_name", "未命名账号")
        account_logger = bind_logger(self.logger, account=account_name)
        log_page_switch(account_logger, self.page_name)

        result: dict[str, Any] = {
            "account_name": account_name,
            "success": False,
            "auth_expired": False,
            "message": "",
            "portal_info": {},
            "free_member_checkin": {"sign_date": "", "sign_status": "", "reward_title": "", "signed_days": 0, "sign_series_id": "", "message": ""},
            "member_trial": {"remain_times": 0, "candidates": [], "attempts": [], "message": ""},
            "daily_lottery": {
                "remain_times": 0, "session_id": "", "session_name": "", "stock_status": "", "sign_day": 0,
                "reward_pool": [], "attempts": [],
                "reward_claim": {"attempted": False, "success": False, "message": ""},
                "message": "",
            },
        }

        cookies = account_info.get("cookies", "")
        user_agent = account_info.get("user_agent")
        if not cookies:
            result["message"] = "账号配置中缺少 cookies"
            account_logger.error(result["message"])
            return result

        api = DailyBenefitsAPI(cookies=cookies, user_agent=user_agent)
        portal_result = api.get_benefit_portal()
        if not portal_result["success"]:
            result["message"] = portal_result["error"]
            if portal_result.get("error_type") == "token_expired" or is_auth_expired(result["message"]):
                result["auth_expired"] = True
                result["message"] = "Token已过期，请重新登录"
            log_task_result(account_logger, "📍 入口发现", f"❌ {result['message']}")
            return result

        result["portal_info"] = {
            "title": portal_result.get("title", ""),
            "position": portal_result.get("position", ""),
            "activity_number": portal_result["activity_number"],
            "page_number": portal_result["page_number"],
        }
        log_task_result(account_logger, "📍 入口发现", f"✅ {portal_result.get('position') or portal_result.get('title') or '未知入口'} ({portal_result['activity_number']})")

        page_info_result = api.get_page_info(portal_result)
        if not page_info_result["success"]:
            result["message"] = page_info_result["error"]
            if page_info_result.get("error_type") == "token_expired" or is_auth_expired(result["message"]):
                result["auth_expired"] = True
                result["message"] = "Token已过期，请重新登录"
            log_task_result(account_logger, "📍 入口发现", f"❌ {result['message']}")
            return result

        current_page_info = page_info_result["data"]
        initial_fragment_result = api.get_fragment_collect_info(current_page_info)
        if initial_fragment_result["success"] and safe_int(initial_fragment_result.get("signed_days", 0)) >= 7:
            pending = self._claim_daily_lottery_reward_if_ready(
                api=api, portal_result=portal_result, page_info=current_page_info,
                account_name=account_name, result=result,
                force_claim=True, fragment_result=initial_fragment_result,
            )
            if not pending["success"]:
                result["success"] = False
                result["message"] = pending["message"]
                result["daily_lottery"]["message"] = pending["message"]
                if result["auth_expired"]:
                    result["message"] = "Token已过期，请重新登录"
                log_task_result(account_logger, "🏆 第7天奖励", f"❌ {result['message']}")
                return result
            if pending["claimed"]:
                refreshed = api.get_page_info(portal_result)
                if refreshed["success"]:
                    current_page_info = refreshed["data"]
                else:
                    result["success"] = False
                    result["message"] = f"{pending['message']}，但刷新页面信息失败: {refreshed['error']}"
                    result["daily_lottery"]["message"] = result["message"]
                    log_task_result(account_logger, "🏆 第7天奖励", f"❌ {result['message']}")
                    return result

        fragment_status = self._process_fragment_collect_sign_in(
            api=api, portal_result=portal_result, page_info=current_page_info,
            account_name=account_name, result=result,
        )
        if fragment_status["refresh_page_info"]:
            refreshed_page_info = api.get_page_info(portal_result)
            if refreshed_page_info["success"]:
                current_page_info = refreshed_page_info["data"]
                refreshed_fragment = api.get_fragment_collect_info(current_page_info)
                if refreshed_fragment["success"]:
                    self._sync_free_member_checkin_state(result["free_member_checkin"], refreshed_fragment)
                    fragment_status["message"] = self._build_free_member_checkin_message(
                        result["free_member_checkin"], signed_now=fragment_status.get("signed_now", False),
                    )
                    result["free_member_checkin"]["message"] = fragment_status["message"]
                else:
                    fragment_status = {"success": False, "message": (
                        f"{fragment_status['message']}，但刷新后的签到状态解析失败: {refreshed_fragment['error']}"
                    )}
                    result["free_member_checkin"]["message"] = fragment_status["message"]
            else:
                fragment_status = {"success": False, "message": f"{fragment_status['message']}，但刷新页面信息失败: {refreshed_page_info['error']}"}
                result["free_member_checkin"]["message"] = fragment_status["message"]

        if result["auth_expired"]:
            result["success"] = False
            result["message"] = "Token已过期，请重新登录"
            log_task_result(account_logger, "📅 打卡签到", "❌ Token已过期")
            return result

        member_trial_status = self._process_member_trial(api, portal_result, current_page_info, account_name, result)
        if result["auth_expired"]:
            result["success"] = False
            result["message"] = "Token已过期，请重新登录"
            log_task_result(account_logger, "🎁 会员试用", "❌ Token已过期")
            return result

        lottery_status = self._process_daily_lottery(api, portal_result, current_page_info, account_name, result)
        if result["auth_expired"]:
            result["success"] = False
            result["message"] = "Token已过期，请重新登录"
            log_task_result(account_logger, "🎰 天天抽奖", "❌ Token已过期")
            return result

        result["success"] = fragment_status["success"] and member_trial_status["success"] and lottery_status["success"]
        result["message"] = " | ".join(m for m in [fragment_status["message"], member_trial_status["message"], lottery_status["message"]] if m) or "处理完成"

        # 日志摘要
        for key, emoji in [("free_member_checkin", "📅 打卡签到"), ("member_trial", "🎁 会员试用"), ("daily_lottery", "🎰 天天抽奖")]:
            sub = result[key]
            msg = sub.get("message", "")
            if not msg:
                continue
            status = "✅" if "成功" in msg or "已签到" in msg else "❌"
            if "无" in msg or "已达上限" in msg or "无需重复" in msg or "已签到" in msg:
                status = "⏭" if "无" in msg else "✅" if "已签到" in msg else "⏭"
            log_task_result(account_logger, emoji, f"{status} {msg}")

        return result

    def run(self) -> None:
        self.logger.info("%s", "=" * 60)
        self.logger.info("WPS 天天领福利任务开始")
        self.logger.info("%s", "=" * 60)
        if not self.accounts:
            self.logger.warning("没有可处理的 WPS 账号")
            return
        apply_startup_jitter("WPS_JITTER_MAX", 600)
        self.account_results = run_accounts(
            self.accounts,
            lambda _idx, account: self.process_account(account),
            interval_range=(3, 8),
        )
        self._print_summary()
        if self.enable_notification:
            self._send_notification()

    @staticmethod
    def build_notification_lines(item: dict[str, Any]) -> list[str]:
        lines = [f"    [{DailyBenefitsTasks.page_name}] {item.get('message', '')}"]
        free_member_checkin = item.get("free_member_checkin", {})
        if free_member_checkin.get("message"):
            lines.append(f"      打卡免费领会员: {free_member_checkin.get('message', '')}")
        member_trial = item.get("member_trial", {})
        lines.append(f"      剩余试用申请次数: {member_trial.get('remain_times', 0)}")
        for attempt in member_trial.get("attempts", []):
            status = "成功" if attempt["success"] else "失败"
            lines.append(f"        {status} - {attempt['title']}: {attempt['message']}")
        daily_lottery = item.get("daily_lottery", {})
        lines.append(f"      剩余抽奖次数: {daily_lottery.get('remain_times', 0)}")
        if daily_lottery.get("sign_day"):
            lines.append(f"      当前签到天数: 第 {daily_lottery.get('sign_day')} 天")
        for attempt in daily_lottery.get("attempts", []):
            status = "成功" if attempt["success"] else "失败"
            lines.append(f"        第{attempt['index']}次 {status}: {attempt['message']}")
        reward_claim = daily_lottery.get("reward_claim", {})
        if reward_claim.get("message"):
            status = "成功" if reward_claim.get("success") else "失败"
            if not reward_claim.get("attempted"):
                status = "跳过"
            lines.append(f"      第7天奖励领取: {status} - {reward_claim.get('message', '')}")
        return lines

    def _print_summary(self) -> None:
        self.logger.info("%s", "=" * 60)
        self.logger.info("执行结果统计")
        self.logger.info("%s", "=" * 60)
        summary = build_summary(self.account_results)
        self.logger.info("总账号数: %s", summary["total"])
        self.logger.info("执行成功: %s", summary["success"])
        self.logger.info("执行失败: %s", summary["failed"])
        for item in self.account_results:
            status = "✅ 成功" if item["success"] else "❌ 失败"
            self.logger.info("%s: %s - %s", item["account_name"], status, item["message"])
        self.logger.info("%s", "=" * 60)

    def _send_notification(self) -> None:
        if not self.account_results:
            return
        summary = build_summary(self.account_results)
        send_summary_notification(
            "WPS天天领福利",
            self.account_results,
            title="WPS天天领福利结果通知",
            summary=summary,
            sound=NotificationSound.BIRDSONG,
        )


# ---------------------------------------------------------------------------
# WPSTaskCenterPage（原 task_center.py）
# ---------------------------------------------------------------------------
class WPSTaskCenterPage:
    """WPS 任务中心活动执行器"""

    page_name = "任务中心"

    def __init__(
        self,
        config_path: str = None,
        enable_notification: bool = True,
        load_accounts: bool = True,
    ):
        if config_path is None:
            self.config_path = project_root / "config" / "token.json"
        else:
            self.config_path = Path(config_path)
        self.enable_notification = enable_notification
        self.accounts: list[dict[str, Any]] = []
        self.account_results: list[dict[str, Any]] = []
        self.logger = bind_logger(setup_logger("wps.task_center"), page=self.page_name)
        if load_accounts:
            self._init_accounts()

    def _init_accounts(self) -> None:
        self.accounts = load_platform_accounts("wps", self.config_path)

    def process_account(self, account_info: dict[str, Any]) -> dict[str, Any]:
        account_name = account_info.get("account_name", "未命名账号")
        account_logger = bind_logger(self.logger, account=account_name)
        log_page_switch(account_logger, self.page_name)

        result: dict[str, Any] = {
            "account_name": account_name,
            "success": False,
            "auth_expired": False,
            "message": "",
            "sign_info": {},
            "sign_rewards": [],
            "lottery_info": {},
            "user_info": {},
            "final_user_info": {},
        }

        try:
            user_id = account_info.get("user_id")
            cookies = account_info.get("cookies", "")
            user_agent = account_info.get("user_agent")
            if not user_id:
                result["message"] = "账号配置中缺少 user_id，跳过任务中心签到"
                account_logger.warning(result["message"])
                return result
            if not cookies:
                result["message"] = "账号配置中缺少 cookies"
                account_logger.error(result["message"])
                return result

            api = WPSAPI(cookies=cookies, user_agent=user_agent)
            sign_result = api.sign_in(user_id=user_id)
            if not sign_result["success"]:
                if sign_result.get("error_type") == "token_expired":
                    result["auth_expired"] = True
                    result["message"] = "Token已过期，请重新登录"
                    log_task_result(account_logger, "🔐 签到", "❌ Token已过期")
                else:
                    result["message"] = sign_result.get("error", "任务中心签到失败")
                    log_task_result(account_logger, "🔐 签到", f"❌ {result['message']}")
                return result

            result["success"] = True
            result["sign_info"] = sign_result.get("data", {}) or {}
            if sign_result.get("already_signed"):
                result["message"] = "任务中心今日已签到"
                log_task_result(account_logger, "🔐 签到", "✅ 今日已签到")
            else:
                result["message"] = "任务中心签到成功"
                log_task_result(account_logger, "🔐 签到", "✅ 签到成功")
                rewards = result["sign_info"].get("rewards", [])
                result["sign_rewards"] = [r.get("reward_name", "") for r in rewards if r.get("reward_name")]

            user_info_result = api.get_user_info()
            if user_info_result["success"]:
                result["user_info"] = user_info_result
            else:
                if user_info_result.get("error_type") == "token_expired" or is_auth_expired(user_info_result.get("error", "")):
                    result["auth_expired"] = True
                    result["message"] = "Token已过期，请重新登录"
                    result["success"] = False
                    log_task_result(account_logger, "💎 积分", "❌ Token已过期")
                    return result
                log_task_result(account_logger, "💎 积分", f"⚠ 获取失败: {user_info_result.get('error', '获取用户信息失败')}")

            lottery_times = result["user_info"].get("lottery_times", 0)
            component_number = result["user_info"].get("lottery_component_number", "ZJ2025092916515917")
            component_node_id = result["user_info"].get("lottery_component_node_id", "FN1762346087mJlk")
            max_lottery_limit = account_info.get("max_lottery_limit")
            if max_lottery_limit is None:
                max_lottery_limit = 5
            actual_lottery_times = min(lottery_times, max_lottery_limit)

            if lottery_times > 0:
                lottery_results = []
                prize_list = []
                for _index in range(actual_lottery_times):
                    time.sleep(random.uniform(1, 3))
                    lottery_result = api.lottery(
                        component_number=component_number, component_node_id=component_node_id,
                    )
                    lottery_results.append(lottery_result)
                    if lottery_result["success"]:
                        prize_list.append(lottery_result.get("prize_name", "未知奖品"))
                    else:
                        if lottery_result.get("error_type") == "token_expired" or is_auth_expired(lottery_result.get("error", "")):
                            result["auth_expired"] = True
                            result["message"] = "Token已过期，请重新登录"
                            result["success"] = False
                            result["lottery_info"] = {
                                "total_attempts": len(lottery_results),
                                "successful_draws": sum(1 for r in lottery_results if r["success"]),
                                "results": lottery_results,
                                "prizes": prize_list,
                            }
                            log_task_result(account_logger, "🎰 抽奖", "❌ Token已过期")
                            return result
                        log_task_result(account_logger, "🎰 抽奖", f"❌ {lottery_result.get('error', '抽奖失败')}")

                result["lottery_info"] = {
                    "total_attempts": actual_lottery_times,
                    "successful_draws": sum(1 for r in lottery_results if r["success"]),
                    "results": lottery_results,
                    "prizes": prize_list,
                }
                if prize_list:
                    log_task_result(account_logger, "🎰 抽奖", f"✅ {', '.join(prize_list)}")
                else:
                    log_task_result(account_logger, "🎰 抽奖", "⚠ 未中奖")
            else:
                log_task_result(account_logger, "🎰 抽奖", "⏭ 无可用次数")

            final_user_info = api.get_user_info()
            if final_user_info["success"]:
                result["final_user_info"] = final_user_info
                log_task_result(account_logger, "💎 积分", f"{final_user_info.get('points', 0)} pt")
            else:
                if final_user_info.get("error_type") == "token_expired" or is_auth_expired(final_user_info.get("error", "")):
                    result["auth_expired"] = True
                    result["message"] = "Token已过期，请重新登录"
                    result["success"] = False
                    log_task_result(account_logger, "💎 积分", "❌ Token已过期")
                    return result
                log_task_result(account_logger, "💎 积分", "⚠ 获取失败")

        except Exception as exc:
            result["success"] = False
            result["message"] = f"处理任务中心账号时发生异常: {exc}"
            account_logger.error(result["message"])
            import traceback
            traceback.print_exc()
        return result

    @staticmethod
    def build_notification_lines(result: dict[str, Any]) -> list[str]:
        lines = [f"    [{WPSTaskCenterPage.page_name}] {result.get('message', '')}"]
        if result.get("sign_rewards"):
            lines.append(f"      签到奖励: {', '.join(result['sign_rewards'])}")
        for i, r in enumerate(result.get("lottery_info", {}).get("results", []), start=1):
            if r["success"]:
                lines.append(f"      第{i}次: {r.get('prize_name', '未知')}")
            else:
                lines.append(f"      第{i}次: {r.get('error', '抽奖失败')}")
        final_info = result.get("final_user_info", {}) or {}
        if final_info.get("success"):
            lines.append(
                f"      账户信息: 抽奖次数 {final_info.get('lottery_times', 0)} | "
                f"积分 {final_info.get('points', 0)} | 即将过期 {final_info.get('advent_points', 0)}"
            )
        return lines

    def run(self) -> None:
        self.logger.info("%s", "=" * 60)
        self.logger.info("WPS任务中心任务开始")
        self.logger.info("%s", "=" * 60)
        if not self.accounts:
            self.logger.warning("没有需要处理的账号")
            return
        apply_startup_jitter("WPS_JITTER_MAX", 600)
        self.account_results = run_accounts(
            self.accounts,
            lambda _idx, account: self.process_account(account),
            interval_range=(5, 10),
        )
        self._print_summary()
        if self.enable_notification:
            self._send_notification()

    def _print_summary(self) -> None:
        self.logger.info("%s", "=" * 60)
        self.logger.info("任务中心执行结果统计")
        self.logger.info("%s", "=" * 60)
        summary = build_summary(self.account_results)
        self.logger.info("总账号数: %s", summary["total"])
        self.logger.info("执行成功: %s", summary["success"])
        self.logger.info("执行失败: %s", summary["failed"])

        prize_summary: dict[str, int] = {}
        total_attempts = 0
        total_successful_draws = 0
        for result in self.account_results:
            lottery_info = result.get("lottery_info")
            if not lottery_info:
                continue
            for single_result in lottery_info.get("results", []):
                if not single_result["success"]:
                    continue
                prize_name = single_result.get("data", {}).get("prize_name", "未知")
                if prize_name and prize_name not in {"未知", "未中奖"}:
                    prize_summary[prize_name] = prize_summary.get(prize_name, 0) + 1
            total_attempts += lottery_info.get("total_attempts", 0)
            total_successful_draws += lottery_info.get("successful_draws", 0)

        if total_attempts > 0:
            self.logger.info("📊 抽奖统计: 总共尝试 %s 次，成功 %s 次", total_attempts, total_successful_draws)
        if prize_summary:
            self.logger.info("🎁 任务中心奖品统计:")
            for prize, count in prize_summary.items():
                self.logger.info("  %s: %s 个", prize, count)
        for result in self.account_results:
            status = "✅ 成功" if result["success"] else "❌ 失败"
            self.logger.info("  %s: %s - %s", result["account_name"], status, result["message"])
        self.logger.info("%s", "=" * 60)

    def _send_notification(self) -> None:
        if not self.account_results:
            return
        summary = build_summary(self.account_results)
        send_summary_notification(
            "WPS任务中心",
            self.account_results,
            title="WPS任务中心结果通知",
            summary=summary,
            sound=NotificationSound.BIRDSONG,
        )


# ---------------------------------------------------------------------------
# 统一入口（整合原 main.py 的多页面调度器 + argparse）
# ---------------------------------------------------------------------------
PAGE_REGISTRY = {
    "task_center": WPSTaskCenterPage,
    "daily_benefits": DailyBenefitsTasks,
}


class WPSMultiPageRunner:
    """统一入口：串行执行选定的所有页面"""

    def __init__(self, pages: Optional[list[str]] = None, config_path: str = None):
        if pages is None:
            pages = list(PAGE_REGISTRY.keys())
        self.page_names: list[str] = [p for p in pages if p in PAGE_REGISTRY]
        if config_path is None:
            self.config_path = project_root / "config" / "token.json"
        else:
            self.config_path = Path(config_path)
        self.logger = setup_logger("wps")
        self.accounts: list[dict[str, Any]] = load_platform_accounts("wps", self.config_path)
        self.page_runners = [
            (name, PAGE_REGISTRY[name](
                config_path=str(self.config_path),
                enable_notification=False,
                load_accounts=False,
            ))
            for name in self.page_names
        ]

    def _process_account(self, account_index: int, account_info: dict[str, Any]) -> dict[str, Any]:
        account_name = account_info.get("account_name", "未命名账号")
        account_result: dict[str, Any] = {
            "account_name": account_name,
            "success": True,
            "message": "",
            "pages": [],
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
                    "message": f"{page_name}执行异常: {exc}",
                }
                self.logger.exception("%s 页面执行失败", page_name)

            account_result["pages"].append({"page_name": page_name, "result": page_result})

            builder = getattr(page_runner, "build_notification_lines", None)
            if callable(builder):
                try:
                    account_result.setdefault("details", []).extend(builder(page_result))
                except Exception:
                    self.logger.exception("构造 %s 推送详情行失败", page_name)

            if not page_result.get("success", False):
                account_result["success"] = False

            # Token 过期则停止该账号后续页面
            if page_result.get("auth_expired") or is_auth_expired(page_result.get("message", "")):
                self.logger.warning("[%s] 登录态已失效，停止执行后续页面", account_name)
                break

            if page_index < len(self.page_runners) - 1:
                time.sleep(random.uniform(1, 2))

        account_result["message"] = " | ".join(
            f"{item['page_name']}: {item['result'].get('message', '')}"
            for item in account_result["pages"]
        )
        log_account_end(self.logger, account_name, account_result["success"])
        return account_result

    def run(self) -> None:
        log_startup(self.logger, len(self.accounts))
        if not self.accounts:
            self.logger.warning("没有需要处理的账号")
            return
        apply_startup_jitter("WPS_JITTER_MAX", 600)
        self.logger.info("将依次执行页面: %s", " → ".join(self.page_names))
        self.logger.info("")

        account_results = run_accounts(
            self.accounts,
            self._process_account,
            interval_range=(3, 6),
        )
        self._print_summary(account_results)
        self._send_notification(account_results)

    def _print_summary(self, account_results) -> None:
        self.logger.info("")
        log_banner(self.logger, "多页面任务执行结果统计")
        summary = build_summary(account_results)
        self.logger.info("总账号数: %s", summary["total"])
        self.logger.info("执行成功: %s", summary["success"])
        self.logger.info("执行失败: %s", summary["failed"])
        for item in account_results:
            status = "✅ 成功" if item["success"] else "❌ 失败"
            self.logger.info("%s: %s", item["account_name"], status)
            for page_item in item.get("pages", []):
                self.logger.info("  - %s: %s", page_item["page_name"], page_item["result"].get("message", ""))
        self.logger.info("%s", "=" * 60)

    def _send_notification(self, account_results) -> None:
        summary = build_summary(account_results)
        send_summary_notification(
            "WPS多页面任务",
            account_results,
            title="WPS多页面任务结果通知",
            summary=summary,
            sound=NotificationSound.BIRDSONG,
        )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="WPS 签到抽奖统一脚本 — 任务中心 + 天天领福利",
    )
    parser.add_argument(
        "--page", "-p",
        choices=["task_center", "daily_benefits", "all"],
        default="all",
        help="选择执行的页面（默认 all 表示依次执行所有页面）",
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="账号配置文件路径（默认读取项目根目录 config/token.json）",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    logger = setup_logger("wps")

    try:
        if args.page == "all":
            pages: Optional[list[str]] = None  # 全部
        else:
            pages = [args.page]

        runner = WPSMultiPageRunner(pages=pages, config_path=args.config)
        runner.run()

    except FileNotFoundError as exc:
        logger.error("❌ 错误: %s", exc)
        logger.error("请确保配置文件存在并包含 WPS 账号信息")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，退出")
        sys.exit(130)
    except Exception as exc:
        logger.exception("❌ 发生未知错误: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
