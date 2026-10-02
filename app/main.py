import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

from . import config, line_api, store
from .ai import ask_ai
from .knowledge import build_system_prompt, find_fixed_reply

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ===== 每日自動清理對話紀錄 =====
async def cleanup_loop():
    while True:
        now = datetime.now(config.TZ)
        next_run = now.replace(hour=config.CLEANUP_HOUR, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            await asyncio.to_thread(store.clean_old_logs)
        except Exception:
            logger.exception("clean_old_logs failed")


@asynccontextmanager
async def lifespan(app):
    missing = [name for name in ("LINE_TOKEN", "LINE_CHANNEL_SECRET", "GEMINI_API_KEY", "GEMINI_MODEL")
               if not getattr(config, name)]
    if missing:
        logger.error("Missing environment variables: %s (check .env)", ", ".join(missing))
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


# 健康檢查，用瀏覽器開 http://localhost:8000/ 看到 OK 就代表服務有起來
@app.get("/", response_class=PlainTextResponse)
def health():
    return "OK"


# ===== LINE Webhook 入口 =====
@app.post("/callback", response_class=PlainTextResponse)
async def callback(request: Request, background: BackgroundTasks, x_line_signature: str = Header(default="")):
    body = await request.body()
    if not line_api.verify_signature(body, x_line_signature):
        logger.warning("Invalid LINE signature, request ignored")
        raise HTTPException(status_code=400, detail="Invalid signature")
    # 先回 200 給 LINE，AI 回覆放到背景處理，避免 LINE 等太久判定逾時
    for ev in json.loads(body).get("events", []):
        background.add_task(handle_event, ev)
    return "OK"


def handle_event(ev):
    # 目前只處理一對一聊天的文字訊息，群組之後再做
    if (ev.get("source", {}).get("type") != "user" or ev.get("type") != "message"
            or ev.get("message", {}).get("type") != "text"):
        return
    try:
        user_id = ev["source"]["userId"]
        text = ev["message"]["text"].strip()

        # 選單關鍵字：直接回固定內容，不呼叫 AI
        fixed = find_fixed_reply(text)
        if fixed:
            line_api.reply_text(ev["replyToken"], fixed)
            return

        line_api.show_loading(user_id)
        history = store.load_history(user_id)
        history.append({"role": "user", "content": text})
        answer = ask_ai(build_system_prompt(), history)
        history.append({"role": "assistant", "content": answer})
        store.save_history(user_id, history)

        line_api.reply_text(ev["replyToken"], answer)
        store.log_chat(user_id, text, answer)
    except Exception:
        logger.exception("handle_event failed")
