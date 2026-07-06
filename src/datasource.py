"""碳酸锂价格数据源模块。

数据源（多源兜底策略）：
1. 东方财富 push2 - 广期所碳酸锂期货行情（主源）
2. 东方财富 push2his - 碳酸锂主连K线（兜底）
3. 新浪财经 - 碳酸锂期货合约（额外兜底）
4. 现货参考：期货主连价格

关键信息：
- 广期所(GFEX)在东方财富的市场编号 = 225
- 碳酸锂主连 secid = 225.lcm
- 碳酸锂合约 secid = 225.lc2608 等
- 所有请求通过 _get() 统一处理，内置重试
"""
import datetime
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import REQUEST_TIMEOUT, DEBUG

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.eastmoney.com/",
}

# 带重试的 Session
_session = requests.Session()
_retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"],
)
_session.mount("https://", HTTPAdapter(max_retries=_retry))
_session.mount("http://", HTTPAdapter(max_retries=_retry))


def _get(url: str, params: dict = None, timeout: int = None,
         headers: dict = None) -> requests.Response:
    """统一的 GET 请求，内置重试（自动重试 502/503/504）。"""
    if timeout is None:
        timeout = REQUEST_TIMEOUT
    if headers is None:
        headers = HEADERS
    return _session.get(url, params=params, headers=headers, timeout=timeout)


# 广期所市场编号
GFEX_MKT = "225"


@dataclass
class PriceItem:
    """单条价格信息。"""
    name: str
    price: str
    change: str = ""
    change_pct: str = ""
    source: str = ""
    extra: str = ""


@dataclass
class DataResult:
    """一次抓取的聚合结果。"""
    futures: List[PriceItem] = field(default_factory=list)
    spot: List[PriceItem] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _log(msg: str) -> None:
    if DEBUG:
        print(f"  [datasource] {msg}")


def _fmt_price(raw) -> str:
    try:
        val = float(raw)
        return f"{val:,.0f} 元/吨" if val >= 10000 else f"{val} 元/吨"
    except (ValueError, TypeError):
        return str(raw)


def _fmt_pct(raw) -> str:
    try:
        return f"{float(raw):+.2f}%"
    except (ValueError, TypeError):
        return str(raw)


def _fmt_chg(raw) -> str:
    try:
        return f"{float(raw):+,.0f}"
    except (ValueError, TypeError):
        return str(raw)


def _parse_clist_row(row: dict) -> Optional[PriceItem]:
    """解析东财 clist 接口的一行数据。"""
    code = str(row.get("f12", ""))
    name = str(row.get("f14", ""))
    price = row.get("f2")
    if "碳酸锂" not in name and not code.startswith("lc"):
        return None
    if price in (None, "-", ""):
        return None
    extra = ""
    if code == "lcm":
        extra = "主力合约"
        name = "碳酸锂主连"
    elif code == "lcs":
        extra = "次主力"
        name = "碳酸锂次主连"
    return PriceItem(
        name=name + "(期货)",
        price=_fmt_price(price),
        change=_fmt_chg(row.get("f4", "")),
        change_pct=_fmt_pct(row.get("f3", "")),
        source="东方财富",
        extra=extra,
    )


# ============================================================
# 数据源 1：东财 push2 - 广期所碳酸锂期货行情
# ============================================================
def fetch_em_push2() -> List[PriceItem]:
    """东财 push2 接口（实时行情，最全）。"""
    items = []
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "30", "po": "1", "np": "1",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": f"m:{GFEX_MKT}",
        "fields": "f2,f3,f4,f12,f14",
    }
    r = _get(url, params)
    r.raise_for_status()
    resp = r.json()
    diff = (resp.get("data") or {}).get("diff") or []
    if not isinstance(diff, list):
        raise RuntimeError(f"东财返回格式异常: {type(diff)}")
    for row in diff:
        item = _parse_clist_row(row)
        if item:
            items.append(item)
    # 排序
    items.sort(key=lambda it: 0 if it.extra == "主力合约" else (1 if it.extra == "次主力" else 2))
    _log(f"东财push2: 获取 {len(items)} 条")
    return items


