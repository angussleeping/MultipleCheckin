# -*- coding: utf-8 -*-
"""什么值得买 - 任务执行相关API(自 api.py 拆分, 经 Mixin 组合回 SmzdmAPI)"""

import logging
import time
from typing import Any, Dict, List, Optional

try:
    from .sign_calculator import calculate_sign_from_params, calculate_sign
except ImportError:  # 无包上下文(直接运行)时回退为同级导入
    from sign_calculator import calculate_sign_from_params, calculate_sign

logger = logging.getLogger('smzdm')


class TasksMixin:
    """任务执行相关API: 浏览/收藏/评分/分享任务与领奖"""
    # ==================== 任务执行相关API ====================

    def view_article_task(
        self,
        task_id: str,
        article_id: str,
        channel_id: int,
        task_event_type: str = "interactive.view.article"
    ) -> bool:
        """
        完成浏览文章任务

        Args:
            task_id: 任务ID
            article_id: 文章ID (字符串类型,如'a3re2odk')
            channel_id: 文章频道ID
            task_event_type: 任务事件类型

        Returns:
            是否成功
        """

        url = f"{self.USER_API_URL}/task/event_view_article_sync"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'article_id': str(article_id),
            'basic_v': '0',
            'channel_id': str(channel_id),
            'f': 'iphone',
            'task_event_type': task_event_type,
            'task_id': task_id,
            'time': str(current_time),
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
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip'
        })

        logger.info(f"正在完成浏览文章任务 (task_id={task_id}, article_id={article_id}, channel_id={channel_id})...")
        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 浏览文章任务完成成功")
                return True
            else:
                logger.error(f"❌ 浏览文章任务失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 浏览文章任务请求失败: {str(e)}")
            return False

    def get_article_channel_id(self, article_id: str) -> Optional[int]:
        """
        通过article_id获取文章的channel_id

        Args:
            article_id: 文章ID (字符串类型,如'a3re2odk')

        Returns:
            channel_id,失败返回None
        """
        # 构建URL
        url = f"{self.ARTICLE_CDN_URL}/preload/{article_id}/fiphone/v11_1_35/wx1/im0/hcae67e467x7q/h5cc7e8ebddb8f0f73.json"

        logger.info(f"📌 正在获取文章channel_id (article_id={article_id})...")

        try:
            response = request_with_retry(self.session, 'GET', url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                channel_id = data.get('data', {}).get('channel_id')
                if channel_id:
                    channel_id = int(channel_id)
                    logger.info(f"✅ 成功获取channel_id: {channel_id}")
                    return channel_id
                else:
                    logger.error(f"响应中没有找到channel_id")
                    return None
            else:
                logger.error(f"❌ 获取文章信息失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取文章channel_id请求失败: {str(e)}")
            return None

    def favorite_article_task(
        self,
        task_id: str,
        article_id: str
    ) -> bool:
        """
        完成收藏文章任务

        Args:
            task_id: 任务ID
            article_id: 文章ID (字符串类型,如'a3re2odk')

        Returns:
            是否成功
        """
        # 通过article_id获取channel_id
        channel_id = self.get_article_channel_id(article_id)
        if channel_id is None:
            logger.error(f"无法获取文章的channel_id，任务失败")
            return False

        url = f"{self.USER_API_URL}/favorites/create"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)


        params = {
            'basic_v': '0',
            'channel_id': str(channel_id),
            'f': 'iphone',
            'id': article_id,
            'time': str(current_time),
            'token': token,
            # 'touchstone_event': str(touchstone_event).replace("'", '"'),
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

        logger.info(f"正在完成收藏文章任务 (task_id={task_id}, article_id={article_id}, channel_id={channel_id})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 收藏文章任务完成成功")
                return True
            else:
                logger.error(f"❌ 收藏文章任务失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 收藏文章任务请求失败: {str(e)}")
            return False

    def rating_article_task(
        self,
        task_id: str,
        article_id: str
    ) -> bool:
        """
        完成点赞文章任务

        Args:
            task_id: 任务ID
            article_id: 文章ID (字符串类型,如'a3re2odk')

        Returns:
            是否成功
        """
        # 通过article_id获取channel_id
        channel_id = self.get_article_channel_id(article_id)
        if channel_id is None:
            logger.error(f"无法获取文章的channel_id，任务失败")
            return False

        url = f"{self.USER_API_URL}/rating/like_create"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)

        # 构建touchstone_event (简化版本,只包含必要信息)
        # touchstone_event = {
        #     "event_value": {
        #         "cid": str(channel_id),
        #         "aid": article_id,
        #         "otype": "点赞"
        #     },
        #     "event_key": "点赞",
        #     "user_id":"1619566011"
        # }

        params = {
            'basic_v': '0',
            'channel_id': str(channel_id),
            'f': 'iphone',
            'id': article_id,
            'time': str(current_time),
            'token': token,
            # 'touchstone_event': str(touchstone_event).replace("'", '"'),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }
        # params = {
        #     'basic_v': '0',
        #     'channel_id': '80',
        #     'f': 'iphone',
        #     'id': 'a8w3kkel',
        #     'sign': '',
        #     'time': '1760959472000',
        #     'token': 'BC-1UTFKA5S+nJM9aijvc+yVpLcJ7cOnZ38OMcDmaZ6OySZwECUqT91hrA7UE/SSDLFDV1OGBToh+xPIbmJ3HZuiuEbljtyEKDkSLCCkO0IjGQTnh7L9L1AVcFEaw==',
        #     'v': '11.1.35',
        #     'weixin': '1',
        #     'zhuanzai_ab': 'b',
        # }


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

        logger.info(f"正在完成点赞文章任务 (task_id={task_id}, article_id={article_id}, channel_id={channel_id})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 点赞文章任务完成成功")
                return True
            else:
                logger.error(f"❌ 点赞文章任务失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 点赞文章任务请求失败: {str(e)}")
            return False

    def share_probation_task(
        self,
        article_id: str,
        channel_id: str
    ) -> bool:
        """
        完成分享众测招募任务

        Args:
            article_id: 文章ID (众测商品ID)
            channel_id: 频道ID

        Returns:
            是否成功
        """
        url = f"{self.USER_API_URL}/share/callback"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)

        params = {
            'article_id': article_id,
            'basic_v': '0',
            'channel_id': channel_id,
            'f': 'iphone',
            'time': str(current_time),
            'token': token,
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

        logger.info(f"正在完成分享众测招募任务 (article_id={article_id}, channel_id={channel_id})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 分享众测招募任务完成成功")
                return True
            else:
                logger.error(f"❌ 分享众测招募任务失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 分享众测招募任务请求失败: {str(e)}")
            return False

    def execute_share_task(self, task: Dict[str, Any]) -> bool:
        """
        执行分享众测招募任务

        Args:
            task: 任务信息字典

        Returns:
            是否成功
        """
        task_name = task.get('task_name', '未知任务')
        task_finished_num = task.get('task_finished_num', 0)
        task_even_num = task.get('task_even_num', 0)

        # 计算还需要分享的次数
        remaining_count = task_even_num - task_finished_num

        if remaining_count <= 0:
            logger.info(f"任务 [{task_name}] 已完成所有分享 ({task_finished_num}/{task_even_num})")
            return True

        logger.info(f"任务 [{task_name}] 需要分享 {remaining_count} 次 (已完成 {task_finished_num}/{task_even_num})")

        # 获取众测列表
        probation_list = self.get_probation_list()
        if not probation_list:
            logger.error("获取众测列表失败，无法完成分享任务")
            return False

        # 提取可分享的众测商品信息
        available_shares = []
        for item in probation_list:
            article_id = item.get('article_id', '')
            article_channel_id = item.get('article_channel_id', '')
            article_title = item.get('article_title', '未知商品')

            if article_id and article_channel_id:
                available_shares.append({
                    'article_id': article_id,
                    'channel_id': article_channel_id,
                    'title': article_title
                })

        if not available_shares:
            logger.warning("当前没有可分享的众测商品")
            return False

        logger.info(f"找到 {len(available_shares)} 个可分享的众测商品")

        # 开始分享
        success_count = 0
        for i, share_item in enumerate(available_shares):
            if success_count >= remaining_count:
                break

            logger.info(f"  [{i+1}] 分享众测商品: {share_item['title']}")

            # 执行分享
            if self.share_probation_task(share_item['article_id'], share_item['channel_id']):
                success_count += 1
                logger.info(f"    ✅ 分享成功 (进度: {success_count}/{remaining_count})")
            else:
                logger.info(f"    ❌ 分享失败")

            # 分享间隔
            if success_count < remaining_count:
                time.sleep(2)

        logger.info(f"分享任务完成，成功分享 {success_count} 次")
        return success_count > 0

    def receive_reward(self, task_id: str) -> bool:
        """
        领取任务奖励

        Args:
            task_id: 任务ID

        Returns:
            是否成功
        """
        url = f"{self.BASE_URL}/task/task/ajax_activity_task_receive"

        # 构建请求参数
        params = {
            'task_id': task_id
        }

        logger.info(f"正在领取任务奖励 (task_id={task_id})...")

        try:
            # 使用POST请求,表单编码
            headers = self.session.headers.copy()
            headers.update({
                'Content-Type': 'application/x-www-form-urlencoded'
            })

            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == 0 or data.get('error_code') == '0':
                reward_info = data.get('data', {})
                logger.info(f"✅ 任务奖励领取成功! 奖励: {reward_info}")
                return True
            else:
                logger.error(f"❌ 领取任务奖励失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 领取任务奖励请求失败: {str(e)}")
            return False

    def receive_activity_reward(self, activity_id: str) -> bool:
        """
        领取活动阶段性奖励

        Args:
            activity_id: 活动ID

        Returns:
            是否成功
        """
        url = f"{self.USER_API_URL}/task/activity_receive"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'activity_id': activity_id,
            'basic_v': '0',
            'f': 'iphone',
            'time': str(current_time),
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

        logger.info(f"正在领取活动阶段性奖励 (activity_id={activity_id})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                reward_info = data.get('data', {})
                logger.info(f"✅ 活动阶段性奖励领取成功! 奖励: {reward_info}")
                return True
            else:
                logger.error(f"❌ 领取活动阶段性奖励失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 领取活动阶段性奖励请求失败: {str(e)}")
            return False

