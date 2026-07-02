import json
import datetime
import pytz
import yfinance as yf

STOCKS = ['NOW', 'NVDA', 'LITE', 'ONDS', 'MRVL', 'GOOG', 'SPCX', 'TSM', 'MU', 'SNDK', 'TSLA']

def load_existing_data():
    try:
        with open('stock_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def load_existing_news(old_data):
    existing_news = {}
    for sym, entry in old_data.get('data', {}).items():
        existing_news[sym] = entry.get('news', [])
    return existing_news

def get_market_phase(market_state: str) -> str:
    """將 Yahoo Finance marketState 映射至顯示用時段字串。

    以 Yahoo 伺服器端 marketState 作為唯一 source of truth。
    不自行計算台灣時間邊界，徹底消除 preMarketPrice/postMarketPrice
    殘留值（stale cache）造成的 phase 誤判。

    Yahoo Finance marketState 已知值：
      PRE      → 盤前（美東 04:00–09:29）
      REGULAR  → 正式盤（美東 09:30–16:00）
      POST     → 盤後（美東 16:00–20:00）
      POSTPOST → 盤後結束後過渡態，仍顯示盤後
      PREPRE   → 深夜過渡態，無延長交易，顯示昨收基準
      CLOSED   → 週末/假日休市，顯示昨收基準
    """
    _PHASE_MAP: dict[str, str] = {
        'PRE':      '盤前',
        'REGULAR':  '正式盤',
        'POST':     '盤後',
        'POSTPOST': '盤後',
        'PREPRE':   '正式盤',
        'CLOSED':   '正式盤',
    }
    return _PHASE_MAP.get((market_state or '').upper().strip(), '正式盤')

def check_alert_sent(old_data, tw_now, session):
    today = tw_now.strftime('%Y-%m-%d')
    alert_log = old_data.get('alert_sent', {})
    return alert_log.get(session) == today

def mark_alert_sent(final_payload, tw_now, session):
    today = tw_now.strftime('%Y-%m-%d')
    if 'alert_sent' not in final_payload:
        final_payload['alert_sent'] = {}
    final_payload['alert_sent'][session] = today


def calc_next_update_at(tw_now: datetime.datetime) -> str:
    """Calculate the ISO-8601 UTC timestamp of the next expected data update.

    Logic mirrors the GitHub Actions cron schedule:
      - Regular session (TW 21:30-03:59): every 5 min (Actions throttle floor)
      - Pre/Post market  (TW 04:00-21:29): every 30 min
    Returns UTC ISO string so the frontend can use Date.parse() directly.
    """
    tw_minutes = tw_now.hour * 60 + tw_now.minute
    REGULAR_START = 21 * 60 + 30  # 1290
    POST_START    = 4  * 60       # 240
    POST_END      = 4  * 60 + 59  # 299

    is_regular = (tw_minutes >= REGULAR_START) or (tw_minutes <= POST_START - 1)
    interval_minutes = 5 if is_regular else 30

    next_dt = tw_now + datetime.timedelta(minutes=interval_minutes)
    # Truncate to interval boundary for predictability
    boundary = (next_dt.minute // interval_minutes + 1) * interval_minutes
    next_dt  = next_dt.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(minutes=boundary)
    return next_dt.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def fetch_stock_data():
    output_data = {}
    tw_tz = pytz.timezone('Asia/Taipei')
    tw_now = datetime.datetime.now(tw_tz)
    tw_hour = tw_now.hour
    tw_minute = tw_now.minute
    old_data = load_existing_data()
    existing_news = load_existing_news(old_data)

    print(f"🕐 台灣時間：{tw_now.strftime('%Y-%m-%d %H:%M')}（{tw_hour}時{tw_minute}分）")

    morning = (tw_hour == 5 and tw_minute >= 30) or (tw_hour == 6 and tw_minute <= 30)
    evening = (tw_hour == 17 and tw_minute >= 30) or (tw_hour == 18 and tw_minute <= 30)

    if morning:
        session = 'morning'
    elif evening:
        session = 'evening'
    else:
        session = None

    already_sent = check_alert_sent(old_data, tw_now, session) if session else False

    UPDATE_NEWS = (tw_hour >= 5 and tw_hour <= 7)
    print(f"新聞更新: {UPDATE_NEWS} | 推播判斷: session={session} already_sent={already_sent}")

    if session and already_sent:
        print(f"⚠️ 今天 {session} 推播已發送過，跳過推播")
    elif session:
        print(f"✅ 在推播窗口內（{session}），本次將推播")
    else:
        print("🤫 非推播時段，靜默更新")

    send_alert = session is not None and not already_sent
    with open('should_alert.txt', 'w') as f:
        f.write('true' if send_alert else 'false')
    print(f"推播決定: {'true' if send_alert else 'false'}")

    for sym in STOCKS:
        try:
            print(f"正在抓取 {sym}...")
            ticker = yf.Ticker(sym)

            # ── 資料來源優先順序：info（即時）> fast_info（延遲）> history（保底）──
            regular_price: float = 0.0
            prev_close: float    = 0.0
            pre_price: float | None  = None
            post_price: float | None = None
            info: dict = {}

            try:
                info          = ticker.info or {}
                regular_price = float(
                    info.get('regularMarketPrice') or
                    info.get('currentPrice') or
                    0.0
                )
                prev_close = float(
                    info.get('regularMarketPreviousClose') or
                    info.get('previousClose') or
                    0.0
                )
                pre_price  = info.get('preMarketPrice')
                post_price = info.get('postMarketPrice')
            except Exception as info_err:
                print(f"  ⚠️ {sym} info 接口受限: {info_err}")

            # fast_info 補救（info 完全失敗時）
            if regular_price == 0.0:
                try:
                    f_info        = ticker.fast_info
                    regular_price = float(getattr(f_info, 'last_price', None) or 0.0)
                    prev_close    = float(getattr(f_info, 'previous_close', None) or prev_close or 0.0)
                except Exception as fe:
                    print(f"  ⚠️ {sym} fast_info 補救失敗: {fe}")

            # history 最後保底
            if regular_price == 0.0:
                try:
                    hist = ticker.history(period="2d")
                    if not hist.empty:
                        regular_price = float(hist['Close'].iloc[-1])
                        prev_close    = (
                            float(hist['Close'].iloc[-2])
                            if len(hist) >= 2
                            else float(hist['Open'].iloc[-1])
                        )
                except Exception as he:
                    print(f"  ⚠️ {sym} history 保底失敗: {he}")

            # ── phase：以 Yahoo marketState 為 source of truth ──
            market_state = info.get('marketState', '')
            phase = get_market_phase(market_state)
            print(f"  marketState={market_state!r} → phase={phase}")

            if phase == "盤前" and pre_price is not None:
                current_price = float(pre_price)
            elif phase == "盤後" and post_price is not None:
                current_price = float(post_price)
            else:
                current_price = regular_price

            # 漲跌幅基準對齊 TradingView：
            #   盤前：preMarketPrice   vs prev_close    (T-1 正式盤收盤)
            #   正式盤：regularMarketPrice vs prev_close (T-1 正式盤收盤)
            #   盤後：postMarketPrice  vs regular_price (今日正式盤收盤)
            if phase == "盤後":
                base_price = regular_price
            else:
                base_price = prev_close

            dollar_change  = current_price - base_price
            percent_change = (dollar_change / base_price * 100) if base_price != 0 else 0.0

            reg_change     = regular_price - prev_close
            reg_pct_change = (reg_change / prev_close * 100) if prev_close != 0 else 0.0

            # ── 新聞處理（邏輯未變）──
            if UPDATE_NEWS:
                news_list = []
                try:
                    news_items = ticker.news or []
                    for item in news_items[:1]:
                        title = (
                            item.get('title') or
                            item.get('headline') or
                            (item.get('content', {}).get('title')
                             if isinstance(item.get('content'), dict) else None)
                        )
                        link = (
                            item.get('link') or
                            item.get('url') or
                            (item.get('content', {}).get('canonicalUrl', {}).get('url')
                             if isinstance(item.get('content'), dict) else None)
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

            print(f"  ✅ {sym} [{phase}] 現價${current_price:.2f} 基準${base_price:.2f} "
                  f"昨收${prev_close:.2f} 漲跌{dollar_change:+.2f} ({percent_change:+.2f}%)")

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
        "next_update_at": calc_next_update_at(tw_now),
        "data": output_data,
        "alert_sent": old_data.get('alert_sent', {})
    }

    if send_alert:
        mark_alert_sent(final_payload, tw_now, session)
        print(f"📝 已標記今天 {session} 推播完成")

    with open('stock_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 更新完成！共更新 {len(STOCKS)} 檔股票")
    print(f"📍 更新時間：{tw_now.strftime('%Y-%m-%d %H:%M:%S')} 台灣時間")

if __name__ == "__main__":
    fetch_stock_data()
