"""매크로 파트: 시세·금리·지표·일정 수집(같은 작업 안에서 바로) → 수치 슬라이드(파이썬) + 해설(Claude, 웹 검색).

수치는 전부 데이터에서 파이썬이 직접 표·차트로 만든다(AI가 숫자를 옮겨 적지 않음).
Claude는 수치의 의미, 시장을 움직인 뉴스, 보유주식·서학개미·종합판단을 웹 검색으로 조사해 쓴다.
"""

import csv
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .analyze import SLIDE, STYLE_RULES, _obj, S, SL
from .collect import KST
from .llm import ANALYSIS_MODEL, ask_json

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (market-data GitHub Action)"}
SCRIPTS = ["fetch_market.py", "fetch_macro.py", "fetch_news.py", "fetch_ecos.py", "fetch_history.py", "fetch_breadth.py"]


def log(msg):
    print(f"[macro] {msg}", flush=True)


# ───────────────────────── 수집 ─────────────────────────

def _treasury():
    """미 재무부 일일 국채 수익률(당일 확정치). 최근 2영업일."""
    out = {}
    for y in sorted({datetime.now(timezone.utc).year, (datetime.now(timezone.utc) - timedelta(days=7)).year}, reverse=True):
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
               f"{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
        rows = list(csv.DictReader(io.StringIO(requests.get(url, headers=UA, timeout=30).text)))
        for r in rows:
            d = datetime.strptime(r["Date"], "%m/%d/%Y").strftime("%Y-%m-%d")
            out[d] = {k: float(r[k]) for k in ("2 Yr", "10 Yr", "30 Yr", "3 Mo") if r.get(k)}
        if len(out) >= 2:
            break
    days = sorted(out, reverse=True)[:2]
    return [{"date": d, **out[d]} for d in days]


def _calendar():
    """ForexFactory 주간 경제지표 일정(미국 High/Medium)."""
    ev = []
    for wk in ("thisweek", "nextweek"):
        try:
            r = requests.get(f"https://nfs.faireconomy.media/ff_calendar_{wk}.json", headers=UA, timeout=20)
            if r.status_code != 200:
                continue
            for e in r.json():
                if e.get("country") == "USD" and e.get("impact") in ("High", "Medium"):
                    t = datetime.fromisoformat(e["date"])
                    ev.append({"kst": t.astimezone(KST).strftime("%m/%d(%a) %H:%M"), "et": t.strftime("%m/%d %H:%M"),
                               "title": e.get("title"), "impact": e.get("impact"),
                               "forecast": e.get("forecast") or "", "previous": e.get("previous") or "", "ts": t.timestamp()})
        except Exception as e:
            log(f"캘린더 {wk} 실패: {e.__class__.__name__}")
    ev.sort(key=lambda x: x["ts"])
    return ev


def _earnings(days=8, min_cap=30e9):
    """나스닥 실적 캘린더: 앞으로 days일, 시가총액 min_cap 이상."""
    hdr = {**UA, "Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
    out = []
    today = datetime.now(KST).date()
    for k in range(days):
        day = today + timedelta(days=k)
        if day.weekday() >= 5:
            continue
        try:
            rows = (requests.get(f"https://api.nasdaq.com/api/calendar/earnings?date={day}", headers=hdr, timeout=20)
                    .json().get("data") or {}).get("rows") or []
        except Exception:
            continue
        for r in rows:
            try:
                cap = float(str(r.get("marketCap", "")).replace("$", "").replace(",", "") or 0)
            except ValueError:
                cap = 0
            if cap >= min_cap:
                t = {"time-pre-market": "장전", "time-after-hours": "장후"}.get(r.get("time"), "미정")
                out.append({"date": str(day), "symbol": r.get("symbol"), "name": r.get("name"), "when": t,
                            "eps_forecast": r.get("epsForecast") or "", "cap_b": round(cap / 1e9)})
    out.sort(key=lambda x: (x["date"], -x["cap_b"]))
    return out


# 연준 FOMC 결정일(2일 회의의 둘째 날). 연준 공식 일정 기준 — 매년 갱신 필요.
FOMC = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"]
_MCODE = "FGHJKMNQUVXZ"


def _fomc_dates():
    """연준 홈페이지 FOMC 일정에서 결정일(회의 마지막 날)을 읽는다. 실패하면 내장 목록."""
    import re
    months = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                          "September", "October", "November", "December"], 1)}
    try:
        html = requests.get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", headers=UA, timeout=20).text
        out = []
        parts = re.split(r"(\d{4}) FOMC Meetings", html)
        for y, body in zip(parts[1::2], parts[2::2]):
            for mo, dt in re.findall(r'fomc-meeting__month[^>]*>\s*(?:<strong>)?([A-Za-z/]+).*?fomc-meeting__date[^>]*>\s*([0-9\-]+)', body, re.S):
                mon = months.get(mo.split("/")[-1])
                if mon:
                    out.append(f"{int(y)}-{mon:02d}-{int(dt.split('-')[-1]):02d}")
        if out:
            return sorted(set(out) | set(FOMC))
    except Exception:
        pass
    return FOMC


