#!/usr/bin/env python3
"""
new Env('TraeCN签到');
cron: 30 4 * * *
"""

"""
Trae CN 每日签到脚本

Trae CN 已切换为积分计费，本脚本每天自动为配置中的每个账号领取签到积分。
接口实现参考 cockpit-tools PR #2179 (feat/trae-cn-checkin-credits)：
- 签到状态: POST https://api.trae.cn/trae/api/v2/ug/checkin_credits/status
- 领取积分: POST https://api.trae.cn/trae/api/v2/ug/checkin_credits/claim

设备绑定说明（重要，按凭证模式区分）：
- 桌面令牌模式（access_token）：签到按「账号 × 已注册设备」校验，x-device-id 必须使用该账号
  自己注册的设备（本机客户端 icube-dc 键后缀的 16 位数字 ID）。一台机器上多个账号共用同一
  设备时，只有该设备所属账号能领取成功，其它账号会被服务端以 code=9095（设备当日已被占用）
  或 code=9074（设备未登记/冲突，文案常为「当前参与用户太多」）拒绝。
- 网页会话模式（session，推荐多账号）：用 X-Cloudide-Session 换取 JWT 后，随机 16 位设备
  即可签到（实测 code=0）。9074 为偶发风控，脚本会自动换随机设备重试 5 次。
- 长效登录 Cookie（sessionid，推荐）：配置后每次运行先调 /cloudide/api/v3/trae/Login
  自动刷新 X-Cloudide-Session（与浏览器打开 trae.cn 的续期链路一致）。实测只需
  `sessionid` 一个 Cookie 即可刷新，约 60 天不失效；配了它就不再需要手工更新 session。

主要能力：
- 多账号依次处理，账号间随机延迟 5-10 秒
- 账号级签到设备 ID：优先取账号自身配置/官方客户端配对设备
- 网页会话（session）失效时自动回退该账号 access_token 再试一次
- 令牌本地过期预检（expires_at），HTTP 连接/5xx 自动重试（会话复用）
- 网页会话 9074 偶发风控自动换设备重试；领取失败自动复查状态，如实上报
- 长效 Cookie 自动刷新 session，隔天/隔周签到不因 session 过期失效
- 重复账号识别：不同 sessionid 指向同一账号（UserID 相同）时报「重复」而非误报「今日已签到」
- 通知显示名 = 配置 account_name + UserID 尾号（服务端无昵称接口，以配置名为主、尾号兜底）
- 汇总与推送单列「需更新凭证」账号，便于及时处理

Author: Assistant
Date: 2026-09-07
"""

import random
import sys
import time
from pathlib import Path
from typing import Any, Optional

# 路径布局:项目根目录(notification)、script/ 目录(_shared)、脚本所在目录(api 等 sibling 模块)
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(script_dir.parent))
sys.path.insert(0, str(script_dir))

from _shared import (
    apply_startup_jitter,
    build_summary,
    get_default_config_path,
    load_platform_accounts,
    run_accounts,
    send_summary_notification,
    setup_logger,
)
from api import TraeAPI, TraeWebAPI, login_refresh
from import_accounts import (
    get_or_create_device_id,
    scan_client_device_pairs,
)

from notification import NotificationSound

logger = setup_logger('trae')

# 领取接口设备类错误码：9074 设备未登记/冲突；9095 设备当日已用于其它账号签到
DEVICE_CONFLICT_CODES = {9074, 9095}
# 网页会话模式 9074 偶发风控的换随机设备重试次数
WEB_9074_RETRY = 5
# 9074：设备未登记或伪造（文案「当前参与用户太多」）；9095：共享设备今日已被其它账号占用
DEVICE_MISSING_HINT = (
    "签到被设备校验拒绝（code={code}: {message}）。Trae CN 领取积分必须使用该账号"
    "自己注册的设备（x-device-id），伪造/随机设备不可用。请先在本机官方 Trae 客户端"
    "用该账号登录一次完成设备注册后重新导入，或在账号配置中手动填写其 device_id。"
)
DEVICE_SHARED_HINT = "共享设备今日已被其它账号签到（code={code}: {message}），该设备每日仅一次签到名额。如需独立签到请改用网页会话模式（配置 session 即可，无需本机设备）。"


