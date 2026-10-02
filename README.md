# LINE AI 智慧客服

客人在 LINE 官方帳號一對一聊天室提問，機器人依照 `config/knowledge.yaml` 裡的 FAQ，用 Gemini AI 自動回答。

- 執行環境：Python (FastAPI) + Docker，本機測試用 ngrok 對外開放
- AI：Google Gemini API 免費層 (不用綁信用卡)
- 知識庫：`config/knowledge.yaml`，**改答案只要改這個檔案，不用重啟**
- 訊息服務：LINE Messaging API，全部使用回覆訊息 (reply)，不佔免費推播額度

## 運作方式

```
客人提問 → LINE → ngrok → bot 容器 ─┬─ 符合「固定回覆」關鍵字 → 直接回固定內容 (不呼叫 AI)
                                    └─ 其他問題 → Gemini + FAQ → 回覆，並寫入對話紀錄
```

- AI 只根據 FAQ 回答，FAQ 沒寫的會請客人留電話，不會自己編答案
- 會記住同一位客人最近 10 則對話，6 小時沒講話就重新開始 (重啟容器也會重新開始)
- AI 思考時，客人會看到「輸入中」動畫
- 主模型塞車時，自動改用備用模型 (需設定 `GEMINI_FALLBACK_MODEL`)
- 會用 Channel secret 驗證請求確實來自 LINE，其他人亂打網址會被擋掉
- 每天凌晨 3 點自動刪除超過保留天數的對話紀錄
- 目前只處理一對一聊天，群組訊息會略過

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `app/main.py` | Webhook 入口 (`/callback`)、每日清理排程 |
| `app/ai.py` | 呼叫 Gemini，**換 AI 服務只改這個檔案** |
| `app/knowledge.py` | 讀取知識庫、組 system prompt、固定回覆 |
| `app/store.py` | 對話記憶、對話紀錄 (SQLite) |
| `app/line_api.py` | LINE API 呼叫與簽章驗證 |
| `app/cli.py` | 手動執行的指令 (測試 AI、看紀錄、清理) |
| `config/knowledge.yaml` | 知識庫：設定、FAQ、固定回覆 |
| `.env.example` | 金鑰範本，複製成 `.env` 後填入 |
| `Dockerfile`、`docker-compose.yml` | 容器設定，包含 bot 與 ngrok 兩個服務；ngrok 只在測試環境 (`--profile dev`) 啟動 |

## 知識庫 `config/knowledge.yaml`

| 區塊 | 內容 | 用途 |
|------|------|------|
| `設定` | `店名`、`聯絡電話`、`補充規則` (語氣、稱呼等額外要求)、`紀錄保留天數` (沒填預設 90 天) | 組成 AI 的回答規則 |
| `FAQ` | 每一筆有 `問`、`答` | AI 的知識來源，寫越完整 AI 答得越好 |
| `固定回覆` | `關鍵字: 回覆內容` | 客人訊息**完全等於**關鍵字時直接回，給圖文選單按鈕用 |

> ⚠️ YAML 格式要注意：冒號後面要空一格、縮排用空白不要用 Tab；內容含有 `#` 或開頭是數字 (例如電話) 時，用雙引號包起來。格式錯誤時 log 會出現 `Failed to load /config/knowledge.yaml`。

對話紀錄存在 Docker volume 裡的 SQLite 資料庫，用 `logs` 指令查看 (見「手動指令」)。

---

## 操作流程

建議先開一個記事本，把過程中拿到的 key、token、網址暫存在裡面。每一步完成後再做下一步。

### 步驟 1：申請 Gemini API key

