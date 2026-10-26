"""什么值得买 - 关注用户相关API(自 api.py 拆分, 经 Mixin 组合回 SmzdmAPI)"""

import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

# 确保 _shared 可导入(Mixin 独立运行时需要)
_script_dir = Path(__file__).resolve().parent.parent.parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

from _shared.http_client import request_with_retry

try:
    from .sign_calculator import calculate_sign_from_params
except ImportError:  # 无包上下文(直接运行)时回退为同级导入
    from sign_calculator import calculate_sign_from_params

logger = logging.getLogger('smzdm')


class FollowMixin:
    """关注用户相关功能: 互动任务/关注/取关"""
    # ==================== 关注用户相关功能 ====================

    def get_follow_user_list(self, page: int = 1) -> Optional[dict[str, Any]]:
        """
        获取被关注用户列表信息

        Args:
            page: 页码，默认为1

        Returns:
            用户列表数据，失败返回None
        """
        url = "https://dingyue-api.smzdm.com/tuijian/search_result"

        # 获取token
        self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'nav_id': '83',
            'page': str(page),
            'time': str(current_time),
            'type': 'user',
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"📌 正在获取关注用户列表 (页码: {page})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info("✅ 成功获取关注用户列表")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取关注用户列表失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取关注用户列表请求失败: {str(e)}")
            return None

    def follow_user(self, keyword: str, keyword_id: str) -> bool:
        """
        关注用户

        Args:
            keyword: 用户名称 (从用户列表中获取的article_title)
            keyword_id: 用户ID (从用户列表中获取的用户ID)

        Returns:
            是否成功
        """
        url = "https://dingyue-api.smzdm.com/dingyue/create"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'is_follow_activity_page': '1',
            'is_from_task': '1',
            'keyword': keyword,
            'keyword_id': keyword_id,
            'refer': 'iPhone/关注/达人/推荐/',
            'time': str(current_time),
            'token': token,
            'type': 'user',
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在关注用户: {keyword} (ID: {keyword_id})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 关注用户成功: {keyword}")
                return True
            else:
                logger.error(f"❌ 关注用户失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 关注用户请求失败: {str(e)}")
            return False

    def unfollow_user(self, keyword: str, keyword_id: str) -> bool:
        """
        取消关注用户

        Args:
            keyword: 用户名称
            keyword_id: 用户ID

        Returns:
            是否成功
        """
        url = "https://dingyue-api.smzdm.com/dingyue/destroy"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'keyword': keyword,
            'keyword_id': keyword_id,
            'refer': 'iPhone/公共/我的兴趣管理/感兴趣/全部',
            'time': str(current_time),
            'token': token,
            'type': 'user',
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在取消关注用户: {keyword} (ID: {keyword_id})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 取消关注用户成功: {keyword}")
                return True
            else:
                logger.error(f"❌ 取消关注用户失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 取消关注用户请求失败: {str(e)}")
            return False

    def execute_follow_task(self, max_follow_count: int = 5) -> dict[str, int]:
        """
        执行关注任务（关注用户后立即取消关注）

        Args:
            max_follow_count: 最大关注用户数量，默认为5

        Returns:
            执行统计字典 {success: 成功数, fail: 失败数}
        """
        logger.info(f"开始执行关注任务，最大关注用户数: {max_follow_count}")

        success_count = 0
        fail_count = 0

        try:
            # 获取用户列表
            user_data = self.get_follow_user_list()
            if not user_data:
                logger.error("获取用户列表失败")
                return {'success': 0, 'fail': 1}

            # 解析用户列表
            rows = user_data.get('rows', [])
            if not rows:
                logger.warning("用户列表为空")
                return {'success': 0, 'fail': 1}

            logger.info(f"获取到 {len(rows)} 个用户")

            processed_count = 0
            for user_row in rows:
                if processed_count >= max_follow_count:
                    break

                # 提取用户信息
                article_title = user_row.get('article_title', '')
                # 从用户数据中提取用户ID，这里需要根据实际返回的数据结构调整
                user_id = user_row.get('keyword_id', '')

                if not article_title or not user_id:
                    logger.warning(f"用户信息不完整，跳过: {user_row}")
                    continue

                logger.info(f"  [{processed_count + 1}] 处理用户: {article_title}")

                # 执行关注
                if self.follow_user(article_title, user_id):
                    logger.info("    ✅ 关注成功")

                    # 等待一下再取消关注
                    time.sleep(2)

                    # 取消关注
                    if self.unfollow_user(article_title, user_id):
                        logger.info("    ✅ 取消关注成功")
                        success_count += 1
                    else:
                        logger.info("    ❌ 取消关注失败")
                        fail_count += 1
                else:
                    logger.info("    ❌ 关注失败")
                    fail_count += 1

                processed_count += 1

                # 处理间隔
                if processed_count < max_follow_count:
                    time.sleep(3)

            logger.info(f"关注任务执行完成: 成功 {success_count} 个, 失败 {fail_count} 个")
            return {'success': success_count, 'fail': fail_count}

        except Exception as e:
            logger.error(f"执行关注任务时发生错误: {str(e)}")
            return {'success': success_count, 'fail': fail_count + 1}





