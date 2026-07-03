"""消息格式化模块。

将采集到的价格数据和资讯统一格式化为：
1. 飞书/企业微信：Markdown 富文本
2. Server酱/纯文本：简洁纯文本

输出统一的 Markdown 消息体，各推送模块自行适配。
"""
import datetime
from typing import List

from .datasource import DataResult, PriceItem
from .news import NewsItem


def _arrow(price_item: PriceItem) -> str:
    """根据涨跌幅返回箭头。"""
    pct = price_item.change_pct.replace("%", "").replace("+", "").replace("-", "").strip()
    try:
        val = float(pct)
    except ValueError:
        return ""
    if val > 0:
        return "🔺"
    if val < 0:
        return "🔻"
    return "➖"


def _color_mark(price_item: PriceItem) -> str:
    """飞书/企微富文本颜色标记（用 HTML span）。"""
    pct = price_item.change_pct.replace("%", "").replace("+", "").replace("-", "").strip()
    try:
        val = float(pct)
    except ValueError:
        return price_item.change_pct
    if val > 0:
        return f"<font color='red'>{price_item.change_pct}</font>"
    if val < 0:
        return f"<font color='green'>{price_item.change_pct}</font>"
    return price_item.change_pct


def format_markdown(result: DataResult, news: List[NewsItem]) -> str:
    """生成 Markdown 格式的推送消息。"""
    today = datetime.date.today().strftime("%Y-%m-%d")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        datetime.date.today().weekday()
    ]
    lines = []
    lines.append(f"## 🔋 碳酸锂日报 — {today} {weekday}\n")

    # —— 期货 ——
    if result.futures:
        lines.append("### 📈 期货行情")
        for it in result.futures:
            arrow = _arrow(it)
            line = f"- **{it.name}**：{it.price}"
            if it.change:
                line += f"  |  {it.change}"
            if it.change_pct:
                line += f"  ({it.change_pct})"
            if arrow:
                line = f"{line} {arrow}"
            lines.append(line)
        lines.append("")

    # —— 现货 ——
    if result.spot:
        lines.append("### 💰 现货报价")
        for it in result.spot:
            extra = f" [{it.extra}]" if it.extra else ""
            lines.append(f"- **{it.name}**{extra}：{it.price}")
            if it.source:
                lines[-1] += f"（{it.source}）"
        lines.append("")

    # —— 行业资讯 ——
    if news:
        lines.append("### 📰 行业资讯")
        for i, n in enumerate(news, 1):
            title = n.title
            if len(title) > 60:
                title = title[:57] + "..."
            lines.append(f"{i}. [{title}]({n.url})")
        lines.append("")

    # —— 异常提示 ——
    if result.errors:
        lines.append("---")
        lines.append(f"⚠️ 部分数据源异常（已自动兜底）：")
        for e in result.errors[:3]:
            lines.append(f"- {e[:60]}")

    if not result.futures and not result.spot and not news:
        lines.append("> ⚠️ 今日数据暂未更新，可能开盘前或节假日，请稍后再查。")

    return "\n".join(lines)


def format_text(result: DataResult, news: List[NewsItem]) -> str:
    """生成纯文本版本（用于 Server酱 等不支持 Markdown 的通道）。"""
    today = datetime.date.today().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"【碳酸锂日报】{today}\n")

    if result.futures:
        lines.append(">> 期货行情")
        for it in result.futures:
            line = f"  {it.name}: {it.price}"
            if it.change_pct:
                line += f" ({it.change_pct})"
            lines.append(line)
        lines.append("")

    if result.spot:
        lines.append(">> 现货报价")
        for it in result.spot:
            lines.append(f"  {it.name}: {it.price}")
        lines.append("")

    if news:
        lines.append(">> 行业资讯")
        for i, n in enumerate(news, 1):
            lines.append(f"  {i}. {n.title}")
            if n.url:
                lines.append(f"     {n.url}")
        lines.append("")

    if result.errors:
        lines.append(f"[异常] {result.errors[0][:50]}")

    return "\n".join(lines)
