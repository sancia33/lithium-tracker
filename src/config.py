"""配置模块：所有配置通过环境变量读取，方便一键部署。

部署时只需在 GitHub Actions Secrets（或本地 .env）中填入对应的环境变量即可，
不需要改动任何代码。
"""
import os
from typing import List, Optional


def _get(key: str, default: str = "") -> str:
    """读取环境变量，自动去除首尾空白。"""
    return os.environ.get(key, default).strip()


def _get_list(key: str) -> List[str]:
    """读取逗号分隔的环境变量为列表。"""
    val = _get(key)
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


# ============ 推送通道配置 ============
# 飞书自定义机器人 Webhook（在飞书群 → 设置 → 群机器人 → 添加自定义机器人获取）
FEISHU_WEBHOOKS: List[str] = _get_list("FEISHU_WEBHOOKS")
# 飞书机器人签名校验（启用加签时填，逗号分隔，与 webhook 一一对应；不启用则留空）
FEISHU_SECRETS: List[str] = _get_list("FEISHU_SECRETS")

# 企业微信群机器人 Webhook（在企微群 → 右上角 → 群机器人 → 添加机器人获取）
WECOM_WEBHOOKS: List[str] = _get_list("WECOM_WEBHOOKS")

# Server酱（推送到个人微信），在 https://sct.ftqq.com/ 获取 SendKey
SERVERCHAN_KEYS: List[str] = _get_list("SERVERCHAN_KEYS")

# ============ 运行控制 ============
# 强制运行（忽略节假日判断），用于手动触发测试
FORCE_RUN: bool = _get("FORCE_RUN", "false").lower() in ("1", "true", "yes")

# 数据请求超时秒数
REQUEST_TIMEOUT: int = int(_get("REQUEST_TIMEOUT", "15"))

# 是否开启调试模式（输出更多日志）
DEBUG: bool = _get("DEBUG", "false").lower() in ("1", "true", "yes")


def has_any_channel() -> bool:
    """是否配置了至少一个推送通道。"""
    return bool(FEISHU_WEBHOOKS or WECOM_WEBHOOKS or SERVERCHAN_KEYS)


def configured_channels() -> List[str]:
    """返回已配置的通道名称列表，用于日志展示。"""
    channels = []
    if FEISHU_WEBHOOKS:
        channels.append(f"飞书({len(FEISHU_WEBHOOKS)})")
    if WECOM_WEBHOOKS:
        channels.append(f"企业微信({len(WECOM_WEBHOOKS)})")
    if SERVERCHAN_KEYS:
        channels.append(f"Server酱({len(SERVERCHAN_KEYS)})")
    return channels
