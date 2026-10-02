import logging

import yaml

from . import config

logger = logging.getLogger(__name__)


# 每次都重新讀檔，改完 knowledge.yaml 不用重啟就會生效
def load_knowledge():
    try:
        with config.KNOWLEDGE_FILE.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as err:
        logger.error("Failed to load %s: %s", config.KNOWLEDGE_FILE, err)
        return {}


def read_settings(knowledge=None):
    if knowledge is None:
        knowledge = load_knowledge()
    settings = knowledge.get("設定") or {}
    return {str(k).strip(): str(v).strip() for k, v in settings.items() if v is not None}


# ===== 組 system prompt：客服規則 + 設定 + FAQ =====
def build_system_prompt():
    knowledge = load_knowledge()
    settings = read_settings(knowledge)
    faq = "\n\n".join(
        "Q：" + str(item["問"]).strip() + "\nA：" + str(item["答"]).strip()
        for item in knowledge.get("FAQ") or []
        if item and item.get("問") and item.get("答")
    )
    lines = [
        "你是「" + (settings.get("店名") or "本店") + "」的 LINE 客服。",
        "用繁體中文 (台灣用語) 回答，語氣親切、口語，回答盡量簡短，適合在手機上閱讀。",
        "只能根據下方 <faq> 的內容回答。FAQ 沒有寫到的事情，不要自己推測或編造，"
        + "請回答「這個問題我需要請專人確認」，並請客人留下聯絡電話或來電 "
        + (settings.get("聯絡電話") or "本店") + "。",
        "不要使用 Markdown 語法 (例如 **粗體**、# 標題)，LINE 不會顯示格式。",
        settings.get("補充規則", ""),
        "<faq>\n" + faq + "\n</faq>",
    ]
    return "\n".join(s for s in lines if s)


# ===== 固定回覆：關鍵字完全相符才回 =====
def find_fixed_reply(text):
    replies = load_knowledge().get("固定回覆") or {}
    for keyword, reply in replies.items():
        if str(keyword).strip() == text and reply:
            return str(reply).strip()
    return None
