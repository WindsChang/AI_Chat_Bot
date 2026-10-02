import os
from pathlib import Path
from zoneinfo import ZoneInfo

# ===== 金鑰與模型：從環境變數 (.env) 讀取，不要寫進程式碼 =====
LINE_TOKEN = os.environ.get("LINE_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "")
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "")

# ===== 檔案位置 =====
# 知識庫 (設定、FAQ、固定回覆)
KNOWLEDGE_FILE = Path(os.environ.get("KNOWLEDGE_FILE", "/config/knowledge.yaml"))
# 對話紀錄資料庫
DB_FILE = Path(os.environ.get("DB_FILE", "/data/chat.db"))

# ===== 行為參數 =====
TZ = ZoneInfo("Asia/Taipei")
# 每位使用者保留的對話則數 (問 + 答各算一則)
HISTORY_SIZE = 10
# 多久沒講話就重新開始對話 (秒)
HISTORY_TTL = 6 * 60 * 60
# LINE 單則文字訊息上限
LINE_TEXT_LIMIT = 5000
# 對話紀錄保留天數，knowledge.yaml 沒填「紀錄保留天數」時使用
DEFAULT_KEEP_DAYS = 90
# 每天幾點自動清理對話紀錄 (台北時間)
CLEANUP_HOUR = 3
