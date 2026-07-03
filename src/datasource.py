"""碳酸锂价格数据源模块。

设计思路：每个数据源独立抓取，互为兜底。任何一个源失败都不影响整体，
最终把所有成功抓取到的数据合并成一条消息。

数据源：
1. 东方财富 - 广期所碳酸锂期货主力合约（公开行情接口）
2. 新浪财经 - 碳酸锂期货/现货报价
3. 生意社 - 电池级/工业级碳酸锂现货价格（网页抓取）
"""
import datetime
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

import requests

from .config import REQUEST_TIMEOUT, DEBUG

# 统一请求头，模拟正常浏览器访问
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://www.baidu.com",
}


@dataclass
class PriceItem:
    """单条价格信息。"""
    name: str            # 名称，如「碳酸锂期货主力」
    price: str           # 最新价/报价
    change: str = ""     # 涨跌
    change_pct: str = "" # 涨跌幅
    source: str = ""     # 数据来源
    extra: str = ""      # 附加说明（如「电池级」「工业级」）


@dataclass
class DataResult:
    """一次抓取的聚合结果。"""
    futures: List[PriceItem] = field(default_factory=list)   # 期货
    spot: List[PriceItem] = field(default_factory=list)      # 现货
    errors: List[str] = field(default_factory=list)          # 各源失败原因


def _log(msg: str) -> None:
    if DEBUG:
        print(f"  [datasource] {msg}")


