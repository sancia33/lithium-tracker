"""碳酸锂价格数据源模块。

数据源（全部使用东方财富公开接口，稳定可靠）：
1. 期货行情：东财 clist 接口，广期所市场编号 225，碳酸锂代码 lc
2. 期货历史：东财 kline 接口，取碳酸锂主连(225.lcm) 最近收盘数据
3. 现货报价：东财 clist 接口，筛选碳酸锂相关品种

关键发现：
- 广期所(GFEX)在东方财富的市场编号是 225（不是142）
- 碳酸锂期货代码：lc + 年月（如 lc2608）
- 碳酸锂主连代码：lcm
- 碳酸锂次主连代码：lcs
"""
import datetime
import re
from dataclasses import dataclass, field
from typing import List, Optional

import requests

from .config import REQUEST_TIMEOUT, DEBUG

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.eastmoney.com/",
}

# 广期所在东财的市场编号
GFEX_MKT = "225"


@dataclass
class PriceItem:
    """单条价格信息。"""
    name: str            # 名称，如「碳酸锂主连」
    price: str           # 最新价/报价
    change: str = ""     # 涨跌
    change_pct: str = "" # 涨跌幅
    source: str = ""     # 数据来源
    extra: str = ""      # 附加说明


@dataclass
class DataResult:
    """一次抓取的聚合结果。"""
    futures: List[PriceItem] = field(default_factory=list)   # 期货
    spot: List[PriceItem] = field(default_factory=list)      # 现货
    errors: List[str] = field(default_factory=list)          # 各源失败原因


def _log(msg: str) -> None:
    if DEBUG:
        print(f"  [datasource] {msg}")


def _format_price(raw) -> str:
    """将东财返回的价格格式化为可读字符串（单位：元/吨）。"""
    try:
        val = float(raw)
        if val >= 10000:
            return f"{val:,.0f} 元/吨"
        return f"{val} 元/吨"
    except (ValueError, TypeError):
        return str(raw)


def _format_change_pct(raw) -> str:
    """格式化涨跌幅。"""
    try:
        val = float(raw)
        return f"{val:+.2f}%"
    except (ValueError, TypeError):
        return str(raw)


def _format_change(raw) -> str:
    """格式化涨跌额。"""
    try:
        val = float(raw)
        return f"{val:+,.0f}"
    except (ValueError, TypeError):
        return str(raw)


