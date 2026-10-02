"""手動執行的指令，用法：

docker compose exec bot python -m app.cli test-ai [問題]   不經過 LINE，直接測試 AI 回覆
docker compose exec bot python -m app.cli logs [筆數]      查看最近的對話紀錄 (預設 20 筆)
docker compose exec bot python -m app.cli cleanup          立刻清理超過保留天數的對話紀錄
"""
import logging
import sys

from . import store
from .ai import ask_ai
from .knowledge import build_system_prompt


def test_ai(question="你們幾點開門？可以退貨嗎？"):
    print("Q：" + question)
    print("A：" + ask_ai(build_system_prompt(), [{"role": "user", "content": question}]))


def logs(limit="20"):
    for time, user_id, question, answer in store.recent_logs(int(limit)):
        print(f"[{time}] {user_id}\n  Q：{question}\n  A：{answer}\n")


def cleanup():
    print(f"已刪除 {store.clean_old_logs()} 筆過期紀錄")


COMMANDS = {"test-ai": test_ai, "logs": logs, "cleanup": cleanup}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](*sys.argv[2:])
