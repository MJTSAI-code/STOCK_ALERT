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
                current_
