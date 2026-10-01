const P = PropertiesService.getScriptProperties();
// 每位使用者保留的對話則數 (問 + 答各算一則)
const HISTORY_SIZE = 10;
// 多久沒講話就重新開始對話 (秒)
const HISTORY_TTL = 6 * 60 * 60;
// LINE 單則文字訊息上限
const LINE_TEXT_LIMIT = 5000;
// 對話紀錄保留天數，「設定」分頁沒填「紀錄保留天數」時使用
const DEFAULT_KEEP_DAYS = 90;

// ===== LINE Webhook 入口 =====
function doPost(e) {
    const events = JSON.parse(e.postData.contents).events || [];
    events.forEach(ev => {
        // 目前只處理一對一聊天的文字訊息，群組之後再做
        if (ev.source.type !== 'user' || ev.type !== 'message' || ev.message.type !== 'text') return;
        const userId = ev.source.userId;
        const text = ev.message.text.trim();

        // 選單關鍵字：直接回固定內容，不呼叫 AI
        const fixed = findFixedReply(text);
        if (fixed) {
            replyText(ev.replyToken, fixed);
            return;
        }

        showLoading(userId);
        const history = loadHistory(userId);
        history.push({ role: 'user', content: text });
        const answer = askAI(buildSystemPrompt(), history);
        history.push({ role: 'assistant', content: answer });
        saveHistory(userId, history);

        replyText(ev.replyToken, answer);
        logChat(userId, text, answer);
    });
    return ContentService.createTextOutput('OK');
}

// ===== AI 呼叫：只有這裡跟模型有關，之後要換服務只改這裡 =====
function askAI(systemPrompt, history) {
    // 主模型塞車 (503) 或伺服器錯誤 (500) 時，改用備用模型再試一次
    const models = [P.getProperty('GEMINI_MODEL'), P.getProperty('GEMINI_FALLBACK_MODEL')].filter(m => m);
    let res;
    for (const model of models) {
        res = callGemini(model, systemPrompt, history);
        const code = res.getResponseCode();
        if (code !== 503 && code !== 500) break;
        console.error('Gemini ' + model + ' unavailable (' + code + '), trying next model');
    }
    return parseGeminiResponse(res);
}

function callGemini(model, systemPrompt, history) {
    const url = 'https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent';
    return UrlFetchApp.fetch(url, {
        method: 'post',
        contentType: 'application/json',
        headers: { 'x-goog-api-key': P.getProperty('GEMINI_API_KEY') },
        payload: JSON.stringify({
            systemInstruction: { parts: [{ text: systemPrompt }] },
            // Gemini 的角色名稱是 user / model，不是 assistant
            contents: history.map(m => ({
                role: m.role === 'assistant' ? 'model' : 'user',
                parts: [{ text: m.content }]
            }))
        }),
        muteHttpExceptions: true
    });
}

function parseGeminiResponse(res) {
    const code = res.getResponseCode();
    if (code === 429) {
        console.error('Gemini rate limit: ' + res.getContentText());
        return '目前詢問人數較多，請稍等一分鐘再問一次 🙏';
    }
    let body = {};
    try {
        body = JSON.parse(res.getContentText());
    } catch (err) {
        // 錯誤回應不一定是 JSON，交給下面統一處理
    }
    const parts = code === 200 && body.candidates && body.candidates[0].content
        ? body.candidates[0].content.parts || []
        : [];
    const answer = parts.map(p => p.text || '').join('').trim();
    if (!answer) {
        console.error('Gemini error (' + code + '): ' + res.getContentText());
        return '不好意思，系統忙碌中，請稍後再試，或直接來電洽詢 🙏';
    }
    return answer.slice(0, LINE_TEXT_LIMIT);
}

// ===== 組 system prompt：客服規則 + 設定分頁 + FAQ 分頁 =====
function buildSystemPrompt() {
    const settings = readSettings();
    const faq = readRows('FAQ')
        .map(r => 'Q：' + r[0] + '\nA：' + r[1])
        .join('\n\n');
    return [
        '你是「' + (settings['店名'] || '本店') + '」的 LINE 客服。',
        '用繁體中文 (台灣用語) 回答，語氣親切、口語，回答盡量簡短，適合在手機上閱讀。',
        '只能根據下方 <faq> 的內容回答。FAQ 沒有寫到的事情，不要自己推測或編造，'
            + '請回答「這個問題我需要請專人確認」，並請客人留下聯絡電話或來電 '
            + (settings['聯絡電話'] || '本店') + '。',
        '不要使用 Markdown 語法 (例如 **粗體**、# 標題)，LINE 不會顯示格式。',
        settings['補充規則'] || '',
        '<faq>\n' + faq + '\n</faq>'
    ].filter(s => s).join('\n');
}

// ===== 固定回覆：關鍵字完全相符才回 =====
function findFixedReply(text) {
    const row = readRows('固定回覆').find(r => String(r[0]).trim() === text);
    return row ? String(row[1]) : null;
}

// ===== 試算表讀寫 =====
function readRows(sheetName) {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
    if (!sheet || sheet.getLastRow() < 2) return [];
    // 第一列是標題，從第二列開始讀，略過空白列
    return sheet.getRange(2, 1, sheet.getLastRow() - 1, 2).getValues()
        .filter(r => String(r[0]).trim() && String(r[1]).trim());
}

