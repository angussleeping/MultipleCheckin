# -*- coding: utf-8 -*-
"""什么值得买 - 每日签到相关API(自 api.py 拆分, 经 Mixin 组合回 SmzdmAPI)"""

import logging
import time
from typing import Any, Dict, List, Optional

try:
    from .sign_calculator import calculate_sign_from_params
except ImportError:  # 无包上下文(直接运行)时回退为同级导入
    from sign_calculator import calculate_sign_from_params

logger = logging.getLogger('smzdm')


class CheckinMixin:
    """每日签到与众测报名相关API"""
    # ==================== 每日签到相关API ====================

    def daily_checkin(self) -> Optional[Dict[str, Any]]:
        """
        每日签到

        Returns:
            签到结果数据，失败返回None
        """
        url = f"{self.USER_API_URL}/checkin"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
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

        logger.info(f"📌 正在执行每日签到...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                checkin_data = data.get('data', {})
                logger.info(f"✅ 每日签到成功!")
                return checkin_data
            else:
                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ 每日签到失败: {error_msg}")
                return None
        except Exception as e:
            logger.error(f"❌ 每日签到请求失败: {str(e)}")
            return None


    def close(self):
        """关闭会话"""
        self.session.close()

    def get_probation_list(self, status: str = "progress", offset: int = 0) -> Optional[list]:
        """
        获取众测列表

        Args:
            status: 众测状态，默认为"progress"（进行中）
            offset: 偏移量，默认为0

        Returns:
            众测列表，失败返回None
        """
        url = f"{self.TEST_API_URL}/probation/list"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'offset': str(offset),
            'status': status,
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

        logger.info(f"📌 正在获取众测列表 (状态: {status}, 偏移量: {offset})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                rows = data.get('data', {}).get('rows', [])
                logger.info(f"✅ 成功获取众测列表，共 {len(rows)} 个众测商品")
                return rows
            else:
                logger.error(f"❌ 获取众测列表失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取众测列表请求失败: {str(e)}")
            return None

    def submit_probation_apply(self, probation_id: str) -> bool:
        """
        提交众测申请

        Args:
            probation_id: 众测商品ID（对应众测列表中的article_id）

        Returns:
            是否成功
        """
        url = f"{self.TEST_API_URL}/probation/submit"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'attention_merchant': '0',
            'basic_v': '0',
            'f': 'iphone',
            'probation_id': probation_id,
            'remark_list': '["",""]',
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

        logger.info(f"正在提交众测申请 (probation_id={probation_id})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 众测申请提交成功")
                return True
            elif data.get('error_code') == '1':
                error_msg = data.get('error_msg', '')
                if '已经申请过' in error_msg:
                    logger.info(f"该众测商品已经申请过，跳过")
                    return False
                else:
                    logger.error(f"众测申请失败: {error_msg}")
                    return False
            else:
                logger.error(f"众测申请失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 众测申请请求失败: {str(e)}")
            return False

    def apply_zhongce_task(self, task: Dict[str, Any]) -> bool:
        """
        执行申请众测任务

        Args:
            task: 任务信息字典

        Returns:
            是否成功
        """
        task_name = task.get('task_name', '未知任务')
        task_finished_num = task.get('task_finished_num', 0)
        task_even_num = task.get('task_even_num', 0)

        # 计算还需要申请的次数
        remaining_count = task_even_num - task_finished_num

        if remaining_count <= 0:
            logger.info(f"任务 [{task_name}] 已完成所有申请 ({task_finished_num}/{task_even_num})")
            return True

        logger.info(f"任务 [{task_name}] 需要申请 {remaining_count} 次 (已完成 {task_finished_num}/{task_even_num})")

        # 获取众测列表
        probation_list = self.get_probation_list()
        if not probation_list:
            logger.error("获取众测列表失败，无法完成申请任务")
            return False

        # 过滤出可申请的众测商品
        available_probations = []
        for item in probation_list:
            article_probation = item.get('article_probation', {})
            product_status = article_probation.get('product_status', '')

            # product_status == "1" 表示可申请
            if product_status == '1':
                article_id = item.get('article_id', '')
                article_title = item.get('article_title', '未知商品')
                apply_num = article_probation.get('apply_num', '')
                product_num = article_probation.get('product_num', '')
                product_status_name = article_probation.get('product_status_name', '')

                available_probations.append({
                    'id': article_id,
                    'title': article_title,
                    'apply_num': apply_num,
                    'product_num': product_num,
                    'status_name': product_status_name
                })

        if not available_probations:
            logger.warning("当前没有可申请的众测商品")
            return False

        logger.info(f"找到 {len(available_probations)} 个可申请的众测商品")

        # 开始申请
        success_count = 0
        for i, probation in enumerate(available_probations):
            if success_count >= remaining_count:
                break

            logger.info(f"  [{i+1}] {probation['title']} - {probation['apply_num']} - {probation['status_name']}")

            # 提交申请
            if self.submit_probation_apply(probation['id']):
                success_count += 1
                logger.info(f"    ✅ 申请成功 (进度: {success_count}/{remaining_count})")
            else:
                logger.info(f"    ⏭️  跳过该商品")

            # 申请间隔
            if success_count < remaining_count:
                time.sleep(1)

        logger.info(f"众测申请任务完成，成功申请 {success_count} 次")
        return success_count > 0

    def get_interactive_task_list(
        self,
        point_type: int = 0,
        limit: int = 100,
        offset: int = 0,
        source_from: str = "任务活动"
    ) -> Optional[Dict[str, Any]]:
        """
        获取互动任务列表

        Args:
            point_type: 积分类型，默认为0
            limit: 每页数量，默认100
            offset: 偏移量，默认0
            source_from: 来源标识，默认"任务活动"

        Returns:
            任务列表数据，失败返回None
        """
        url = f"{self.USER_API_URL}/task/list_v2"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'get_total': '1',
            'limit': str(limit),
            'offset': str(offset),
            'point_type': str(point_type),
            'source_from': source_from,
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

        logger.info(f"📌 正在获取互动任务列表...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 成功获取互动任务列表")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取互动任务列表失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取互动任务列表请求失败: {str(e)}")
            return None


