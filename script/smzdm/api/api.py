"""
什么值得买API接口模块
功能：提供所有与什么值得买服务交互的API接口
版本：2.0
更新：优化日志输出、改进错误处理、统一代码规范

按业务域拆分到同目录 Mixin 模块, SmzdmAPI 经多重继承组合全部能力, 对外接口不变:
- activity.py: 众测任务相关API
- tasks.py:    任务执行相关API
- checkin.py:  每日签到相关API
- follow.py:   关注用户相关功能
- baoliao.py:  爆料相关API
"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

import requests

# 以便本文件被直接执行(__main__ 自测)时也能 import _shared 与同目录模块
_api_dir = Path(__file__).resolve().parent
_script_dir = _api_dir.parent.parent  # script/
for _p in (str(_script_dir), str(_api_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from .activity import ActivityMixin
    from .baoliao import BaoliaoMixin
    from .checkin import CheckinMixin
    from .follow import FollowMixin
    from .tasks import TasksMixin
except ImportError:  # 直接运行本文件时无包上下文,回退为同级导入
    from activity import ActivityMixin
    from baoliao import BaoliaoMixin
    from checkin import CheckinMixin
    from follow import FollowMixin
    from tasks import TasksMixin
from _shared.http_client import create_session, request_with_retry

# 获取logger实例（由main.py统一配置）
logger = logging.getLogger('smzdm')


class SmzdmAPI(ActivityMixin, TasksMixin, CheckinMixin, FollowMixin, BaoliaoMixin):
    """什么值得买API类 - 封装所有API交互逻辑"""
    # ==================== 常量定义 ====================
    BASE_URL = "https://zhiyou.m.smzdm.com"
    TEST_URL = "https://test.m.smzdm.com"
    USER_API_URL = "https://user-api.smzdm.com"
    TEST_API_URL = "https://test-api.smzdm.com"
    ARTICLE_CDN_URL = "https://article-cdn.smzdm.com"
    DINGYUE_API_URL = "https://dingyue-api.smzdm.com"
    BAOLIAO_TASK_URL = "https://user-api.smzdm.com"

    def __init__(self, cookie: str, user_agent: str, setting: str):
        """
        初始化API客户端

        Args:
            cookie: 账号Cookie
            user_agent: 用户代理字符串
        """
        self.cookie = cookie
        self.user_agent = user_agent
        self.session = create_session()
        self._setup_headers()
        self.setting = setting
        logger.debug("API客户端初始化完成")

    def _setup_headers(self):
        """设置默认请求头"""
        self.session.headers.update({
            'User-Agent': f'Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148/{self.user_agent}/wkwebview/jsbv_1.0.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
            'Origin': self.TEST_URL,
            'Referer': f'{self.TEST_URL}/',
            'Cookie': self.cookie
        })

    def _get_token_from_cookie(self) -> str:
        """
        从Cookie中提取token(sess字段)

        Returns:
            token字符串，提取失败返回空字符串
        """
        for item in self.cookie.split(';'):
            if 'sess=' in item:
                return unquote(item.split('sess=')[1].strip())
        logger.warning("未能从Cookie中提取token")
        return ""

    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Optional[dict[str, Any]]:
        """
        发送HTTP请求的通用方法

        Args:
            method: HTTP方法 (GET, POST等)
            url: 请求URL
            **kwargs: 其他请求参数

        Returns:
            响应的JSON数据，失败返回None
        """
        try:
            response = request_with_retry(self.session, method, url, timeout=30, **kwargs)
            response.raise_for_status()
            data = response.json()

            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:
                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ API返回错误: {error_msg} (错误码: {error_code})")
                return None

            return data
        except requests.exceptions.Timeout:
            logger.error(f"❌ 请求超时: {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 请求失败: {url} | 错误: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 未知错误: {str(e)}")
            return None


if __name__ == '__main__':
    # 自测入口: 从 config/token.json 读取第一个 smzdm 账号,测试爆料图片上传
    import json

    _config_path = _script_dir.parent / 'config' / 'token.json'
    with open(_config_path, encoding='utf-8') as _f:
        _account = json.load(_f)['smzdm']['accounts'][0]

    api = SmzdmAPI(_account['cookie'], _account['user_agent'], _account.get('setting', ''))

    api.upload_baoliao_image("https://img.alicdn.com/i4/2014491970/O1CN01iOBG9z1QQJEt06kJm_!!2014491970.jpg")
