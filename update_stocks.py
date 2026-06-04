import json
import datetime
import pytz
import yfinance as yf

STOCKS = ['NOW', 'NVDA', 'LITE', 'ONDS', 'MRVL', 'GOOG']

def fetch_stock_data():
    output_data = {}

    for sym in STOCKS:
        try:
            print(f"正在抓取 {sym}...")
            ticker = yf.Ticker(sym)
            info = ticker.info

            regular_price  = info.get('regularMarketPrice') or info.get('currentPrice') or 0.0
            previous_close = info.get('regularMarketPreviousClose') or info.get('previousClose') or 0.0
            pre_price      = info.get('preMarketPrice')
            post_price     = info.get('postMarketPrice')

            # 決定顯示價格與盤別
            if pre_price:
                current_price = pre_price
                phase = "盤前"
            elif post_price:
                current_price = post_price
                phase = "盤後"
            else:
                current_price = regular_price
                phase = "正式盤"

            dollar_change  = current_price - previous_close
            percent_change = (dollar_change / previous_close) * 100 if previous_close else 0

            # 新聞：相容新舊兩種 yfinance 格式
            news_list = []
            try:
                for item in (ticker.news or [])[:3]:
                    content = item.get('content', {})

                    title = (
                        content.get('title') or
                        item.get('title') or
                        item.get('headline', '')
                    )
                    link = (
                        (content.get('canonicalUrl') or {}).get('url') or
                        (content.get('clickThroughUrl') or {}).get('url') or
                        item.get('link') or
                        item.get('url', '')
                    )
                    source = (
                        (content.get('provider') or {}).get('displayName') or
                        item.get('publisher', 'Yahoo Finance')
                    )
                    pub = content.get('pubDate') or item.get('providerPublishTime')
                    if isinstance(pub, str):
                        try:
                            dt = datetime.datetime.fromisoformat(pub.replace('Z', '+00:00'))
                            pub = int(dt.timestamp())
                        except:
                            pub = int(datetime.datetime.now().timestamp())
                    if not pub:
                        pub = int(datetime.datetime.now().timestamp())

                    if title and title.strip() and link and link != '#':
                        news_list.append({
                            "headline": title.strip(),
                            "datetime": pub,
                            "source":   source,
                            "url":      link
                        })
            except Exception as ne:
                print(f"  {sym} 新聞失敗: {ne}")

            output_data[sym] = {
                "quote": {
                    "c":            round(current_price,  2),
                    "d":            round(dollar_change,  2),
                    "dp":           round(percent_change, 4),
                    "regular":      round(regular_price,  2),
                    "pre":          round(pre_price,  2) if pre_price  else None,
                    "post":         round(post_price, 2) if post_price else None,
                    "prev_close":   round(previous_close, 2),
                    "phase":        phase
                },
                "news": news_list
            }
            print(f"  ✅ {sym} [{phase}] ${current_price:.2f} ({dollar_change:+.2f}) 新聞:{len(news_list)}則")

        except Exception as e:
            print(f"  ❌ {sym} 失敗: {e}")
            output_data[sym] = {
                "quote": {"c": 0.0, "d": 0.0, "dp": 0.0, "regular": 0.0, "pre": None, "post": None, "prev_close": 0.0, "phase": ""},
                "news": []
            }

    final_payload = {
        "name": "美股盤前情報資料庫",
        "updated_at": datetime.datetime.now(pytz.utc).isoformat(),
        "data": output_data
    }

    with open('stock_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)
    print("✅ stock_data.json 寫入成功！")

if __name__ == "__main__":
    fetch_stock_data()
