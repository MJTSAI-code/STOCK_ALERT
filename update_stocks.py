import json
import os
import datetime
import pytz
import yfinance as yf

# 要追蹤的股票
STOCKS = ['NOW', 'NVDA', 'LITE', 'ONDS', 'MRVL', 'GOOG', 'SPCX', 'TSM', 'MU', 'SNDK']

# 是否要在這次執行中重新抓取新聞（由 .yml 透過環境變數控制，只有盤前那班會設為 true）
UPDATE_NEWS = os.environ.get('UPDATE_NEWS', 'false').lower() == 'true'

def load_existing_news():
    """讀取現有 stock_data.json，把每檔股票舊的新聞保留下來備用"""
    existing_news = {}
    try:
        with open('stock_data.json', 'r', encoding='utf-8') as f:
            old_data = json.load(f)
            for sym, entry in old_data.get('data', {}).items():
                existing_news[sym] = entry.get('news', [])
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return existing_news

def fetch_stock_data():
    output_data = {}
    tw_tz = pytz.timezone('Asia/Taipei')
    existing_news = load_existing_news()

    if UPDATE_NEWS:
        print("📰 本次執行會更新新聞（盤前班次）")
    else:
        print("🤫 本次不更新新聞，沿用既有資料")

    for sym in STOCKS:
        try:
            print(f"正在抓取 {sym}...")
            ticker = yf.Ticker(sym)

            # --- 💡 安全防禦第一層：fast_info（最穩定但欄位較少）---
            # 注意：FastInfo 是物件不是字典，部分 yfinance 版本不支援 .get()，
            # 改用 getattr 才能相容各版本，並印出實際錯誤方便排查
            regular_price = 0.0
            previous_close = 0.0
            try:
                f_info = ticker.fast_info
                regular_price = getattr(f_info, 'last_price', None) or 0.0
                previous_close = getattr(f_info, 'previous_close', None) or 0.0
            except Exception as fe:
                print(f"  ⚠️ {sym} fast_info 讀取失敗: {fe}")

            # --- 💡 安全防禦第二層：history（fast_info 也失敗時的極限補救）---
            if regular_price == 0.0:
                try:
                    hist = ticker.history(period="2d")
                    if not hist.empty:
                        regular_price = float(hist['Close'].iloc[-1])
                        previous_close = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else float(hist['Open'].iloc[-1])
                except Exception as he:
                    print(f"  ⚠️ {sym} history 補救失敗: {he}")

            # --- 💡 處理盤前、盤後欄位（info 是最不穩定的來源，放最後當加值） ---
            pre_price = None
            post_price = None

            try:
                info = ticker.info or {}
                # info 能讀的話，用它的數字優先（通常比 fast_info 更新）
                regular_price = info.get('regularMarketPrice') or info.get('currentPrice') or regular_price
                previous_close = info.get('regularMarketPreviousClose') or info.get('previousClose') or previous_close
                pre_price = info.get('preMarketPrice')
                post_price = info.get('postMarketPrice')
            except Exception as info_err:
                # 即使 info 掛了，前面 fast_info/history 抓到的價格還在，程式不會崩潰
                print(f"  ⚠️ {sym} info 接口受限: {info_err}")

            # 依據抓到的即時欄位決定市場階段
            if pre_price is not None:
                current_price = pre_price
                phase = "盤前"
            elif post_price is not None:
                current_price = post_price
                phase = "盤後"
            else:
                current_price = regular_price
                phase = "正式盤"

            # 計算漲跌
            dollar_change = current_price - previous_close
            percent_change = (dollar_change / previous_close * 100) if previous_close != 0 else 0

            # 新聞處理：只有 UPDATE_NEWS=true 才重新抓取
            if UPDATE_NEWS:
                news_list = []
                try:
                    news_items = ticker.news or []
                    for item in news_items[:1]:
                        title = (
                            item.get('title') or
                            item.get('headline') or
                            (item.get('content', {}).get('title') if isinstance(item.get('content'), dict) else None)
                        )
                        link = (
                            item.get('link') or
                            item.get('url') or
                            (item.get('content', {}).get('canonicalUrl', {}).get('url') if isinstance(item.get('content'), dict) else None)
                        )
                        source = item.get('publisher') or item.get('source') or "Yahoo Finance"

                        if title and title.strip() and link:
                            news_list.append({
                                "headline": title.strip(),
                                "datetime": int(datetime.datetime.now(tw_tz).timestamp()),
                                "source": source,
                                "url": link
                            })
                except Exception as ne:
                    print(f"  {sym} 新聞抓取失敗: {ne}")

                if not news_list:
                    news_list = existing_news.get(sym, []) or [
                        {
                            "headline": "暫無最新新聞",
                            "datetime": int(datetime.datetime.now(tw_tz).timestamp()),
                            "source": "Yahoo Finance",
                            "url": "#"
                        }
                    ]
            else:
                news_list = existing_news.get(sym, []) or [
                    {
                        "headline": "暫無最新新聞",
                        "datetime": int(datetime.datetime.now(tw_tz).timestamp()),
                        "source": "Yahoo Finance",
                        "url": "#"
                    }
                ]

            # 寫入資料（結構維持不變，100% 對接前端）
            output_data[sym] = {
                "quote": {
                    "c": round(float(current_price), 2),
                    "d": round(float(dollar_change), 2),
                    "dp": round(float(percent_change), 4),
                    "regular": round(float(regular_price), 2),
                    "pre": round(float(pre_price), 2) if pre_price is not None else None,
                    "post": round(float(post_price), 2) if post_price is not None else None,
                    "prev_close": round(float(previous_close), 2),
                    "phase": phase
                },
                "news": news_list
            }

            print(f" ✅ {sym} [{phase}] ${current_price:.2f} ({dollar_change:+.2f} / {percent_change:+.2f}%)")

        except Exception as e:
            # 最外層防線：單一股票遭遇不可預期的崩潰，不影響其他股票繼續跑
            print(f" ❌ {sym} 嚴重抓取失敗: {e}")
            output_data[sym] = {
                "quote": {
                    "c": 0.0, "d": 0.0, "dp": 0.0,
                    "regular": 0.0, "pre": None, "post": None,
                    "prev_close": 0.0, "phase": "錯誤"
                },
                "news": existing_news.get(sym, [])
            }

    # 最終輸出
    final_payload = {
        "name": "美股盤前情報資料庫",
        "updated_at": datetime.datetime.now(tw_tz).isoformat(),
        "data": output_data
    }

    with open('stock_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 更新完成！共更新 {len(STOCKS)} 檔股票")
    print(f"📍 更新時間：{datetime.datetime.now(tw_tz).strftime('%Y-%m-%d %H:%M:%S')} 台灣時間")

if __name__ == "__main__":
    fetch_stock_data()