# ============================================================
# 数据源 2：东财 push2his - K线（兜底）
# ============================================================
def fetch_em_kline() -> List[PriceItem]:
    """东财 kline 接口（历史数据，作为实时接口的兜底）。"""
    items = []
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": f"{GFEX_MKT}.lcm",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": "101", "fqt": "1",
        "beg": "0", "end": "20500101", "lmt": "3",
    }
    r = _get(url, params)
    r.raise_for_status()
    data = r.json().get("data")
    if not data:
        raise RuntimeError("kline data 为空")
    name = data.get("name", "碳酸锂主连")
    klines = data.get("klines", [])
    if not klines:
        raise RuntimeError("klines 为空")

    last = klines[-1].split(",")
    if len(last) < 8:
        raise RuntimeError("kline 格式异常")
    trade_date, open_p, close_p = last[0], last[1], last[2]
    high, low = last[3], last[4]

    change, change_pct = "", ""
    if len(klines) >= 2:
        prev_close = float(klines[-2].split(",")[2])
        curr_close = float(close_p)
        chg = curr_close - prev_close
        change = f"{chg:+,.0f}"
        if prev_close != 0:
            change_pct = f"{chg / prev_close * 100:+.2f}%"

    items.append(PriceItem(
        name=f"{name}(期货)",
        price=_fmt_price(close_p),
        change=change,
        change_pct=change_pct,
        source="东方财富",
        extra=f"主力合约 | {trade_date} | 开{float(open_p):,.0f} 高{float(high):,.0f} 低{float(low):,.0f}",
    ))
    _log(f"东财K线: 获取 {len(items)} 条 (日期: {trade_date})")
    return items


# ============================================================
# 数据源 3：新浪财经 - 碳酸锂期货（额外兜底）
# ============================================================
def fetch_sina_futures() -> List[PriceItem]:
    """新浪财经期货行情接口。合约代码：lc + 年月（小写）。"""
    items = []
    now = datetime.date.today()
    codes = []
    for y_offset in range(2):
        y = now.year + y_offset
        for m in range(1, 13):
            codes.append(f"lc{y % 100}{m:02d}")

    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    sina_headers = {**HEADERS, "Referer": "https://finance.sina.com.cn"}
    r = _get(url, headers=sina_headers)
    r.raise_for_status()
    r.encoding = "gbk"

    for code in codes:
        m = re.search(r'hq_str_' + code + r'="([^"]*)"', r.text)
        if not m:
            continue
        fields = m.group(1).split(",")
        if len(fields) < 10 or not fields[0]:
            continue
        # 0=名称 1=昨结 3=最新 4=最高 5=最低
        name, prev_settle, latest = fields[0], fields[1], fields[3]
        if not latest:
            continue

        change, change_pct = "", ""
        try:
            chg = float(latest) - float(prev_settle)
            change = f"{chg:+,.0f}"
            if float(prev_settle) != 0:
                change_pct = f"{chg / float(prev_settle) * 100:+.2f}%"
        except ValueError:
            pass

        extra = ""
        # 判断是否主力（最新价最高的近月合约通常为主力）
        if code == f"lc{now.year % 100}{now.month:02d}":
            extra = "近月合约"

        items.append(PriceItem(
            name=f"{name}(期货)",
            price=_fmt_price(latest),
            change=change,
            change_pct=change_pct,
            source="新浪财经",
            extra=extra,
        ))

    # 只保留有价格的
    if items:
        _log(f"新浪期货: 获取 {len(items)} 条")
    return items


# ============================================================
# 现货参考价
# ============================================================
def _spot_from_futures(futures_items: List[PriceItem]) -> List[PriceItem]:
    items = []
    for it in futures_items:
        if "主连" in it.name and it.price:
            items.append(PriceItem(
                name="碳酸锂现货参考价",
                price=it.price,
                source="期货主连参考",
                extra="主连价格贴近现货",
            ))
            break
    return items


# ============================================================
# 聚合入口
# ============================================================
def collect_all() -> DataResult:
    """聚合所有数据源，失败不影响整体。"""
    result = DataResult()

    # 期货：东财push2 → 东财K线 → 新浪 三重兜底
    try:
        result.futures.extend(fetch_em_push2())
    except Exception as e:
        result.errors.append(str(e))
        _log(f"push2失败({e})，尝试K线...")
        try:
            result.futures.extend(fetch_em_kline())
        except Exception as e2:
            result.errors.append(str(e2))
            _log(f"K线也失败({e2})，尝试新浪...")
            try:
                result.futures.extend(fetch_sina_futures())
            except Exception as e3:
                result.errors.append(str(e3))

    # 现货参考：期货主连
    if not result.spot and result.futures:
        result.spot.extend(_spot_from_futures(result.futures))

    # 期货只保留主连 + 次主连 + 前3个月份
    main = [it for it in result.futures if it.extra in ("主力合约", "次主力")]
    others = [it for it in result.futures if it.extra not in ("主力合约", "次主力")][:3]
    result.futures = main + others

    return result