def _fedwatch(effr):
    """연방기금 선물(ZQ)로 다음 FOMC 2회의 금리 변동 확률 추정(CME FedWatch와 같은 계산 원리, 수치는 다를 수 있음)."""
    import calendar as _cal
    import yfinance as yf
    today = datetime.now(KST).date()
    meets = [datetime.strptime(x, "%Y-%m-%d").date() for x in _fomc_dates()]
    meets = [m for m in meets if m >= today][:2]
    if not meets or effr is None:
        return []

    def implied(y, mth):
        sym = f"ZQ{_MCODE[mth - 1]}{y % 100:02d}.CBT"
        h = yf.Ticker(sym).history(period="5d")
        return 100 - float(h["Close"].dropna().iloc[-1])

    out, pre = [], effr
    for m in meets:
        n = _cal.monthrange(m.year, m.month)[1]
        nxt = (m.year + (m.month == 12), m.month % 12 + 1)
        if m.day > n - 7:  # 월말 회의는 다음 달 계약으로 회의 후 금리를 본다
            post = implied(*nxt)
        else:
            avg = implied(m.year, m.month)
            post = (avg - pre * m.day / n) / ((n - m.day) / n)
        chg = post - pre
        steps = chg / 0.25
        lo = int(steps // 1)
        frac = steps - lo
        probs = {}
        for st_, pr in ((lo, 1 - frac), (lo + 1, frac)):
            if pr > 0.005:
                probs[f"{st_ * 25:+d}bp" if st_ else "동결"] = round(pr * 100, 1)
        out.append({"meeting": str(m), "pre": round(pre, 3), "post": round(post, 3), "change_bp": round(chg * 100, 1), "probs": probs})
        pre = post
    return out


def collect(start_after=None):
    """데이터 수집. start_after(KST datetime)까지 기다렸다가 시작(미국 종가 반영 대기)."""
    if start_after:
        wait = (start_after - datetime.now(KST)).total_seconds()
        if 0 < wait < 3600:
            time.sleep(wait)
    env = dict(os.environ)
    for sc in SCRIPTS:
        try:
            p = subprocess.run([sys.executable, sc], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
            log(f"{sc}: {'ok' if p.returncode == 0 else 'exit ' + str(p.returncode) + ' ' + (p.stderr or '').strip().splitlines()[-1:][0][:200] if (p.stderr or '').strip() else 'exit ' + str(p.returncode)}")
        except Exception as e:
            log(f"{sc}: {e.__class__.__name__}")
    d = {}
    for name in ("market_latest", "macro_latest", "breadth_latest", "news_latest", "krw_official", "history_ytd"):
        try:
            d[name] = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
        except Exception:
            d[name] = {}
    try:
        d["treasury"] = _treasury()
    except Exception as e:
        log(f"treasury 실패: {e.__class__.__name__}")
        d["treasury"] = []
    d["calendar"] = _calendar()
    try:
        d["earnings"] = _earnings()
    except Exception as e:
        log(f"실적 캘린더 실패: {e.__class__.__name__}")
        d["earnings"] = []
    try:
        effr = ((d.get("macro_latest") or {}).get("series", {}).get("DFF") or {}).get("value")
        d["fedwatch"] = _fedwatch(effr)
    except Exception as e:
        log(f"금리 확률 계산 실패: {e.__class__.__name__}")
        d["fedwatch"] = []
    return d


# ───────────────────────── 수치 슬라이드 (파이썬) ─────────────────────────

def _g(d, group):
    return (d.get("market_latest", {}).get("groups", {}) or {}).get(group, {}) or {}


def _ok(it):
    return isinstance(it, dict) and isinstance(it.get("close"), (int, float))


def _pct(v):
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "-"


def _n(v, nd=2):
    if not isinstance(v, (int, float)):
        return "-"
    return f"{v:,.{nd}f}"


def _tone(v):
    return "up" if isinstance(v, (int, float)) and v > 0 else "down" if isinstance(v, (int, float)) and v < 0 else "neutral"


def base_date(d):
    sp = _g(d, "us_indices").get("S&P500", {})
    return sp.get("last_date") or ""


def _blank(tag, title):
    return {"tag": tag, "title": title, "key": "", "kpis": [], "charts": [], "boxes": [], "table_headers": [],
            "table_rows": [], "deep": [], "calc": [], "so_what": "", "sources": "", "refs": []}


def _rows(group, nd=2, date=True):
    rows = []
    for name, it in group.items():
        if not _ok(it):
            rows.append([name, "-", "-", "확인 실패"] + ([""] if date else []))
            continue
        rows.append([name, _n(it["close"], nd), _pct(it.get("change_pct"))] + ([it.get("last_date", "")] if date else []))
    return rows


def _chart(title, group, unit="%", sort=True):
    items = [{"label": n, "value": round(it["change_pct"], 2)}
             for n, it in group.items() if _ok(it) and isinstance(it.get("change_pct"), (int, float))]
    if sort:
        items.sort(key=lambda x: -x["value"])
    return {"kind": "change", "title": title, "unit": unit, "items": items}


def number_slides(d):
    """[(키, 슬라이드)] — 키는 해설(notes)을 붙일 자리."""
    src = "Yahoo Finance(GitHub Actions 자동수집)"
    out = []
    bd = base_date(d)

    us = _g(d, "us_indices")
    s = _blank("US MARKET CLOSE", f"미국 증시 마감 ({bd} 종가, 미 동부시간)")
    for n in ("S&P500", "나스닥종합", "다우존스", "러셀2000", "필라델피아반도체(SOX)", "VIX"):
        it = us.get(n, {})
        if _ok(it):
            s["kpis"].append({"v": f"{_n(it['close'])} ({_pct(it.get('change_pct'))})", "l": n,
                              "tone": _tone(it.get("change_pct"))})
    s["charts"] = [_chart("지수 등락률", {k: v for k, v in us.items() if k != "VIX"}), _chart("매그니피센트7·노키아 등락률", _g(d, "stocks"))]
    s["table_headers"] = ["지수·종목", "종가", "등락률", "기준일"]
    s["table_rows"] = _rows(us) + _rows(_g(d, "stocks"))
    s["sources"] = src
    out.append(("indices", s))

    b = d.get("breadth_latest") or {}
    s = _blank("BREADTH & SECTORS", "시장폭과 섹터·테마 흐름")
    if b.get("count"):
        sp = us.get("S&P500", {}).get("change_pct")
        s["kpis"] = [
            {"v": f"{b['advancers']} / {b['decliners']}", "l": f"S&P500 상승/하락 종목 ({b.get('last_date')})", "tone": _tone(b["advancers"] - b["decliners"])},
            {"v": f"{b['new_52w_highs']} / {b['new_52w_lows']}", "l": "52주 신고가/신저가(종가)", "tone": "neutral"},
            {"v": f"{b['pct_above_50dma']}% · {b['pct_above_200dma']}%", "l": "50일선·200일선 위 종목 비율", "tone": "neutral"},
            {"v": f"{_pct(b['equal_weight_avg_change_pct'])} vs {_pct(sp)}", "l": "동일가중 평균 vs S&P500(시총가중)", "tone": _tone(b["equal_weight_avg_change_pct"])},
        ]
        s["table_headers"] = ["구분", "종목", "섹터", "등락률"]
        s["table_rows"] = ([["상승 상위", f"{x['name']}({x['symbol']})", x.get("sector", ""), _pct(x["change_pct"])] for x in b.get("top_gainers", [])[:5]]
                           + [["하락 상위", f"{x['name']}({x['symbol']})", x.get("sector", ""), _pct(x["change_pct"])] for x in b.get("top_losers", [])[:5]])
    s["charts"] = [_chart("섹터 ETF 11개 등락률(SPDR)", _g(d, "sector_etfs")), _chart("테마 ETF 등락률", _g(d, "theme_etfs"))]
    s["sources"] = src + " · 시장폭은 S&P500 구성종목 기준 직접 계산"
    out.append(("breadth_sectors", s))

    m = (d.get("macro_latest") or {}).get("series", {})
    tr = d.get("treasury") or []
    s = _blank("RATES & CREDIT", "금리·크레딧")
    rows = []
    if tr:
        t0 = tr[0]; t1 = tr[1] if len(tr) > 1 else {}
        for k, lab in (("3 Mo", "3개월"), ("2 Yr", "2년"), ("10 Yr", "10년"), ("30 Yr", "30년")):
            if k in t0:
                ch = (t0[k] - t1[k]) * 100 if k in t1 else None
                rows.append([f"국채 {lab}", f"{t0[k]:.2f}%", f"{ch:+.0f}bp" if ch is not None else "-", f"{t0['date']} (미 재무부)"])
        if "2 Yr" in t0 and "10 Yr" in t0:
            sp_now = (t0["10 Yr"] - t0["2 Yr"]) * 100
            rows.append(["10년-2년 스프레드", f"{sp_now:+.0f}bp", "역전" if sp_now < 0 else "정상(우상향)", t0["date"]])
        if "10 Yr" in t0:
            ch10 = (t0["10 Yr"] - t1.get("10 Yr", t0["10 Yr"])) * 100
            s["kpis"].append({"v": f"{t0['10 Yr']:.2f}% ({ch10:+.0f}bp)", "l": "미 국채 10년", "tone": _tone(ch10)})
        if "2 Yr" in t0:
            ch2 = (t0["2 Yr"] - t1.get("2 Yr", t0["2 Yr"])) * 100
            s["kpis"].append({"v": f"{t0['2 Yr']:.2f}% ({ch2:+.0f}bp)", "l": "미 국채 2년", "tone": _tone(ch2)})
    for sid, lab, unit in (("DFF", "실효연방기금금리(EFFR)", "%"), ("BAMLH0A0HYM2", "하이일드 스프레드(HY OAS)", "%p")):
        it = m.get(sid)
        if it:
            rows.append([lab, f"{it['value']:.2f}{unit}", f"{(it.get('change') or 0) * 100:+.0f}bp", f"{it['period']} (FRED)"])
            if sid == "BAMLH0A0HYM2":
                s["kpis"].append({"v": f"{it['value']:.2f}%p", "l": "HY 스프레드(1영업일 지연)", "tone": _tone(it.get("change") or 0)})
    s["table_headers"] = ["항목", "수준", "전일 대비", "기준"]
    s["table_rows"] = rows
    fw = d.get("fedwatch") or []
    if fw:
        s["boxes"].append({"title": "다음 FOMC 금리 확률(연방기금 선물 기반 추정)", "bullets": [
            f"{x['meeting']} 회의: " + ", ".join(f"{k} {v}%" for k, v in x["probs"].items()) + f" (시장 기대 변화 {x['change_bp']:+.0f}bp)" for x in fw]})
    rec = ((d.get("news_latest") or {}).get("treasury_auctions") or {}).get("recent") or []
    if rec:
        s["boxes"].append({"title": "최근 국채 입찰 결과", "bullets": [
            f"{a['auction_date']} {a['type']} {a['term']}{'(재발행)' if a.get('reopening') == 'Yes' else ''}: "
            + (f"낙찰금리 {a['high_yield']}%" if a.get("high_yield") else f"할인율 {a['high_discount_rate']}%" if a.get("high_discount_rate") else "낙찰금리 -")
            + (f", 응찰률 {a['bid_to_cover']}배" if a.get("bid_to_cover") else "")
            + (f", 해외(간접) {a['indirect_pct']}%" if a.get("indirect_pct") is not None else "")
            for a in rec[:6]]})
    s["sources"] = "미 재무부 일일 국채 수익률 · FRED · CME 연방기금 선물(Yahoo) · 재무부 입찰 결과"
    out.append(("rates", s))

    s = _blank("FX · COMMODITIES · CRYPTO", "환율·원자재·코인")
    fx, cm, cr = _g(d, "fx"), _g(d, "commodities"), _g(d, "crypto")
    k = d.get("krw_official") or {}
    for n in ("원/달러", "달러인덱스(DXY)"):
        it = fx.get(n, {})
        if _ok(it):
            s["kpis"].append({"v": f"{_n(it['close'])} ({_pct(it.get('change_pct'))})", "l": n + (" (글로벌 시세)" if n == "원/달러" else ""), "tone": _tone(it.get("change_pct"))})
    for n in ("WTI", "금"):
        it = cm.get(n, {})
        if _ok(it):
            s["kpis"].append({"v": f"{_n(it['close'])} ({_pct(it.get('change_pct'))})", "l": f"{n} 근월물", "tone": _tone(it.get("change_pct"))})
    s["charts"] = [_chart("원자재 근월물 등락률", cm), _chart("환율·코인 등락률", {**fx, **cr})]
    s["table_headers"] = ["항목", "가격", "등락률", "기준일"]
    s["table_rows"] = _rows(fx, 4) + _rows(cm) + _rows(cr, 0)
    if k.get("status") == "ok":
        s["table_rows"].insert(0, ["원/달러 매매기준율(한국은행)", _n(k.get("value")), _pct(k.get("change_pct")), k.get("date", "")])
    s["sources"] = src + (" · 한국은행 ECOS" if k.get("status") == "ok" else "")
    out.append(("fx_commodities", s))

    s = _blank("GLOBAL MARKETS", "글로벌 증시")
    s["charts"] = [_chart("아시아·유럽 지수 등락률", _g(d, "world_indices"))]
    s["table_headers"] = ["지수", "종가", "등락률", "기준일"]
    s["table_rows"] = _rows(_g(d, "world_indices"))
    s["sources"] = src
    out.append(("global", s))

    s = _blank("MACRO DATA", "물가·고용 지표 (직전 발표치)")
    rows = []
    for sid in ("CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "PPIFIS"):
        it = m.get(sid)
        if it:
            rows.append([it["name"], it["period"][:7], f"{it.get('mom_pct', 0):+.2f}%", f"{it.get('yoy_pct', 0):.2f}%", f"{it.get('prev_yoy_pct', 0):.2f}%"])
    for sid in ("UNRATE", "PAYEMS", "ICSA"):
        it = m.get(sid)
        if it:
            val = f"{it['value']:.1f}%" if sid == "UNRATE" else (f"{it.get('change', 0):+,.0f}천 명" if sid == "PAYEMS" else f"{it['value']:,.0f}")
            prev = f"{it.get('prev_value', 0):.1f}%" if sid == "UNRATE" else (f"{it.get('prev_change', 0):+,.0f}천 명" if sid == "PAYEMS" else f"{it.get('prev_value', 0):,.0f}")
            rows.append([it["name"], it["period"][:10] if sid == "ICSA" else it["period"][:7], val, "", prev])
    s["table_headers"] = ["지표", "해당 기간", "전월비/수준", "전년비", "직전(전년비/수준)"]
    s["table_rows"] = rows
    cpi = m.get("CPIAUCSL")
    if cpi:
        s["kpis"].append({"v": f"{cpi['yoy_pct']:.2f}%", "l": f"CPI 전년비 ({cpi['period'][:7]})", "tone": _tone(cpi["yoy_pct"] - cpi.get("prev_yoy_pct", cpi["yoy_pct"]))})
    un = m.get("UNRATE")
    if un:
        s["kpis"].append({"v": f"{un['value']:.1f}%", "l": f"실업률 ({un['period'][:7]})", "tone": "neutral"})
    s["sources"] = "FRED(BLS·BEA 원자료). 지수에서 계산해 공식 발표 반올림과 0.1%p 다를 수 있음"
    out.append(("macro_data", s))

    h = d.get("history_ytd") or {}
    items = []
    names = {"SPY": "S&P500(SPY)", "QQQ": "나스닥100(QQQ)", "DIA": "다우(DIA)", "IWM": "러셀2000(IWM)", "SOXX": "반도체(SOXX)",
             "UUP": "달러(UUP)", "KRW": "원/달러", "WTI": "WTI", "GOLD": "금", "BTC": "비트코인"}
    y0 = f"{bd[:4]}-01-01" if bd else ""
    for key, lab in names.items():
        ser = h.get(key) or []
        cur = [v for dt, v in ser if dt <= bd] if bd else []
        start = [v for dt, v in sorted(ser) if dt >= y0]
        if cur and start:
            items.append({"label": lab, "value": round((cur[0] / start[0] - 1) * 100, 2)})
    if items:
        s = _blank("YEAR TO DATE", f"연초 대비 등락률 ({bd[:4]}년)")
        s["charts"] = [{"kind": "change", "title": "연초 첫 거래일 대비 등락률", "unit": "%", "items": sorted(items, key=lambda x: -x["value"])}]
        s["sources"] = src
        out.append(("ytd", s))
    return out


def calendar_slide(d):
    s = _blank("CALENDAR", "이번 주·다음 주 주요 일정")
    rows = [[e["kst"], e["et"], e["title"], "★" if e["impact"] == "High" else "", e["forecast"], e["previous"]]
            for e in d.get("calendar", []) if e["ts"] > time.time() - 3600 * 12][:30]
    s["table_headers"] = ["한국시간", "미 동부시간", "미국 지표·이벤트", "중요", "예상", "직전"]
    s["table_rows"] = rows
    auc = (d.get("news_latest") or {}).get("treasury_auctions", {}).get("upcoming", [])[:8]
    if auc:
        s["boxes"].append({"title": "예정 국채 입찰", "bullets": [f"{a['auction_date']} {a['type']} {a['term']}" + (" (재발행)" if a.get("reopening") == "Yes" else "") for a in auc]})
    er = d.get("earnings") or []
    if er:
        s["boxes"].append({"title": "주요 실적 발표(시총 300억달러 이상)", "bullets": [
            f"{e['date'][5:]} {e['when']} {e['name']}({e['symbol']})" + (f" · EPS 예상 {e['eps_forecast']}" if e["eps_forecast"] else "")
            for e in er[:20]]})
    s["sources"] = "ForexFactory 경제 캘린더 · 재무부 입찰 일정 · 나스닥 실적 캘린더"
    return s


# ───────────────────────── 해설 (Claude + 웹 검색) ─────────────────────────

NOTE = _obj({"key": S, "so_what": S, "deep": {"type": "array", "items": _obj({"lead": S, "text": S})}})
COV = {"type": "array", "items": _obj({
    "item": S,
    "status": {"type": "string", "enum": ["확인 완료", "부분 확인", "확인함-해당없음", "확인함(구조적 지연)", "확인 실패"]},
    "source": S, "gap": S})}
NOTE_KEYS = ("indices", "breadth_sectors", "rates", "fx_commodities", "global", "macro_data", "ytd", "calendar")

# 조사를 세 갈래로 나눠 병렬 실행(하나가 실패해도 나머지는 살아남고, 실패한 갈래만 재시도) → 마지막에 짧은 종합 호출
PART_SCHEMAS = {
    "market": _obj({"notes": _obj({k: NOTE for k in NOTE_KEYS}), "coverage": COV}),
    "issues": _obj({"issues": {"type": "array", "items": SLIDE}, "coverage": COV}),
    "holdings": _obj({"holdings": {"type": "array", "items": SLIDE}, "flows": SLIDE, "coverage": COV}),
}
SYNTH_SCHEMA = _obj({"hero": _obj({"headline": S, "verdict": S, "points": SL, "watch": SL}), "verdict": SLIDE})

COV_RULE = """coverage status 판정 기준(엄격히): '확인 완료' = 수치 데이터가 있고 원인·의미를 기사 1건 이상으로 확인(수치만으로 충분한 항목 — 지수·섹터·시장폭·글로벌·원자재 수치,
국채 입찰 결과, FOMC 확률, 일정 — 은 데이터가 있으면 '확인 완료'). '확인함-해당없음' = 찾아봤으나 실제로 새 소식·이벤트가 없음. '확인함(구조적 지연)' = 소스 공표 주기상
최신치가 아님(HY 스프레드 1영업일, 서학개미 결제 3~5영업일). '부분 확인' = 일부 하위 내용만 확인 → gap에 빠진 것을 구체적으로. '확인 실패' = 못 찾음 → gap에 일반적인 사유.
gap은 완료·해당없음이면 빈 문자열. 소스가 막히면 이유를 쓰지 말고 다른 기사로."""

PART_TASKS = {
    "market": """너의 담당: '시장 수치 해설'. 아래 수치 슬라이드 8개에 붙일 해설(notes)만 쓴다. 정책·관세·지정학·개별 기업 뉴스·보유주식·서학개미는 다른 담당이 쓰므로
자세히 쓰지 말 것(필요하면 한 줄 언급만).
조사(WebSearch·WebFetch 합계 12회 이내): ① 미국장 마감 랩업 1~2건 — 오늘의 지배 서사, 지수·섹터·테마(±2% 이상)·상승/하락 상위 종목의 원인
② 연준 인사 발언(누가·톤), FOMC 확률(수치에 있는 선물 기반 추정치와 기사 속 CME FedWatch 비교), 국채 입찰 결과의 의미, ECB·BOJ·BOE·한국은행 동향
③ 원/달러(서울 종가 기사 있으면 병기)·달러·유가·금·코인 변동 원인 ④ 아시아·유럽 증시와 오늘 코스피 개장에 줄 영향 ⑤ 물가·고용 지표의 24시간 내 새 발표 여부·예상치 대비
출력: notes — key=핵심 한 문장, so_what=투자자 시사점, deep=원인·의미 2~4문단(lead=소제목, text=4~6문장, 기사 출처명 괄호)
(indices=지수·M7, breadth_sectors=시장폭·섹터·테마, rates=금리·연준·입찰·FOMC 확률·해외 중앙은행, fx_commodities=환율·원자재·코인, global=아시아·유럽·코스피 영향,
 macro_data=물가·고용, ytd=연초 대비 흐름, calendar=이번 주 일정·실적 발표 해설). 중요한 내용일수록 deep를 길게.
coverage 항목: 지수, 시장폭, 섹터, 금리·연준, FedWatch, 국채입찰, 해외중앙은행, 환율, 원자재, 물가·고용, 글로벌, 크레딧·코인, 일정.""",
    "issues": """너의 담당: '시장을 움직인 이슈'. 정책·관세·무역·규제(반도체·AI·에너지·금융), 지정학, 시장 전체에 영향을 준 대형 기업 뉴스(실적·M&A·소송·대형 계약).
지수·금리·환율 수치 해설, 구글·노키아, 서학개미는 다른 담당이 쓰므로 다루지 말 것.
조사(WebSearch·WebFetch 합계 12회 이내): 최근 24시간(주말이면 직전 거래일 마감 이후) 기사, 중요한 정책은 백악관·USTR·연방관보 등 1차 출처 확인.
출력: issues — 슬라이드 2~4장(이슈당 1장, 같은 사건은 하나로). 진행 중 이슈는 며칠째인지·누적 경과와 오늘 새로 추가된 전개를 구분.
중요한 이슈는 deep 4~6문단, 관련 업종·종목에 미칠 영향과 so_what 포함.
coverage 항목: 무역·정책, 지정학, 기업 뉴스.""",
    "holdings": """너의 담당: '보유주식(구글·노키아)'과 '서학개미 동향'. 다른 주제는 다루지 말 것.
조사(WebSearch·WebFetch 합계 12회 이내, 종목당 4~5회 + 서학개미 2~3회):
- 구글(GOOGL): 디지털광고·검색·클라우드·AI 모델 경쟁 섹터 뉴스와 종목 뉴스(실적·제품·규제), 주가 움직임 이유
- 노키아(NOK): 섹터는 '광통신'으로 볼 것 — AI 데이터센터 광연결 수요, 광네트워크·코히어런트 광모듈·광트랜시버 업황, 동종업체(시에나·루멘텀·코히런트·코닝·패브리넷) 실적·주가. 종목 뉴스(수주·계약·실적)와 주가 이유
- 헤드라인 중 주가에 영향을 줄 만한 것은 기사 원문을 열어 확인(제목만으로 단정 금지)
- 서학개미: 예탁결제원 기반 순매수·순매도 상위, 레버리지·인버스 ETF(SOXL/SOXS 등), 세이브로는 3~5영업일 시차 표기, 텔레그램 요약의 서학개미 데이터 참고
출력: holdings — 정확히 2장, 순서 [구글, 노키아], tag 'HOLDING · GOOGL' / 'HOLDING · NOK'. 종목마다 kpis(종가·등락률과 관련 수치 2~4개),
boxes 3개(① 종목 뉴스 ② 섹터·경쟁사 뉴스 ③ 주가 움직임의 이유와 주시할 점), deep 3~5문단(뉴스별 무슨 일·왜 중요·주가와의 연결, 출처 괄호), so_what.
새 소식이 적으면 짧게, '새로운 소식 없음' 명시. 펀더멘털 심층분석·밸류에이션은 하지 말 것.
flows — 서학개미 동향 1장.
coverage 항목: 보유주식, 서학개미.""",
}


def _compact(d):
    """Claude에게 줄 수치 요약(텍스트)."""
    L = [f"기준 거래일(미 동부): {base_date(d)} / 수집 시각(UTC): {(d.get('market_latest') or {}).get('fetched_at_utc')}"]
    for grp in ("us_indices", "stocks", "optical", "sector_etfs", "theme_etfs", "fx", "commodities", "world_indices", "crypto"):
        L.append(f"[{grp}] " + "; ".join(f"{n} {_n(it['close'])} {_pct(it.get('change_pct'))} ({it.get('last_date')})"
                                         for n, it in _g(d, grp).items() if _ok(it)))
    b = d.get("breadth_latest") or {}
    if b.get("count"):
        L.append(f"[시장폭 S&P500 {b.get('last_date')}] 상승 {b['advancers']} 하락 {b['decliners']} 신고가 {b['new_52w_highs']} 신저가 {b['new_52w_lows']} "
                 f"50일선위 {b['pct_above_50dma']}% 200일선위 {b['pct_above_200dma']}% 동일가중 {b['equal_weight_avg_change_pct']}%; "
                 "상승상위 " + ", ".join(f"{x['symbol']} {x['change_pct']:+.1f}%" for x in b.get("top_gainers", [])[:10])
                 + "; 하락상위 " + ", ".join(f"{x['symbol']} {x['change_pct']:+.1f}%" for x in b.get("top_losers", [])[:10]))
    L.append(f"[미 국채(재무부)] {json.dumps(d.get('treasury'), ensure_ascii=False)}")
    for sid, it in ((d.get("macro_latest") or {}).get("series", {})).items():
        L.append(f"[FRED {sid}] {json.dumps(it, ensure_ascii=False)}")
    n = d.get("news_latest") or {}
    for bank, v in (n.get("central_banks") or {}).items():
        items = v.get("items") or []
        if items:
            L.append(f"[{bank} 최근 72시간] " + " | ".join(f"{i['time_kst']} {i['title']}" for i in items[:6]))
    ta = n.get("treasury_auctions") or {}
    if ta.get("recent"):
        L.append("[최근 국채 입찰] " + json.dumps(ta["recent"], ensure_ascii=False))
    for tk, v in (n.get("holdings_news") or {}).items():
        items = v.get("items") if isinstance(v, dict) else v
        if items:
            L.append(f"[{tk} 헤드라인 36시간] " + " | ".join(f"{i['time_kst']} {i['title']}" for i in items[:12]))
    if d.get("fedwatch"):
        L.append("[다음 FOMC 금리 확률(연방기금 선물로 직접 계산, CME FedWatch와 같은 원리)] " + json.dumps(d["fedwatch"], ensure_ascii=False))
    if d.get("earnings"):
        L.append("[실적 발표 일정(나스닥, 시총 300억달러 이상)] " + "; ".join(f"{e['date']} {e['when']} {e['symbol']}" for e in d["earnings"][:30]))
    L.append("[경제 일정] " + " | ".join(f"{e['kst']} KST {e['title']}({e['impact']}, 예상 {e['forecast']}, 직전 {e['previous']})"
                                        for e in d.get("calendar", [])[:40]))
    return "\n".join(L)


def _part_prompt(part, d, tg_lines, now):
    return f"""지금은 {now:%Y-%m-%d %H:%M} KST. 한국 개인투자자(미국주식 투자)용 데일리 브리핑의 일부를 맡았다.
아래 수치는 오늘 아침 자동 수집한 확정치로, 이미 표·차트로 리포트에 들어간다(재조회 금지, 그대로 인용).

=== 수치 ===
{_compact(d)}

=== 텔레그램 채널 요약(미검증, 별도 '투자 아이디어' 섹션이 따로 있음 — 참고만) ===
{tg_lines}

=== 담당과 조사 ===
{PART_TASKS[part]}
뉴스는 최근 24시간(주말이면 직전 거래일 마감 이후) 기사만, 발행일시를 확인하고 인용. 수치표의 시세는 다시 찾지 말 것.
{COV_RULE}
sources 필드에는 실제 참고한 매체명. 종목 추천 금지. 한국어.

{STYLE_RULES}"""


def _synth(d, parts, now):
    brief = []
    m = parts.get("market") or {}
    for k, v in (m.get("notes") or {}).items():
        brief.append(f"[{k}] {v['key']} / 시사점: {v['so_what']}")
    for s in (parts.get("issues") or {}).get("issues", []):
        brief.append(f"[이슈] {s['title']} — {s['key']} / {s['so_what']}")
    h = parts.get("holdings") or {}
    for s in h.get("holdings", []) + ([h["flows"]] if h.get("flows") else []):
        brief.append(f"[{s['tag']}] {s['title']} — {s['key']} / {s['so_what']}")
    prompt = f"""지금은 {now:%Y-%m-%d %H:%M} KST. 아래는 오늘 데일리 브리핑의 수치와, 각 담당이 쓴 해설의 핵심 문장이다(본문은 리포트에 이미 들어감).

=== 수치 ===
{_compact(d)}

=== 각 담당의 핵심 ===
""" + "\n".join(brief) + f"""

=== 출력 ===
- hero: headline(오늘을 한 줄로), verdict(리스크온/오프 판정과 근거 지표 한 줄), points(오늘 꼭 알아야 할 3~5가지, 각 2~3문장, 수치 포함), watch(오늘·이번 주 주시할 이벤트 2~4개)
- verdict: 종합 판단 슬라이드 1장 — deep 4~6문단: (a) 리스크온/오프(VIX·금리·달러·금·소형주·크레딧 근거, 엇갈리면 그 엇갈림의 의미) (b) 주도 섹터와 자금 이탈
  (c) 향후 심리와 주시 변수 (d) 서학개미 시사점(환율·시간대·세금·환전). 앞 해설을 다시 나열하지 말고 종합 해석에 집중.
웹 검색 없이 위 내용만으로 쓴다. 새로운 사실을 지어내지 말 것.

{STYLE_RULES}"""
    return ask_json(ANALYSIS_MODEL, "데일리 브리핑의 수석 애널리스트. 각 담당의 결론을 종합해 오늘의 판단을 내린다.",
                    [{"type": "text", "text": prompt}], SYNTH_SCHEMA, max_tokens=24000)


def narrative(d, tg_lines):
    """세 갈래 병렬 조사 + 종합. 갈래가 실패해도 나머지로 리포트를 만든다(각 호출은 llm에서 2회 재시도)."""
    from concurrent.futures import ThreadPoolExecutor
    now = datetime.now(KST)
    sysmsg = "미국 증시 매크로·뉴스를 조사해 한국 개인투자자용 데일리 브리핑을 쓰는 시니어 애널리스트."
    parts, failed = {}, []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {k: ex.submit(ask_json, ANALYSIS_MODEL, sysmsg, [{"type": "text", "text": _part_prompt(k, d, tg_lines, now)}],
                             PART_SCHEMAS[k], max_tokens=48000, tools=("WebSearch", "WebFetch"), max_turns=40)
                for k in PART_SCHEMAS}
        for k, f in futs.items():
            try:
                parts[k] = f.result()
            except Exception as e:
                failed.append(k)
                log(f"해설 갈래 '{k}' 실패: {e.__class__.__name__}")
    if not parts:
        raise RuntimeError("매크로 해설 세 갈래 모두 실패")
    try:
        syn = _synth(d, parts, now)
    except Exception as e:
        log(f"종합 판단 실패: {e.__class__.__name__}")
        syn = {}
    cov = []
    for k in ("market", "issues", "holdings"):
        cov += (parts.get(k) or {}).get("coverage", [])
    for k in failed:
        cov.append({"item": {"market": "시장 수치 해설", "issues": "시장을 움직인 이슈", "holdings": "보유주식·서학개미"}[k],
                    "status": "확인 실패", "source": "-", "gap": "해설 생성 오류(재시도 후에도 실패)"})
    return {"hero": syn.get("hero"), "verdict": syn.get("verdict"),
            "notes": (parts.get("market") or {}).get("notes") or {},
            "issues": (parts.get("issues") or {}).get("issues") or [],
            "holdings": (parts.get("holdings") or {}).get("holdings") or [],
            "flows": (parts.get("holdings") or {}).get("flows"),
            "coverage": cov, "failed": failed}


def holding_slides(nar, d):
    """보유종목 슬라이드(구글·노키아 각 1장)에 수집한 헤드라인 표를 붙인다."""
    news = (d.get("news_latest") or {}).get("holdings_news") or {}
    out = []
    for s, tk in zip(nar.get("holdings") or [], ("GOOGL", "NOK")):
        if tk == "NOK":
            peers = {**{k: v for k, v in _g(d, "stocks").items() if k == "노키아"}, **_g(d, "optical")}
            ch = _chart("노키아 vs 광통신 동종업체 등락률", peers)
            if ch["items"]:
                s["charts"] = [ch] + [c for c in s.get("charts", []) if c.get("title") != ch["title"]]
        items = (news.get(tk) or {}).get("items") or []
        if items and not s["table_rows"]:
            s["table_headers"] = ["시각(KST)", "매체", "수집된 헤드라인(최근 36시간)"]
            s["table_rows"] = [[i["time_kst"][5:], i.get("source") or "", i["title"].rsplit(" - ", 1)[0]] for i in items[:8]]
        out.append(s)
    return out


def covered_topics(nar):
    """텔레그램 브리프에 넘길 '이미 다룬 주제' 목록."""
    L = [f"- {x['title']}: {x['key']}" for x in nar.get("issues", [])]
    L += [f"- {k}: {v['key']}" for k, v in (nar.get("notes") or {}).items() if v.get("key")]
    for s in (nar.get("holdings") or []) + ([nar["flows"]] if nar.get("flows") else []):
        L.append(f"- {s['title']}: {s['key']}")
    return "\n".join(L)


def merge(slides, notes):
    """수치 슬라이드에 해설을 붙인다."""
    for key, s in slides:
        n = (notes or {}).get(key) or {}
        s["key"] = n.get("key") or s["key"] or s["title"]
        s["so_what"] = n.get("so_what") or ""
        s["deep"] = n.get("deep") or []
    return [s for _, s in slides]


def coverage_slide(rows, d):
    s = _blank("COVERAGE", "커버리지 체크")
    s["key"] = "각 항목을 어디서 확인했는지와 확인 상태"
    s["table_headers"] = ["항목", "상태", "소스", "부족한 점"]
    s["table_rows"] = [[r["item"], r["status"], r["source"], r.get("gap", "")] for r in rows]
    m = d.get("market_latest") or {}
    s["sources"] = f"시세 수집 {m.get('fetched_at_utc', '-')} UTC, 실패 {len(m.get('failed') or [])}건"
    return s
