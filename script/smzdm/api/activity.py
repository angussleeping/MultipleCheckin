# -*- coding: utf-8 -*-
"""什么值得买 - 众测任务相关API(自 api.py 拆分, 经 Mixin 组合回 SmzdmAPI)"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

try:
    from .sign_calculator import calculate_sign
except ImportError:  # 无包上下文(直接运行)时回退为同级导入
    from sign_calculator import calculate_sign

logger = logging.getLogger('smzdm')


class ActivityMixin:
    """众测任务相关API: 活动ID/活动信息/任务列表/能量值"""
    # ==================== 众测任务相关API ====================

    def get_activity_id(self, from_source: str = "zhongce") -> Optional[str]:
        """
        获取活动ID

        Args:
            from_source: 来源标识，默认为"zhongce"

        Returns:
            活动ID，失败返回None
        """
        url = f"{self.BASE_URL}/task/task/ajax_get_activity_id"
        params = {'from': from_source}

        logger.info("📌 正在获取活动ID...")
        data = self._make_request('GET', url, params=params)

        if data and 'data' in data and 'activity_id' in data['data']:
            activity_id = str(data['data']['activity_id'])
            logger.info(f"✅ 成功获取活动ID: {activity_id}")
            return activity_id

        logger.error("❌ 获取活动ID失败")
        return None

    def get_activity_info(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """
        获取活动信息和任务列表

        Args:
            activity_id: 活动ID

        Returns:
            活动信息字典，失败返回None
        """
        url = f"{self.BASE_URL}/task/task/ajax_get_activity_info"
        params = {'activity_id': activity_id}

        logger.info(f"📌 正在获取活动信息 (activity_id={activity_id})...")
        data = self._make_request('GET', url, params=params)

        if data and 'data' in data:
            logger.info("✅ 成功获取活动信息")
            return data['data']

        logger.error("❌ 获取活动信息失败")
        return None




    def get_baoliao_task_list(self) -> Optional[Dict[str, Any]]:
        """
        获取爆料任务列表

        Args:

        Returns:
            爆料任务信息字典，失败返回None
        """
        url = f"{self.BAOLIAO_TASK_URL}/task/list_v2"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            "basic_v": "0",
            "f": "iphone",
            "get_total": "1",
            "limit": "100",
            "offset": "0",
            "point_type": "0",
            "source_from": "任务活动",
            "time": str(current_time),
            "v": "11.1.35",
            "weixin": "1",
            "zhuanzai_ab": "b"
        }

        # 计算签名
        sign = calculate_sign(params)
        params['sign'] = sign

        # 设置特殊的请求头，匹配curl命令中的User-Agent
        headers = {
            'User-Agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(current_time)[:15],  # 使用时间戳的前15位作为request_key
            'content-encoding': 'gzip',
            'accept-language': 'zh-Hans-CN;q=1',
            'Cookie': self.cookie
        }

        logger.info(f"📌 正在获取爆料任务列表")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:
                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ 获取爆料任务列表失败: {error_msg} (错误码: {error_code})")
                return None

            if data and 'data' in data:
                logger.info("✅ 成功获取爆料任务列表")
                return data['data']
            else:
                logger.error("❌ 响应数据格式异常")
                return None

        except requests.exceptions.Timeout:
            logger.error("❌ 请求超时")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 请求失败: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ JSON解析失败: {str(e)}")
            return None
    def get_task_list(self, activity_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取任务列表

        Args:
            activity_id: 活动ID

        Returns:
            任务列表，失败返回None
        """
        activity_info = self.get_activity_info(activity_id)
        # print(activity_info)
        if not activity_info:
            return None

        # 提取所有类型的任务列表
        task_lists = []
        activity_task = activity_info.get('activity_task', {})

        # 合并所有任务列表
        for task_type in ['default_list', 'accumulate_list', 'clock_list']:
            task_list = activity_task.get(task_type, [])
            if task_list:
                task_lists.extend(task_list)

        logger.info(f"✅ 获取到 {len(task_lists)} 个任务")
        return task_lists

    def get_user_energy_info(self) -> Optional[Dict[str, Any]]:
        """
        获取用户众测能量值信息

        Returns:
            用户能量值信息字典，失败返回None
        """
        url = f"{self.TEST_URL}/win_coupon/user_data"

        logger.info("📌 正在获取用户能量值信息...")

        try:
            response = request_with_retry(self.session, 'GET', url, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == 0:
                logger.info("✅ 成功获取用户能量值信息")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取用户能量值信息失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取用户能量值信息请求失败: {str(e)}")
            return None

