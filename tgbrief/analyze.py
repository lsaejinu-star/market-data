"""채널 글 전수 요약(누락 방지) → 투자 브리프 덱, 리포트 갤러리 미장 리포트 선별·분석."""

import os
from collections import OrderedDict

from .llm import ANALYSIS_MODEL, SCREEN_MODEL, ask_json, image_block

DIGEST_MODEL = os.environ.get("TG_DIGEST_MODEL") or SCREEN_MODEL


def _obj(props, req=None):
    return {"type": "object", "properties": props,
            "required": req or list(props), "additionalProperties": False}


S = {"type": "string"}
SL = {"type": "array", "items": S}
IL = {"type": "array", "items": {"type": "integer"}}

CHART = _obj({
    "kind": {"type": "string", "enum": ["change", "level", "stack"]},
    "title": S, "unit": S,
    "items": {"type": "array", "items": _obj({"label": S, "value": {"type": "number"}})},
})
SLIDE = _obj({
    "tag": S, "title": S, "key": S,
    "kpis": {"type": "array", "items": _obj({"v": S, "l": S, "tone": {"type": "string", "enum": ["up", "down", "neutral"]}})},
    "charts": {"type": "array", "items": CHART},
    "boxes": {"type": "array", "items": _obj({"title": S, "bullets": SL})},
    "table_headers": SL,
    "table_rows": {"type": "array", "items": SL},
    "deep": {"type": "array", "items": _obj({"lead": S, "text": S})},
    "calc": SL,
    "so_what": S,
    "sources": S,
    "refs": IL,
})
DECK = _obj({"headline": S, "summary": SL, "slides": {"type": "array", "items": SLIDE}})

STYLE_RULES = """작성 규칙:
- 한국어. 독자는 미국·한국 주식에 투자하는 개인투자자. '뉴스 제목 나열'이 아니라 투자 아이디어 중심으로 깊이 있게.
- 각 슬라이드: tag(영문 대문자 섹션명), title(주장형 제목), key(핵심 한 문장), kpis(핵심 수치 2~5개, 상승=up 하락=down),
  charts(비교할 수치가 3개 이상이면 적극 사용. kind='change': 등락률·변화폭처럼 상승/하락 의미가 있는 값(항목 4~12개, 큰 순 정렬),
  kind='level': 응답률·점유율·확률·금액처럼 크기만 비교하는 값(상승/하락 의미 없음), kind='stack': 합이 100인 구성비(2~5개).
  unit에 '%','bp','달러' 등 단위. 값은 원문 숫자만),
  boxes(2~4개, 짧은 글머리표 3~6개), 필요하면 table_headers/table_rows(없으면 빈 배열),
  deep(상세 해설 문단 3~5개: lead=굵은 소제목, text=인과관계와 의미를 4~7문장으로 풀어쓴 해설),
  calc(원문 수치로 직접 계산해 해석한 항목, 없으면 빈 배열), so_what(투자자가 판단할 것 1~2문장),
  sources(근거 채널/증권사 이름만), refs(이 슬라이드가 근거로 쓴 글 번호 목록 — 본문에는 번호를 쓰지 말 것).
- 본문 어디에도 (#12) 같은 글 번호를 쓰지 말 것. 근거 번호는 refs에만.
- 강조는 **굵게** 표기만 사용. 수치는 원문 그대로, 계산 근거는 calc에. 원문에 없는 사실을 지어내지 말 것.
- 투자 권유 표현 금지(매수하라 X). 상반된 시각이 있으면 함께 제시.
- 중복 금지: 같은 사건·종목·테마는 덱 전체에서 한 슬라이드에서만 다룬다(여러 슬라이드로 쪼개거나 다른 슬라이드에서 되풀이하지 말 것).
  슬라이드 수를 늘리기보다 중요한 내용의 해설(deep·calc)을 길고 깊게 쓴다. 덜 중요한 내용은 짧게."""

CATEGORIES = ["매크로·금리", "정치·정책", "지정학·전쟁", "시장·수급", "실적·가이던스", "AI·반도체", "에너지·원자재",
              "기업 뉴스", "크립토", "한국 시장", "부동산", "투자 의견·전략", "기타"]