1. 打開 [Google AI Studio](https://aistudio.google.com/)，用 Google 帳號登入。
2. 第一次進入會跳出服務條款，勾選同意。
3. 點左側 **Get API key → Create API key**，專案選預設的即可。
4. 複製 `AIza...` 開頭的 key，貼到記事本。
5. 在模型清單找兩個模型，名稱都記到記事本 (以 AI Studio 當下列出的為準)：
   - **主模型**：flash 系列，例如 `gemini-3.8-flash`
   - **備用模型**：flash-lite 系列 (選填，主模型塞車時使用)

✅ 記事本應該有：API key、主模型名稱、備用模型名稱

> ⚠️ 免費層的對話內容可能被 Google 用來改善產品，且有每分鐘、每日請求數限制。**正式給客人使用前，請改用付費層或其他付費 AI**。

### 步驟 2：設定 LINE 官方帳號

**2-1 啟用 Messaging API**

1. 打開 [LINE Official Account Manager](https://manager.line.biz/)，點選你的官方帳號 (還沒有就先按「建立」)。
2. 右上角 **設定** → 左側 **Messaging API** → 按 **啟用 Messaging API**。
3. 第一次會要求建立 Provider (提供者)，名稱自訂。

**2-2 回應設定**

左側 **回應設定**：

| 項目 | 設定 |
|------|------|
| Webhook | **開** |
| 自動回應訊息 | **關** (改由知識庫的「固定回覆」處理，避免重複回覆) |
| 加入好友的歡迎訊息 | 隨意，建議註明「本帳號由 AI 協助回覆」 |

**2-3 取得 Channel secret 與 Channel access token**

1. 打開 [LINE Developers Console](https://developers.line.biz/console/)，點剛剛的 Provider → 點你的頻道。
2. **Basic settings** 分頁 → 找到 **Channel secret**，複製貼到記事本。
3. 上方切到 **Messaging API** 分頁 → 拉到最下面 **Channel access token** → 按 **Issue**。
4. 複製那串很長的 token，貼到記事本。

✅ 記事本應該有：API key、模型名稱、LINE Channel secret、LINE token

> ⚠️ 這兩個值不要搞混：**Channel secret** (Basic settings 分頁，較短) 用來驗證請求，**Channel access token** (Messaging API 分頁，很長) 用來回覆訊息。

### 步驟 3：申請 ngrok authtoken

LINE 只能呼叫公開的 HTTPS 網址，ngrok 會把本機的服務開一個公開網址。

1. 打開 [ngrok](https://dashboard.ngrok.com/signup) 註冊免費帳號。
2. 登入後左側 **Your Authtoken**，複製 token 貼到記事本。

### 步驟 4：設定金鑰

1. 在專案資料夾把 `.env.example` 複製一份，命名為 `.env`。
2. 用記事本打開 `.env`，從記事本複製貼上 (`=` 前後不要有空白)：

   | 變數 | 值 | 必填 |
   |------|----|------|
   | `LINE_TOKEN` | LINE Channel access token | ✅ |
   | `LINE_CHANNEL_SECRET` | LINE Channel secret | ✅ |
   | `GEMINI_API_KEY` | `AIza...` 那串 | ✅ |
   | `GEMINI_MODEL` | 主模型名稱 | ✅ |
   | `GEMINI_FALLBACK_MODEL` | 備用模型名稱，主模型回 503 / 500 時自動改用 | 選填 |
   | `NGROK_AUTHTOKEN` | ngrok authtoken | 只有測試環境需要 |

3. 把 `config/knowledge.yaml` 的範例內容換成自己的 (之後隨時可以改)。

### 步驟 5：啟動服務

Docker 在 WSL2 裡執行，打開 WSL (Ubuntu) 終端機：

```bash
cd "/mnt/c/Users/user/Desktop/Line Bot/AI_Chat_Bot"
docker compose --profile dev up -d --build
```

> 💡 `--profile dev` 代表測試環境，會連 ngrok 一起啟動。正式環境不要加，見「測試環境與正式環境」。

確認服務有起來：

1. 瀏覽器打開 <http://localhost:8000/>，看到 `OK`。
2. 瀏覽器打開 <http://localhost:4040/>，這是 ngrok 的管理頁面，上方會顯示公開網址，例如 `https://xxxx-xxxx.ngrok-free.app`，複製到記事本。

> 💡 免費版 ngrok 每次重啟都會換網址，就要重新貼到 LINE。可以到 ngrok 後台 **Domains** 領一個免費的固定網域，再把 `docker-compose.yml` 裡 ngrok 的 `command` 改成 `http bot:8000 --url=你的網域.ngrok-free.app`，網址就不會變。

### 步驟 6：測試 AI

```bash
docker compose exec bot python -m app.cli test-ai
```

```
Q：你們幾點開門？可以退貨嗎？
A：您好～我們營業時間是週一至週五 10:00-19:00 ...
```

✅ 出現 `A：` 加上依照 FAQ 的回答，就是成功。也可以自己指定問題：`... test-ai "運費怎麼算？"`

❌ 出現「系統忙碌中」時，看上方 `Gemini error (數字)` 的數字：

| 數字 | 原因 | 處理 |
|------|------|------|
| `400` / `403` | API key 錯誤 | 重新複製 key 到 `.env`，確認前後沒有空白，再執行 `docker compose up -d` |
| `404` | 模型名稱錯誤 | 對照 AI Studio 的模型名稱 |
| `503` | Google 端模型塞車，**不是設定問題** | 等幾分鐘再試，或設定 `GEMINI_FALLBACK_MODEL` |

**這一步沒成功前，不要往下做。**

### 步驟 7：串接 LINE

1. 回到 [LINE Developers Console](https://developers.line.biz/console/) → 你的頻道 → **Messaging API** 分頁。
2. **Webhook URL** → **Edit** → 貼上 ngrok 網址，**後面加上 `/callback`**，例如 `https://xxxx-xxxx.ngrok-free.app/callback` → **Update**。
3. 開啟 **Use webhook**。
4. 按 **Verify**，出現 **Success** 就完成。

### 步驟 8：手機實測

1. 在 Messaging API 分頁上方，用手機 LINE 掃 **QR code** 加好友。
2. 依序傳送以下訊息：

   | 傳送 | 預期結果 |
   |------|---------|
   | `營業時間？` | 依照 FAQ 回答 |
   | FAQ 沒有的問題，例如 `你們有賣手機嗎？` | 說要請專人確認、請你留電話，**不會亂編** |
   | `聯絡我們` | 立刻回 `固定回覆` 的內容 |
   | 先問營業時間，再問 `那週六呢？` | 接得上前一句 |

3. 執行 `docker compose exec bot python -m app.cli logs`，確認有剛剛的問答。

🎉 全部正常就完成了。

---

## 手動指令

在專案資料夾 (WSL) 執行：

| 指令 | 說明 |
|------|------|
| `docker compose --profile dev up -d --build` | 測試環境：啟動或更新服務 (bot + ngrok) |
| `docker compose --profile dev down` | 測試環境：停止服務 (對話紀錄會保留) |
| `docker compose up -d --build` | 正式環境：啟動或更新服務 (只有 bot) |
| `docker compose down` | 正式環境：停止服務 (對話紀錄會保留) |
| `docker compose logs -f bot` | 即時查看 bot 的 log，`Ctrl + C` 離開 |
| `docker compose exec bot python -m app.cli test-ai ["問題"]` | 不經過 LINE，直接測試 AI 回覆 |
| `docker compose exec bot python -m app.cli logs [筆數]` | 查看最近的對話紀錄，預設 20 筆 |
| `docker compose exec bot python -m app.cli cleanup` | 立刻清理超過保留天數的對話紀錄 |

> ⚠️ `docker compose down -v` 會連對話紀錄一起刪除，沒有要清空資料不要加 `-v`。

## 搭配圖文選單

在 OA Manager 建立圖文選單時，按鈕動作設為「**文字**」，內容填知識庫 `固定回覆` 裡的關鍵字。客人點按鈕就會回固定內容，不花 AI 額度，其他自由提問才交給 AI。

## 日常維護

| 想做的事 | 做法 | 需要重啟？ |
|----------|------|-----------|
| 新增或修改 FAQ | 改 `config/knowledge.yaml` 的 `FAQ` | 不用 |
| 改店名、電話、語氣 | 改 `config/knowledge.yaml` 的 `設定` | 不用 |
| 新增選單關鍵字 | 改 `config/knowledge.yaml` 的 `固定回覆` | 不用 |
| 改對話紀錄保留天數 | 改 `config/knowledge.yaml` 的 `紀錄保留天數` | 不用 |
| 換 Gemini 模型、換金鑰 | 改 `.env` | **要**，執行 `docker compose up -d` |
| 修改 `app/` 的程式 | 改完執行 `docker compose up -d --build` | **要** |

建議每週看一次對話紀錄，AI 答不出來的問題就補進 `FAQ`。

## 換成付費 AI

只有 `app/ai.py` 跟 Gemini 有關：

- **換成 Gemini 付費層**：在 AI Studio 為該專案啟用計費即可，程式不用改。
- **換成 Claude 或 OpenAI**：改寫 `app/ai.py` 的 `ask_ai()`，其他程式不用動。

## 測試環境與正式環境

ngrok 設定了 `profiles: ["dev"]`，**只有指令加上 `--profile dev` 才會啟動**：

| 環境 | 啟動指令 | 會啟動的服務 | 需要 `NGROK_AUTHTOKEN` |
|------|---------|-------------|----------------------|
| 測試 (本機) | `docker compose --profile dev up -d --build` | bot + ngrok | 要 |
| 正式 | `docker compose up -d --build` | 只有 bot | 不用 |

正式環境不會有 ngrok，需要自行提供對外的 HTTPS 網址，例如：

- 部署到雲端 (例如 Google Cloud Run)，平台會直接給 HTTPS 網址
- 放在自己的主機上，前面加一層有 SSL 憑證的反向代理 (例如 nginx)，轉到 bot 的 8000 port

再把 LINE 的 Webhook URL 改成正式網址 (一樣要加 `/callback`)。

> 💡 測試和正式建議使用**不同的 LINE 頻道**，測試時才不會打到正式客人的聊天室。

---

## 疑難排解

先用 `docker compose logs -f bot` 查看 log，再對照下表：

| 狀況 | 原因 | 解法 |
|------|------|------|
| LINE Verify 失敗，或傳訊息後 log 完全沒有 `/callback` | LINE 沒呼叫到 bot | 確認 ngrok 網址沒換 (看 <http://localhost:4040/>)、Webhook URL 結尾有 `/callback`、Use webhook 已開啟 |
| log 出現 `Invalid LINE signature` | Channel secret 錯誤 | 確認 `.env` 的 `LINE_CHANNEL_SECRET` 是 Basic settings 分頁的 Channel secret，改完執行 `docker compose up -d` |
| log 出現 `Missing environment variables` | `.env` 少填 | 依步驟 4 補上，再執行 `docker compose up -d` |
| log 出現 `LINE API ... failed (401)` | LINE token 錯誤 | 確認 `LINE_TOKEN` 是 Channel access token，前後無空白 |
| ngrok 容器一直重啟 | `NGROK_AUTHTOKEN` 錯誤 | `docker compose logs ngrok` 查看錯誤，重新複製 authtoken |
| 回覆「系統忙碌中」 | Gemini 呼叫失敗 | 依步驟 6 的錯誤數字對照表處理 |
| 回覆「詢問人數較多」 | 超過 Gemini 免費層速率限制 (429) | 等一分鐘再試；常發生的話改用付費層 |
| 回覆很慢 (數十秒) | Gemini 塞車 | 主模型改用 flash-lite 系列 |
| AI 說不知道，但 FAQ 明明有寫 | 讀不到知識庫 | log 有 `Failed to load` 就是 YAML 格式錯誤，依錯誤訊息的行號修正 |
| 改了 `.env` 或程式沒生效 | 容器還在跑舊設定 | 依「日常維護」重啟 |
| `docker compose build` 卡在 `pip install` 連不出去 | WSL 的 proxy 設定 | 先 `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY` 再重試 |

## 安全注意事項

- `LINE_TOKEN`、`LINE_CHANNEL_SECRET`、`GEMINI_API_KEY`、`NGROK_AUTHTOKEN` 只放在 `.env`，**不要寫進程式碼、不要 commit、不要分享給他人** (`.gitignore` 已排除 `.env`)。
- 記事本裡暫存的 key、token 用完就刪除。
- ngrok 網址任何人都能連，但沒有正確簽章的請求會被擋掉；不需要測試時執行 `docker compose --profile dev down` 關閉。
- 對話紀錄會存客人的提問，可能含個資。超過 `紀錄保留天數` 的紀錄會每天自動刪除。
- token 或 key 外流時，到 LINE Developers Console / AI Studio / ngrok 後台重新發行，並更新 `.env`。
