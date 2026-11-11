"""매일 실행되는 투자 브리프.

두 단계로 나눠 Claude 사용 시간을 03:00~08:00 KST 안에 몰아 둔다(구독 5시간 한도가 08:00에 초기화되도록).
- prep  (03:00 KST): 전날 07:00 ~ 당일 03:00 텔레그램 글 전수 요약 + 리포트 갤러리 선별·분석 → 암호화된 상태 파일로 저장
- final (06:00 KST): 03:00 ~ 06:00 새 글 요약 + 매크로 수집·해설 + 브리프 작성 → 07:30 메일 → 읽음 처리
  (prep 상태 파일이 없으면 final이 전 구간을 혼자 처리)
공개 저장소이므로 로그에는 건수·사용량만 남긴다.
"""

import asyncio
import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from . import analyze, llm, macro, mailer, memory, render
from .collect import KST, collect, mark_read

# auto = 텔레그램 대화 목록에 있는 모든 구독 채널(비공개 채널 포함, 사기 표시·리포트 채널 제외)
# 뒤의 사용자명들은 그룹형 채널일 수도 있어 함께 명시(중복은 자동 제거)
DEFAULT_CHANNELS = ("auto,bornlupin,hana_us_stock,d_ticker,FastStockNewsUSA,insidertracking,grmtstudy,"
                    "ai_masters_community,FastLandNews,Onionfarmer,bzcftel,MacroAllocation,harveyspecterMike,"
                    "Macrojunglemicrolens")
STATE = os.environ.get("TG_STATE") or os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "prep_state.json")


def log(msg):
    print(f"[brief] {msg}", flush=True)


def _hhmm(v, default):
    h, m = (v or default).split(":")
    return int(h), int(m)


def slot_of(now):
    """아침(19~07시 글, 07:30 발송) / 저녁(07~19시 글, 19:30 발송). TG_SLOT이 없으면 시각으로 정한다."""
    s = (os.environ.get("TG_SLOT") or "").strip()
    if s in ("morning", "evening"):
        return s
    return "morning" if now.astimezone(KST).hour < 13 else "evening"


def window(now):
    """아침: 전날 19:00 ~ 당일 07:00 / 저녁: 당일 07:00 ~ 19:00 (KST)."""
    today = now.astimezone(KST)
    if slot_of(now) == "morning":
        until = today.replace(hour=7, minute=0, second=0, microsecond=0)
        return until - timedelta(hours=12), until
    until = today.replace(hour=19, minute=0, second=0, microsecond=0)
    return until - timedelta(hours=12), until


def prep_window(now):
    """아침 1단계: 전날 19:00 ~ 당일 TG_PREP_AT(기본 03:00)."""
    ph, pm = _hhmm(os.environ.get("TG_PREP_AT"), "03:00")
    today = now.astimezone(KST)
    until = today.replace(hour=7, minute=0, second=0, microsecond=0)
    return until - timedelta(hours=12), until.replace(hour=ph, minute=pm)


def wait_until_send_time(now_fn=lambda: datetime.now(KST)):
    sh, sm = _hhmm(os.environ.get("TG_SEND_AT"), "07:30" if slot_of(now_fn()) == "morning" else "19:30")
    target = now_fn().replace(hour=sh, minute=sm, second=0, microsecond=0)
    wait = (target - now_fn()).total_seconds()
    if 0 < wait < 3 * 3600:
        log(f"발송 시각({sh:02d}:{sm:02d})까지 {int(wait // 60)}분 대기")
        time.sleep(wait)


def _channels():
    chs = [c.strip() for c in (os.environ.get("TG_CHANNELS") or DEFAULT_CHANNELS).split(",") if c.strip()]
    return chs, (os.environ.get("TG_REPORT_CHANNEL") or "report_figure_by_offset").strip()


def _report_analyses(report_posts, cap):
    """리포트 갤러리: 묶기 → 미장 선별 → 분석. 반환 (분석 목록, 전체 수, 미장 수)."""
    if not report_posts:
        return [], 0, 0
    groups = analyze._group_reports(report_posts)
    us = analyze.screen_reports(groups)
    n_us = len(us)
    if n_us > cap:
        us = us[-cap:]
    return (analyze.analyze_reports(us) if us else []), len(groups), n_us


