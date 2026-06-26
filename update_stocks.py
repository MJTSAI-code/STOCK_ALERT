import json
import os
import datetime
import pytz
import yfinance as yf

STOCKS = ['NOW', 'NVDA', 'LITE', 'ONDS', 'MRVL', 'GOOG', 'SPCX', 'TSM', 'MU', 'SNDK', 'TSLA']
UPDATE_NEWS = os.environ.get('UPDATE_NEWS', 'false').lower() == 'true'

def load_existing_news():
    existing_news = {}
    try:
        with open('stock_data.json', 'r', encoding='utf-8') as f:
            old_data = json.load(f)
            for sym, entry in old_data.get('data', {}).items():
                existing_news[sym] = entry.get('news', [])
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return existing_news

def get_market_phase(tw_hour, tw_minute, pre_price, post_price):
    """
    根據台灣時間判斷市場階段：
    盤前：台灣時間 05:00 ~ 21:30（美東 16:00 前）
    正式盤：台灣時間 21:30 ~ 04:00
    盤後：台灣時間 04:00 ~ 05:00，以及正式盤結束後
    """
    total_minutes = tw_hour * 60 + tw_minute

    # 盤前時段：台灣 05:00 ~ 21:29
    pre_market_start  = 5 * 60        # 05:00
    pre_market_end    = 21 * 60 + 29  # 21:29

    # 正式盤時段：台灣 21:30 ~ 03:59（隔天）
    regular_start = 21 * 60 + 30  # 21:30
    # 跨午夜處理：03:59 = 239 分鐘

    # 盤後時段：台灣 04:00 ~ 04:59
    post_start = 4 * 60   # 04:00
    post_end   = 4 * 60 + 59  # 04:59

    if pre_price is not None:
        return "盤前"
    if post_price is not None:
        return "盤後"

    # yfinance 沒有回傳盤前/盤後價，用時間判斷
    if pre_market_start <= total_minutes <= pre_market_end:
        return "盤前"
    elif total_minutes >= regular_start or total_minutes <= post_end - 60:
        # 21:30以後 或 凌晨04:00以前 = 正式盤或盤後
        if total_minutes >= regular_start:
            return "正式盤"
        else:
            return "盤後"
    elif post_start <= total_minutes <= post_end:
        return "盤後"
    else:
        return "正式盤"

def fetch_stock_data():
    output_data = {}
    tw_tz = pytz.timezone('Asia/Taipei')
    tw_now = datetime.datetime.now(tw_tz)
    tw_hour = tw_now.hour
    tw_minute = tw_now.minute
    existing_news = load_existing_news()

    if UPDATE_NEWS:
        print("📰 本次執行會更新新聞（盤前班次）")
    else:
        print("🤫 本次不更新新聞，沿用既有資料")

    print(f"🕐 台灣時間：{tw_now.strftime('%Y-%m-%d %H:%M')}（{tw_hour}時{tw_minute}分）")

    for sym in STOCKS:
        try:
            print(f"正在抓取 {sym}...")
            ticker = yf.Ticker(sym)

            regular_price = 0.0
            prev_close = 0.0
            try:
                f_info = ticker.fast_info
                regular_price = getattr(f_info, 'last_price', None) or 0.0
                prev_close = getattr(f_info, 'previous_close', None) or 0.0
            except Exception as fe:
                print(f"  ⚠️ {sym} fast_info 讀取失敗: {fe}")

            if regular_price == 0.0:
                try:
                    hist = ticker.history(period="2d")
                    if not hist.empty:
                        regular_price = float(hist['Close'].iloc[-1])
                        prev_close = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else float(hist['Open'].iloc[-1])
                except Exception as he:
                    print(f"  ⚠️ {sym} history 補救失敗: {he}")

            pre_price = None
            post_price = None

            try:
                info = ticker.info or {}
                regular_price = info.get('regularMarketPrice') or info.get('currentPrice') or regular_price
                prev_close    = info.get('regularMarketPreviousClose') or info.get('previousClose') or prev_close
                pre_price     = info.get('preMarketPrice')
                post_price    = info.get('postMarketPrice')
            except Exception as info_err:
                print(f"  ⚠️ {sym} info 接口受限: {info_err}")

            # 決定市場階段（時間 + yfinance 雙重判斷）
            phase = get_market_phase(tw_hour, tw_minute, pre_price, post_price)

            if phase == "盤前" and pre_price is not None:
                current_price = pre_price
            elif phase == "盤後" and post_price is not None:
                current_price = post_price
            else:
                current_price = regular_price

            # 漲跌：現價 vs 收盤
            dollar_change  = current_price - regular_price
            percent_change = (dollar_change / regular_price * 100) if regular_price != 0 else 0

            # 收盤 vs 前收漲跌
            reg_change     = regular_price - prev_close
            reg_pct_change = (reg_change / prev_close * 100) if prev_close != 0 else 0

            # 新聞處理
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
                                "datetime": int(tw_now.timestamp()),
                                "source": source,
                                "url": link
                            })
                except Exception as ne:
                    print(f"  {sym} 新聞抓取失敗: {ne}")

                if not news_list:
                    news_list = existing_news.get(sym, []) or [{
                        "headline": "暫無最新新聞",
                        "datetime": int(tw_now.timestamp()),
                        "source": "Yahoo Finance", "url": "#"
                    }]
            else:
                news_list = existing_news.get(sym, []) or [{
                    "headline": "暫無最新新聞",
                    "datetime": int(tw_now.timestamp()),
                    "source": "Yahoo Finance", "url": "#"
                }]

            output_data[sym] = {
                "quote": {
                    "c":          round(float(current_price), 2),
                    "d":          round(float(dollar_change), 2),
                    "dp":         round(float(percent_change), 4),
                    "regular":    round(float(regular_price), 2),
                    "reg_d":      round(float(reg_change), 2),
                    "reg_dp":     round(float(reg_pct_change), 4),
                    "pre":        round(float(pre_price), 2) if pre_price is not None else None,
                    "post":       round(float(post_price), 2) if post_price is not None else None,
                    "prev_close": round(float(prev_close), 2),
                    "phase":      phase
                },
                "news": news_list
            }

            print(f"  ✅ {sym} [{phase}] 現價${current_price:.2f} 收盤${regular_price:.2f} 前收${prev_close:.2f} ({reg_change:+.2f} / {reg_pct_change:+.2f}%)")

        except Exception as e:
            print(f"  ❌ {sym} 嚴重抓取失敗: {e}")
            output_data[sym] = {
                "quote": {
                    "c": 0.0, "d": 0.0, "dp": 0.0,
                    "regular": 0.0, "reg_d": 0.0, "reg_dp": 0.0,
                    "pre": None, "post": None,
                    "prev_close": 0.0, "phase": "錯誤"
                },
                "news": existing_news.get(sym, [])
            }

    final_payload = {
        "name": "美股盤前情報資料庫",
        "updated_at": tw_now.isoformat(),
        "data": output_data
    }

    with open('stock_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 更新完成！共更新 {len(STOCKS)} 檔股票")
    print(f"📍 更新時間：{tw_now.strftime('%Y-%m-%d %H:%M:%S')} 台灣時間")

if __name__ == "__main__":
    fetch_stock_data()