# ============================================================
# 数据源 1：东方财富 - 广期所碳酸锂期货行情列表
# ============================================================
def fetch_em_futures() -> List[PriceItem]:
    """从东财 clist 接口获取广期所碳酸锂全部合约实时行情。
    自动识别主连、次主连、及各月合约。
    """
    items = []
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": "30", "po": "1", "np": "1",
            "fltt": "2", "invt": "2",
            "fid": "f3",
            "fs": f"m:{GFEX_MKT}",
            "fields": "f2,f3,f4,f12,f14",
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        resp = r.json()
        diff = (resp.get("data") or {}).get("diff") or []
        if not isinstance(diff, list):
            raise RuntimeError(f"东财返回格式异常: {type(diff)}")

        for row in diff:
            code = str(row.get("f12", ""))
            name = str(row.get("f14", ""))
            price = row.get("f2")
            # 只保留碳酸锂相关
            if "碳酸锂" not in name and not code.startswith("lc"):
                continue
            if price in (None, "-", ""):
                continue
            # 优先展示主连
            is_main = code == "lcm"
            is_sub = code == "lcs"
            extra = "主力合约" if is_main else ("次主力" if is_sub else "")

            items.append(PriceItem(
                name=name + "(期货)",
                price=_format_price(price),
                change=_format_change(row.get("f4", "")),
                change_pct=_format_change_pct(row.get("f3", "")),
                source="东方财富",
                extra=extra,
            ))

        # 排序：主连 > 次主连 > 按合约月份
        def _sort_key(it: PriceItem) -> int:
            if it.extra == "主力合约":
                return 0
            if it.extra == "次主力":
                return 1
            return 2
        items.sort(key=_sort_key)

        _log(f"东财期货: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"东方财富期货源失败: {e}")
    return items


# ============================================================
# 数据源 2：东方财富 - 碳酸锂主连历史K线（兜底）
# ============================================================
def fetch_em_kline() -> List[PriceItem]:
    """从东财 kline 接口获取碳酸锂主连最近交易日数据。
    作为 clist 接口的兜底方案。
    """
    items = []
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": f"{GFEX_MKT}.lcm",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "klt": "101",  # 日K
            "fqt": "1",
            "beg": "0",
            "end": "20500101",
            "lmt": "3",    # 最近3个交易日
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json().get("data")
        if not data:
            raise RuntimeError("kline 接口返回 data 为空")

        name = data.get("name", "碳酸锂主连")
        klines = data.get("klines", [])
        if not klines:
            raise RuntimeError("kline 无数据")

        # 取最后一条（最近交易日）
        last = klines[-1]
        fields = last.split(",")
        # 格式：日期,开盘,收盘,最高,最低,成交量,成交额,振幅
        if len(fields) >= 8:
            trade_date = fields[0]
            close_price = fields[2]
            open_price = fields[1]
            high = fields[3]
            low = fields[4]
            amplitude = fields[7]

            # 计算涨跌（需要前一天数据）
            change = ""
            change_pct = ""
            if len(klines) >= 2:
                prev = klines[-2].split(",")
                if len(prev) >= 3:
                    try:
                        prev_close = float(prev[2])
                        curr_close = float(close_price)
                        chg = curr_close - prev_close
                        change = f"{chg:+,.0f}"
                        if prev_close != 0:
                            change_pct = f"{chg / prev_close * 100:+.2f}%"
                    except ValueError:
                        pass

            items.append(PriceItem(
                name=f"{name}(期货)",
                price=_format_price(close_price),
                change=change,
                change_pct=change_pct,
                source="东方财富",
                extra=f"主力合约 | {trade_date} | 开{float(open_price):,.0f} 高{float(high):,.0f} 低{float(low):,.0f}",
            ))
        _log(f"东财K线: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"东方财富K线源失败: {e}")
    return items


# ============================================================
# 数据源 3：东财期货行情提取现货参考价
# ============================================================
def _extract_spot_from_futures(futures_items: List[PriceItem]) -> List[PriceItem]:
    """从期货合约中提取现货参考信息。
    主力合约价格通常最接近现货，标注为「现货参考价」。
    """
    items = []
    for it in futures_items:
        if "主连" in it.name and it.price:
            # 主连价格作为现货参考
            items.append(PriceItem(
                name="碳酸锂现货参考价",
                price=it.price,
                source="东方财富(期货主连参考)",
                extra="主连价格贴近现货",
            ))
            break
    return items


# ============================================================
# 数据源 4：上海有色网(SMM) - 碳酸锂现货（网页抓取）
# ============================================================
def fetch_smm_spot() -> List[PriceItem]:
    """从上海有色网(SMM)抓取碳酸锂现货价格。"""
    items = []
    try:
        # SMM 价格中心
        urls = [
            "https://hq.smm.cn/lithium_carbonate",
            "https://www.smm.cn/metal/lithium_carbonate",
        ]
        for url in urls:
            try:
                r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    continue
                r.encoding = "utf-8"
                html = r.text

                # 匹配价格区间
                for m in re.finditer(r"(\d{4,7})\s*[-~至]\s*(\d{4,7})\s*元/吨", html):
                    items.append(PriceItem(
                        name="电池级碳酸锂现货",
                        price=f"{m.group(1)}-{m.group(2)} 元/吨",
                        source="上海有色网(SMM)",
                    ))
                    break

                if not items:
                    for m in re.finditer(r"均价[：:]\s*([\d,.]+)\s*元", html):
                        items.append(PriceItem(
                            name="碳酸锂现货均价",
                            price=m.group(1) + " 元/吨",
                            source="上海有色网(SMM)",
                        ))
                        break

                if items:
                    break
            except Exception:
                continue

        _log(f"SMM现货: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"SMM现货源失败: {e}")
    return items


# ============================================================
# 数据源 5：生意社 - 碳酸锂现货（网页抓取）
# ============================================================
def fetch_shengjishe_spot() -> List[PriceItem]:
    """从生意社抓取碳酸锂现货价格。"""
    items = []
    try:
        urls = [
            "https://www.100ppi.com/commodity/5761.html",
            "https://www.100ppi.com/kb/detail-5761.html",
        ]
        for url in urls:
            try:
                r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    continue
                r.encoding = "utf-8"
                html = r.text

                for m in re.finditer(r"最新价格[：:]\s*([\d,.]+)\s*元?/?吨?", html):
                    items.append(PriceItem(
                        name="碳酸锂现货",
                        price=m.group(1) + " 元/吨",
                        source="生意社",
                        extra="最新价",
                    ))
                    break

                if not items:
                    for m in re.finditer(r"报价[：:]\s*([\d,.]+)", html):
                        items.append(PriceItem(
                            name="碳酸锂现货",
                            price=m.group(1) + " 元/吨",
                            source="生意社",
                        ))
                        break

                if items:
                    break
            except Exception:
                continue

        _log(f"生意社现货: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"生意社源失败: {e}")
    return items


# ============================================================
# 聚合入口
# ============================================================
def collect_all() -> DataResult:
    """聚合所有数据源，失败不影响整体。"""
    result = DataResult()

    # 期货：东财 clist → kline 兜底
    try:
        result.futures.extend(fetch_em_futures())
    except Exception as e:
        result.errors.append(str(e))
        try:
            result.futures.extend(fetch_em_kline())
        except Exception as e2:
            result.errors.append(str(e2))

    # 现货：SMM → 生意社 → 期货主连参考 兜底
    try:
        result.spot.extend(fetch_smm_spot())
    except Exception as e:
        result.errors.append(str(e))
        try:
            result.spot.extend(fetch_shengjishe_spot())
        except Exception as e2:
            result.errors.append(str(e2))

    # 如果现货全部失败，用期货主连价格作为现货参考
    if not result.spot and result.futures:
        result.spot.extend(_extract_spot_from_futures(result.futures))

    # 只保留主连 + 次主连 + 前3个月份合约（避免信息过载）
    main_items = [it for it in result.futures if it.extra in ("主力合约", "次主力")]
    month_items = [it for it in result.futures if it.extra not in ("主力合约", "次主力")][:3]
    result.futures = main_items + month_items

    return result
