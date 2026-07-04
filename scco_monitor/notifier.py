"""通知推送 — 飞书 / Telegram (可选)."""

import requests

from .config import FEISHU_WEBHOOK, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def push(text: str) -> None:
    if FEISHU_WEBHOOK:
        try:
            requests.post(
                FEISHU_WEBHOOK,
                json={"msg_type": "text", "content": {"text": text}},
                timeout=10,
            )
        except requests.RequestException as e:
            print(f"WARN: 飞书推送失败: {e}")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
                timeout=10,
            )
        except requests.RequestException as e:
            print(f"WARN: Telegram 推送失败: {e}")
