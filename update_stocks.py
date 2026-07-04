import json
import datetime
import pytz
import yfinance as yf

DEFAULT_STOCKS = ['NOW', 'NVDA', 'LITE', 'ONDS', 'MRVL', 'GOOG', 'SPCX', 'TSM', 'MU', 'SNDK', 'TSLA']


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
    tw_minutes = tw_now.hour * 60 + tw_now.minute
    REGULAR_START = 21 * 60 + 30
    POST_START    = 4  * 60
    POST_END      = 4  * 60 + 59
    is_regular = (tw_minutes >= REGULAR_START) or (tw_minutes <= POST_START - 1)
    interval_minutes = 5 if is_regular else 30
    next_dt = tw_now + datetime.timedelta(minutes=interval_minutes)
    boundary = (next_dt.minute // interval_minutes + 1) * interval_minutes
    next_dt  = next_dt.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(minutes=boundary)
    return next_dt.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _fetch_market_headline() -> str:
    """Fetch latest headline from ^SOX (Philadelphia Semiconductor Index) news.

    Falls back to ^GSPC (S&P 500) if SOX news is unavailable.
    Returns empty string on any failure — caller handles gracefully.
    """
    for symbol in ('^SOX', '^GSPC'):
        try:
            ticker = yf.Ticker(symbol)
            news_items = ticker.news or []
            for item in news_items[:3]:
                title: str | None = (
                    item.get('title') or
                    item.get('headline') or
                    (item.get('content', {}).get('title')
                     if isinstance(item.get('content'), dict) else None)
                )
                if title and title.strip():
                    return title.strip()
        except Exception as e:
            print(f"  ⚠️ _fetch_market_headline({symbol}) failed: {e}")
    return ""

def build_alert_summary(output_data: dict, phase: str, tw_now: datetime.datetime, stocks: list[str]) -> str:
    """異動播報：標題句 + 只報顯著漲跌（>±0.5%），綠漲黃平紅跌（美股慣例）。"""
    crash: list[str] = []
    flat:  list[str] = []
    rise:  list[str] = []

    for sym in stocks:
        entry = output_data.get(sym)
        if not entry:
            continue
        dp = entry['quote'].get('dp', 0.0)
        label = f"{sym} {dp:+.2f}%"
        if dp >= 0.5:
            rise.append(label)
        elif dp > -0.5:
            flat.append(label)
        else:
            crash.append(label)

    date_str = tw_now.strftime('%m/%d %H:%M')
    headline = _fetch_market_headline()

    lines = [
        f"🛡 美股播報 | {phase} {date_str}",
        f"📰 {headline}",
        "",
    ]

    def fmt(label: str) -> str:
        sym, pct = label.split(" ", 1)
        return f"<code>{sym}</code> {pct}"

    if crash:
        lines.append("🔴 " + "  ".join(fmt(l) for l in crash))
    if flat:
        lines.append("🟡 " + "  ".join(fmt(l) for l in flat))
    if rise:
        lines.append("🟢 " + "  ".join(fmt(l) for l in rise))

    lines.append("")
    lines.append("📊 完整數據 → https://mjtsai-code.github.io/STOCK_ALERT/")

    return "\n".join(lines)

def build_telegram_message(output_data: dict, phase: str, tw_now: datetime.datetime, stocks: list[str]) -> str:
    """組裝 Telegram 推播文字（純文字，無 Markdown，相容所有客戶端）。"""
    return build_alert_summary(output_data, phase, tw_now, stocks)

def get_display_phase(tw_now: datetime.datetime) -> str:
    """Display phase for alert messages based on TW wall-clock time.
    Independent of yfinance marketState cache.
    """
    tw_minutes = tw_now.hour * 60 + tw_now.minute
    REGULAR_START = 21 * 60 + 30
    POST_START    = 4  * 60
    POST_END      = 4  * 60 + 59
    if (tw_minutes >= REGULAR_START) or (tw_minutes <= POST_START - 1):
        return '正式盤'
    if POST_START <= tw_minutes <= POST_END:
        return '盤後'
    return '盤前'

def fetch_stock_data():
    output_data = {}
    tw_tz = pytz.timezone('Asia/Taipei')
    tw_now = datetime.datetime.now(tw_tz)
    tw_hour = tw_now.hour
    tw_minute = tw_now.minute
    old_data = load_existing_data()
    existing_news = load_existing_news(old_data)

    # ── 股票清單：優先讀 stock_data.json 的 stocks 欄位，fallback 到 DEFAULT ──
    STOCKS: list[str] = old_data.get('stocks', DEFAULT_STOCKS)
    if not STOCKS:
        STOCKS = DEFAULT_STOCKS
    print(f"📋 追蹤股票（{len(STOCKS)} 支）：{', '.join(STOCKS)}")

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

    display_phase = get_display_phase(tw_now)

    for sym in STOCKS:
        try:
            print(f"正在抓取 {sym}...")
            ticker = yf.Ticker(sym)

            regular_price: float = 0.0
            prev_close: float    = 0.0
            pre_price: float | None  = None
            post_price: float | None = None
            info: dict = {}

            try:
                info          = ticker.info or {}
                regular_price = float(info.get('regularMarketPrice') or info.get('currentPrice') or 0.0)
                prev_close    = float(info.get('regularMarketPreviousClose') or info.get('previousClose') or 0.0)
                pre_price     = info.get('preMarketPrice')
                post_price    = info.get('postMarketPrice')
            except Exception as info_err:
                print(f"  ⚠️ {sym} info 接口受限: {info_err}")

            if regular_price == 0.0:
                try:
                    f_info        = ticker.fast_info
                    regular_price = float(getattr(f_info, 'last_price', None) or 0.0)
                    prev_close    = float(getattr(f_info, 'previous_close', None) or prev_close or 0.0)
                except Exception as fe:
                    print(f"  ⚠️ {sym} fast_info 補救失敗: {fe}")

            if regular_price == 0.0:
                try:
                    hist = ticker.history(period="2d")
                    if not hist.empty:
                        regular_price = float(hist['Close'].iloc[-1])
                        prev_close    = (float(hist['Close'].iloc[-2]) if len(hist) >= 2
                                         else float(hist['Open'].iloc[-1]))
                except Exception as he:
                    print(f"  ⚠️ {sym} history 保底失敗: {he}")

            market_state = info.get('marketState', '')
            phase = get_market_phase(market_state)
            print(f"  marketState={market_state!r} → phase={phase}")

            if phase == "盤前" and pre_price is not None:
                current_price = float(pre_price)
            elif phase == "盤後" and post_price is not None:
                current_price = float(post_price)
            else:
                current_price = regular_price

            if phase == "盤後":
                base_price = regular_price
            else:
                base_price = prev_close

            dollar_change  = current_price - base_price
            percent_change = (dollar_change / base_price * 100) if base_price != 0 else 0.0
            reg_change     = regular_price - prev_close
            reg_pct_change = (reg_change / prev_close * 100) if prev_close != 0 else 0.0

            if UPDATE_NEWS:
                news_list = []
                try:
                    news_items = ticker.news or []
                    for item in news_items[:1]:
                        title = (
                            item.get('title') or item.get('headline') or
                            (item.get('content', {}).get('title')
                             if isinstance(item.get('content'), dict) else None)
                        )
                        link = (
                            item.get('link') or item.get('url') or
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

    # 組裝推播訊息並寫出供 yml 讀取
    telegram_msg = build_telegram_message(output_data, display_phase, tw_now, STOCKS)
    with open('telegram_msg.txt', 'w', encoding='utf-8') as f:
        f.write(telegram_msg)
    print("\n📨 推播訊息預覽：")
    print(telegram_msg)

    final_payload = {
        "name": "美股盤前情報資料庫",
        "updated_at": tw_now.isoformat(),
        "next_update_at": calc_next_update_at(tw_now),
        "stocks": STOCKS,
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