DIGEST_SCHEMA = _obj({"items": {"type": "array", "items": _obj({
    "no": {"type": "integer"},
    "category": {"type": "string", "enum": CATEGORIES},
    "importance": {"type": "integer", "enum": [1, 2, 3]},
    "line": S})}})


# ───────────────────────── 1) 전수 요약 (누락 방지) ─────────────────────────

def digest_posts(posts, chunk=40):
    """모든 글(과 본문이 이미지인 글의 이미지)을 빠짐없이 읽고 글마다 한 줄 요약·분류·중요도를 만든다."""
    out = {}
    for k in range(0, len(posts), chunk):
        part = posts[k:k + chunk]
        content = []
        for p in part:
            content.append({"type": "text", "text": f"## #{p['no']} [{p['title']}] {p['time']}\n{p['text'] or '(텍스트 없음 — 이미지 글)'}"})
            if p["photo"]:
                content += [{"type": "text", "text": f"[#{p['no']} 첨부 이미지]"}, image_block(p["photo"])]
        content.append({"type": "text", "text": (
            "위 글 각각에 대해 빠짐없이 하나씩 답하라(no=글 번호). line=투자자 관점의 한 줄 요약(이미지 글이면 이미지 속 핵심 수치·내용 포함, 60~120자). "
            "importance: 3=시장·종목에 의미 있는 사실/분석, 2=알아둘 만한 소식, 1=잡담·공지·링크만·중복 재게시.")})
        try:
            res = ask_json(DIGEST_MODEL, "투자 텔레그램 글을 한 줄로 요약·분류하는 보조자.", content, DIGEST_SCHEMA, max_tokens=16000)
        except Exception as e:  # 이 묶음만 원문 앞부분으로 대체하고 나머지는 계속
            print(f"[digest] 묶음 {k // chunk + 1} 요약 실패({e.__class__.__name__}) → 원문 앞부분으로 대체", flush=True)
            continue
        for it in res["items"]:
            out[it["no"]] = it
    for p in posts:  # 혹시 응답에서 빠진 글은 원문 앞부분으로 채운다
        out.setdefault(p["no"], {"no": p["no"], "category": "기타", "importance": 2,
                                 "line": (p["text"] or "(이미지 글)")[:120].replace("\n", " ")})
    return out


# ───────────────────────── 2) 채널 브리프 ─────────────────────────

def channel_brief(posts, digests, with_macro=False, covered=""):
    corpus = []
    for p in posts:
        d = digests.get(p["no"]) or {"importance": 2, "line": (p["text"] or "(이미지 글)")[:120], "category": "기타"}
        body = p["text"] or "(텍스트 없음)"
        if p["photo"]:
            body += f"\n[이미지 내용 요약] {d['line']}"
        corpus.append(f"## #{p['no']} [{p['title']}] {p['time']} (중요도 {d['importance']})\n{body}")
    prompt = ("\n".join(corpus) + "\n\n"
              "위는 투자 텔레그램 채널들의 수집 구간 글 전부(#번호)다. 이를 '투자 아이디어 브리프' 덱으로 만들어라. "
              "채널별 나열 금지, 중복 내용은 하나의 아이디어로 합칠 것. 중요도 3인 글은 가능한 한 모두 반영.\n"
              + (("구성: ① 핵심 이벤트 해부(1장) ② 투자 아이디어 4~7개(아이디어당 1장. 같은 종목·테마·사건은 반드시 하나로 합칠 것. "
                  "중요한 아이디어일수록 deep 5~7문단·calc로 깊게) ③ 실적 상세 표(실적 글이 있을 때만 1장) ④ 한국 투자자 관점(1장). "
                  "Executive Summary·채널 운영자 비교·체크리스트·시장 수치·경제 일정 슬라이드는 만들지 말 것(리포트의 다른 섹션에 있음). "
                  "summary(3분 요약)는 3개 이내.\n"
                  + (f"[리포트 앞부분(매크로 섹션)에서 이미 다룬 주제 — 별도 슬라이드로 다시 만들지 말고, 채널에서 새로 나온 관점·수치가 있을 때만 "
                     f"관련 아이디어 안에서 1~2문장으로 덧붙일 것. 이 주제에 해당하는 글 번호도 가장 관련된 슬라이드의 refs에 넣을 것(본문 반복 없이)]\n{covered}" if covered else "")) if with_macro else
                 ("구성: ① Executive Summary(아이디어 목록 표: 아이디어|한 줄 결론|방향) ② 시장 스냅샷(지수·업종·종목 등락은 change 차트로) "
                  "③ 핵심 이벤트 해부 ④ 투자 아이디어 6~10개(각각 별도 슬라이드, deep 해설 필수) ⑤ 실적 상세 표 "
                  "⑥ 한국 투자자 관점 ⑦ 채널 운영자 시각 비교 ⑧ 캘린더·점검 체크리스트."))
              + "\n\n" + STYLE_RULES)
    return ask_json(ANALYSIS_MODEL, "텔레그램 투자 채널을 읽고 투자 아이디어 브리프를 만드는 시니어 애널리스트.",
                    [{"type": "text", "text": prompt}], DECK, max_tokens=64000)


