"""매일 실행: 수집 → 분석 → 렌더 → 메일. 로그에는 건수·사용량만 남긴다(공개 저장소)."""

import asyncio
import os
import traceback
from datetime import datetime, timedelta, timezone

from . import analyze, llm, mailer, render
from .collect import KST, collect

DEFAULT_CHANNELS = ("bornlupin,hana_us_stock,d_ticker,FastStockNewsUSA,insidertracking,grmtstudy,"
                    "ai_masters_community,FastLandNews,Onionfarmer,bzcftel,MacroAllocation,harveyspecterMike,"
                    "Macrojunglemicrolens")


def log(msg):
    print(f"[brief] {msg}", flush=True)


def main():
    channels = [c.strip() for c in (os.environ.get("TG_CHANNELS") or DEFAULT_CHANNELS).split(",") if c.strip()]
    report_ch = (os.environ.get("TG_REPORT_CHANNEL") or "report_figure_by_offset").strip()
    hours = int(os.environ.get("TG_HOURS", "24"))
    now = datetime.now(timezone.utc)

    brief_posts, report_posts, errors = asyncio.run(collect(channels, report_ch, hours))
    log(f"수집: 채널글 {len(brief_posts)}건, 리포트 이미지글 {len(report_posts)}건, 수집오류 {len(errors)}건")

    sections, notes = [], []
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
                links = {i: a["url"] for i, a in enumerate(analyses, 1) if a["url"]}
                sections.append(("리포트 갤러리 · 미국 증시 리포트 분석", deck, links, "rep"))
        except Exception:
            log("리포트 분석 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append("리포트 갤러리 분석 중 오류가 발생해 이번 메일에서 제외됐습니다.")

    # 2) 구독 채널 투자 브리프
    if brief_posts:
        try:
            deck = analyze.channel_brief(brief_posts)
            links = {p["no"]: p["url"] for p in brief_posts}
            sections.append(("구독 채널 투자 아이디어 브리프", deck, links, "brief"))
        except Exception:
            log("브리프 생성 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append("채널 브리프 생성 중 오류가 발생해 이번 메일에서 제외됐습니다.")

    since = (now - timedelta(hours=hours)).astimezone(KST)
    date_label = f"{since:%Y.%m.%d %H:%M} ~ {now.astimezone(KST):%m.%d %H:%M} KST"
    notes += [f"수집 대상: 구독 채널 {len(channels)}개 + 리포트 갤러리",
              f"채널 글 {len(brief_posts)}건, 리포트 {n_groups}건 중 미국 증시 관련 {n_us}건 분석",
              "영상·투표 등 일부 미디어와 외부 링크 본문은 분석 대상이 아닙니다.",
              "수치는 원문 기준이며 교차검증 전입니다. 투자 판단과 책임은 투자자 본인에게 있습니다."]
    if errors:
        notes.append(f"수집 실패 채널 {len(errors)}개(채널명 변경·비공개 전환 가능성)")

    title = f"{now.astimezone(KST):%m월 %d일} 텔레그램 투자 브리프"
    stats = [(f"{len(brief_posts)}건", "채널 글"), (f"{n_us}건", "미장 리포트 분석"),
             (f"{len(sections)}개", "섹션"), (f"{llm.USAGE['calls']}회", "AI 분석 호출")]
    html_doc = render.page(title, date_label, stats, sections, notes) if sections else \
        f"<p>{date_label} 동안 분석할 새 글이 없거나 분석에 실패했습니다.</p>"
    fname = f"telegram_brief_{now.astimezone(KST):%Y%m%d}.html"
    out = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), fname)
    with open(out, "w", encoding="utf-8") as fp:
        fp.write(html_doc)
    log(f"Claude 사용량(구독): 호출 {llm.USAGE['calls']}회, 입력 {llm.USAGE['input']:,} / 출력 {llm.USAGE['output']:,} 토큰"
        f" · API 환산 참고치 ${llm.USAGE['cost_usd']:.2f} (구독 방식이라 별도 청구 없음)")
    mailer.send(f"[텔레그램 브리프] {title}", html_doc, fname)
    log("메일 발송 완료")


if __name__ == "__main__":
    main()
