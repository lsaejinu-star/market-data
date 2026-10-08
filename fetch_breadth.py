"""S&P500 구성종목으로 시장폭(breadth)을 계산해 data/breadth_latest.json 으로 저장한다.

거래소 전체(NYSE·나스닥) 집계가 아니라 S&P500 기준이다.
신고가/신저가는 종가 기준(최근 252거래일 종가 최고·최저 경신)이다.
"""

import io
import json
import os
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

HEADERS = {"User-Agent": "Mozilla/5.0 (market-data GitHub Action)"}
WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
FALLBACK = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"


def get_constituents():
    """(심볼, 종목명, 섹터) 목록. 위키백과 실패 시 공개 CSV로 대체."""
    try:
        html = requests.get(WIKI, headers=HEADERS, timeout=30).text
        df = pd.read_html(io.StringIO(html))[0]
        df = df.rename(columns={"Symbol": "symbol", "Security": "name", "GICS Sector": "sector"})
        src = "wikipedia"
    except Exception as e:
        print(f"[breadth] 위키백과 실패, 대체 목록 사용: {e}")
        df = pd.read_csv(io.StringIO(requests.get(FALLBACK, headers=HEADERS, timeout=30).text))
        df = df.rename(columns={"Symbol": "symbol", "Security": "name", "GICS Sector": "sector", "Name": "name", "Sector": "sector"})
        src = "datasets/s-and-p-500-companies"
    df["symbol"] = df["symbol"].astype(str).str.replace(".", "-", regex=False).str.strip()
    return df[["symbol", "name", "sector"]].drop_duplicates("symbol"), src


def compute(closes, meta):
    """closes: 날짜 x 심볼 종가 DataFrame."""
    closes = closes.dropna(how="all")
    # 가장 많은 종목이 거래된 마지막 날을 기준일로
    counts = closes.notna().sum(axis=1)
    last_date = counts[counts >= counts.max() * 0.9].index[-1]
    hist = closes.loc[:last_date]
    last = hist.iloc[-1]
    prev = hist.iloc[-2]
    valid = last.notna() & prev.notna()
    chg = ((last - prev) / prev * 100)[valid]

    window = hist.tail(252)
    hi = window.max()
    lo = window.min()
    ma50 = hist.tail(50).mean()
    ma200 = hist.tail(200).mean()

    n = int(valid.sum())
    adv = int((chg > 0).sum())
    dec = int((chg < 0).sum())
    names = meta.set_index("symbol")["name"].to_dict()
    sectors = meta.set_index("symbol")["sector"].to_dict()

    def movers(series):
        return [
            {"symbol": s, "name": names.get(s), "sector": sectors.get(s), "close": round(float(last[s]), 2), "change_pct": round(float(v), 2)}
            for s, v in series.items()
        ]

    return {
        "last_date": str(last_date.date()),
        "universe": "S&P500 구성종목",
        "count": n,
        "advancers": adv,
        "decliners": dec,
        "unchanged": n - adv - dec,
        "advance_pct": round(adv / n * 100, 1) if n else None,
        "new_52w_highs": int(((last >= hi) & valid).sum()),
        "new_52w_lows": int(((last <= lo) & valid).sum()),
        "pct_above_50dma": round(float((last > ma50)[valid].mean() * 100), 1),
        "pct_above_200dma": round(float((last > ma200)[valid].mean() * 100), 1),
        "equal_weight_avg_change_pct": round(float(chg.mean()), 3),
        "top_gainers": movers(chg.sort_values(ascending=False).head(10)),
        "top_losers": movers(chg.sort_values().head(10)),
    }


def main():
    meta, src = get_constituents()
    tickers = meta["symbol"].tolist()
    data = yf.download(tickers, period="14mo", interval="1d", auto_adjust=True, progress=False, threads=True)
    closes = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data
    result = {
        "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "constituents_source": src,
        "notes": "S&P500 기준 시장폭. 신고가/신저가는 최근 252거래일 종가 기준. 거래소 전체 집계와 다름.",
        **compute(closes, meta),
    }
    os.makedirs("data", exist_ok=True)
    with open("data/breadth_latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"breadth 저장: {result['last_date']} 상승 {result['advancers']} / 하락 {result['decliners']} (총 {result['count']})")


if __name__ == "__main__":
    main()