def coverage_slide(posts, digests, decks):
    """브리프가 근거로 쓰지 않은 글 중 중요도 2 이상을 '그 밖에 알아둘 소식'으로 모아 누락을 없앤다."""
    used = set()
    for d in decks:
        for s in d["slides"]:
            used.update(s.get("refs", []))
    dg = {p["no"]: digests.get(p["no"]) or {"no": p["no"], "category": "기타", "importance": 2,
                                            "line": (p["text"] or "(이미지 글)")[:120].replace("\n", " ")} for p in posts}
    rest = [dg[p["no"]] for p in posts if p["no"] not in used and dg[p["no"]]["importance"] >= 2]
    low = sum(1 for p in posts if p["no"] not in used and dg[p["no"]]["importance"] == 1)
    if not rest:
        return None, low
    rest.sort(key=lambda d: (CATEGORIES.index(d["category"]), -d["importance"]))
    return {
        "tag": "MORE NEWS", "title": "그 밖에 알아둘 소식",
        "key": f"브리프 본문에 들어가지 않은 글 {len(rest)}건을 분야별로 한 줄씩 정리했습니다. 빠짐없이 훑어보는 용도입니다.",
        "kpis": [], "charts": [], "boxes": [], "table_headers": ["분야", "내용"],
        "table_rows": [[("★ " if d["importance"] == 3 else "") + d["category"], d["line"]] for d in rest],
        "deep": [], "calc": [], "so_what": "", "refs": [],
        "sources": f"구독 채널 전체 (잡담·공지·링크·중복 {low}건 제외)",
    }, low


# ───────────────────────── 3) 리포트 갤러리 ─────────────────────────

def _group_reports(posts):
    groups = OrderedDict()
    for p in posts:
        g = groups.setdefault(p["group"], {"time": p["time"], "url": p["url"], "text": "", "images": []})
        if p["text"]:
            g["text"] += p["text"] + "\n"
        if p["photo"]:
            g["images"].append(p["photo"])
    return [g for g in groups.values() if g["images"]]


SCREEN_SCHEMA = _obj({"items": {"type": "array", "items": _obj({
    "id": S, "us_related": {"type": "boolean"}, "broker": S, "title": S, "tickers": SL, "topic": S})}})


def screen_reports(groups, batch=10):
    keep = []
    for k in range(0, len(groups), batch):
        chunk = groups[k:k + batch]
        content = []
        for i, g in enumerate(chunk):
            content.append({"type": "text", "text": f"[R{i}] 캡션: {g['text'][:300] or '(없음)'}"})
            content += [image_block(img) for img in g["images"][:1]]  # 표지 1장만(구독 사용량 절약)
        content.append({"type": "text", "text": "각 R번호에 대해 판정하라. us_related=true 조건: 미국 상장 종목·미국 산업·미국 매크로(연준, 미국 경기, 미국 정책)가 리포트의 주된 대상. 한국 종목 리포트라도 미국 빅테크·미국 수요가 핵심 논지면 true. id는 'R0' 형식."})
        out = ask_json(SCREEN_MODEL, "증권사 리서치 리포트 그림을 분류하는 보조자.", content, SCREEN_SCHEMA, max_tokens=4000)
        for it in out["items"]:
            try:
                g = chunk[int(it["id"].lstrip("R"))]
            except (ValueError, IndexError):
                continue
            if it["us_related"]:
                g.update(broker=it["broker"], title=it["title"], tickers=it["tickers"], topic=it["topic"])
                keep.append(g)
    return keep


