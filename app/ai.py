import logging

import httpx

from . import config

logger = logging.getLogger(__name__)


# ===== AI 呼叫：只有這個檔案跟模型有關，之後要換服務只改這裡 =====
def ask_ai(system_prompt, history):
    # 主模型塞車 (503) 或伺服器錯誤 (500) 時，改用備用模型再試一次
    models = [m for m in (config.GEMINI_MODEL, config.GEMINI_FALLBACK_MODEL) if m]
    res = None
    for model in models:
        res = call_gemini(model, system_prompt, history)
        if res is None or res.status_code not in (500, 503):
            break
        logger.error("Gemini %s unavailable (%s), trying next model", model, res.status_code)
    return parse_gemini_response(res)


def call_gemini(model, system_prompt, history):
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        # Gemini 的角色名稱是 user / model，不是 assistant
        "contents": [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in history
        ],
    }
    try:
        return httpx.post(url, json=payload, headers={"x-goog-api-key": config.GEMINI_API_KEY}, timeout=60)
    except httpx.HTTPError as err:
        logger.error("Gemini %s request failed: %s", model, err)
        return None


def parse_gemini_response(res):
    if res is not None and res.status_code == 429:
        logger.error("Gemini rate limit: %s", res.text)
        return "目前詢問人數較多，請稍等一分鐘再問一次 🙏"
    body = {}
    try:
        body = res.json()
    except Exception:
        # 錯誤回應不一定是 JSON，交給下面統一處理
        pass
    parts = []
    candidates = body.get("candidates") if res is not None and res.status_code == 200 else None
    if candidates:
        parts = (candidates[0].get("content") or {}).get("parts") or []
    answer = "".join(p.get("text", "") for p in parts).strip()
    if not answer:
        if res is None:
            logger.error("Gemini error: no response (check GEMINI_MODEL or network)")
        else:
            logger.error("Gemini error (%s): %s", res.status_code, res.text)
        return "不好意思，系統忙碌中，請稍後再試，或直接來電洽詢 🙏"
    return answer[: config.LINE_TEXT_LIMIT]
