"""매일 미국장 마감 후 시세를 모아 data/market_latest.json 으로 저장한다.

GitHub Actions에서 실행되며, 매크로 브리핑 예약 작업이 이 JSON을 읽어 쓴다.
각 종목마다 '마지막 거래일'을 함께 저장하므로, 읽는 쪽에서 기준일과 맞는지 확인할 수 있다.
"""

import json
import math
import os
from datetime import datetime, timezone

import yfinance as yf

# 그룹 -> {표시 이름: 야후 심볼}
SYMBOLS = {
    "us_indices": {
        "S&P500": "^GSPC",
        "나스닥종합": "^IXIC",
        "다우존스": "^DJI",
        "러셀2000": "^RUT",
        "필라델피아반도체(SOX)": "^SOX",
        "VIX": "^VIX",
    },
    "fx": {
        "원/달러": "KRW=X",
        "엔/달러": "JPY=X",
        "유로/달러": "EURUSD=X",
        "위안/달러": "CNY=X",
        "달러인덱스(DXY)": "DX-Y.NYB",
    },
    "commodities": {
        "WTI": "CL=F",
        "브렌트": "BZ=F",
        "금": "GC=F",
        "은": "SI=F",
        "구리": "HG=F",
        "천연가스": "NG=F",
    },
    "world_indices": {
        "코스피": "^KS11",
        "코스닥": "^KQ11",
        "니케이225": "^N225",
        "항셍": "^HSI",
        "상해종합": "000001.SS",
        "DAX": "^GDAXI",
        "FTSE100": "^FTSE",
        "STOXX600": "^STOXX",
    },
    "sector_etfs": {
        "기술(XLK)": "XLK",
        "금융(XLF)": "XLF",
        "에너지(XLE)": "XLE",
        "헬스케어(XLV)": "XLV",
        "임의소비재(XLY)": "XLY",
        "필수소비재(XLP)": "XLP",
        "산업재(XLI)": "XLI",
        "소재(XLB)": "XLB",
        "유틸리티(XLU)": "XLU",
        "부동산(XLRE)": "XLRE",
        "커뮤니케이션(XLC)": "XLC",
    },
    "stocks": {
        "애플": "AAPL",
        "마이크로소프트": "MSFT",
        "알파벳": "GOOGL",
        "아마존": "AMZN",
        "엔비디아": "NVDA",
        "메타": "META",
        "테슬라": "TSLA",
        "노키아": "NOK",
    },
    "ytd_etfs": {
        "SPY": "SPY",
        "QQQ": "QQQ",
        "DIA": "DIA",
        "IWM": "IWM",
        "SOXX": "SOXX",
        "VIXY": "VIXY",
        "UUP": "UUP",
    },
    "crypto": {
        "비트코인": "BTC-USD",
        "이더리움": "ETH-USD",
    },
}

# 야후에서 못 받았을 때 FinanceDataReader로 한 번 더 시도할 항목
FDR_FALLBACK = {
    "^KS11": "KS11",
    "^KQ11": "KQ11",
    "KRW=X": "USD/KRW",
}


def _clean(value):
    """NaN/inf를 None으로 바꾸고 소수 4자리로 반올림한다."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, 4)


def _summarize(closes):
    """종가 시리즈(날짜 인덱스)에서 마지막 두 거래일을 뽑아 요약한다."""
    closes = closes.dropna()
    if len(closes) < 2:
        return None
    last_date, last = closes.index[-1], closes.iloc[-1]
    prev_date, prev = closes.index[-2], closes.iloc[-2]
    change = last - prev
    return {
        "last_date": str(last_date.date()),
        "close": _clean(last),
        "prev_date": str(prev_date.date()),
        "prev_close": _clean(prev),
        "change": _clean(change),
        "change_pct": _clean(change / prev * 100) if prev else None,
    }


def fetch_yahoo(tickers):
    """여러 심볼을 한 번에 받아 {심볼: 요약} 으로 돌려준다."""
    data = yf.download(
        tickers,
        period="15d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    out = {}
    for t in tickers:
        try:
            closes = data[t]["Close"] if len(tickers) > 1 else data["Close"]
            out[t] = _summarize(closes)
        except Exception as e:  # 심볼 하나가 실패해도 나머지는 계속
            print(f"[yahoo] {t} 실패: {e}")
            out[t] = None
    return out


def fetch_fdr(code):
    try:
        import FinanceDataReader as fdr

        df = fdr.DataReader(code)
        return _summarize(df["Close"].tail(15))
    except Exception as e:
        print(f"[fdr] {code} 실패: {e}")
        return None


def main():
    all_tickers = sorted({t for group in SYMBOLS.values() for t in group.values()})
    yahoo = fetch_yahoo(all_tickers)

    result = {
        "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": {
            "last_date": "그 종목이 마지막으로 거래된 날짜(거래소 현지 기준). 기준일과 다르면 그날 값이 아직 없거나 휴장이다.",
            "fx": "환율은 글로벌 외환시장 시세로, 서울외환시장 공식 종가가 아니다.",
            "commodities": "원자재는 근월물 선물 가격이다.",
        },
        "groups": {},
        "failed": [],
    }

    for group, items in SYMBOLS.items():
        rows = {}
        for name, ticker in items.items():
            row = yahoo.get(ticker)
            source = "yahoo"
            if row is None and ticker in FDR_FALLBACK:
                row = fetch_fdr(FDR_FALLBACK[ticker])
                source = "financedatareader"
            if row is None:
                result["failed"].append(f"{name}({ticker})")
                rows[name] = {"symbol": ticker, "error": "데이터 없음"}
            else:
                rows[name] = {"symbol": ticker, "source": source, **row}
        result["groups"][group] = rows

    os.makedirs("data", exist_ok=True)
    with open("data/market_latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    ok = sum(len(g) for g in SYMBOLS.values()) - len(result["failed"])
    print(f"저장 완료: 성공 {ok}개, 실패 {len(result['failed'])}개 {result['failed']}")


if __name__ == "__main__":
    main()
