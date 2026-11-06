"""매일 실행: 수집(전날 07:00~당일 06:00 KST) → 전수 요약 → 분석 → 렌더 → 07:00에 메일 → 읽음 처리.
공개 저장소이므로 로그에는 건수·사용량만 남긴다."""

import asyncio
import os
import time
import traceback
from datetime import datetime, timedelta

from . import analyze, llm, mailer, render
from .collect import KST, collect, mark_read

DEFAULT_CHANNELS = ("bornlupin,hana_us_stock,d_ticker,FastStockNewsUSA,insidertracking,grmtstudy,"
                    "ai_masters_community,FastLandNews,Onionfarmer,bzcftel,MacroAllocation,harveyspecterMike,"
                    "Macrojunglemicrolens")


def log(msg):
    print(f"[brief] {msg}", flush=True)


def _hhmm(v, default):
    h, m = (v or default).split(":")
    return int(h), int(m)


def window(now):
    """전날 TG_WINDOW_START ~ 당일 TG_WINDOW_END (KST). 기본 07:00 ~ 06:00."""
    sh, sm = _hhmm(os.environ.get("TG_WINDOW_START"), "07:00")
    eh, em = _hhmm(os.environ.get("TG_WINDOW_END"), "06:00")
    today = now.astimezone(KST)
    until = today.replace(hour=eh, minute=em, second=0, microsecond=0)
    if until > today:  # 아직 마감 시각 전이면 전날 마감 기준
        until -= timedelta(days=1)
    since = (until - timedelta(days=1)).replace(hour=sh, minute=sm)
    return since, until


def wait_until_send_time(now_fn=lambda: datetime.now(KST)):
    sh, sm = _hhmm(os.environ.get("TG_SEND_AT"), "07:00")
    target = now_fn().replace(hour=sh, minute=sm, second=0, microsecond=0)
    wait = (target - now_fn()).total_seconds()
    if 0 < wait < 3 * 3600:
        log(f"발송 시각({sh:02d}:{sm:02d})까지 {int(wait // 60)}분 대기")
        time.sleep(wait)


def main():
    channels = [c.strip() for c in (os.environ.get("TG_CHANNELS") or DEFAULT_CHANNELS).split(",") if c.strip()]
    report_ch = (os.environ.get("TG_REPORT_CHANNEL") or "report_figure_by_offset").strip()
    since, until = window(datetime.now(KST))
    log(f"수집 구간: {since:%m-%d %H:%M} ~ {until:%m-%d %H:%M} KST")

    brief_posts, report_posts, errors, read_marks, media_only = asyncio.run(collect(channels, report_ch, since, until))
    n_img = sum(1 for p in brief_posts if p["photo"])
    log(f"수집: 채널글 {len(brief_posts)}건(이미지 {n_img}장, 영상·투표 등 {media_only}건), 리포트 이미지글 {len(report_posts)}건, 오류 {len(errors)}건")

    sections, notes, decks = [], [], []
    n_us = n_groups = 0

    # 1) 리포트 갤러리 — 미장 리포트
    if report_posts:
        try:
            groups = analyze._group_reports(report_posts)
            n_groups = len(groups)
            us = analyze.screen_reports(groups)
            n_us = len(us)
            cap = int(os.environ.get("TG_MAX_REPORTS") or 25)  # 구독 사용량 보호용 일일 상한
            if n_us > cap:
                notes.append(f"미장 관련 리포트 {n_us}건 중 최신 {cap}건만 분석했습니다(일일 상한).")
                us = us[-cap:]
            log(f"리포트 {n_groups}건 중 미장 관련 {n_us}건, 분석 {len(us)}건")
            if us:
                analyses = analyze.analyze_reports(us)
                deck = analyze.synthesize_reports(analyses)
                sections.append(("리포트 갤러리 · 미국 증시 리포트 분석", deck, None, "rep"))
        except Exception:
            log("리포트 분석 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append("리포트 갤러리 분석 중 오류가 발생해 이번 메일에서 제외됐습니다.")

    # 2) 구독 채널: 전수 요약 → 브리프 → 누락 글 슬라이드
    if brief_posts:
        try:
            digests = analyze.digest_posts(brief_posts)
            log(f"전수 요약: {len(digests)}/{len(brief_posts)}건")
            deck = analyze.channel_brief(brief_posts, digests)
            extra, low = analyze.coverage_slide(brief_posts, digests, [deck])
            if extra:
                deck["slides"].insert(-1, extra)  # 체크리스트 앞에 배치
            log(f"브리프 슬라이드 {len(deck['slides'])}장, 본문 외 소식 {len(extra['table_rows']) if extra else 0}건, 잡담·중복 {low}건")
            sections.append(("구독 채널 투자 아이디어 브리프", deck, None, "brief"))
        except Exception:
            log("브리프 생성 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append("채널 브리프 생성 중 오류가 발생해 이번 메일에서 제외됐습니다.")

    date_label = f"{since:%Y.%m.%d %H:%M} ~ {until:%m.%d %H:%M} KST"
    notes += [f"수집 대상: 구독 채널 {len(channels)}개 + 리포트 갤러리",
              f"채널 글 {len(brief_posts)}건을 모두 읽고(이미지 {n_img}장 포함) 본문 또는 '그 밖에 알아둘 소식'에 반영했습니다.",
              f"영상·투표 등 내용을 읽을 수 없는 글 {media_only}건은 제외됐습니다.",
              f"리포트 {n_groups}건 중 미국 증시 관련 {n_us}건 분석",
              "수치는 원문 기준이며 교차검증 전입니다. 투자 판단과 책임은 투자자 본인에게 있습니다."]
    if errors:
        notes.append(f"수집 실패 채널 {len(errors)}개(채널명 변경·비공개 전환 가능성)")

    title = f"{until:%m월 %d일} 텔레그램 투자 브리프"
    stats = [(f"{len(brief_posts)}건", "채널 글 전수 확인"), (f"{n_us}건", "미장 리포트 분석"),
             (f"{sum(len(d['slides']) for _, d, _, _ in sections)}장", "슬라이드"), (f"{llm.USAGE['calls']}회", "AI 분석 호출")]
    html_doc = render.page(title, date_label, stats, sections, notes) if sections else \
        f"<p>{date_label} 동안 분석할 새 글이 없거나 분석에 실패했습니다.</p>"
    fname = f"telegram_brief_{until:%Y%m%d}.html"
    with open(os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), fname), "w", encoding="utf-8") as fp:
        fp.write(html_doc)
    log(f"Claude 사용량(구독): 호출 {llm.USAGE['calls']}회, 입력 {llm.USAGE['input']:,} / 출력 {llm.USAGE['output']:,} 토큰"
        f" · API 환산 참고치 ${llm.USAGE['cost_usd']:.2f} (구독 방식이라 별도 청구 없음)")

    wait_until_send_time()
    mailer.send(f"[텔레그램 브리프] {title}", html_doc, fname)
    log("메일 발송 완료")

    if sections and (os.environ.get("TG_MARK_READ") or "1") == "1":
        n = asyncio.run(mark_read(read_marks))
        log(f"읽음 처리: {n}/{len(read_marks)}개 채널 (수집 구간 마감 시각까지의 글)")


if __name__ == "__main__":
    main()
