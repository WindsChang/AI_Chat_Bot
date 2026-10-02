import logging
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta

from . import config
from .knowledge import read_settings

logger = logging.getLogger(__name__)

# ===== 對話記憶 =====
# 放在記憶體，重啟容器後會重新開始對話
_history = {}
_history_lock = threading.Lock()


def load_history(user_id):
    with _history_lock:
        item = _history.get(user_id)
    if not item or time.time() - item[0] > config.HISTORY_TTL:
        return []
    return list(item[1])


def save_history(user_id, history):
    recent = history[-config.HISTORY_SIZE:]
    # 對話必須從使用者的提問開始
    while recent and recent[0]["role"] != "user":
        recent.pop(0)
    now = time.time()
    with _history_lock:
        _history[user_id] = (now, recent)
        # 順便清掉過期的對話，避免記憶體一直變大
        for key in [k for k, (t, _) in _history.items() if now - t > config.HISTORY_TTL]:
            del _history[key]


# ===== 對話紀錄 (SQLite) =====
def _connect():
    config.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chat_log ("
        "time TEXT NOT NULL, user_id TEXT NOT NULL, question TEXT, answer TEXT)"
    )
    return conn


def _now():
    return datetime.now(config.TZ).strftime("%Y-%m-%d %H:%M:%S")


def log_chat(user_id, question, answer):
    try:
        with closing(_connect()) as conn, conn:
            conn.execute("INSERT INTO chat_log VALUES (?, ?, ?, ?)", (_now(), user_id, question, answer))
    except Exception as err:
        # 紀錄失敗不影響回覆
        logger.error("log_chat failed: %s", err)


def recent_logs(limit):
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM chat_log ORDER BY time DESC LIMIT ?", (limit,)).fetchall()
    return list(reversed(rows))


# 刪除超過保留天數的對話紀錄，每天自動執行
def clean_old_logs():
    try:
        days = int(read_settings().get("紀錄保留天數", ""))
    except ValueError:
        days = 0
    keep_days = days if days > 0 else config.DEFAULT_KEEP_DAYS
    cutoff = (datetime.now(config.TZ) - timedelta(days=keep_days)).strftime("%Y-%m-%d %H:%M:%S")
    with closing(_connect()) as conn, conn:
        count = conn.execute("DELETE FROM chat_log WHERE time < ?", (cutoff,)).rowcount
    logger.info("clean_old_logs: keep %s days, deleted %s rows", keep_days, count)
    return count