REPORT_SCHEMA = _obj({"reports": {"type": "array", "items": _obj({
    "rid": S, "broker": S, "title": S, "tickers": SL, "theme": S, "stance": S,
    "thesis": S, "evidence": SL, "chart_reading": S, "risks": S, "so_what": S})}})


def analyze_reports(groups, batch=4):
    results = []
    for k in range(0, len(groups), batch):
        chunk = groups[k:k + batch]
        content = []
        for i, g in enumerate(chunk):
            content.append({"type": "text", "text": f"=== 리포트 R{i} ({g['time']}) 캡션: {g['text'][:500] or '(없음)'}"})
            content += [image_block(img) for img in g["images"][:6]]
        content.append({"type": "text", "text": (
            "각 리포트 그림을 꼼꼼히 읽고 분석하라. rid='R0' 형식. stance=투자의견·목표가(없으면 '명시 없음'). "
            "thesis=핵심 주장 5~8문장(왜 그런 결론인지 논리 전개 포함). evidence=그림·표에서 읽은 구체 수치 근거 4~8개. "
            "chart_reading=핵심 차트가 보여주는 추세·의미 3~5문장. risks=리포트가 말한/함축한 리스크. "
            "so_what=미국 주식 투자자에게 주는 시사점 2~3문장. theme=테마 분류(예: AI 반도체, 빅테크, 금리·매크로, 에너지 등). "
            "그림에 없는 내용은 지어내지 말 것.")})
        out = ask_json(ANALYSIS_MODEL, "미국 주식 전문 리서치 애널리스트. 증권사 리포트 그림을 읽고 투자자 관점으로 해설한다.",
                       content, REPORT_SCHEMA, max_tokens=32000)
        for r in out["reports"]:
            try:
                g = chunk[int(r["rid"].lstrip("R"))]
                r["url"], r["time"] = g["url"], g["time"]
            except (ValueError, IndexError):
                r["url"], r["time"] = "", ""
            results.append(r)
    return results


def synthesize_reports(analyses):
    lines = []
    for i, r in enumerate(analyses, 1):
        lines.append(f"#{i} [{r['broker']}] {r['title']} | 종목 {', '.join(r['tickers'])} | 테마 {r['theme']} | 의견 {r['stance']}\n"
                     f"주장: {r['thesis']}\n근거: {' / '.join(r['evidence'])}\n차트: {r['chart_reading']}\n"
                     f"리스크: {r['risks']}\n시사점: {r['so_what']}")
    prompt = ("아래는 리포트 갤러리에 올라온 '미국 증시 관련' 증권사 리포트 분석이다(#=리포트 번호). 투자자용 슬라이드 덱으로 재구성하라.\n"
              "- 첫 슬라이드: 리포트 전체를 관통하는 결론(공통점·엇갈리는 지점)과 테마별 리포트 수(stack 또는 level 차트).\n"
              "- 이후: 테마(또는 핵심 종목)별 슬라이드. 같은 종목·테마는 여러 증권사 시각을 비교해 하나로 합칠 것. 목표가·전망치 비교는 level 차트 활용.\n"
              "- 마지막: 리포트 목록 표(증권사|제목|종목|의견) 슬라이드. 모든 리포트가 최소 한 슬라이드의 refs에 들어가야 한다.\n\n"
              + STYLE_RULES + "\n\n" + "\n\n".join(lines))
    return ask_json(ANALYSIS_MODEL, "미국 주식 리서치 헤드. 여러 증권사 리포트를 종합해 투자 아이디어 덱을 만든다.",
                    [{"type": "text", "text": prompt}], DECK, max_tokens=64000)
