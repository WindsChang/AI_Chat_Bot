import base64
import hashlib
import hmac
import logging

import httpx

from . import config

logger = logging.getLogger(__name__)


# 確認請求真的是 LINE 送來的：用 Channel secret 對 body 算 HMAC-SHA256，跟 header 比對
def verify_signature(body, signature):
    digest = hmac.new(config.LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


# 顯示「輸入中」動畫，AI 回覆送出後會自動消失
def show_loading(user_id):
    _post("https://api.line.me/v2/bot/chat/loading/start", {"chatId": user_id, "loadingSeconds": 20})


def reply_text(reply_token, text):
    _post(
        "https://api.line.me/v2/bot/message/reply",
        {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
    )


def _post(url, body):
    try:
        res = httpx.post(url, json=body, headers={"Authorization": "Bearer " + config.LINE_TOKEN}, timeout=10)
        if res.status_code != 200:
            logger.error("LINE API %s failed (%s): %s", url, res.status_code, res.text)
    except httpx.HTTPError as err:
        logger.error("LINE API %s failed: %s", url, err)
