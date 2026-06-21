import json
import os
import datetime
import pytz
import yfinance as yf

# 要追蹤的股票
STOCKS = ['NOW', 'NVDA', 'LITE', 'ONDS', 'MRVL', 'GOOG', 'SPCX', 'TSM']

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
            info = ticker.info

            # 價格資訊
            regular_price = info.get('regularMarketPrice') or info.get('currentPrice') or 0.0
            previous_close = info.get('regularMarketPreviousClose') or info.get('previousClose') or 0.0
            pre_price = info.get('preMarketPrice')
            post_price = info.get('postMarketPrice')

            # 決定目前階段與顯示價格
            if pre_price is not None:
                current_price = pre_price
                phase = "盤前"
            elif post_price is not None:
                current_price = post_price
                phase = "盤後"
            else:
                current_price = regular_price
                phase = "正式盤"

            dollar_change = current_price - previous_close
            percent_change = (dollar_change / previous_close * 100) if previous_close != 0 else 0

            # 新聞處理：只有 UPDATE_NEWS=true（盤前班次）才重新抓取，否則沿用舊資料
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
                    # 這次抓不到，退回舊資料而不是顯示「暫無新聞」，避免覆蓋掉本來有效的新聞
                    news_list = existing_news.get(sym, []) or [
                        {
                            "headline": "暫無最新新聞",
                            "datetime": int(datetime.datetime.now(tw_tz).timestamp()),
                            "source": "Yahoo Finance",
                            "url": "#"
                        }
                    ]
            else:
                # 非盤前班次，直接沿用舊新聞，不呼叫 yfinance news
                news_list = existing_news.get(sym, []) or [
                    {
                        "headline": "暫無最新新聞",
                        "datetime": int(datetime.datetime.now(tw_tz).timestamp()),
                        "source": "Yahoo Finance",
                        "url": "#"
                    }
                ]

            # 寫入資料
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
            print(f" ❌ {sym} 抓取失敗: {e}")
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
