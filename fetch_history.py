"""대시보드 YTD 차트용 시계열을 매일 통째로 다시 만들어 data/history_ytd.json 으로 저장한다.

형식은 대시보드의 chart_data_ytd.json 과 같다: {지표: [[날짜, 값], ...]} (최신 날짜가 앞).
매번 전체를 새로 받으므로 빠진 날이 생기지 않는다.
"""

import io
import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import yfinance as yf

HEADERS = {"User-Agent": "Mozilla/5.0 (market-data GitHub Action)"}
START = (datetime.now(timezone.utc) - timedelta(days=430)).strftime("%Y-%m-%d")

YAHOO = {
    "SPY": "SPY", "QQQ": "QQQ", "DIA": "DIA", "IWM": "IWM", "SOXX": "SOXX",
    "VIXY": "VIXY", "UUP": "UUP", "KRW": "KRW=X", "WTI": "CL=F", "GOLD": "GC=F", "BTC": "BTC-USD",
}


def fred(sid):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={START}"
    df = pd.read_csv(io.StringIO(requests.get(url, headers=HEADERS, timeout=30).text))
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().set_index(pd.to_datetime(df.dropna()["date"]))["value"]


def to_pairs(s, nd=4):
    s = s.dropna()
    return [[d.strftime("%Y-%m-%d"), round(float(v), nd)] for d, v in s.sort_index(ascending=False).items()]


def main():
    out, failed = {}, []
    data = yf.download(list(YAHOO.values()), start=START, interval="1d", auto_adjust=False, progress=False, threads=True)
    closes = data["Close"]
    for key, sym in YAHOO.items():
        try:
            pairs = to_pairs(closes[sym])
            if not pairs:
                raise ValueError("empty")
            out[key] = pairs
        except Exception as e:
            print(f"[history] {key} 실패: {e}")
            failed.append(key)
    try:
        out["UST10Y"] = to_pairs(fred("DGS10"), 2)
    except Exception as e:
        print(f"[history] UST10Y 실패: {e}")
        failed.append("UST10Y")
    try:
        cpi = fred("CPIAUCSL")
        yoy = (cpi / cpi.shift(12) - 1) * 100
        out["CPI_YOY"] = to_pairs(yoy, 2)
    except Exception as e:
        print(f"[history] CPI_YOY 실패: {e}")
        failed.append("CPI_YOY")

    os.makedirs("data", exist_ok=True)
    with open("data/history_ytd.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    meta = {
        "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "failed": failed,
        "latest": {k: v[0] for k, v in out.items()},
        "notes": "WTI·GOLD는 근월물 선물(CL=F, GC=F), KRW는 글로벌 시장 시세(KRW=X), UST10Y는 FRED DGS10(1영업일 지연), CPI_YOY는 FRED CPIAUCSL 전년비.",
    }
    with open("data/history_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"history 저장: {len(out)}개 지표, 실패 {failed}")


if __name__ == "__main__":
    main()