def _strip(posts):
    """상태 파일용: 이미지 바이트는 버리고 '이미지 있음' 표시만 남긴다(요약에 이미 반영됨)."""
    return [{**p, "photo": bool(p["photo"])} for p in posts]


# ───────────────────────── prep (03:00) ─────────────────────────

def run_prep():
    chs, report_ch = _channels()
    since, cut = prep_window(datetime.now(KST))
    log(f"[prep] 1차 수집 구간: {since:%m-%d %H:%M} ~ {cut:%m-%d %H:%M} KST")
    posts, reports, errors, marks, media_only, n_ch = asyncio.run(collect(chs, report_ch, since, cut))
    log(f"[prep] 채널글 {len(posts)}건, 리포트 이미지글 {len(reports)}건, 오류 {len(errors)}건")
    cap = int(os.environ.get("TG_MAX_REPORTS") or 25)
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_rep = ex.submit(_report_analyses, reports, cap)
        digests = analyze.digest_posts(posts) if posts else {}
        analyses, n_groups, n_us = f_rep.result()
    log(f"[prep] 전수 요약 {len(digests)}/{len(posts)}건, 리포트 {n_groups}건 중 미장 {n_us}건 분석 {len(analyses)}건")
    state = {"since": since.isoformat(), "cut": cut.isoformat(), "posts": _strip(posts),
             "digests": {str(k): v for k, v in digests.items()}, "analyses": analyses,
             "n_groups": n_groups, "n_us": n_us, "read_marks": {str(k): v for k, v in marks.items()},
             "media_only": media_only, "n_channels": n_ch, "errors": errors}
    with open(STATE, "w", encoding="utf-8") as fp:
        json.dump(state, fp, ensure_ascii=False)
    log(f"[prep] 상태 저장 완료 · Claude 호출 {llm.USAGE['calls']}회, 입력 {llm.USAGE['input']:,} / 출력 {llm.USAGE['output']:,} 토큰")


def _load_state(since, cut):
    try:
        with open(STATE, encoding="utf-8") as fp:
            st = json.load(fp)
    except (OSError, ValueError):
        return None
    if st.get("since") != since.isoformat() or st.get("cut") != cut.isoformat():
        log("prep 상태 파일의 구간이 오늘과 달라 사용하지 않음")
        return None
    st["digests"] = {int(k): v for k, v in st["digests"].items()}
    st["read_marks"] = {int(k): v for k, v in st["read_marks"].items()}
    return st


def _light_mode():
    """TG_FORCE_LIGHT=1(오늘 앞선 자동 실행이 이미 실패한 경우)이면 항상 간이 모드.
    예약 실행이 Claude 마감 시각(기본 07:15 KST) 이후에 시작되면 True.
    이후에 Claude를 쓰면 08:00 이후까지 이어져 업무 시간 5시간 한도를 새로 시작시키기 때문."""
    if os.environ.get("TG_FORCE_LIGHT") == "1":
        return True
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule" and os.environ.get("TG_AUTO") != "1":
        return False
    now = datetime.now(KST)
    if slot_of(now) != "morning":  # 저녁 브리프는 08:00 초기화와 무관
        return False
    h, m = _hhmm(os.environ.get("TG_CLAUDE_DEADLINE"), "07:30")
    return now >= now.replace(hour=h, minute=m, second=0, microsecond=0) and now.hour < 12


def _blank(tag, title, key):
    return {"tag": tag, "title": title, "key": key, "kpis": [], "charts": [], "boxes": [], "table_headers": [],
            "table_rows": [], "deep": [], "calc": [], "so_what": "", "sources": "", "refs": []}


