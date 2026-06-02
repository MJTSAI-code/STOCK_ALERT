import os
import json
import datetime
import pytz
import yfinance as yf

# 定義我們要監控的 6 檔股票
STOCKS = ['NOW', 'NVDA', 'LITE', 'ONDS', 'MRVL', 'GOOG']

def fetch_stock_data():
    output_data = {}
    
    for sym in STOCKS:
        try:
            print(f"正在抓取 {sym} 的即時數據...")
            ticker = yf.Ticker(sym)
            
            # 1. 抓取股價與漲跌幅
            # 使用 fast_info 確保極速讀取
            info = ticker.fast_info
            current_price = info.last_price
            previous_close = info.previous_close
            
            dollar_change = current_price - previous_close
            percent_change = (dollar_change / previous_close) * 100 if previous_close else 0
            
            # 2. 抓取最新新聞 (取前 3 則)
            news_list = []
            yf_news = ticker.news
            if yf_news:
                for item in yf_news[:3]:
                    news_list.append({
                        "headline": item.get("title", "無新聞標題"),
                        "datetime": item.get("providerPublishTime", int(datetime.datetime.now().timestamp())),
                        "source": item.get("publisher", "Yahoo Finance"),
                        "url": item.get("link", "#")
                    })
            
            # 3. 依照 HTML 的防禦性結構進行打包
            output_data[sym] = {
                "quote": {
                    "c": current_price,
                    "d": dollar_change,
                    "dp": percent_change
                },
                "news": news_list
            }
        except Exception as e:
            print(f"抓取 {sym} 失敗: {e}")
            # 失敗時的防禦性空結構，防止前端 JavaScript 崩潰
            output_data[sym] = {
                "quote": {"c": 0.0, "d": 0.0, "dp": 0.0},
                "news": []
            }

    # 取得當前 ISO 8601 標準時間 (含 UTC 時區)，完美餵給前端進行盤前盤後判定
    now_utc = datetime.datetime.now(pytz.utc).isoformat()
    
    final_payload = {
        "name": "美股盤前情報資料庫",
        "updated_at": now_utc,
        "data": output_data
    }
    
    # 寫入 stock_data.json
    with open('stock_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)
    print("stock_data.json 部署成功！")

if __name__ == "__main__":
    fetch_stock_data()
