"""行业资讯抓取模块。

从财经媒体抓取「碳酸锂」「锂电」相关最新资讯标题。
数据源（按优先级）：
1. 东方财富 - 资讯搜索 JSONP 接口
2. 东方财富 - 期货频道资讯接口
3. 百度新闻搜索（兜底）

注意：东财搜索接口返回 JSONP 格式，回调名动态生成，
需要用正则截取 JSON 部分。某些 type 参数可能只返回用户结果
而非文章，需要遍历所有 type 寻找文章列表。
"""
import json
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
    source: str
    time: str = ""


def _log(msg: str) -> None:
    if DEBUG:
        print(f"  [news] {msg}")


def _clean_html(text: str) -> str:
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
    接口返回 JSONP 格式，需要解析出文章列表。
    不同的 type 参数返回不同结果，依次尝试。
    """
    items = []
    # 依次尝试不同的 type，优先文章类型
    type_list = [
        "cmsArticleWebOld",
        "cmsArticleWeb",
        "newsArticleWeb",
        "webArticle",
    ]
    for type_val in type_list:
        if items:
            break
        try:
            url = "https://search-api-web.eastmoney.com/search/jsonp"
            params = {
                "cb": "cb",
                "param": keyword,
                "type": type_val,
                "token": "D43BF722C8E33BDC906FB84D85E326E8",
                "pageindex": "0",
                "pagesize": str(count),
            }
            r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            # 解析 JSONP
            m = re.search(r"\((\{.*\})\)", r.text, re.S)
            if not m:
                continue
            data = json.loads(m.group(1))
            result = data.get("result") or {}
            # 遍历 result 中的所有列表字段，寻找文章
            for _key, val in result.items():
                if not isinstance(val, list) or len(val) == 0:
                    continue
                if not isinstance(val[0], dict):
                    continue
                first = val[0]
                # 判断是否是文章（含 title/Title 字段，且不是用户信息）
                has_title = "title" in first or "Title" in first or "articleTitle" in first
                is_user = "stockFollowerCount" in first or "fansCount" in first
                if has_title and not is_user:
                    for art in val[:count]:
                        title = _clean_html(
                            art.get("title") or art.get("Title") or art.get("articleTitle") or ""
                        )
                        url_link = art.get("url") or art.get("Url") or art.get("articleUrl") or ""
                        date = art.get("date") or art.get("Date") or ""
                        if not title:
                            continue
                        items.append(NewsItem(
                            title=_truncate(title, 80),
                            url=url_link,
                            source="东方财富",
                            time=str(date)[:10] if date else "",
                        ))
                    break  # 找到文章列表就不继续遍历其他 key
        except Exception:
            continue

    _log(f"东财资讯: 获取 {len(items)} 条")
    if not items:
        raise RuntimeError("东财资讯接口未返回文章数据")
    return items


# ============================================================
# 数据源 2：东方财富期货频道资讯
# ============================================================
def fetch_em_futures_news(keyword: str = KEYWORDS, count: int = 5) -> List[NewsItem]:
    """东财期货频道资讯接口。"""
    items = []
    try:
        # 东财资讯列表接口（多个栏目ID尝试）
        for col_id in ["250", "262", "261"]:
            if items:
                break
            try:
                url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
                params = {
                    "client": "web",
                    "biz": "web_news_col",
                    "column": col_id,
                    "order": "1",
                    "needInteractData": "0",
                    "page_index": "1",
                    "page_size": str(count),
                }
                r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    continue
                data = r.json()
                rows = (data.get("data") or {}).get("list") or []
                for row in rows:
                    title = row.get("title", "")
                    if not title or keyword not in title:
                        continue
                    url_link = row.get("url", "")
                    date = row.get("showTime", "") or row.get("time", "")
                    items.append(NewsItem(
                        title=_truncate(title, 80),
                        url=url_link,
                        source="东方财富期货",
                        time=str(date)[:10] if date else "",
                    ))
            except Exception:
                continue
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
        # 百度新闻结果
        titles = re.findall(
            r'<h3[^>]*class="[^"]*c-title[^"]*"[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            html, re.S,
        )
        # 如果没找到新闻格式，试普通搜索结果格式
        if not titles:
            titles = re.findall(
                r'<h3[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
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
# 数据源 4：新浪财经搜索
# ============================================================
def fetch_sina_news(keyword: str = KEYWORDS, count: int = 5) -> List[NewsItem]:
    """新浪财经资讯搜索。"""
    items = []
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get"
        params = {
            "pageid": "153",
            "lid": "2516",
            "k": keyword,
            "num": str(count * 3),  # 多取一些再过滤
            "page": "1",
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        raw_items = (data.get("result") or {}).get("data") or []
        for item in raw_items:
            title = item.get("title", "")
            # 过滤包含关键词的
            if not title or keyword not in title:
                # 放宽匹配：锂电、锂矿也行
                if not any(kw in title for kw in ["锂", "碳酸锂", "电池"]):
                    continue
            url_link = item.get("url", "")
            ctime = item.get("ctime", "")
            items.append(NewsItem(
                title=_truncate(title, 80),
                url=url_link,
                source="新浪财经",
                time=str(ctime)[:10] if ctime else "",
            ))
            if len(items) >= count:
                break
        _log(f"新浪资讯: 获取 {len(items)} 条")
    except Exception as e:
        raise RuntimeError(f"新浪资讯源失败: {e}")
    return items


# ============================================================
# 聚合入口
# ============================================================
def collect_news(keyword: str = KEYWORDS, count: int = 5) -> List[NewsItem]:
    """聚合资讯源，按优先级尝试，失败自动兜底。"""
    sources = [
        ("东财资讯", fetch_eastmoney_news),
        ("东财期货", fetch_em_futures_news),
        ("新浪财经", fetch_sina_news),
        ("百度新闻", fetch_baidu_news),
    ]

    for name, func in sources:
        try:
            items = func(keyword, count)
            if items:
                return items
        except Exception as e:
            print(f"  [news] {name}失败，尝试下一个: {e}")

    return []