def _light_sections(posts, digests, analyses):
    """Claude 없이 만드는 간이 섹션: 03:00 1단계 요약 + 이후 원문 앞부분 + 리포트 분석 표."""
    out = []
    rows = []
    for p in posts:
        d = digests.get(p["no"])
        if d and d["importance"] >= 2:
            rows.append((-d["importance"], [("★ " if d["importance"] == 3 else "") + d["category"], p["title"], d["line"]]))
        elif not d:
            rows.append((0, ["(요약 전)", p["title"], (p["text"] or "(이미지 글)")[:140].replace("\n", " ")]))
    rows.sort(key=lambda x: x[0])
    s = _blank("TELEGRAM", "채널 글 요약표", "1단계(03:00)에서 AI가 요약한 내용과 이후 글의 원문 앞부분입니다(간이 버전).")
    s["table_headers"], s["table_rows"] = ["분류", "채널", "내용"], [r for _, r in rows[:120]]
    s["sources"] = "구독 텔레그램 채널"
    out.append(("텔레그램 채널 요약(간이)", {"headline": "", "summary": [], "slides": [s]}, None, "brief"))
    if analyses:
        s = _blank("REPORTS", "미국 증시 리포트 요약표", "1단계에서 분석한 리포트입니다(간이 버전).")
        s["table_headers"] = ["증권사", "제목", "종목", "의견", "시사점"]
        s["table_rows"] = [[a["broker"], a["title"], ", ".join(a["tickers"]), a["stance"], a["so_what"]] for a in analyses]
        s["sources"] = "리포트 갤러리"
        out.append(("리포트 갤러리(간이)", {"headline": "", "summary": [], "slides": [s]}, None, "rep"))
    return out


# ───────────────────────── final (06:00) ─────────────────────────

