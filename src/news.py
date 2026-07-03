"""行业资讯抓取模块。

从财经媒体抓取「碳酸锂」「锂电」「锂矿」相关最新资讯标题，
提供摘要链接，帮助快速了解行业动态。

数据源：
1. 东方财富 - 要闻资讯搜索接口
2. 百度新闻搜索（兜底）
"""
import re
from dataclasses import dataclass
from typing import List, Optional

import requests

from .config import REQUEST_TIMEOUT, DEBUG

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.baidu.com",
}

KEYWORDS = "碳酸锂"


@dataclass
class NewsItem:
    title: str
    url: str
    source: str   # 来源网站名
    time: str = "" # 发布时间（原文）


def _log(msg: str) -> None:
    if DEBUG:
        print(f"  [news] {msg}")


def _clean_html(text: str) -> str:
    """去除 HTML 标签。"""
    return re.sub(r"<[^>]+>", "", text).strip()


def _truncate(text: str, max_len: int = 80) -> str:
    if len(text) > max_len:
        return text[:max_len - 1] + "…"
    return text


# ============================================================
# 数据源 1：东方财富资讯搜索
# ============================================================
def fetch_eastmoney_news(keyword: str = KEYWORDS, count: int = 5) -> List[NewsItem]:
    """东财搜索接口：按关键词检索最新资讯。"""
    items = []
    try:
        url = "https://search-api-web.eastmoney.com/search/jsonp"
        params = {
            "cb": "jQuery",  # JSONP 回调，返回的是 JS 表达式需要截取
            "param": keyword,
            "type": ["cmsArticleWebOld"],
            "token": "E1F1B0D9F1D4E7F3D9E4E3E5",
            "pageindex": "0",
            "pagesize": str(count),
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        text = r.text
        # JSONP 截取 JSON
        m = re.search(r"jQuery\((.+)\)\s*$", text, re.S)
        if not m:
            _log("东财资讯: JSONP 解析失败")
            return []
        data = __import__("json").loads(m.group(1))
        articles = data.get("Articles", []) or []
        for art in articles[:count]:
            items.append(NewsItem(
                title=_clean_html(art.get("Title", "")),
                url=art.get("Url", ""),
                source="东方财富",
                time=art.get("Date", ""),
            ))
        _log(f"东财资讯: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"东财资讯源失败: {e}")
    return items


# ============================================================
# 数据源 2：百度新闻搜索（纯文本，无需 API Key）
# ============================================================
def fetch_baidu_news(keyword: str = KEYWORDS, count: int = 5) -> List[NewsItem]:
    """百度新闻搜索页面抓取。"""
    items = []
    try:
        url = "https://www.baidu.com/s"
        params = {
            "wd": f"{keyword} 最新消息",
            "rtt": "1",        # 只搜新闻
            "bsst": "1",
            "cl": "2",
            "tn": "news",
        }
        headers = {**HEADERS, "Referer": "https://www.baidu.com"}
        r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        r.encoding = "utf-8"
        html = r.text
        # 百度新闻结果：标题在 <h3 class="c-title"> <a href="...">标题</a>
        titles = re.findall(r'<h3[^>]*class="[^"]*c-title[^"]*"[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.S)
        for href, title_html in titles[:count]:
            title = _clean_html(title_html)
            if not title:
                continue
            # 百度新闻链接经常是跳转链接，直接用
            items.append(NewsItem(
                title=_truncate(title, 80),
                url=href,
                source="百度新闻",
            ))
        _log(f"百度资讯: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"百度资讯源失败: {e}")
    return items


# ============================================================
# 聚合入口
# ============================================================
def collect_news(keyword: str = KEYWORDS, count: int = 5) -> List[NewsItem]:
    """聚合资讯源，失败时自动兜底。"""
    # 东财优先
    try:
        items = fetch_eastmoney_news(keyword, count)
        if items:
            return items
    except Exception as e:
        print(f"  [news] 东财失败，尝试百度: {e}")

    # 百度兜底
    try:
        items = fetch_baidu_news(keyword, count)
        if items:
            return items
    except Exception as e:
        print(f"  [news] 百度也失败: {e}")

    return []
