#!/usr/bin/env python3
"""
统一 HTTP 客户端

提供带默认超时、自动重试的 requests.Session 工厂,
避免每个平台重复实现 Session 初始化和重试逻辑。
"""

from typing import Any, Callable, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT: tuple[int, int] = (5, 30)  # (connect, read)


def create_session(
    *,
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
    allowed_methods: tuple[str, ...] = ('GET', 'POST', 'PUT', 'DELETE'),
    default_headers: Optional[dict] = None,
) -> requests.Session:
    """
    创建带重试策略的 Session

    Args:
        retries: 失败重试次数
        backoff_factor: 指数退避因子 (0.5 → 0.5s, 1s, 2s ...)
        status_forcelist: 触发重试的 HTTP 状态码
        allowed_methods: 允许重试的方法
        default_headers: 注入到 session 的默认请求头

    Returns:
        配置完成的 requests.Session
    """
    session = requests.Session()

    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(allowed_methods),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    if default_headers:
        session.headers.update(default_headers)

    return session


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: Union[int, tuple[int, int], None] = None,
    **kwargs,
) -> requests.Response:
    """
    带默认超时的请求封装

    所有调用方应通过本函数发起请求,避免忘记设置 timeout 导致挂死。

    Args:
        session: 已配置的 Session
        method: HTTP 方法
        url: 目标 URL
        timeout: 超时,None 时使用 DEFAULT_TIMEOUT
        **kwargs: 透传给 session.request
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    return session.request(method, url, timeout=timeout, **kwargs)


def post_and_parse(
    session: requests.Session,
    url: str,
    *,
    path_hint: str,
    headers: Optional[dict[str, str]] = None,
    timeout: Union[int, tuple[int, int], None] = None,
    payload: Optional[dict] = None,
    require_object_body: bool = False,
    require_data_field: bool = False,
    data_getter: Optional[Callable[[dict[str, Any]], Any]] = None,
    auth_error_checker: Optional[Callable[[Any, str], bool]] = None,
    unauthorized_error: str = '令牌已失效 (http=401)',
) -> dict[str, Any]:
    """
    发送 POST 请求并按「code == 0 为成功」的统一约定解析响应

    收敛各平台 _post 的公共骨架: 网络异常 → http 401 → JSON 解析 →
    http 状态码 → 业务 code → 成功取数; 平台差异通过钩子参数注入。

    Args:
        session: 已配置的 Session
        url: 完整请求地址
        path_hint: 接口路径, 仅用于错误文案
        headers: 请求头
        timeout: 超时, None 时使用 DEFAULT_TIMEOUT
        payload: JSON body, None 时发送 {}
        require_object_body: 为 True 时要求响应必须是 JSON 对象, 否则报 parse 错误
        require_data_field: 为 True 时要求成功响应必须包含 data 字段
        data_getter: 成功时从 body 提取 data, 默认返回整个 body
        auth_error_checker: 业务错误时判断是否为凭证失效 (code, message) -> bool,
            None 时业务错误一律标记为 business
        unauthorized_error: http 401 时的错误文案

    Returns:
        包含 success/data/error/error_type/code 的结果字典
    """
    try:
        response = request_with_retry(
            session, 'POST', url,
            headers=headers, json=payload if payload is not None else {},
            timeout=timeout,
        )
    except requests.RequestException as e:
        return {'success': False, 'error': f'请求 {path_hint} 失败: {e}', 'error_type': 'network'}

    if response.status_code == 401:
        return {'success': False, 'error': unauthorized_error, 'error_type': 'token_expired'}

    try:
        body = response.json()
    except ValueError:
        return {
            'success': False,
            'error': f'解析 {path_hint} 响应失败: {response.text[:200]}',
            'error_type': 'parse',
        }

    if require_object_body and not isinstance(body, dict):
        return {
            'success': False,
            'error': f'{path_hint} 响应不是 JSON 对象: {str(body)[:200]}',
            'error_type': 'parse',
        }

    message = body.get('message') or body.get('msg') or 'unknown error'
    if not isinstance(message, str):
        message = str(message)

    if not response.ok:
        return {
            'success': False,
            'error': f'请求 {path_hint} 失败 (http={response.status_code}): {message}',
            'error_type': 'http',
        }

    # 仅 code == 0 视为成功, 其余均为业务错误
    code = body.get('code', -1)
    if code != 0:
        error_type = 'business'
        if auth_error_checker is not None and auth_error_checker(code, message):
            error_type = 'token_expired'
        return {
            'success': False,
            'error': f'{message} (code={code})',
            'error_type': error_type,
            'code': code,
            'body': body,
        }

    if require_data_field and 'data' not in body:
        return {
            'success': False,
            'error': f'{path_hint} 响应缺少 data 字段',
            'error_type': 'parse',
        }

    data = data_getter(body) if data_getter is not None else body
    return {'success': True, 'data': data}
