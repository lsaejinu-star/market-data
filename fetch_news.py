"""국채 입찰 결과, 중앙은행·연준 발표(RSS), 보유주식 뉴스 헤드라인을 모아 data/news_latest.json 으로 저장한다."""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (market-data GitHub Action)"}
NOW = datetime.now(timezone.utc)
KST = timezone(timedelta(hours=9))

# 중앙은행·연준 공식 RSS (주소 후보를 순서대로 시도)
CB_FEEDS = {
    "Fed 보도자료": ["https://www.federalreserve.gov/feeds/press_all.xml"],
    "Fed 연설": ["https://www.federalreserve.gov/feeds/speeches.xml"],
    "ECB": ["https://www.ecb.europa.eu/rss/press.html"],
    "BOE": ["https://www.bankofengland.co.uk/rss/news"],
    "BOJ": ["https://www.boj.or.jp/en/rss/whatsnew.xml"],
    "BOK(한국은행)": [
        "https://www.bok.or.kr/portal/bbs/B0000338/news.rss?menuNo=200761",
        "https://www.bok.or.kr/eng/bbs/E0000634/news.rss?menuNo=400069",
    ],
}
CB_HOURS = 72  # 주말을 넘겨도 놓치지 않도록 3일치

# 보유주식 뉴스 (구글 뉴스 RSS)
HOLDINGS = {
    "GOOGL": ["Alphabet Google stock", "구글 알파벳 주가"],
    "NOK": ["Nokia stock", "노키아 주가", "Nokia optical networking", "optical networking AI data center Ciena Lumentum Coherent"],
}
NEWS_HOURS = 36
NEWS_MAX = 15


def _when(entry):
    for key in ("published", "updated"):
        val = entry.get(key)
        if val:
            try:
                return parsedate_to_datetime(val).astimezone(timezone.utc)
            except Exception:
                pass
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            return datetime(*val[:6], tzinfo=timezone.utc)
    return None


def _item(entry, source=None):
    t = _when(entry)
    return {
        "time_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None,
        "time_kst": t.astimezone(KST).strftime("%Y-%m-%d %H:%M") if t else None,
        "title": re.sub(r"\s+", " ", entry.get("title", "")).strip(),
        "source": source or (entry.get("source") or {}).get("title"),
        "url": entry.get("link"),
    }


