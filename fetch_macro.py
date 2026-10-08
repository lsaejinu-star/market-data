"""FRED에서 물가·고용·금리·크레딧 지표를 받아 data/macro_latest.json 으로 저장한다.

API 키 없이 쓸 수 있는 fredgraph CSV 주소를 사용한다.
FRED의 날짜는 '발표일'이 아니라 '해당 기간'이다 (예: 2026-08-01 = 8월 지표).
"""

import io
import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

START = (datetime.now(timezone.utc) - timedelta(days=800)).strftime("%Y-%m-%d")
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
HEADERS = {"User-Agent": "Mozilla/5.0 (market-data GitHub Action)"}

# id: (표시 이름, 주기, 계산 방식)
#   level  : 값 그대로 (금리·스프레드·실업률 등)
#   index  : 물가지수 -> 전월비·전년비(%) 계산
#   diff   : 전월 대비 증감 (비농업고용, 천 명)
SERIES = {
    # 물가
    "CPIAUCSL": ("CPI 헤드라인(계절조정)", "monthly", "index"),
    "CPILFESL": ("CPI 근원(계절조정)", "monthly", "index"),
    "PCEPI": ("PCE 헤드라인", "monthly", "index"),
    "PCEPILFE": ("PCE 근원", "monthly", "index"),
    "PPIFIS": ("PPI 최종수요", "monthly", "index"),
    # 고용
    "UNRATE": ("실업률(%)", "monthly", "level"),
    "PAYEMS": ("비농업고용(천 명)", "monthly", "diff"),
    "ICSA": ("신규 실업수당청구(건)", "weekly", "level"),
    # 금리
    "DFF": ("실효연방기금금리 EFFR(%)", "daily", "level"),
    "DGS2": ("국채 2년(%)", "daily", "level"),
    "DGS10": ("국채 10년(%)", "daily", "level"),
    "DGS30": ("국채 30년(%)", "daily", "level"),
    "T10Y2Y": ("10년-2년 스프레드(%p)", "daily", "level"),
    # 크레딧
    "BAMLH0A0HYM2": ("하이일드 스프레드 HY OAS(%p)", "daily", "level"),
}


def _r(x, n=4):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if pd.isna(v):
        return None
    return round(v, n)


def fetch_series(sid):
    resp = requests.get(URL.format(sid=sid, start=START), headers=HEADERS, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna().set_index("date")["value"]


def summarize(s, kind):
    if len(s) < 2:
        return None
    last_date, last = s.index[-1], s.iloc[-1]
    prev_date, prev = s.index[-2], s.iloc[-2]
    out = {
        "period": str(last_date.date()),
        "value": _r(last),
        "prev_period": str(prev_date.date()),
        "prev_value": _r(prev),
    }
    if kind == "index":
        out["mom_pct"] = _r((last / prev - 1) * 100, 2)
        year_ago = last_date - pd.DateOffset(years=1)
        if year_ago in s.index:
            out["yoy_pct"] = _r((last / s.loc[year_ago] - 1) * 100, 2)
            prev_year_ago = prev_date - pd.DateOffset(years=1)
            if prev_year_ago in s.index:
                out["prev_yoy_pct"] = _r((prev / s.loc[prev_year_ago] - 1) * 100, 2)
    elif kind == "diff":
        out["change"] = _r(last - prev, 1)
        if len(s) >= 3:
            out["prev_change"] = _r(prev - s.iloc[-3], 1)
    else:
        out["change"] = _r(last - prev)
    return out


def main():
    result = {
        "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "FRED (St. Louis Fed), fredgraph CSV",
        "notes": {
            "period": "지표의 해당 기간(월간 지표는 그 달 1일로 표시). 발표일이 아님.",
            "mom_pct/yoy_pct": "물가지수에서 계산한 전월비·전년비(%). 공식 발표 반올림과 0.1%p 차이 날 수 있음.",
            "daily": "일간 시계열은 1영업일 정도 늦게 반영될 수 있음.",
        },
        "series": {},
        "failed": [],
    }
    for sid, (name, freq, kind) in SERIES.items():
        try:
            row = summarize(fetch_series(sid), kind)
        except Exception as e:
            print(f"[fred] {sid} 실패: {e}")
            row = None
        if row is None:
            result["failed"].append(sid)
            result["series"][sid] = {"name": name, "error": "데이터 없음"}
        else:
            result["series"][sid] = {"name": name, "frequency": freq, **row}

    os.makedirs("data", exist_ok=True)
    with open("data/macro_latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"macro 저장: 실패 {result['failed']}")


if __name__ == "__main__":
    main()