# ============================================================
# 数据源 1：东方财富 - 广期所碳酸锂期货
# ============================================================
# 东财 secid 格式：广期所碳酸锂主力为 142.lc2510 之类，这里用搜索接口拿实时
def fetch_eastmoney_futures() -> List[PriceItem]:
    """东方财富：碳酸锂期货主力合约行情。
    通过公开搜索接口获取碳酸锂相关期货实时行情。
    """
    items = []
    try:
        # 东财行情搜索接口：查找碳酸锂期货
        # 广期所碳酸锂期货代码以 lc 开头，secid 前缀 142
        candidates = [
            ("142.lc2509", "碳酸锂2509"),
            ("142.lc2510", "碳酸锂2510"),
            ("142.lc2511", "碳酸锂2511"),
        ]
        # 用实时行情接口
        secids = ",".join(c[0] for c in candidates)
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2",
            "fields": "f2,f3,f4,f12,f14",
            "secids": secids,
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        resp_json = r.json()
        if not resp_json:
            raise RuntimeError("东方财富返回空数据")
        data = (resp_json.get("data") or {}).get("diff") or []
        if not isinstance(data, list):
            raise RuntimeError(f"东方财富返回格式异常: {type(data)}")
        for row in data:
            price = row.get("f2")
            pct = row.get("f3")
            chg = row.get("f4")
            name = row.get("f14") or row.get("f12")
            if price in (None, "-"):
                continue
            items.append(PriceItem(
                name=f"{name}(期货)",
                price=str(price),
                change=str(chg) if chg is not None else "",
                change_pct=f"{pct}%" if pct is not None else "",
                source="东方财富",
            ))
        _log(f"东财期货: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"东方财富期货源失败: {e}")
    return items


# ============================================================
# 数据源 2：新浪财经 - 碳酸锂期货
# ============================================================
def fetch_sina_futures() -> List[PriceItem]:
    """新浪财经：碳酸锂期货主力合约。
    新浪行情接口返回文本格式：var hq_str_lc2510="名称,昨结,今开,..."
    """
    items = []
    codes = ["lc2510", "lc2509"]
    try:
        # 新浪期货接口
        url = f"https://hq.sinajs.cn/list=" + ",".join(codes)
        headers = {**HEADERS, "Referer": "https://finance.sina.com.cn"}
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        r.encoding = "gbk"
        for code in codes:
            m = re.search(r'hq_str_' + code + r'="([^"]*)"', r.text)
            if not m:
                continue
            fields = m.group(1).split(",")
            if len(fields) < 10 or not fields[0]:
                continue
            # 新浪期货字段：0=名称 1=昨结 2=今开 3=最新 4=最高 5=最低 ...
            name = fields[0]
            price = fields[3] if len(fields) > 3 else ""
            prev_settle = fields[1] if len(fields) > 1 else ""
            change = ""
            change_pct = ""
            try:
                if price and prev_settle:
                    chg = float(price) - float(prev_settle)
                    change = f"{chg:+.0f}"
                    if float(prev_settle) != 0:
                        change_pct = f"{chg / float(prev_settle) * 100:+.2f}%"
            except ValueError:
                pass
            if price:
                items.append(PriceItem(
                    name=f"{name}(期货)",
                    price=price,
                    change=change,
                    change_pct=change_pct,
                    source="新浪财经",
                ))
        _log(f"新浪期货: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"新浪期货源失败: {e}")
    return items


# ============================================================
# 数据源 3：生意社 - 碳酸锂现货价格
# ============================================================
SHENGJISHE_URL = "https://www.100ppi.com/commodity/5761.html"  # 碳酸锂商品页


def fetch_shengjishe_spot() -> List[PriceItem]:
    """生意社：碳酸锂现货价格。从商品详情页解析最新报价。"""
    items = []
    try:
        r = requests.get(SHENGJISHE_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        r.encoding = "utf-8"
        html = r.text

        # 生意社页面顶部有「最新价格」与涨跌信息，结构多变，这里做多模式匹配
        # 模式1：匹配「最新价格 xxxxx 元/吨」
        for m in re.finditer(r"最新价格[：:]\s*([\d,.]+)\s*元?/?吨?", html):
            items.append(PriceItem(
                name="碳酸锂现货",
                price=m.group(1) + " 元/吨",
                source="生意社",
                extra="最新价",
            ))
            break

        # 模式2：表格中「产品名称 最新价格 涨跌」
        # <td>碳酸锂</td><td>xxxxx</td><td>↓/↑xx</td>
        table_pat = re.compile(
            r"碳酸锂.*?(\d{4,7})\s*</td>.*?([↑↓\-+\d.]+)",
            re.S,
        )
        if not items:
            tm = table_pat.search(html)
            if tm:
                items.append(PriceItem(
                    name="碳酸锂现货",
                    price=tm.group(1) + " 元/吨",
                    source="生意社",
                ))

        # 模式3：净价数字提取（兜底）
        if not items:
            # 找形如「报价：xxxxx」
            m = re.search(r"报价[：:]\s*([\d,.]+)", html)
            if m:
                items.append(PriceItem(
                    name="碳酸锂现货",
                    price=m.group(1) + " 元/吨",
                    source="生意社",
                ))

        _log(f"生意社现货: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"生意社源失败: {e}")
    return items


# ============================================================
# 数据源 4：东方财富 - 碳酸锂现货/产业链（移动接口）
# ============================================================
def fetch_eastmoney_spot() -> List[PriceItem]:
    """东方财富数据中心：现货报价（数据宝/行情中心）。"""
    items = []
    try:
        # 东财商品行情：氢氧化锂、碳酸锂等
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": "20", "po": "1", "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:128 t:6",   # 现货板块
            "fields": "f2,f3,f4,f12,f14",
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        diff = r.json().get("data", {}).get("diff", []) or []
        for row in diff:
            name = (row.get("f14") or "")
            if "碳酸锂" not in name and "氢氧化锂" not in name:
                continue
            price = row.get("f2")
            if price in (None, "-"):
                continue
            items.append(PriceItem(
                name=name,
                price=str(price),
                change=str(row.get("f4", "")),
                change_pct=f"{row.get('f3', '')}%",
                source="东方财富",
                extra="现货",
            ))
        _log(f"东财现货: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"东财现货源失败: {e}")
    return items


# ============================================================
# 聚合入口
# ============================================================
def collect_all() -> DataResult:
    """聚合所有数据源，失败不影响整体。"""
    result = DataResult()

    # 期货：东财 → 新浪 兜底
    try:
        result.futures.extend(fetch_eastmoney_futures())
    except Exception as e:
        result.errors.append(str(e))
        try:
            result.futures.extend(fetch_sina_futures())
        except Exception as e2:
            result.errors.append(str(e2))

    # 现货：生意社 → 东财现货 兜底
    try:
        result.spot.extend(fetch_shengjishe_spot())
    except Exception as e:
        result.errors.append(str(e))
        try:
            result.spot.extend(fetch_eastmoney_spot())
        except Exception as e2:
            result.errors.append(str(e2))

    # 去重（同名只保留第一条）
    def dedup(lst: List[PriceItem]) -> List[PriceItem]:
        seen, out = set(), []
        for it in lst:
            if it.name in seen:
                continue
            seen.add(it.name)
            out.append(it)
        return out

    result.futures = dedup(result.futures)
    result.spot = dedup(result.spot)
    return result