def read_feed(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if not feed.entries:
        raise ValueError("빈 피드")
    return feed.entries


def central_banks():
    out = {}
    cutoff = NOW - timedelta(hours=CB_HOURS)
    for name, urls in CB_FEEDS.items():
        out[name] = {"status": "error", "items": []}
        for url in urls:
            try:
                entries = read_feed(url)
            except Exception as e:
                out[name]["status"] = f"error: {e.__class__.__name__}"
                continue
            items = [_item(e) for e in entries]
            recent = [i for i in items if i["time_utc"] and i["time_utc"] >= cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")]
            out[name] = {"status": "ok", "feed": url, "items": recent[:15], "latest_any": items[:3] if not recent else []}
            break
    return out


def holdings_news():
    out = {}
    cutoff = (NOW - timedelta(hours=NEWS_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for ticker, queries in HOLDINGS.items():
        seen, items, errors = set(), [], []
        for q in queries:
            ko = any("가" <= ch <= "힣" for ch in q)
            hl, gl, ceid = ("ko", "KR", "KR:ko") if ko else ("en-US", "US", "US:en")
            url = f"https://news.google.com/rss/search?q={requests.utils.quote(q + ' when:2d')}&hl={hl}&gl={gl}&ceid={ceid}"
            try:
                for e in read_feed(url):
                    it = _item(e)
                    key = it["title"].lower()[:80]
                    if it["time_utc"] and it["time_utc"] >= cutoff and key not in seen:
                        seen.add(key)
                        items.append(it)
            except Exception as e:
                errors.append(f"{q}: {e.__class__.__name__}")
        items.sort(key=lambda i: i["time_utc"], reverse=True)
        out[ticker] = {"items": items[:NEWS_MAX], "errors": errors}
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


FISCAL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od"


def _fiscal(path, params):
    r = requests.get(f"{FISCAL}/{path}", params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("data") or []


def _val(x):
    return None if x in (None, "", "null") else x


def treasury_auctions():
    """국채 입찰 결과·예정. 1순위 재무부 FiscalData API(필드명이 문서화돼 있음), 실패 시 TreasuryDirect."""
    out = {"recent": [], "upcoming": [], "errors": [], "source": "FiscalData"}
    since = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        for a in _fiscal("auctions_query", {"filter": f"auction_date:gte:{since}", "sort": "-auction_date", "page[size]": 100}):
            comp = _num(a.get("comp_accepted"))
            ind = _num(a.get("indirect_bidder_accepted"))
            dirb = _num(a.get("direct_bidder_accepted"))
            if not _val(a.get("bid_to_cover_ratio")) and not _val(a.get("high_yield")) and not _val(a.get("high_discount_rate")):
                continue  # 아직 결과가 없는(발표만 된) 입찰
            out["recent"].append({
                "auction_date": (a.get("auction_date") or "")[:10],
                "type": a.get("security_type"), "term": a.get("security_term"), "reopening": a.get("reopening"),
                "high_yield": _val(a.get("high_yield")), "high_discount_rate": _val(a.get("high_discount_rate")),
                "bid_to_cover": _val(a.get("bid_to_cover_ratio")),
                "indirect_pct": round(ind / comp * 100, 1) if comp and ind is not None else None,
                "direct_pct": round(dirb / comp * 100, 1) if comp and dirb is not None else None,
                "offering_amount": a.get("offering_amt"),
            })
        for a in _fiscal("upcoming_auctions", {"filter": f"auction_date:gte:{today}", "sort": "auction_date", "page[size]": 50}):
            out["upcoming"].append({"auction_date": (a.get("auction_date") or "")[:10], "type": a.get("security_type"),
                                    "term": a.get("security_term"), "reopening": a.get("reopening"),
                                    "offering_amount": a.get("offering_amt")})
    except Exception as e:
        out["errors"].append(f"fiscaldata: {e.__class__.__name__}")
    if out["recent"] or out["upcoming"]:
        return out
    # 대체: TreasuryDirect (키 이름이 바뀌어도 대소문자 무시로 찾는다)
    out["source"] = "TreasuryDirect"
    base = "https://www.treasurydirect.gov/TA_WS/securities"

    def g(a, *keys):
        low = {k.lower(): v for k, v in a.items()}
        for k in keys:
            v = _val(low.get(k.lower()))
            if v is not None:
                return v
        return None
    try:
        for a in requests.get(f"{base}/auctioned?format=json&days=8", headers=HEADERS, timeout=30).json():
            comp, ind, dirb = (_num(g(a, k)) for k in ("competitiveAccepted", "indirectBidderAccepted", "directBidderAccepted"))
            out["recent"].append({
                "auction_date": (g(a, "auctionDate", "auction_date") or "")[:10],
                "type": g(a, "securityType"), "term": g(a, "securityTerm"), "reopening": g(a, "reopening"),
                "high_yield": g(a, "highYield"), "high_discount_rate": g(a, "highDiscountRate"),
                "bid_to_cover": g(a, "bidToCoverRatio"),
                "indirect_pct": round(ind / comp * 100, 1) if comp and ind is not None else None,
                "direct_pct": round(dirb / comp * 100, 1) if comp and dirb is not None else None,
                "offering_amount": g(a, "offeringAmount"),
            })
            if not out["recent"][-1]["auction_date"]:
                out["errors"].append("treasurydirect keys: " + ",".join(sorted(a)[:40]))
        out["recent"].sort(key=lambda r: r["auction_date"], reverse=True)
    except Exception as e:
        out["errors"].append(f"auctioned: {e.__class__.__name__}")
    return out


def main():
    result = {
        "fetched_at_utc": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": {
            "treasury_auctions": "TreasuryDirect 최근 7일 입찰 결과와 예정 입찰. indirect_pct/direct_pct는 경쟁입찰 낙찰액 대비 비중(%).",
            "central_banks": f"공식 RSS의 최근 {CB_HOURS}시간 항목. 최근 항목이 없으면 latest_any에 가장 최근 3개.",
            "holdings_news": f"구글 뉴스 RSS 검색 결과 최근 {NEWS_HOURS}시간 헤드라인(제목만, 본문 아님).",
        },
        "treasury_auctions": treasury_auctions(),
        "central_banks": central_banks(),
        "holdings_news": holdings_news(),
    }
    os.makedirs("data", exist_ok=True)
    with open("data/news_latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    cb = {k: (v["status"], len(v["items"])) for k, v in result["central_banks"].items()}
    hn = {k: len(v["items"]) for k, v in result["holdings_news"].items()}
    print(f"news 저장: 입찰 {len(result['treasury_auctions']['recent'])}건, 중앙은행 {cb}, 보유주식 {hn}")


if __name__ == "__main__":
    main()
