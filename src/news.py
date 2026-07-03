"""行业资讯抓取模块。

从财经媒体抓取「碳酸锂」「锂电」「锂矿」相关最新资讯标题，
提供摘要链接，帮助快速了解行业动态。

数据源：
1. 东方财富 - 资讯搜索接口（JSONP格式）
2. 东财期货频道 - 碳酸锂相关新闻
"""
import re
from dataclasses import dataclass
from typing import List

import requests

from .config import REQUEST_TIMEOUT, DEBUG

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.eastmoney.com/",
}

KEYWORDS = "碳酸锂"


@dataclass
class NewsItem:
    title: str
    url: str
    source: str   # 来源网站名
    time: str = "" # 发布时间


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
# 数据源 1：东方财富资讯搜索（JSONP 接口）
# ============================================================
def fetch_eastmoney_news(keyword: str = KEYWORDS, count: int = 5) -> List[NewsItem]:
    """东财搜索接口：按关键词检索最新资讯。
    返回的是 JSONP 格式，回调名是动态的（jQuery + 数字_时间戳），
    需要用正则截取括号内的 JSON。
    """
    items = []
    try:
        url = "https://search-api-web.eastmoney.com/search/jsonp"
        params = {
            "cb": "jQuery_callback",
            "param": keyword,
            "type": "cmsArticleWebOld",
            "token": "E1F1B0D9F1D4E7F3D9E4E3E5",
            "pageindex": "0",
            "pagesize": str(count),
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        text = r.text

        # JSONP 截取：匹配 callback( ... ) 中的 JSON
        # 回调名可能是 jQuery_callback({...}) 或 jQuery123_456({...})
        m = re.search(r'\((\{.*\})\)\s*$', text, re.S)
        if not m:
            _log("东财资讯: JSONP 解析失败")
            return []

        import json
        data = json.loads(m.group(1))

        # 数据在 result.cmsArticleWebOld 中
        articles = (data.get("result") or {}).get("cmsArticleWebOld") or []
        if not articles:
            # 也可能在其他字段
            result = data.get("result") or {}
            for key, val in result.items():
                if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                    if "title" in val[0] or "Title" in val[0] or "articleTitle" in val[0]:
                        articles = val
                        break

        for art in articles[:count]:
            # 字段名可能是 Title 或 title
            title = _clean_html(
                art.get("title") or art.get("Title") or art.get("articleTitle") or ""
            )
            url_link = art.get("url") or art.get("Url") or art.get("articleUrl") or ""
            date = art.get("date") or art.get("Date") or art.get("publishDate") or ""
            if not title:
                continue
            items.append(NewsItem(
                title=_truncate(title, 80),
                url=url_link,
                source="东方财富",
                time=str(date),
            ))
        _log(f"东财资讯: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"东财资讯源失败: {e}")
    return items


# ============================================================
# 数据源 2：东财期货新闻（API接口）
# ============================================================
def fetch_em_futures_news(keyword: str = KEYWORDS, count: int = 5) -> List[NewsItem]:
    """东财期货资讯接口：获取期货相关新闻。"""
    items = []
    try:
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPTA_WEB_NEWS_BD",
            "columns": "ALL",
            "filter": f'(TITLE like "%{keyword}%")',
            "pageNumber": "1",
            "pageSize": str(count),
            "sortTypes": "-1",
            "sortColumns": "NOTICE_DATE",
            "source": "WEB",
            "client": "WEB",
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            raise RuntimeError(f"接口返回失败: {data.get('message', '')}")

        result = data.get("result") or {}
        rows = result.get("data") or []
        for row in rows[:count]:
            title = row.get("TITLE", "")
            url_link = row.get("URL", "") or row.get("INFO_CODE", "")
            date = row.get("NOTICE_DATE", "")
            if not title:
                continue
            items.append(NewsItem(
                title=_truncate(title, 80),
                url=url_link,
                source="东方财富期货",
                time=str(date)[:10] if date else "",
            ))
        _log(f"东财期货资讯: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"东财期货资讯源失败: {e}")
    return items


# ============================================================
# 数据源 3：百度新闻搜索
# ============================================================
def fetch_baidu_news(keyword: str = KEYWORDS, count: int = 5) -> List[NewsItem]:
    """百度新闻搜索页面抓取。"""
    items = []
    try:
        url = "https://www.baidu.com/s"
        params = {
            "wd": f"{keyword} 最新消息",
            "rtt": "1",
            "bsst": "1",
            "cl": "2",
            "tn": "news",
        }
        headers = {**HEADERS, "Referer": "https://www.baidu.com"}
        r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        r.encoding = "utf-8"
        html = r.text
        titles = re.findall(
            r'<h3[^>]*class="[^"]*c-title[^"]*"[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            html, re.S,
        )
        for href, title_html in titles[:count]:
            title = _clean_html(title_html)
            if not title:
                continue
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
    # 东财资讯搜索
    try:
        items = fetch_eastmoney_news(keyword, count)
        if items:
            return items
    except Exception as e:
        print(f"  [news] 东财搜索失败，尝试下一个: {e}")

    # 东财期货新闻接口
    try:
        items = fetch_em_futures_news(keyword, count)
        if items:
            return items
    except Exception as e:
        print(f"  [news] 东财期货接口失败，尝试百度: {e}")

    # 百度兜底
    try:
        items = fetch_baidu_news(keyword, count)
        if items:
            return items
    except Exception as e:
        print(f"  [news] 百度也失败: {e}")

    return []