class TraeTasks:
    """Trae CN 签到任务自动化执行类"""

    def __init__(self, config_path: str = None):
        """
        初始化任务执行器

        Args:
            config_path (str): 配置文件的完整路径，如果为 None 则使用项目根目录下的 config/token.json
        """
        if config_path is None:
            self.config_path = get_default_config_path()
        else:
            self.config_path = Path(config_path)

        self.logger = logger
        # 只保留 CN 账号（签到积分接口仅存在于 Trae CN）
        all_accounts = load_platform_accounts('trae', self.config_path)
        self.accounts: list[dict[str, Any]] = [
            a for a in all_accounts if a.get('region', 'CN') == 'CN'
        ]
        if self.accounts:
            self.logger.info(f"成功加载 {len(self.accounts)} 个 CN 账号配置")
        self.account_results: list[dict[str, Any]] = []
        # 已处理账号的 UserID → 账号名，用于识别指向同一账号的重复配置条目
        self.seen_user_ids: dict[str, str] = {}

    def resolve_device_for(self, account: dict[str, Any], pair_map: dict[str, str],
                           shared_device: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """
        解析账号的签到设备 ID（签到领取必须携带账号自己注册的设备）

        优先级：账号配置 device_id → 官方客户端配对（userId 匹配）→
        显式授权使用本机主客户端设备（use_shared_device=true 或单账号场景）→ 无。

        Returns:
            Tuple[Optional[str], Optional[str]]: (device_id, 缺失原因)，可取到设备时第二项为 None
        """
        device = str(account.get('device_id') or '').strip()
        if device:
            return device, None

        user_id = str(account.get('user_id') or '')
        if user_id and user_id in pair_map:
            return pair_map[user_id], None

        # 本机主客户端设备是「单设备每日仅一次」的共享资源：仅当账号显式授权
        # （use_shared_device=true 或全配置仅此一个 CN 账号）时才回退使用
        if shared_device and (bool(account.get('use_shared_device')) or len(self.accounts) == 1):
            return shared_device, None

        return None, (
            "账号未配置签到设备 device_id，本机官方客户端无该账号的注册设备配对，"
            "也未授权使用本机共享设备。Trae CN 桌面令牌链路领取必须用该账号自己注册"
            "的设备（伪造/随机设备会 code=9074，多账号共用会 code=9095）。"
            "多账号场景建议改为网页会话模式：为该账号配置 session"
            "（浏览器 https://www.trae.cn 登录后复制 X-Cloudide-Session）即不受本机"
            "设备限制。单账号可将 use_shared_device 置为 true 使用本机主客户端设备"
            "（该设备每日只能成功领取一次）。"
        )

    def _build_api(self, account_info: dict[str, Any], prefer_desktop: bool = False
                   ) -> tuple[Optional[Any], str, Optional[str], Optional[str]]:
        """
        按账号凭证构造 API 实例

        Args:
            account_info (Dict[str, Any]): 账号信息字典
            prefer_desktop (bool): 为 True 时跳过 session，强制走桌面令牌（用于会话失效回退）

        Returns:
            Tuple[Optional[Any], str, Optional[str], Optional[str]]:
                (api, mode, device_id, missing_reason)；api 为 None 表示凭证不可用
        """
        session = str(account_info.get('session') or '').strip()
        sessionid = str(account_info.get('sessionid') or '').strip()
        if sessionid:
            # 配置了长效登录 Cookie 时，每次运行先调 /cloudide/api/v3/trae/Login
            # 刷新 X-Cloudide-Session，保证隔天/隔周 session 失效也能自动续期
            refreshed = login_refresh(sessionid)
            if refreshed['success']:
                session = refreshed['session']
                account_info['session'] = session
                self.logger.info(
                    f"{account_info.get('account_name') or '账号'} - 已用长效 Cookie 刷新 session")
            else:
                self.logger.warning(
                    f"{account_info.get('account_name') or '账号'} 刷新登录态失败: "
                    f"{refreshed['error']}，改用旧 session")
        if session and not prefer_desktop:
            # 网页会话 JWT 不绑定设备，随机设备即可签到；实测固定设备会触发
            # code=9095（该设备当日已被占用），故每次运行使用全新随机设备
            device_id = str(random.randint(10 ** 15, 10 ** 16 - 1))
            return TraeWebAPI(session=session, device_id=device_id), '网页会话', device_id, None

        access_token = account_info.get('access_token')
        if not access_token:
            if sessionid:
                return None, '', None, 'sessionid 失效且未配置 session/access_token，请回浏览器重新复制 sessionid'
            return None, '', None, '账号配置缺少 access_token（或未配置 session）'

        expires_at = account_info.get('expires_at')
        if expires_at:
            try:
                if time.time() > float(expires_at):
                    expired = time.strftime('%Y-%m-%d %H:%M', time.localtime(float(expires_at)))
                    return None, '', None, f'access_token 已于 {expired} 过期，请重新导入账号'
            except (TypeError, ValueError):
                pass

        device_id, missing_reason = self.resolve_device_for(
            account_info, self.device_pair_map, self.shared_device)
        mode = '桌面令牌（会话失效回退）' if (prefer_desktop and session) else '桌面令牌'
        return TraeAPI(access_token=access_token, device_id=device_id or ''), mode, device_id, missing_reason

    def _display_name(self, name: str, api: Optional[Any],
                      account_info: dict[str, Any]) -> str:
        """
        组装账号显示名：配置名 + UserID 尾号后缀，便于在通知里区分同名/笼统命名的账号

        服务端只提供 UserID（无昵称接口），故以配置里手写的名字为主、UserID 尾号兜底。
        拿不到 UserID 时原样返回配置名。
        """
        user_id = ''
        if isinstance(api, TraeWebAPI):
            user_id = api.get_user_id() or ''
        if not user_id:
            user_id = str(account_info.get('user_id') or '')
        if not user_id:
            return name
        return f'{name}(#{user_id[-6:]})'

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
        result = {
            'account_name': account_name,
            'success': False,
            'message': '',
            'already_checked': False,
            'credit': None,
            'token_error': False,
            'device_missing': False,
            'duplicate': False,
        }

        try:
            api, mode, device_id, missing_reason = self._build_api(account_info)
            account_name = self._display_name(account_name, api, account_info)
            result['account_name'] = account_name

            self.logger.info(f"\n{'=' * 60}")
            self.logger.info(f"开始处理账号: {account_name}")
            self.logger.info(f"{'=' * 60}")

            if api is None:
                result['message'] = missing_reason
                result['token_error'] = True
                self.logger.error(f"❌ {account_name}: {missing_reason}")
                return result

            # 查询签到状态（状态接口与设备无关，无设备也可查询）
            self.logger.info(f"{account_name} - 查询签到状态（{mode}）")
            status = api.get_checkin_status()

            # 网页会话失效且账号仍有 access_token：回退桌面令牌再试一次
            if (not status['success'] and status.get('error_type') == 'session_invalid'
                    and account_info.get('access_token')):
                self.logger.warning(f"⚠️ {account_name} 网页会话已失效，回退桌面令牌重试")
                api, mode, device_id, missing_reason = self._build_api(
                    account_info, prefer_desktop=True)
                if api is None:
                    result['message'] = f"{missing_reason}（网页会话已失效）"
                    result['token_error'] = True
                    self.logger.error(f"❌ {account_name} {result['message']}")
                    return result
                status = api.get_checkin_status()

            if not status['success']:
                if status.get('error_type') in ('token_expired', 'session_invalid'):
                    result['message'] = f"{status.get('error', '凭证已失效')}，请重新导入账号/更新 session"
                    result['token_error'] = True
                    self.logger.error(f"❌ {account_name} {result['message']}")
                else:
                    result['message'] = status.get('error', '查询签到状态失败')
                    self.logger.error(f"❌ {account_name} {result['message']}")
                return result

            # 重复账号识别：不同 sessionid 可能指向同一账号（同一账号的多个登录会话），
            # 此时后出现的条目必然显示「今日已签到」，明确提示为重复配置而非误报已签
            user_id = getattr(api, 'user_id', None)
            if user_id:
                owner = self.seen_user_ids.get(user_id)
                if owner:
                    result['success'] = True
                    result['duplicate'] = True
                    result['message'] = (
                        f'与「{owner}」为同一账号（UserID={user_id}），本条目重复，已跳过签到'
                    )
                    self.logger.warning(f"⚠️ {account_name} {result['message']}")
                    return result
                self.seen_user_ids[user_id] = account_name

            # 功能不可用（服务端 enable=false，如活动未开放）
            if not status.get('enable', True):
                result['success'] = True
                result['message'] = '签到活动未开启或不适用'
                self.logger.info(f"ℹ️ {account_name} 签到活动未开启")
                return result

            # 今日已签到（状态接口为账号维度，与本次所用设备无关）
            if status.get('checked_in'):
                result['success'] = True
                result['already_checked'] = True
                result['message'] = '今日已签到'
                self.logger.info(f"✅ {account_name} 今日已签到")
                return result

            # dry-run 模式不执行领取
            if self.dry_run:
                result['success'] = True
                result['message'] = '状态正常，dry-run 未执行签到'
                self.logger.info(f"👀 {account_name} 状态正常（dry-run 跳过领取）")
                return result

            # 桌面令牌模式且未配置设备：无法领取，如实提示（不能伪造/复用主设备）
            if mode.startswith('桌面令牌') and not device_id:
                result['message'] = missing_reason or '账号缺少签到设备 device_id'
                result['device_missing'] = True
                self.logger.warning(f"⚠️ {account_name} 缺少签到设备: {result['message']}")
                return result

            # 执行签到
            self.logger.info(f"{account_name} - 执行签到 (device={device_id})")
            checkin = api.claim_checkin()

            # 网页会话模式：9074 为偶发风控（实测随机设备可签到，见 web_checkin.py 验证），
            # 换全新随机设备重试 WEB_9074_RETRY 次；桌面令牌模式 9074 是真实设备错误，不重试
            if (not checkin['success'] and checkin.get('code') == 9074
                    and mode == '网页会话'):
                for attempt in range(WEB_9074_RETRY):
                    retry_device = str(random.randint(10 ** 15, 10 ** 16 - 1))
                    self.logger.info(
                        f"🔄 {account_name} 9074 偶发风控，换随机设备重试 "
                        f"({attempt + 1}/{WEB_9074_RETRY})")
                    retry_api = TraeWebAPI(
                        session=str(account_info.get('session') or ''),
                        device_id=retry_device)
                    checkin = retry_api.claim_checkin()
                    if checkin['success']:
                        break

            if checkin['success']:
                result['success'] = True
                result['message'] = checkin.get('message') or '签到成功'
                result['credit'] = checkin.get('credits')
                extra = f"，奖励 {result['credit']} 积分" if result['credit'] is not None else ''
                self.logger.info(f"✅ {account_name} 签到成功{extra}")
            else:
                # 凭证失效单独处理
                if checkin.get('error_type') in ('token_expired', 'session_invalid'):
                    result['message'] = f"{checkin.get('error', '凭证已失效')}，请重新导入账号/更新 session"
                    result['token_error'] = True
                    self.logger.error(f"❌ {account_name} {result['message']}")
                    return result

                # 领取失败后复查状态：status 为账号维度，若已变真签到则按已签处理
                latest = api.get_checkin_status()
                if latest['success'] and latest.get('checked_in'):
                    result['success'] = True
                    result['already_checked'] = True
                    result['message'] = '领取报错但复查已签到'
                    self.logger.info(f"✅ {account_name} 领取报错但复查已签到")
                    return result

                # 设备类错误给出可操作指引；其它错误保留服务端原文
                code = checkin.get('code')
                raw_error = checkin.get('error', '签到失败')
                if code in DEVICE_CONFLICT_CODES or '设备' in raw_error or '参与用户' in raw_error:
                    if code == 9095:
                        result['message'] = DEVICE_SHARED_HINT.format(code=code or '?', message=raw_error)
                    elif mode == '网页会话':
                        result['message'] = (
                            f"签到被临时风控拒绝（code={code}: {raw_error}），已自动换随机设备重试仍失败。"
                            "网页会话模式无需绑定设备，稍后重跑即可；若持续失败请确认 session 仍有效。"
                        )
                    else:
                        result['message'] = DEVICE_MISSING_HINT.format(code=code or '?', message=raw_error)
                        result['device_missing'] = True
                else:
                    result['message'] = raw_error
                self.logger.error(f"❌ {account_name} 签到失败: {result['message']}")

        except Exception as e:
            error_msg = f"处理账号时发生异常: {str(e)}"
            self.logger.exception(f"❌ {error_msg}")
            result['message'] = error_msg

        return result

    def run(self, dry_run: bool = False):
        """执行所有账号的签到任务"""
        self.dry_run = dry_run

        # 设备解析：官方客户端 userId→设备配对表；本机主客户端设备仅在单账号或
        # 账号显式 use_shared_device=true 时回退使用
        self.device_pair_map = scan_client_device_pairs()
        if self.device_pair_map:
            self.logger.info(f"📱 官方客户端设备配对: {len(self.device_pair_map)} 个")
        use_shared = len(self.accounts) == 1 or any(
            a.get('use_shared_device') for a in self.accounts)
        self.shared_device = get_or_create_device_id(self.config_path.parent) if use_shared else None
        if self.shared_device:
            scope = '单账号' if len(self.accounts) == 1 else '显式授权'
            self.logger.info(f"📱 {scope}场景回退本机主客户端设备: {self.shared_device}")

        # 启动随机抖动，错开请求高峰
        apply_startup_jitter('TRAE_JITTER_MAX', 600)

        self.logger.info("=" * 60)
        self.logger.info("Trae CN 自动签到任务开始" + ("（dry-run 状态检查）" if dry_run else ""))
        self.logger.info("=" * 60)

        if not self.accounts:
            self.logger.warning("没有需要处理的账号")
            return

        self.account_results = run_accounts(self.accounts, self.process_account)

        self._print_summary()
        if not dry_run:
            self._send_notification()

    def _stats(self) -> dict[str, int]:
        """汇总各分类计数（重复配置条目单独统计，不计入签到成功/失败）"""
        total = len(self.account_results)
        duplicate = sum(1 for r in self.account_results if r.get('duplicate'))
        already = sum(1 for r in self.account_results if r.get('already_checked'))
        success = sum(1 for r in self.account_results
                      if r['success'] and not r.get('duplicate') and not r.get('already_checked'))
        return {
            'total': total,
            'success': success,
            'already': already,
            'duplicate': duplicate,
            'failed': total - success - already - duplicate,
            'token_failed': sum(1 for r in self.account_results if r.get('token_error')),
            'device_missing': sum(1 for r in self.account_results if r.get('device_missing')),
        }

    def _print_summary(self):
        """打印执行结果统计"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("执行结果统计")
        self.logger.info("=" * 60)

        stats = self._stats()

        self.logger.info(f"总账号数: {stats['total']}")
        self.logger.info(f"签到成功: {stats['success']}")
        self.logger.info(f"今日已签: {stats['already']}")
        self.logger.info(f"签到失败: {stats['failed']}")
        if stats['duplicate']:
            self.logger.info(f"其中重复账号: {stats['duplicate']}")
            for r in self.account_results:
                if r.get('duplicate'):
                    self.logger.info(f"  ⚠️ {r['account_name']} {r['message']}")
        if stats['token_failed']:
            self.logger.info(f"其中需更新凭证: {stats['token_failed']}")
            for r in self.account_results:
                if r.get('token_error'):
                    self.logger.info(f"  ⚠️ {r['account_name']} 凭证失效，需重新导入账号/更新 session")
        if stats['device_missing']:
            self.logger.info(f"其中设备缺失/冲突: {stats['device_missing']}")

        self.logger.info("\n详细结果:")
        for result in self.account_results:
            if result.get('duplicate'):
                status = "⚠️ 重复"
            else:
                status = "✅ 成功" if result['success'] else "❌ 失败"
            self.logger.info(f"  {result['account_name']}: {status} - {result['message']}")

        self.logger.info("=" * 60)

    def _send_notification(self):
        """发送推送通知"""
        if not self.account_results:
            return

        stats = self._stats()
        extra_stats: dict[str, Any] = {}
        if stats['duplicate']:
            extra_stats['⚠️ 重复账号'] = stats['duplicate']
        if stats['token_failed']:
            extra_stats['⚠️ 需更新凭证'] = stats['token_failed']
        if stats['device_missing']:
            extra_stats['⚠️ 设备缺失/冲突'] = stats['device_missing']

        # build_summary 会把 duplicate 计入 success,这里按业务口径覆写:
        # success 字段 = 真签到成功 + 今日已签,渲染时 success - already = 真签到成功
        summary = build_summary(self.account_results, extra_stats=extra_stats)
        summary['success'] = stats['success'] + stats['already']
        summary['failed'] = stats['failed']
        summary['already_checked'] = stats['already']

        send_summary_notification(
            'Trae CN',
            self.account_results,
            title='Trae CN签到结果通知',
            summary=summary,
            sound=NotificationSound.BIRDSONG,
        )


def main():
    """主函数"""
    dry_run = '--dry-run' in sys.argv
    try:
        tasks = TraeTasks()
        tasks.run(dry_run=dry_run)

    except FileNotFoundError as e:
        logger.error(f"❌ 错误: {e}")
        logger.error("请确保配置文件存在并包含 trae 账号信息")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ 发生未知错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
