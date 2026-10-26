"""什么值得买 - 爆料相关API(自 api.py 拆分, 经 Mixin 组合回 SmzdmAPI)"""

import base64
import logging
import time
from io import BytesIO
from typing import Any, Optional

import requests
from PIL import Image

try:
    from .sign_calculator import calculate_sign, calculate_sign_from_params
except ImportError:  # 无包上下文(直接运行)时回退为同级导入
    from sign_calculator import calculate_sign, calculate_sign_from_params
from _shared.http_client import request_with_retry

logger = logging.getLogger('smzdm')


class BaoliaoMixin:
    """爆料相关API: 查重/预检/提交/图片上传/阶段性奖励"""
    # ==================== 爆料相关API ====================

    def check_repeat_baoliao(self, url: str) -> Optional[dict[str, Any]]:
        """
        检查爆料链接是否重复

        Args:
            url: 要检查的商品链接URL

        Returns:
            检查结果字典，失败返回None
        """
        api_url = "https://app-api.smzdm.com/v2/baoliao/check_repeat"

        # 获取当前时间戳
        current_time = int(time.time() * 1000)

        # 构建请求参数
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'pdd_token': '1086704855cd376d73bd5507c1926cf2',  # 从curl命令中提取的固定token
            'setting': self.setting,
            'time': str(current_time),
            'url': url,  # 用户传入的URL参数
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置请求头，完全匹配curl命令
        headers = {
            'User-Agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'content-encoding': 'gzip',
            'accept-language': 'zh-Hans-CN;q=1',
            'Cookie': self.cookie
        }

        logger.info(f"📌 正在检查爆料链接是否重复: {url}")

        try:
            response = request_with_retry(
                self.session, 'POST',
                api_url,
                data=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:
                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ 检查爆料重复失败: {error_msg} (错误码: {error_code})")
                return None

            logger.info("✅ 成功检查爆料链接重复状态")
            return data

        except requests.exceptions.Timeout:
            logger.error("❌ 检查爆料重复请求超时")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 检查爆料重复请求失败: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ 检查爆料重复响应JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 检查爆料重复未知错误: {str(e)}")
            return None

    def submit_pre_check_baoliao(self, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        提交爆料前置检查

        Args:

        Returns:
            检查结果字典，失败返回None
        """

        api_url = "https://app-api.smzdm.com/baoliao_v2/submit_pre_check"

        params["setting"] = self.setting
        # 获取当前时间戳
        current_time = int(time.time() * 1000)
        # 构建请求参数
        params['time'] = str(current_time)
        # 计算签名
        sign = calculate_sign(params)
        params['sign'] = sign

        # print(json.dumps(params, ensure_ascii=False))


        # 设置请求头，完全匹配curl命令
        headers = {
            'User-Agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'content-encoding': 'gzip',
            'accept-language': 'zh-Hans-CN;q=1',
            'Cookie': self.cookie
        }

        try:
            response = request_with_retry(
                self.session, 'POST',
                api_url,
                data=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:

                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ 爆料前置检查失败: {error_msg} (错误码: {error_code})")
                return None

            logger.info("✅ 爆料前置检查成功")
            return data

        except requests.exceptions.Timeout:
            logger.error("❌ 爆料前置检查请求超时")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 爆料前置检查请求失败: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ 爆料前置检查响应JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 爆料前置检查未知错误: {str(e)}")
            return None


    def submit_baoliao_article(self, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        提交爆料

        Args:

        Returns:
            检查结果字典，失败返回None
        """

        api_url = "https://app-api.smzdm.com/v2/baoliao/submit"

        # 获取当前时间戳
        current_time = int(time.time() * 1000)

        params["setting"] = self.setting
        # 构建请求参数
        params['time'] = str(current_time)
        # 计算签名
        sign = calculate_sign(params)
        params['sign'] = sign

        # 设置请求头，完全匹配curl命令
        headers = {
            'User-Agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'content-encoding': 'gzip',
            'accept-language': 'zh-Hans-CN;q=1',
            'Cookie': self.cookie
        }

        try:
            response = request_with_retry(
                self.session, 'POST',
                api_url,
                data=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:
                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ 爆料前置检查失败: {error_msg} (错误码: {error_code})")
                return None

            logger.info("✅ 爆料前置检查成功")
            return data

        except requests.exceptions.Timeout:
            logger.error("❌ 爆料前置检查请求超时")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 爆料前置检查请求失败: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ 爆料前置检查响应JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 爆料前置检查未知错误: {str(e)}")
            return None



    def upload_baoliao_image(self, image_url: str, pic_index: int = 0) -> Optional[dict[str, Any]]:
        """
        上传图片到什么值得买服务器

        Args:
            image_url: 图片的URL地址
            pic_index: 图片索引，默认为0

        Returns:
            上传结果字典，失败返回None
        """
        logger.info(f"📌 正在下载图片: {image_url}")

        # 下载并处理图片
        img_data, img_format = self._download_and_process_image(image_url)
        if not img_data:
            return None

        # 上传图片
        return self._upload_to_smzdm(img_data, img_format, pic_index)

    def _download_and_process_image(self, image_url: str) -> tuple[Optional[bytes], str]:
        """
        下载并处理图片，统一转换为 JPEG 格式

        Returns:
            (图片数据, 格式) 或 (None, '')
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/123.0.0.0 Safari/537.36",
            "Referer": "https://detail.tmall.com/",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }

        try:
            response = request_with_retry(self.session, 'GET', image_url, headers=headers, timeout=30)
            response.raise_for_status()

            # 使用 PIL 打开图片，自动识别格式
            img = Image.open(BytesIO(response.content))

            # 统一转换为 JPEG（SMZDM 更兼容）
            if img.mode in ('RGBA', 'LA', 'P'):
                # 处理透明通道
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # 保存为 JPEG
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=90, optimize=True)
            img_data = buffer.getvalue()

            logger.info(f"✅ 图片处理成功，格式: JPEG, 大小: {len(img_data)} 字节")
            return img_data, 'jpeg'

        except requests.RequestException as e:
            logger.error(f"❌ 下载图片失败: {e}")
            return None, ''
        except Exception as e:
            logger.error(f"❌ 处理图片失败: {e}")
            return None, ''

    def _upload_to_smzdm(self, img_data: bytes, img_format: str, pic_index: int) -> Optional[dict[str, Any]]:
        """
        上传图片数据到什么值得买服务器
        """
        api_url = "https://app-api.smzdm.com/util/image/upload"

        # 尝试三种 base64 格式
        img_base64 = base64.b64encode(img_data).decode('utf-8')

        # 格式1: 带 data URI scheme (最常见)
        pic_data_formats = [
            f"data:image/{img_format};base64,{img_base64}",  # 标准格式
            img_base64,  # 纯 base64
            f"data:image/jpeg;base64,{img_base64}",  # 强制 jpeg
        ]

        for idx, pic_data in enumerate(pic_data_formats):
            logger.info(f"📌 尝试格式 {idx + 1}: {'带前缀' if pic_data.startswith('data:') else '纯base64'}")

            params = {
                'basic_v': '0',
                'f': 'iphone',
                'pic_data': pic_data,
                'pic_index': str(pic_index),
                'time': str(int(time.time() * 1000)),
                'v': '11.1.35',
                'weixin': '1',
                'zhuanzai_ab': 'b'
            }

            params['sign'] = calculate_sign_from_params(params)

            headers = {
                'Cookie': self.cookie,
                'content-type': 'application/x-www-form-urlencoded',
                'request_key': '944831971761922056',
                'accept': '*/*',
                'accept-language': 'zh-Hans-CN;q=1',
                'user-agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            }

            try:
                response = request_with_retry(self.session, 'POST', api_url, data=params, headers=headers, timeout=60)
                response.raise_for_status()
                data = response.json()

                error_code = data.get('error_code')

                # 成功
                if error_code in [0, '0', None]:
                    logger.info("✅ 图片上传成功")
                    if upload_data := data.get('data', {}):
                        logger.info(f"    图片URL: {upload_data.get('url', '')}")
                        logger.info(f"   图片HASH: {upload_data.get('hash', '')}")
                    return data

                # 格式错误，尝试下一种格式
                if error_code == '10004':
                    logger.warning(f"⚠️ 格式 {idx + 1} 失败: {data.get('error_msg')}")
                    continue

                # 其他错误，直接返回
                logger.error(f"❌ 上传失败: {data.get('error_msg')} (错误码: {error_code})")
                return None

            except requests.Timeout:
                logger.error("❌ 请求超时")
                return None
            except Exception as e:
                logger.error(f"❌ 请求异常: {e}")
                return None

        logger.error("❌ 所有格式尝试失败")
        return None


    def activity_task_receive(self, activity_id: str, token: str) -> bool:
        """
        领取活动阶段性奖励

        Args:
            activity_id: 活动ID

        Returns:
            是否成功
            :param token:
        """
        url = f"{self.USER_API_URL}/task/activity_task_receive"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        data = {
          "basic_v": "0",
          "f": "iphone",
          "robot_token": token,
          "sign": "",
          "task_id": activity_id,
          "time": str(current_time),
          "v": "11.1.35",
          "weixin": "1",
          "zhuanzai_ab": "b"
        }

        # 计算签名
        sign = calculate_sign_from_params(data)
        data['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在领取爆料阶段性奖励 (activity_id={activity_id})...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=data, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                reward_info = data.get('data', {})
                logger.info(f"✅ 爆料阶段性奖励领取成功! 奖励: {reward_info}")
                return True
            else:
                logger.error(f"❌ 领取爆料阶段性奖励失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 领取爆料阶段性奖励请求失败: {str(e)}")
            return False

    def get_user_article(self):
        """
        获取用户的爆料文章列表

        Returns:
            文章列表数据，失败返回None
        """
        url = f"{self.USER_API_URL}/articles/publish/baoliao"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'limit': '30',
            'offset': '0',
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

        logger.info("📌 正在获取用户爆料文章列表...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info("✅ 成功获取用户爆料文章列表")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取用户爆料文章列表失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取用户爆料文章列表请求失败: {str(e)}")
            return None

    def get_robot_token(self):
        """
        获取用户的爆料文章列表

        Returns:
            文章列表数据，失败返回None
        """
        url = f"{self.USER_API_URL}/robot/token"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'sign': '',
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

        logger.info("📌 正在获取用户robot生成token...")

        try:
            response = request_with_retry(self.session, 'POST', url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"响应数据: {data}")
            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info("✅ 成功获取用户robot生成token")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取用户robot生成token失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取用户robot生成token请求失败: {str(e)}")
            return None





    def getcaptcha_switch(self) -> bool:
        """
        领取活动阶段性奖励

        Args:
            activity_id: 活动ID

        Returns:
            是否成功
            :param token:
        """
        url = f"{self.USER_API_URL}/getcaptcha/switch"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        data = {
          "basic_v": "0",
          "f": "iphone",
          "sign": "",
          "time": str(current_time),
          "v": "11.1.35",
          "weixin": "1",
          "zhuanzai_ab": "b"
        }

        # 计算签名
        sign = calculate_sign_from_params(data)
        data['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })


        try:
            response = request_with_retry(self.session, 'POST', url, data=data, headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"响应数据: {data}")
            if data.get('error_code') == '0' or data.get('error_code') == 0:
                reward_info = data.get('data', {})
                logger.info(f"✅ 爆料阶段性奖励领取成功! 奖励: {reward_info}")
                return True
            else:
                logger.error(f"❌ 领取爆料阶段性奖励失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 领取爆料阶段性奖励请求失败: {str(e)}")
            return False

