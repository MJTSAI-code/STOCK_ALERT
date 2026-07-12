"""Generate symbols.json — US stock symbol/name library for frontend search validation.

Primary source: NASDAQ Trader official daily symbol directories (no key, public).
Fallback source: SEC company_tickers.json (requires User-Agent header).

Output format (compact, ~300-400KB for ~10k symbols):
    [["AAPL", "Apple Inc. - Common Stock"], ["NVDA", "..."], ...]

Run monthly via update_symbols.yml. Commits only when content changed.
"""
import json
import re
import sys
import urllib.request

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
SEC_URL = "https://www.sec.gov/files/company_tickers.json"
OUT_PATH = "symbols.json"

# Frontend injects symbol into inline onclick — restrict to safe charset.
_SYM_RE = re.compile(r"^[A-Z0-9.\-^$]{1,12}$")


def _fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "STOCK_ALERT symbols updater (github.com/mjtsai-code/STOCK_ALERT)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_pipe_file(text: str, sym_idx: int, name_idx: int, test_idx: int) -> list[tuple[str, str]]:
    """Parse NASDAQ Trader pipe-delimited file. Skips header row and
    'File Creation Time' footer. Skips test issues (Test Issue == Y).
    """
    rows: list[tuple[str, str]] = []
    lines = text.splitlines()
    for line in lines[1:]:  # skip header
        if line.startswith("File Creation Time") or not line.strip():
            continue
        parts = line.split("|")
        if len(parts) <= max(sym_idx, name_idx, test_idx):
            continue
        sym = parts[sym_idx].strip().upper()
        name = parts[name_idx].strip()
        test_flag = parts[test_idx].strip().upper()
        if test_flag == "Y":
            continue
        if not _SYM_RE.match(sym) or not name:
            continue
        rows.append((sym, name))
    return rows


def fetch_from_nasdaq_trader() -> list[tuple[str, str]]:
    # nasdaqlisted.txt: Symbol|Security Name|Market Category|Test Issue|...
    nasdaq = _parse_pipe_file(_fetch(NASDAQ_URL), sym_idx=0, name_idx=1, test_idx=3)
    print(f"  nasdaqlisted: {len(nasdaq)} symbols")
    # otherlisted.txt: ACT Symbol|Security Name|Exchange|CUSIP|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
    other = _parse_pipe_file(_fetch(OTHER_URL), sym_idx=0, name_idx=1, test_idx=6)
    print(f"  otherlisted:  {len(other)} symbols")
    return nasdaq + other


def fetch_from_sec() -> list[tuple[str, str]]:
    data = json.loads(_fetch(SEC_URL))
    rows: list[tuple[str, str]] = []
    for entry in data.values():
        sym = str(entry.get("ticker", "")).strip().upper()
        name = str(entry.get("title", "")).strip()
        if _SYM_RE.match(sym) and name:
            rows.append((sym, name))
    print(f"  SEC fallback: {len(rows)} symbols")
    return rows


def main() -> int:
    rows: list[tuple[str, str]] = []
    try:
        rows = fetch_from_nasdaq_trader()
    except Exception as e:
        print(f"⚠️ NASDAQ Trader 來源失敗: {e}，改用 SEC 備援")
        try:
            rows = fetch_from_sec()
        except Exception as e2:
            print(f"❌ SEC 備援也失敗: {e2}")
            return 1

    # Dedup (nasdaq+other overlap is rare but possible), sort for stable diff
    seen: dict[str, str] = {}
    for sym, name in rows:
        if sym not in seen:
            seen[sym] = name
    merged = sorted(seen.items())

    # Sanity gate: a broken source returning a tiny list must NOT clobber a
    # good existing library. 8000 is well below the real universe (~10-11k).
    if len(merged) < 8000:
        print(f"❌ 字庫僅 {len(merged)} 筆（<8000），疑似來源異常，拒絕覆寫")
        return 1

    payload = json.dumps([[s, n] for s, n in merged], ensure_ascii=False, separators=(",", ":"))
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            if f.read() == payload:
                print("✅ 字庫無變動，跳過寫入")
                return 0
    except FileNotFoundError:
        pass

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(payload)
    print(f"🎉 symbols.json 更新完成：{len(merged)} 筆")
    return 0


if __name__ == "__main__":
    sys.exit(main())
