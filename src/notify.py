"""推送通知模块。

支持三个通道，全部通过 Webhook 发送，无需登录态：
1. 飞书自定义机器人（支持加签验证）
2. 企业微信群机器人
3. Server酱（推送至个人微信）

每个通道都做成独立函数，可组合调用。
"""
import hashlib
import hmac
import base64
import json
import time
import urllib.parse
from typing import List

import requests

from .config import (
    FEISHU_WEBHOOKS, FEISHU_SECRETS,
    WECOM_WEBHOOKS,
    SERVERCHAN_KEYS,
    REQUEST_TIMEOUT, DEBUG,
)
from .datasource import DataResult
from .news import NewsItem
from .formatter import format_markdown, format_text


def _log(msg: str) -> None:
    if DEBUG:
        print(f"  [notify] {msg}")


# ============================================================
# 飞书机器人推送
# ============================================================
def _feishu_sign(secret: str) -> str:
    """生成飞书加签参数。"""
    ts = str(int(time.time()))
    nonce = ts + "\n" + secret
    key = hashlib.sha256(nonce.encode("utf-8")).digest()
    sig = base64.urlsafe_b64encode(key).decode("utf-8")
    return urllib.parse.quote_plus(sig)


def send_feishu(title: str, md_content: str) -> List[str]:
    """发送到飞书。返回失败原因列表（空=全部成功）。"""
    errors = []
    for i, webhook in enumerate(FEISHU_WEBHOOKS):
        url = webhook
        secret = FEISHU_SECRETS[i] if i < len(FEISHU_SECRETS) else ""
        try:
            # 加签
            if secret:
                sign = _feishu_sign(secret)
                url = f"{webhook}&timestamp={int(time.time())}&sign={sign}"

            # 飞书富文本消息
            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                        "template": "blue",
                    },
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": md_content,
                        },
                    ],
                },
            }
            r = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            resp = r.json()
            if resp.get("code", 0) != 0:
                errors.append(f"飞书#{i}: {resp.get('msg', 'unknown error')}")
            else:
                _log(f"飞书#{i}: 推送成功")
        except Exception as e:
            errors.append(f"飞书#{i}: {e}")
    return errors


# ============================================================
# 企业微信群机器人推送
# ============================================================
def send_wecom(title: str, md_content: str) -> List[str]:
    """发送到企业微信群机器人。"""
    errors = []
    for i, webhook in enumerate(WECOM_WEBHOOKS):
        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## {title}\n\n{md_content}",
                },
            }
            r = requests.post(webhook, json=payload, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            resp = r.json()
            if resp.get("errcode", 0) != 0:
                errors.append(f"企微#{i}: {resp.get('errmsg', 'unknown')}")
            else:
                _log(f"企微#{i}: 推送成功")
        except Exception as e:
            errors.append(f"企微#{i}: {e}")
    return errors


# ============================================================
# Server酱推送（个人微信）
# ============================================================
def send_serverchan(title: str, text_content: str) -> List[str]:
    """发送到 Server酱（微信通知）。"""
    errors = []
    for i, key in enumerate(SERVERCHAN_KEYS):
        try:
            url = f"https://sctapi.ftqq.com/{key}.send"
            payload = {
                "title": title,
                "desp": text_content.replace("\n", "\n\n"),  # Server酱用 Markdown 换行需双换行
            }
            r = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            resp = r.json()
            if resp.get("code", 0) != 0:
                errors.append(f"Server酱#{i}: {resp.get('message', 'unknown')}")
            else:
                _log(f"Server酱#{i}: 推送成功")
        except Exception as e:
            errors.append(f"Server酱#{i}: {e}")
    return errors


# ============================================================
# 统一推送入口
# ============================================================
def push_all(result: DataResult, news: List[NewsItem]) -> List[str]:
    """一键推送所有已配置的通道。返回所有错误信息（空=全部成功）。"""
    title = f"🔋 碳酸锂日报"
    md_content = format_markdown(result, news)
    text_content = format_text(result, news)
    all_errors = []

    if FEISHU_WEBHOOKS:
        all_errors.extend(send_feishu(title, md_content))

    if WECOM_WEBHOOKS:
        all_errors.extend(send_wecom(title, md_content))

    if SERVERCHAN_KEYS:
        all_errors.extend(send_serverchan(title, text_content))

    return all_errors
