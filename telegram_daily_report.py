"""내 텔레그램 계정이 구독 중인 채널의 최근 24시간 게시물을 모아
종류별 요약 레포트를 만들고, 내 텔레그램 '저장한 메시지'로 보낸다.

이 저장소는 공개(public)이므로:
- 수집한 원문과 레포트는 파일로 커밋하지 않는다.
- Actions 로그에는 건수만 남기고 채널 이름·본문은 출력하지 않는다.

필요한 환경변수(GitHub Secrets):
    TG_API_ID, TG_API_HASH, TG_SESSION   필수 (telegram_login.py 로 발급)
    ANTHROPIC_API_KEY                    선택. 있으면 Claude 가 종류별로 요약,
                                         없으면 키워드 기반 분류 레포트로 대신한다.
선택 설정:
    TG_INCLUDE_GROUPS=1   채널뿐 아니라 그룹 대화방도 포함
    TG_EXCLUDE            제외할 채널 (@아이디 또는 채널 이름, 쉼표로 구분)
    TG_REPORT_HOURS       수집 기간(시간), 기본 24
"""

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel

KST = timezone(timedelta(hours=9))
HOURS = int(os.environ.get("TG_REPORT_HOURS", "24"))
INCLUDE_GROUPS = os.environ.get("TG_INCLUDE_GROUPS", "") == "1"
EXCLUDE = {s.strip().lstrip("@").lower() for s in os.environ.get("TG_EXCLUDE", "").split(",") if s.strip()}

MAX_PER_CHANNEL = 80      # 채널당 최대 게시물 수
MAX_CHARS = 1200          # 게시물 본문 최대 길이
MAX_TOTAL_CHARS = 450_000 # Claude 에 보낼 전체 본문 상한(비용·길이 안전장치)
TG_MSG_LIMIT = 4000       # 텔레그램 메시지 1건 최대 길이(4096) 여유분

MODEL = "claude-opus-5-5"


# ───────────────────────── 수집 ─────────────────────────

def post_link(entity, msg_id):
    if getattr(entity, "username", None):
        return f"https://t.me/{entity.username}/{msg_id}"
    return f"https://t.me/c/{entity.id}/{msg_id}"


async def collect(client, since):
    channels = []
    async for dialog in client.iter_dialogs():
        ent = dialog.entity
        if not isinstance(ent, Channel):
            continue
        if not ent.broadcast and not INCLUDE_GROUPS:
            continue
        uname = (ent.username or "").lower()
        if uname in EXCLUDE or (ent.title or "").lower() in EXCLUDE:
            continue
        # 대화 목록은 최근 활동 순: 마지막 메시지가 기간 밖이면 새 글이 없는 채널
        if dialog.date and dialog.date < since:
            continue
        posts = []
        async for m in client.iter_messages(ent, limit=MAX_PER_CHANNEL):
            if m.date < since:
                break
            text = (m.message or "").strip()
            if not text:
                continue
            posts.append({
                "time_kst": m.date.astimezone(KST).strftime("%m-%d %H:%M"),
                "text": text[:MAX_CHARS] + ("…" if len(text) > MAX_CHARS else ""),
                "url": post_link(ent, m.id),
            })
        if posts:
            posts.reverse()  # 오래된 순
            channels.append({"title": ent.title or uname, "posts": posts})
    return channels


# ───────────────────────── 요약 (Claude) ─────────────────────────

SYSTEM_PROMPT = """너는 개인 투자자를 위한 텔레그램 데일리 브리핑 편집자다.
사용자가 구독한 여러 텔레그램 채널의 최근 24시간 게시물이 주어진다.

할 일:
1. 게시물을 내용의 '종류'별로 묶는다. 기본 분류(해당 내용이 없으면 생략, 필요하면 추가 가능):
   - 🌐 매크로·금리·환율·중앙은행
   - 📈 시장 동향·지수·수급
   - 🏢 기업 실적·가이던스·어닝콜
   - 🔔 개별 종목 뉴스·공시·내부자 거래
   - 🧭 섹터·테마·산업
   - 💡 투자 아이디어·전략·리서치 의견
   - 🪙 크립토
   - 📌 기타
2. 각 분류마다 핵심을 3~8개 불릿으로 요약한다. 여러 채널이 같은 사건을 다루면 하나로 합치고,
   숫자(수치·%·가격·날짜)는 원문 그대로 정확히 옮긴다. 추측이나 원문에 없는 내용은 쓰지 않는다.
   각 불릿 끝에 출처 채널명을 괄호로 붙이고, 중요한 항목에는 원문 링크 하나를 붙인다.
3. 맨 위에 '오늘의 핵심 3줄'을, 맨 아래에 '체크할 일정·이벤트'(언급된 것만)를 둔다.

형식: 텔레그램에서 그대로 읽히는 일반 텍스트. 마크다운 기호(#, **, 표)는 쓰지 말고
이모지 제목과 '•' 불릿만 사용한다. 한국어로 쓴다."""