function readSettings() {
    const settings = {};
    readRows('設定').forEach(r => settings[String(r[0]).trim()] = String(r[1]).trim());
    return settings;
}

function logChat(userId, question, answer) {
    try {
        const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('對話紀錄');
        if (sheet) sheet.appendRow([new Date(), userId, question, answer]);
    } catch (err) {
        // 紀錄失敗不影響回覆
        console.error('logChat failed: ' + err);
    }
}

// 刪除超過保留天數的對話紀錄，由每日觸發條件自動執行
function cleanOldLogs() {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('對話紀錄');
    if (!sheet || sheet.getLastRow() < 2) return;
    const days = Number(readSettings()['紀錄保留天數']);
    const keepDays = days > 0 ? days : DEFAULT_KEEP_DAYS;
    const cutoff = new Date(Date.now() - keepDays * 24 * 60 * 60 * 1000);
    const times = sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).getValues();
    // 紀錄依時間往下新增，找出第一筆沒過期的位置，上面的整批刪除
    const firstKept = times.findIndex(r => new Date(r[0]) >= cutoff);
    const count = firstKept === -1 ? times.length : firstKept;
    if (count > 0) sheet.deleteRows(2, count);
    console.log('cleanOldLogs: keep ' + keepDays + ' days, deleted ' + count + ' rows');
}

// ===== 對話記憶 =====
function loadHistory(userId) {
    const raw = CacheService.getScriptCache().get('h_' + userId);
    return raw ? JSON.parse(raw) : [];
}

function saveHistory(userId, history) {
    const recent = history.slice(-HISTORY_SIZE);
    // 對話必須從使用者的提問開始
    while (recent.length && recent[0].role !== 'user') recent.shift();
    try {
        CacheService.getScriptCache().put('h_' + userId, JSON.stringify(recent), HISTORY_TTL);
    } catch (err) {
        // 超過快取大小上限 (100KB) 時就不記，下次重新開始對話
        console.error('saveHistory failed: ' + err);
    }
}

// ===== LINE API =====
// 顯示「輸入中」動畫，AI 回覆送出後會自動消失
function showLoading(userId) {
    UrlFetchApp.fetch('https://api.line.me/v2/bot/chat/loading/start', {
        method: 'post',
        contentType: 'application/json',
        headers: auth(),
        payload: JSON.stringify({ chatId: userId, loadingSeconds: 20 }),
        muteHttpExceptions: true
    });
}

function replyText(replyToken, text) {
    callLine('reply', { replyToken: replyToken, messages: [{ type: 'text', text: text }] });
}

function callLine(type, body) {
    UrlFetchApp.fetch('https://api.line.me/v2/bot/message/' + type, {
        method: 'post',
        contentType: 'application/json',
        headers: auth(),
        payload: JSON.stringify(body)
    });
}

function auth() {
    return { Authorization: 'Bearer ' + P.getProperty('LINE_TOKEN') };
}

// ===== 以下函式在 Apps Script 編輯器手動執行 =====

// 第一次使用時執行：建立分頁、標題列與範例資料 (已存在的分頁不會被覆蓋)
function initSheet() {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const tabs = {
        '設定': [['項目', '內容'],
            ['店名', 'XX 商店'],
            ['聯絡電話', '02-1234-5678'],
            ['補充規則', '稱呼客人為「您」，結尾可以加一個表情符號。'],
            ['紀錄保留天數', DEFAULT_KEEP_DAYS]],
        'FAQ': [['問題', '答案'],
            ['營業時間？', '週一至週五 10:00-19:00，週末公休。'],
            ['可以退換貨嗎？', '收到商品 7 天內可以退換貨，需保留原包裝與發票。'],
            ['運費怎麼算？', '單筆滿 1000 元免運，未滿收 80 元。']],
        '固定回覆': [['關鍵字', '回覆內容'],
            ['聯絡我們', '📞 電話：02-1234-5678\n🕙 服務時間：週一至週五 10:00-19:00']],
        '對話紀錄': [['時間', 'userId', '問題', 'AI 回覆']]
    };
    Object.keys(tabs).forEach(name => {
        if (ss.getSheetByName(name)) return;
        const rows = tabs[name];
        const sheet = ss.insertSheet(name);
        sheet.getRange(1, 1, rows.length, rows[0].length).setValues(rows);
        sheet.setFrozenRows(1);
    });
}

// 建立每日凌晨 3 點自動清理對話紀錄的觸發條件 (重複執行不會建立多個)
function setupCleanupTrigger() {
    ScriptApp.getProjectTriggers()
        .filter(t => t.getHandlerFunction() === 'cleanOldLogs')
        .forEach(t => ScriptApp.deleteTrigger(t));
    ScriptApp.newTrigger('cleanOldLogs').timeBased().everyDays(1).atHour(3).create();
    console.log('已建立每日自動清理觸發條件');
}

// 不經過 LINE，直接測試 AI 回覆，結果看「執行記錄」
function testAI() {
    const question = '你們幾點開門？可以退貨嗎？';
    console.log('Q：' + question);
    console.log('A：' + askAI(buildSystemPrompt(), [{ role: 'user', content: question }]));
}
