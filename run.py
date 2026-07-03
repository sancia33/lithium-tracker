#!/usr/bin/env python3
"""碳酸锂价格与行业信息日报 - 主入口。

功能：
  - 每个工作日自动采集碳酸锂期货/现货价格 + 行业资讯
  - 通过飞书/企业微信/Server酱 推送
  - 支持本地手动运行和 GitHub Actions 自动定时运行

使用方式：
  1. 本地运行：
     pip install -r requirements.txt
     # 设置环境变量（或创建 .env 文件配合 python-dotenv）
     export FEISHU_WEBHOOKS="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
     export FEISHU_SECRETS="SECxxx"   # 可选，加签时填
     export FORCE_RUN=true             # 跳过工作日判断
     python run.py

  2. GitHub Actions：
     Fork 仓库 → Settings → Secrets → 添加对应变量 → 自动运行
"""
import datetime
import sys

# 确保项目根目录在 sys.path 中
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import FORCE_RUN, DEBUG, has_any_channel, configured_channels
from src.holiday import is_workday
from src.datasource import collect_all
from src.news import collect_news
from src.notify import push_all


def main() -> None:
    print("=" * 50)
    print(f"  碳酸锂日报  {datetime.date.today()}")
    print("=" * 50)

    # 1. 工作日检查
    if not FORCE_RUN:
        if not is_workday():
            print("  今天不是工作日，跳过推送。")
            print("  （如需强制运行，请设置 FORCE_RUN=true）")
            return
        print("  ✓ 今天是工作日")
    else:
        print("  ⚙ 强制运行模式（跳过工作日判断）")

    # 2. 检查推送通道
    if not has_any_channel():
        print("  ❌ 错误：未配置任何推送通道！")
        print("  请至少配置以下环境变量之一：")
        print("    - FEISHU_WEBHOOKS（飞书）")
        print("    - WECOM_WEBHOOKS（企业微信）")
        print("    - SERVERCHAN_KEYS（Server酱/微信）")
        sys.exit(1)
    print(f"  ✓ 已配置通道: {', '.join(configured_channels())}")

    # 3. 采集数据
    print("\n📊 正在采集价格数据...")
    result = collect_all()
    print(f"  期货 {len(result.futures)} 条 | 现货 {len(result.spot)} 条")
    if result.errors:
        print(f"  ⚠ 数据源异常: {len(result.errors)} 个")
        for e in result.errors:
            print(f"    - {e}")

    print("\n📰 正在采集行业资讯...")
    news = collect_news()
    print(f"  资讯 {len(news)} 条")

    # DEBUG 模式下打印原始数据
    if DEBUG:
        print("\n[DEBUG] 原始数据:")
        for it in result.futures:
            print(f"  期货: {it}")
        for it in result.spot:
            print(f"  现货: {it}")
        for n in news:
            print(f"  资讯: {n.title}")

    # 4. 推送
    print("\n📤 正在推送...")
    errors = push_all(result, news)
    if errors:
        print("  ⚠ 部分推送失败:")
        for e in errors:
            print(f"    - {e}")
    else:
        print("  ✓ 全部推送成功！")

    print("\n✅ 完成")


if __name__ == "__main__":
    main()