def main():
    if (os.environ.get("TG_PHASE") or "final") == "prep":
        return run_prep()

    chs, report_ch = _channels()
    since, until = window(datetime.now(KST))
    _, cut = prep_window(until)
    st = _load_state(since, cut) if (os.environ.get("TG_PHASE") or "final") == "final" else None
    test = (os.environ.get("TG_TEST") or "0") == "1"
    slot = slot_of(datetime.now(KST))
    mem_key = f"{until:%Y-%m-%d %H}"
    mem = memory.load(mem_key)
    if mem:
        log(f"직전 브리프({mem['date']}시) 기억: 다룬 주제 {len(mem.get('topics', []))}개")
    light = _light_mode()
    if light:
        log("Claude 마감 시각 이후에 시작된 예약 실행 → Claude를 쓰지 않는 간이 브리프로 작성(5시간 한도 보호)")
    start = cut if st else since
    log(f"수집 구간: {since:%m-%d %H:%M} ~ {until:%m-%d %H:%M} KST" + (f" ({cut:%H:%M} 이전 글은 prep 단계 결과 사용, 이번에 {start:%H:%M}~ 수집)" if st else ""))

    new_posts, report_posts, errors, read_marks, media_only, n_channels = asyncio.run(collect(chs, report_ch, start, until))
    prev_posts = st["posts"] if st else []
    for i, p in enumerate(new_posts, len(prev_posts) + 1):  # 번호를 이어 붙인다
        p["no"] = i
    brief_posts = prev_posts + new_posts
    if st:
        for cid, mid in st["read_marks"].items():
            read_marks[cid] = max(read_marks.get(cid, 0), mid)
        media_only += st["media_only"]
        errors = sorted(set(errors) | set(st["errors"]))
    n_img = sum(1 for p in brief_posts if p["photo"])
    log(f"수집: 구독 채널 {n_channels}개, 채널글 {len(brief_posts)}건(이번 {len(new_posts)}건, 이미지 {n_img}장, 영상·투표 등 {media_only}건), "
        f"리포트 이미지글 이번 {len(report_posts)}건, 오류 {len(errors)}건")

    notes = []
    cap = int(os.environ.get("TG_MAX_REPORTS") or 25)
    # 매크로는 파이썬으로 만드는 수치표·일정만(AI 해설·웹 조사 없음), 미국장 마감 직후인 아침 브리프에만
    macro_on = (os.environ.get("TG_MACRO") or "1") == "1" and slot == "morning"
    ex = ThreadPoolExecutor(max_workers=4)
    # 매크로 데이터는 미국 종가가 반영되도록 수집 마감 10분 뒤부터 별도 스레드로 수집
    fut_data = ex.submit(macro.collect) if macro_on else None
    fut_rep = ex.submit(_report_analyses, report_posts, cap) if not light else None

    # 1) 구독 채널 전수 요약 (새 글만, prep 결과와 합침)
    digests = dict(st["digests"]) if st else {}
    if new_posts and not light:
        try:
            digests.update(analyze.digest_posts(new_posts))
        except Exception:
            log("전수 요약 실패: " + traceback.format_exc().splitlines()[-1])
    log(f"전수 요약: {len(digests)}/{len(brief_posts)}건")
    tg_lines = "\n".join(f"- [{d['category']}] {d['line']}" for d in digests.values() if d["importance"] >= 2)[:20000]

    def result(fut, label):
        if not fut:
            return None
        try:
            return fut.result()
        except Exception:
            log(f"{label} 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append(f"{label} 중 오류가 발생해 이번 메일에서 제외됐습니다.")
            return None

    # 2) 리포트 갤러리: prep 분석 + 새 분석 → 종합 (매크로와 병렬)
    new_rep = result(fut_rep, "리포트 갤러리 분석") or ([], 0, 0)
    analyses = (st["analyses"] if st else []) + new_rep[0]
    n_groups = (st["n_groups"] if st else 0) + new_rep[1]
    n_us = (st["n_us"] if st else 0) + new_rep[2]
    if n_us > len(analyses):
        notes.append(f"미장 관련 리포트 {n_us}건 중 {len(analyses)}건만 분석했습니다(일일 상한).")
    log(f"리포트 {n_groups}건 중 미장 관련 {n_us}건, 분석 {len(analyses)}건")
    fut_syn = ex.submit(analyze.synthesize_reports, analyses) if analyses and not light else None

    # 3) 매크로 수치(파이썬 수집만)
    data = nar = None
    if fut_data:
        try:
            data = fut_data.result()
            log(f"매크로 수치 수집 완료: 기준 거래일 {macro.base_date(data)}, 일정 {len(data.get('calendar', []))}건")
        except Exception:
            log("매크로 수치 수집 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append("시장 수치 수집 중 오류가 발생해 이번 메일에서 제외됐습니다.")

    # 4) 텔레그램 아이디어 브리프 — 직전 브리프에서 이미 다룬 주제는 새 전개가 없으면 생략
    covered = ("[직전 브리프에서 다룬 주제]\n" + memory.topics_text(mem)) if mem else ""
    tg_deck = None
    if brief_posts and digests and not light:
        try:
            tg_deck = analyze.channel_brief(brief_posts, digests, with_macro=True, covered=covered)
            extra, low = analyze.coverage_slide(brief_posts, digests, [tg_deck])
            if extra:
                tg_deck["slides"].append(extra)
            log(f"브리프 슬라이드 {len(tg_deck['slides'])}장, 본문 외 소식 {len(extra['table_rows']) if extra else 0}건, 잡담·중복 {low}건")
        except Exception:
            log("채널 브리프 생성 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append("채널 브리프 생성 중 오류가 발생해 이번 메일에서 제외됐습니다.")
    rep_deck = result(fut_syn, "리포트 갤러리 종합")
    ex.shutdown(wait=False)

    # 5) 조립: 텔레그램 투자 아이디어 → 리포트 갤러리 → (아침) 시장 수치·일정(파이썬 수치표, AI 해설 없음)
    sections = []
    bd = macro.base_date(data) if data else ""

    def add(label, build):
        """섹션 하나를 만들다 실패해도 나머지 섹션과 메일 발송은 계속한다."""
        try:
            sec = build()
            if sec:
                sections.append(sec)
        except Exception:
            log(f"{label} 조립 실패: " + traceback.format_exc().splitlines()[-1])
            notes.append(f"{label} 섹션을 만드는 중 오류가 발생해 이번 메일에서 제외됐습니다.")

    def mkt():
        slides = macro.merge(macro.number_slides(data), None) + macro.merge([("calendar", macro.calendar_slide(data))], None)
        return ("시장 수치·일정 (참고)", {"headline": "", "summary": [], "slides": slides}, None, "mkt") if slides else None

    if tg_deck:
        sections.append(("투자 아이디어 · 텔레그램 채널", tg_deck, None, "brief"))
    if rep_deck:
        sections.append(("리포트 갤러리 · 미국 증시 리포트 분석", rep_deck, None, "rep"))
    if light:
        sections += _light_sections(brief_posts, digests, analyses)
        notes.append("Claude 사용 마감 시각(구독 한도 초기화 보호) 이후에 시작돼 AI 해설 없이 요약표 위주의 간이 브리프로 보냈습니다.")
    if data:
        add("시장 수치·일정", mkt)

    if not test and not light and (tg_deck or rep_deck):
        try:
            memory.save(memory.build(mem_key, None, tg_deck, rep_deck))
        except Exception:
            log("브리프 기억 저장 실패: " + traceback.format_exc().splitlines()[-1])

    date_label = f"텔레그램 {since:%m.%d %H:%M} ~ {until:%m.%d %H:%M} KST" + (f" · 미국장 {bd} 종가 기준" if bd else "")
    notes += [f"수집 대상: 구독 채널 {n_channels}개 + 리포트 갤러리",
              f"채널 글 {len(brief_posts)}건을 모두 읽고(이미지 {n_img}장 포함) 본문 또는 '그 밖에 알아둘 소식'에 반영했습니다."
              + (f" ({cut:%H:%M} 이전 {len(prev_posts)}건은 {cut:%H:%M}에 1차로, 이후 {len(new_posts)}건은 {until:%H:%M}에 읽음)" if st else ""),
              f"영상·투표 등 내용을 읽을 수 없는 글 {media_only}건은 제외됐습니다.",
              f"리포트 {n_groups}건 중 미국 증시 관련 {n_us}건 분석"]
    if data:
        notes += ["시장 수치는 파이썬이 직접 수집한 값(AI 해설 없음) — 시세: Yahoo Finance · 국채: 미 재무부 · 물가·고용·EFFR·HY 스프레드: FRED · 일정: ForexFactory · 입찰: TreasuryDirect",
                  "시장폭은 S&P500 구성종목 기준 직접 계산(거래소 전체 집계 아님), 원자재는 근월물 선물, 원/달러는 글로벌 시세"]
    notes += ["텔레그램 내용은 미검증 정보입니다. 정보 제공 목적이며 투자 조언이 아닙니다. 투자 판단과 책임은 투자자 본인에게 있습니다."]
    if errors:
        notes.append(f"수집 실패 채널 {len(errors)}개(채널명 변경·비공개 전환 가능성)")

    title = f"{until:%m월 %d일} {'아침' if slot == 'morning' else '저녁'} 투자 브리프" + (" (간이)" if light else "")
    stats = [(f"{len(brief_posts)}건", "채널 글 전수 확인"), (f"{n_us}건", "미장 리포트 분석"),
             (f"{sum(len(d['slides']) for _, d, _, _ in sections)}장", "슬라이드"), (f"{since:%H}~{until:%H}시", "수집 구간")]
    html_doc = render.page(title, date_label, stats, sections, notes) if sections else \
        f"<p>{date_label} 동안 분석할 내용이 없거나 분석에 실패했습니다.</p>"
    fname = f"invest_brief_{until:%Y%m%d_%H}.html"
    with open(os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), fname), "w", encoding="utf-8") as fp:
        fp.write(html_doc)
    log(f"Claude 사용량(구독, 이번 단계): 호출 {llm.USAGE['calls']}회, 입력 {llm.USAGE['input']:,} / 출력 {llm.USAGE['output']:,} 토큰"
        f" · API 환산 참고치 ${llm.USAGE['cost_usd']:.2f} (구독 방식이라 별도 청구 없음)")

    if not test:
        wait_until_send_time()
    partial = any("오류" in n for n in notes)
    prefix = ("[TEST] " if test else "") + ("[투자 브리프·일부 누락]" if partial else "[투자 브리프]")
    mailer.send(f"{prefix} {title}", html_doc, fname)
    log("메일 발송 완료")

    if (tg_deck or light) and not test and (os.environ.get("TG_MARK_READ") or "1") == "1":
        n, failed = asyncio.run(mark_read(read_marks))
        log(f"읽음 처리: {n}/{len(read_marks)}개 채널 (수집 구간 마감 시각까지의 글)")
        for f in failed:
            log(f"  읽음 처리 실패: {f}")


if __name__ == "__main__":
    main()
