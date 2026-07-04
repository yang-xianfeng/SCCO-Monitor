"""通知推送 — 飞书 / Telegram (可选).

静默跳过未配置的渠道.
"""

import requests

from .config import (
    FEISHU_WEBHOOK,
    HTTP_TIMEOUT,
    TELEGRAM_API_BASE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)


def _push_feishu(text: str) -> None:
    try:
        requests.post(
            FEISHU_WEBHOOK,
            json={"msg_type": "text", "content": {"text": text}},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        print(f"WARN: 飞书推送失败: {e}")


def _push_telegram(text: str) -> None:
    try:
        requests.post(
            f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        print(f"WARN: Telegram 推送失败: {e}")


def push(text: str) -> None:
    if FEISHU_WEBHOOK:
        _push_feishu(text)
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        _push_telegram(text)
