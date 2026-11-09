"""매일 실행: 텔레그램 수집(전날 07:00~당일 06:00 KST) + 매크로 수집 → 전수 요약·분석·매크로 해설 → 하나의 리포트 → 07:30에 메일 → 읽음 처리.
공개 저장소이므로 로그에는 건수·사용량만 남긴다."""

import asyncio
import os
import time
import traceback
from datetime import datetime, timedelta

from concurrent.futures import ThreadPoolExecutor

from . import analyze, llm, macro, mailer, render
from .collect import KST, collect, mark_read

# auto = 텔레그램 대화 목록에 있는 모든 구독 채널(비공개 채널 포함, 사기 표시·리포트 채널 제외)
# 뒤의 사용자명들은 그룹형 채널일 수도 있어 함께 명시(중복은 자동 제거)
DEFAULT_CHANNELS = ("auto,bornlupin,hana_us_stock,d_ticker,FastStockNewsUSA,insidertracking,grmtstudy,"
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
    sh, sm = _hhmm(os.environ.get("TG_SEND_AT"), "07:30")
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

    brief_posts, report_posts, errors, read_marks, media_only, n_channels = asyncio.run(collect(channels, report_ch, since, until))
    n_img = sum(1 for p in brief_posts if p["photo"])
    log(f"수집: 구독 채널 {n_channels}개, 채널글 {len(brief_posts)}건(이미지 {n_img}장, 영상·투표 등 {media_only}건), 리포트 이미지글 {len(report_posts)}건, 오류 {len(errors)}건")

    notes = []
    n_us = n_groups = 0
    macro_on = (os.environ.get("TG_MACRO") or "1") == "1"
    ex = ThreadPoolExecutor(max_workers=4)
    # 매크로 데이터는 미국 종가가 반영되도록 수집 마감 10분 뒤부터 별도 스레드로 수집
    fut_data = ex.submit(macro.collect, until + timedelta(minutes=10)) if macro_on else None

    # 1) 구독 채널 전수 요약 (매크로 해설에도 참고로 전달)
    digests = {}
    if brief_posts:
        try:
            digests = analyze.digest_posts(brief_posts)
            log(f"전수 요약: {len(digests)}/{len(brief_posts)}건")
        except Exception:
            log("전수 요약 실패: " + traceback.format_exc().splitlines()[-1])
    tg_lines = "\n".join(f"- [{d['category']}] {d['line']}" for d in digests.values() if d["importance"] >= 2)[:20000]

    def reports_job():
        nonlocal n_us, n_groups
        groups = analyze._group_reports(report_posts)
        n_groups = len(groups)
        us = analyze.screen_reports(groups)
        n_us = len(us)
        cap = int(os.environ.get("TG_MAX_REPORTS") or 25)  # 구독 사용량 보호용 일일 상한
        if n_us > cap:
            notes.append(f"미장 관련 리포트 {n_us}건 중 최신 {cap}건만 분석했습니다(일일 상한).")
            us = us[-cap:]
        log(f"리포트 {n_groups}건 중 미장 관련 {n_us}건, 분석 {len(us)}건")
        return analyze.synthesize_reports(analyze.analyze_reports(us)) if us else None

    def brief_job():
        deck = analyze.channel_brief(brief_posts, digests, with_macro=macro_on)
        extra, low = analyze.coverage_slide(brief_posts, digests, [deck])
        if extra:
            deck["slides"].insert(-1, extra)  # 체크리스트 앞에 배치
        log(f"브리프 슬라이드 {len(deck['slides'])}장, 본문 외 소식 {len(extra['table_rows']) if extra else 0}건, 잡담·중복 {low}건")
        return deck

    fut_rep = ex.submit(reports_job) if report_posts else None
    fut_brief = ex.submit(brief_job) if brief_posts and digests else None

    data = nar = None
    if fut_data:
        try:
            data = fut_data.result()
            log(f"매크로 데이터 수집 완료: 기준 거래일 {macro.base_date(data)}, 일정 {len(data.get('calendar', []))}건, 국채 {len(data.get('treasury', []))}일치")
            nar = macro.narrative(data, tg_lines)
            log(f"매크로 해설: 이슈 {len(nar['issues'])}장, 커버리지 {len(nar['coverage'])}항목")
        except Exception:
            log("매크로 파트 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append("매크로 해설 생성 중 오류가 발생해 수치 위주로만 실었습니다.")

    def result(fut, label):
        if not fut:
            return None
        try:
            return fut.result()
        except Exception:
            log(f"{label} 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append(f"{label} 중 오류가 발생해 이번 메일에서 제외됐습니다.")
            return None

    rep_deck = result(fut_rep, "리포트 갤러리 분석")
    tg_deck = result(fut_brief, "채널 브리프 생성")
    ex.shutdown(wait=False)

    # 2) 하나의 흐름으로 조립: 핵심 → 시장 수치·해설 → 투자 아이디어 → 보유주식·서학개미 → 리포트 → 일정·종합판단
    sections = []
    bd = macro.base_date(data) if data else ""
    if nar:
        h = nar["hero"]
        sections.append(("오늘의 핵심", {"headline": h["headline"], "slides": [],
                                       "summary": h["points"] + [f"**시장 판정** — {h['verdict']}"] + [f"**주시** — {w}" for w in h["watch"]]}, None, "top"))
    if data:
        nums = macro.merge(macro.number_slides(data), nar["notes"] if nar else None)
        sections.append(("시장 수치와 해설", {"headline": "", "summary": [], "slides": nums + (nar["issues"] if nar else [])}, None, "mkt"))
    if tg_deck:
        sections.append(("오늘의 투자 아이디어 · 텔레그램 채널", tg_deck, None, "brief"))
    if nar:
        sections.append(("보유주식 · 서학개미 동향", {"headline": "", "summary": [], "slides": [nar["holdings"], nar["flows"]]}, None, "hold"))
    if rep_deck:
        sections.append(("리포트 갤러리 · 미국 증시 리포트 분석", rep_deck, None, "rep"))
    if data:
        cal = macro.merge([("calendar", macro.calendar_slide(data))], nar["notes"] if nar else None)
        tail = cal + ([nar["verdict"], macro.coverage_slide(nar["coverage"], data)] if nar else [])
        sections.append(("일정 · 종합 판단", {"headline": "", "summary": [], "slides": tail}, None, "end"))

    date_label = f"텔레그램 {since:%m.%d %H:%M} ~ {until:%m.%d %H:%M} KST" + (f" · 미국장 {bd} 종가 기준" if bd else "")
    notes += [f"수집 대상: 구독 채널 {n_channels}개 + 리포트 갤러리",
              f"채널 글 {len(brief_posts)}건을 모두 읽고(이미지 {n_img}장 포함) 본문 또는 '그 밖에 알아둘 소식'에 반영했습니다.",
              f"영상·투표 등 내용을 읽을 수 없는 글 {media_only}건은 제외됐습니다.",
              f"리포트 {n_groups}건 중 미국 증시 관련 {n_us}건 분석"]
    if data:
        notes += ["시세: Yahoo Finance(이 작업에서 직접 수집) · 국채: 미 재무부 · 물가·고용·EFFR·HY 스프레드: FRED · 일정: ForexFactory · 입찰: TreasuryDirect",
                  "시장폭은 S&P500 구성종목 기준 직접 계산(거래소 전체 집계 아님), 원자재는 근월물 선물, 원/달러는 글로벌 시세"]
    notes += ["텔레그램 내용은 미검증 정보입니다. 정보 제공 목적이며 투자 조언이 아닙니다. 투자 판단과 책임은 투자자 본인에게 있습니다."]
    if errors:
        notes.append(f"수집 실패 채널 {len(errors)}개(채널명 변경·비공개 전환 가능성)")

    title = f"{until:%m월 %d일} 투자 브리프"
    stats = [(f"{len(brief_posts)}건", "채널 글 전수 확인"), (f"{n_us}건", "미장 리포트 분석"),
             (f"{sum(len(d['slides']) for _, d, _, _ in sections)}장", "슬라이드"), (bd or "-", "미국장 기준일")]
    html_doc = render.page(title, date_label, stats, sections, notes) if sections else \
        f"<p>{date_label} 동안 분석할 내용이 없거나 분석에 실패했습니다.</p>"
    fname = f"invest_brief_{until:%Y%m%d}.html"
    with open(os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), fname), "w", encoding="utf-8") as fp:
        fp.write(html_doc)
    log(f"Claude 사용량(구독): 호출 {llm.USAGE['calls']}회, 입력 {llm.USAGE['input']:,} / 출력 {llm.USAGE['output']:,} 토큰"
        f" · API 환산 참고치 ${llm.USAGE['cost_usd']:.2f} (구독 방식이라 별도 청구 없음)")

    wait_until_send_time()
    mailer.send(f"[투자 브리프] {title}", html_doc, fname)
    log("메일 발송 완료")

    if tg_deck and (os.environ.get("TG_MARK_READ") or "1") == "1":
        n, failed = asyncio.run(mark_read(read_marks))
        log(f"읽음 처리: {n}/{len(read_marks)}개 채널 (수집 구간 마감 시각까지의 글)")
        for f in failed:
            log(f"  읽음 처리 실패: {f}")


if __name__ == "__main__":
    main()
