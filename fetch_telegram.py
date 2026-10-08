"""텔레그램 공개 채널(t.me/s/...)의 최근 게시물을 정확한 게시 시각과 함께 수집한다.

채널마다 data/telegram/<채널>.json 으로 따로 저장한다(파일이 너무 커지지 않게).
"""

import json
import os
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

CHANNELS = [
    "insidertracking",
    "FastStockNewsUSA",
    "harveyspecterMike",
    "bornlupin",
    "grmtstudy",
    "MacroAllocation",
    "Macrojunglemicrolens",
]
HOURS = 26          # 이 시간 안의 게시물만 저장
MAX_PAGES = 6       # 채널당 최대 페이지(페이지당 약 20개)
MAX_POSTS = 40      # 채널당 최대 저장 개수
MAX_CHARS = 700     # 게시물 본문 최대 길이
HEADERS = {"User-Agent": "Mozilla/5.0 (market-data GitHub Action)"}


def parse_page(html):
    """한 페이지에서 (게시물 id, 시각, 본문, 링크) 목록을 오래된 순으로 돌려준다."""
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for msg in soup.select("div.tgme_widget_message"):
        post = msg.get("data-post", "")
        t = msg.select_one("a.tgme_widget_message_date time")
        if not post or t is None or not t.get("datetime"):
            continue
        body = msg.select_one("div.tgme_widget_message_text")
        text = body.get_text("\n", strip=True) if body else ""
        try:
            pid = int(post.rsplit("/", 1)[1])
        except ValueError:
            continue
        posts.append({
            "id": pid,
            "time_utc": datetime.fromisoformat(t["datetime"]).astimezone(timezone.utc),
            "text": text,
            "url": f"https://t.me/{post}",
        })
    return posts


def fetch_channel(ch, now):
    cutoff = now - timedelta(hours=HOURS)
    url = f"https://t.me/s/{ch}"
    collected = {}
    for _ in range(MAX_PAGES):
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        posts = parse_page(resp.text)
        if not posts:
            break
        for p in posts:
            if p["time_utc"] >= cutoff:
                collected[p["id"]] = p
        oldest = min(posts, key=lambda p: p["id"])
        if oldest["time_utc"] < cutoff:
            break
        url = f"https://t.me/s/{ch}?before={oldest['id']}"
    items = sorted(collected.values(), key=lambda p: p["id"], reverse=True)[:MAX_POSTS]
    kst = timezone(timedelta(hours=9))
    return [
        {
            "time_utc": p["time_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_kst": p["time_utc"].astimezone(kst).strftime("%Y-%m-%d %H:%M"),
            "text": p["text"][:MAX_CHARS] + ("…" if len(p["text"]) > MAX_CHARS else ""),
            "url": p["url"],
        }
        for p in items
        if p["text"]
    ]


def main():
    now = datetime.now(timezone.utc)
    os.makedirs("data/telegram", exist_ok=True)
    index = {"fetched_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "hours": HOURS, "channels": {}}
    for ch in CHANNELS:
        try:
            posts = fetch_channel(ch, now)
            status = "ok"
        except Exception as e:
            print(f"[telegram] {ch} 실패: {e}")
            posts, status = [], f"error: {e.__class__.__name__}"
        with open(f"data/telegram/{ch}.json", "w", encoding="utf-8") as f:
            json.dump({"channel": ch, "fetched_at_utc": index["fetched_at_utc"], "hours": HOURS, "posts": posts}, f, ensure_ascii=False, indent=1)
        index["channels"][ch] = {"status": status, "posts": len(posts)}
        print(f"[telegram] {ch}: {len(posts)}건 ({status})")
    with open("data/telegram/_index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
