"""节假日判断模块。

工作日判断逻辑：
1. 优先调用免费的第三方节假日 API（判断当天是工作日/节假日/调休补班）。
2. 若 API 不可用，则回退到「周一至周五为工作日」的基础规则。

使用的 API（无需 key）：
- https://timor.tech/api/holiday/info/$date  （主）
- https://api.apihubs.cn/holiday/globals/get  （备，本项目未使用，留作扩展）
"""
import datetime
from typing import Optional

import requests

from .config import REQUEST_TIMEOUT


def _today_str() -> str:
    return datetime.date.today().strftime("%Y-%m-%d")


def _check_timor_tech(date_str: str) -> Optional[bool]:
    """调用 timor.tech API 判断。
    返回 True=工作日（含调休补班），False=休息/节假日，None=查询失败。
    """
    url = f"https://timor.tech/api/holiday/info/{date_str.replace('-', '')}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # type: 0=工作日, 1=周末, 2=节假日, 3=调休补班(算工作日), 4=周五假期等
        if data.get("code") != 0:
            return None
        type_code = data.get("type", {}).get("type")
        if type_code is None:
            return None
        # 0 和 3 视为工作日，其余为非工作日
        return type_code in (0, 3)
    except Exception:
        return None


def _check_apihubs(date_str: str) -> Optional[bool]:
    """备用 API：apihubs。返回语义同上。"""
    url = "https://api.apihubs.cn/holiday/globals/get"
    try:
        resp = requests.get(
            url,
            params={"date": date_str.replace("-", ""), "workday": 1, "order_by": 1, "size": 1},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            return None
        items = data.get("data", {}).get("list", [])
        if not items:
            return None
        # moneyRound: 1=工作日 0=非工作日（apihubs 字段名为 isWorkday）
        is_work = items[0].get("isWorkday")
        if is_work is None:
            return None
        return bool(is_work)
    except Exception:
        return None


def is_workday(d: Optional[datetime.date] = None) -> bool:
    """判断给定日期是否为工作日。不传则判断今天。

    优先使用节假日 API（能识别法定节假日与调休补班），失败时回退到周历判断。
    """
    if d is None:
        d = datetime.date.today()
    date_str = d.strftime("%Y-%m-%d")

    # 主 API
    result = _check_timor_tech(date_str)
    if result is not None:
        return result

    # 备用 API
    result = _check_apihubs(date_str)
    if result is not None:
        return result

    # 回退：周一(0)~周五(4) 视为工作日
    return d.weekday() < 5
