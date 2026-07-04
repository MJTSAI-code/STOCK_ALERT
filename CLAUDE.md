# CLAUDE.md — 美股情報 PRO 專案開發指南

## 1. 專案概述

- **專案名稱**：美股情報 PRO (`mjtsai-code/STOCK_ALERT`)
- **技術棧**：純 HTML/CSS/JS 前端 + Python 後端 + GitHub Actions 自動化 + GitHub Pages 部署
- **核心檔案**：
  - `index.html` — 桌機版儀表板
  - `WORKNOW_mobile9.html` / `WORKNOW_mobile10.html` — 手機版工作檔
  - `update_stocks.py` — yfinance 資料抓取與推播
  - `stock_data.json` — 唯一資料 source of truth
  - `.github/workflows/update_stocks.yml` — GitHub Actions 排程
- **回應語言**：繁體中文（zh-TW）
- **溝通風格**：精確、工程師導向、直接給核心程式碼

---

## 2. 保護檔案清單（禁止直接修改）

以下檔案為受保護的基準版本，**任何情況下都不得直接修改**：

- `WORKNOW_MOBILE0703FINAL.html` — 手機版受保護基準
- `index_STABLE_20250627.html` — 桌機版受保護基準

**正確流程**：
```
cp PROTECTED_FILE.html CP_WORKSPACE/WORKFILE.html
# 只在 WORKFILE 上操作
# 完成後交付 WORKFILE，不動 PROTECTED_FILE
```

---

## 3. 工作目錄規範

- 所有工作檔案必須在 `/home/claude/CP_WORKSPACE/` 內
- 不得在 CP_WORKSPACE 外自行建立或覆蓋任何檔案
- 覆蓋任何既有檔案前，必須明確告知「即將用 X 覆蓋 Y，Y 將遺失」並等待確認

---

## 4. 核心開發規則

### 4-1. Scope Control（零亂改）
- 只修改被明確要求的程式碼區塊
- 不得主動「順便」改其他地方
- 發現相關問題時：**報告，等待指令，不自行修復**
- 每次 `str_replace` 前必須明確聲明：
  - `This change affects: X`
  - `Does NOT affect: Y`

### 4-2. 變更前分析
- 任何 CSS 改動影響 size / position / animation，必須先建立 standalone demo HTML 驗證，用戶確認後才 port 進目標檔案
- 任何修改前，明確列出所有副作用與風險，確認全部處理後才執行
- 遇到架構模糊或可能破壞既有邏輯時，**停下來詢問，不盲猜**

### 4-3. Anti-Pattern Guard（優先找 Server-side Truth）
- 修改現有邏輯前，先問：**「是否有 server-side / source-of-truth API 欄位已經解決了這個問題？」**
- 若有，優先使用，不要在 client-side patch
- 例：`marketState` 欄位 > 自行計算台灣時間邊界

### 4-4. Patch Escalation Rule
- 同一個 bug 超過兩輪 patch 仍未解決 → **停止 patch，重新從根源診斷**
- 兩次失敗 = 錯誤抽象，不是錯誤 patch

### 4-5. 交付驗證（CRITICAL）
- 任何功能寫入檔案後，必須驗證目標檔案確實包含新代碼
- 驗證 LOG 格式：
  ```
  md5sum <file>
  grep -n "<key_string>" <file>
  sed -n '<start>,<end>p' <file>
  ```
- 「我知道要改什麼」≠「我已經改了」

---

## 5. index.html 專屬規則

- 修改前必須先 `cp index_STABLE_20250627.html CP_WORKSPACE/index.html`
- 只在 `CP_WORKSPACE/index.html` 操作，絕不動 `index_STABLE_20250627.html`
- 不得重建 card DOM 結構（split-left, split-right, panel-flap, TradingView iframe）除非明確要求
- 翻頁動畫（`pfFrontFall` / `pfBackRise`）為受保護邏輯，非明確要求不得觸碰

---

## 6. Python 後端規範

### 資料來源優先順序
```
info（regularMarketPrice）> fast_info（last_price）> history（保底）
```

### Phase 判斷
- 使用 `marketState`（Yahoo server-side truth）作為唯一依據
- 不自行計算台灣時間邊界判斷 phase
- `PHASE_MAP`:
  - `PRE` → 盤前
  - `REGULAR` → 正式盤
  - `POST` / `POSTPOST` → 盤後
  - `PREPRE` / `CLOSED` → 正式盤（休市顯示昨收）

### 漲跌幅基準（對齊 TradingView）
- 盤前：`preMarketPrice` vs `regularMarketPreviousClose`
- 正式盤：`regularMarketPrice` vs `regularMarketPreviousClose`
- 盤後：`postMarketPrice` vs `regularMarketPrice`（今日收盤）

---

## 7. 前端規範

### 動畫
- 桌機翻頁動畫：4-layer `pf-stack`，`overflow:hidden` clipping，`perspective` 在 `.pf-stack`
- 手機 sf-wrap：`animation-play-state: paused` 初始，`reveal-full` class 加上後 `running`
- **禁止使用 `clip-path` 動畫**（無法 GPU 加速，手機卡頓）
- 使用 `opacity` + `transform: translateY` 替代

### Overlay 收合
- `.card-overlay` 使用 `visibility` + `transition: opacity + visibility delay` 方式隱藏
- 禁止用 `display:none` 瞬間切換（造成手機殘影）
- `chartEl.src = ''` 必須在 `onfinish` callback 裡執行，不得在 animate 前執行

---

## 8. GitHub Actions 規範

- 盤中 cron：`*/5 13-21 * * 1-5`（對齊 5 分鐘邊界）
- `next_update_at` 欄位：後端寫入，前端精準 setTimeout 觸發 loadData
- 平日判斷：台灣時間 `TW_DOW` 優先，UTC `UTC_DOW` 備援

---

## 9. MEMORY 指令

- 用戶說 **「MEMORY」**：立即執行 `memory_user_edits add`，不需其他動作
- 用戶說 **「驗證」**：立即輸出 md5sum + diff + grep 驗證 LOG
- 用戶說 **「改」或等效明確指令**：才執行修改，「你覺得好嗎」不是指令

---

## 10. 執行哲學

- Think before coding：先假設、先問、先分析，再動手
- Simplicity first：能 50 行解決不寫 200 行
- Every changed line must trace to the user's request
- If it feels hacky, find the right abstraction
- Security by default：validate inputs, least privilege