def build_corpus(channels):
    parts, total = [], 0
    for ch in channels:
        block = [f"### 채널: {ch['title']}"]
        for p in ch["posts"]:
            block.append(f"[{p['time_kst']}] {p['url']}\n{p['text']}")
        s = "\n\n".join(block)
        if total + len(s) > MAX_TOTAL_CHARS:
            parts.append("(분량 상한으로 이후 채널은 생략됨)")
            break
        parts.append(s)
        total += len(s)
    return "\n\n\n".join(parts)


def summarize_with_claude(channels, header):
    import anthropic

    client = anthropic.Anthropic()
    corpus = build_corpus(channels)
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium"},
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"{header}\n\n아래 게시물로 데일리 브리핑을 작성해줘.\n\n{corpus}",
        }],
    ) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude 가 요약을 거절함")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("Claude 응답이 비어 있음")
    print(f"[report] Claude 요약 완료 (입력 {resp.usage.input_tokens} / 출력 {resp.usage.output_tokens} 토큰)")
    return text


# ───────────────────────── 요약 (API 키 없을 때: 키워드 분류) ─────────────────────────

CATEGORIES = [
    ("🌐 매크로·금리·환율", r"연준|Fed|FOMC|금리|국채|CPI|PCE|고용|실업|인플레|환율|달러|DXY|ECB|BOJ|한국은행|GDP|yield|treasury|inflation|payroll"),
    ("🏢 실적·가이던스", r"실적|어닝|EPS|매출|가이던스|컨센서스|영업이익|earnings|revenue|guidance|분기|Q[1-4]"),
    ("🔔 종목·공시·내부자", r"내부자|insider|공시|매수|매도|지분|13F|자사주|buyback|SEC|Form 4"),
    ("📈 시장·수급", r"S&P|나스닥|NASDAQ|다우|코스피|코스닥|지수|수급|외국인|기관|VIX|선물|옵션"),
    ("🪙 크립토", r"비트코인|BTC|이더리움|ETH|크립토|코인|crypto"),
]


def first_line(text, n=110):
    line = text.strip().split("\n", 1)[0]
    return line[:n] + ("…" if len(line) > n else "")


def summarize_by_keywords(channels, header):
    buckets = {name: [] for name, _ in CATEGORIES}
    buckets["📌 기타"] = []
    for ch in channels:
        for p in ch["posts"]:
            for name, pat in CATEGORIES:
                if re.search(pat, p["text"], re.IGNORECASE):
                    buckets[name].append((ch["title"], p))
                    break
            else:
                buckets["📌 기타"].append((ch["title"], p))
    lines = [header, "(ANTHROPIC_API_KEY 가 없어 키워드 분류로 작성됨: 각 글의 첫 줄)", ""]
    for name, items in buckets.items():
        if not items:
            continue
        lines.append(f"{name} ({len(items)}건)")
        for title, p in items[:15]:
            lines.append(f"• [{p['time_kst']}] {first_line(p['text'])} ({title}) {p['url']}")
        if len(items) > 15:
            lines.append(f"  … 외 {len(items) - 15}건")
        lines.append("")
    return "\n".join(lines).strip()


# ───────────────────────── 전송 ─────────────────────────

def split_message(text, limit=TG_MSG_LIMIT):
    chunks, cur = [], ""
    for para in text.split("\n"):
        while len(para) > limit:  # 한 줄이 너무 길면 잘라서 따로 보낸다
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(para[:limit])
            para = para[limit:]
        if len(cur) + len(para) + 1 > limit:
            chunks.append(cur)
            cur = para
        else:
            cur = f"{cur}\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()]


async def main():
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session = os.environ["TG_SESSION"]

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=HOURS)
    header = (f"📰 텔레그램 데일리 레포트\n"
              f"{since.astimezone(KST):%Y-%m-%d %H:%M} ~ {now.astimezone(KST):%Y-%m-%d %H:%M} (KST)")

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        channels = await collect(client, since)
        n_posts = sum(len(c["posts"]) for c in channels)
        print(f"[report] 새 글이 있는 채널 {len(channels)}개, 게시물 {n_posts}건")

        if not channels:
            report = f"{header}\n\n최근 {HOURS}시간 동안 구독 채널에 새 글이 없습니다."
        else:
            header += f"\n채널 {len(channels)}개 · 게시물 {n_posts}건"
            report = None
            if os.environ.get("ANTHROPIC_API_KEY"):
                try:
                    report = summarize_with_claude(channels, header)
                    if not report.startswith("📰"):
                        report = f"{header}\n\n{report}"
                except Exception as e:  # 요약 실패 시에도 레포트는 보낸다
                    print(f"[report] Claude 요약 실패, 키워드 분류로 대체: {e.__class__.__name__}")
            if report is None:
                report = summarize_by_keywords(channels, header)

        chunks = split_message(report)
        for chunk in chunks:
            await client.send_message("me", chunk, link_preview=False)
        print(f"[report] 저장한 메시지로 {len(chunks)}건 전송 완료")


if __name__ == "__main__":
    asyncio.run(main())
