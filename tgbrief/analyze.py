"""리포트 갤러리 미장 리포트 선별·분석 + 구독 채널 투자 브리프 생성."""

from collections import OrderedDict

from .llm import ANALYSIS_MODEL, SCREEN_MODEL, ask_json, image_block


def _obj(props, req=None):
    return {"type": "object", "properties": props,
            "required": req or list(props), "additionalProperties": False}


S = {"type": "string"}
SL = {"type": "array", "items": S}

# ── 슬라이드(덱) 공통 스키마: 렌더러가 HTML로 바꾼다 ──
SLIDE = _obj({
    "tag": S, "title": S, "key": S,
    "kpis": {"type": "array", "items": _obj({"v": S, "l": S, "tone": {"type": "string", "enum": ["up", "down", "neutral"]}})},
    "boxes": {"type": "array", "items": _obj({"title": S, "bullets": SL})},
    "table_headers": SL,
    "table_rows": {"type": "array", "items": SL},
    "deep": {"type": "array", "items": _obj({"lead": S, "text": S})},
    "calc": SL,
    "so_what": S,
    "sources": S,
})
DECK = _obj({"headline": S, "summary": SL, "slides": {"type": "array", "items": SLIDE}})

STYLE_RULES = """작성 규칙:
- 한국어. 독자는 미국·한국 주식에 투자하는 개인투자자. '뉴스 제목 나열'이 아니라 투자 아이디어 중심으로 깊이 있게.
- 각 슬라이드: tag(영문 대문자 섹션명), title(주장형 제목), key(핵심 한 문장), kpis(핵심 수치 2~5개, 상승=up 하락=down),
  boxes(2~4개, 짧은 글머리표 3~6개), 필요하면 table_headers/table_rows(없으면 빈 배열),
  deep(상세 해설 문단 3~5개: lead=굵은 소제목, text=인과관계와 의미를 4~7문장으로 풀어쓴 해설),
  calc(원문 수치로 직접 계산해 해석한 항목, 없으면 빈 배열), so_what(투자자가 판단할 것 1~2문장), sources(근거 채널/증권사).
- 강조는 **굵게** 표기만 사용. 수치는 원문 그대로, 계산은 calc에 근거를 보여줄 것. 원문에 없는 사실을 지어내지 말 것.
- 투자 권유 표현 금지(매수하라 X). 상반된 시각이 있으면 반드시 함께 제시."""


# ───────────────────────── 리포트 갤러리 ─────────────────────────

def _group_reports(posts):
    """앨범(grouped_id) 단위로 이미지를 묶는다."""
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


def screen_reports(groups, batch=8):
    """각 리포트 묶음의 첫 이미지(표지/요약)로 미국 증시 관련 여부를 가린다."""
    keep = []
    for k in range(0, len(groups), batch):
        chunk = groups[k:k + batch]
        content = []
        for i, g in enumerate(chunk):
            content.append({"type": "text", "text": f"[R{i}] 캡션: {g['text'][:300] or '(없음)'}"})
            content += [image_block(img) for img in g["images"][:2]]
        content.append({"type": "text", "text": "각 R번호에 대해 판정하라. us_related=true 조건: 미국 상장 종목·미국 산업·미국 매크로(연준, 미국 경기, 미국 정책)가 리포트의 주된 대상. 한국 종목 리포트라도 미국 빅테크·미국 수요가 핵심 논지면 true. id는 'R0' 형식."})
        out = ask_json(SCREEN_MODEL, "증권사 리서치 리포트 그림을 분류하는 보조자.", content, SCREEN_SCHEMA,
                       effort="low", max_tokens=4000)
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


def analyze_reports(groups, batch=6):
    """선별된 리포트의 모든 그림을 읽고 리포트별 상세 분석을 만든다."""
    results = []
    for k in range(0, len(groups), batch):
        chunk = groups[k:k + batch]
        content = []
        for i, g in enumerate(chunk):
            content.append({"type": "text", "text": f"=== 리포트 R{i} ({g['time']}) 캡션: {g['text'][:500] or '(없음)'}"})
            content += [image_block(img) for img in g["images"][:10]]
        content.append({"type": "text", "text": (
            "각 리포트 그림을 꼼꼼히 읽고 분석하라. rid='R0' 형식. stance=투자의견·목표가(없으면 '명시 없음'). "
            "thesis=핵심 주장 5~8문장(왜 그런 결론인지 논리 전개 포함). evidence=그림·표에서 읽은 구체 수치 근거 4~8개. "
            "chart_reading=핵심 차트가 보여주는 추세·의미 3~5문장. risks=리포트가 말한/함축한 리스크. "
            "so_what=미국 주식 투자자에게 주는 시사점 2~3문장. theme=테마 분류(예: AI 반도체, 빅테크, 금리·매크로, 에너지 등). "
            "그림에 없는 내용은 지어내지 말 것.")})
        out = ask_json(ANALYSIS_MODEL, "미국 주식 전문 리서치 애널리스트. 증권사 리포트 그림을 읽고 투자자 관점으로 해설한다.",
                       content, REPORT_SCHEMA, effort="high", max_tokens=32000)
        for r in out["reports"]:
            try:
                g = chunk[int(r["rid"].lstrip("R"))]
                r["url"], r["time"] = g["url"], g["time"]
            except (ValueError, IndexError):
                r["url"], r["time"] = "", ""
            results.append(r)
    return results


def synthesize_reports(analyses):
    """리포트별 분석을 테마로 묶어 덱(슬라이드)을 만든다."""
    lines = []
    for i, r in enumerate(analyses, 1):
        lines.append(f"#{i} [{r['broker']}] {r['title']} | 종목 {', '.join(r['tickers'])} | 테마 {r['theme']} | 의견 {r['stance']}\n"
                     f"주장: {r['thesis']}\n근거: {' / '.join(r['evidence'])}\n차트: {r['chart_reading']}\n"
                     f"리스크: {r['risks']}\n시사점: {r['so_what']}")
    prompt = ("아래는 오늘 리포트 갤러리에 올라온 '미국 증시 관련' 증권사 리포트 분석이다. 이를 투자자용 슬라이드 덱으로 재구성하라.\n"
              "- 첫 슬라이드: 오늘 리포트 전체를 관통하는 결론(공통점·엇갈리는 지점)과 테마별 리포트 수 표.\n"
              "- 이후: 테마(또는 핵심 종목)별 슬라이드. 같은 종목·테마는 여러 증권사 시각을 비교해 하나로 합칠 것.\n"
              "- 마지막: 리포트 목록 표(증권사|제목|종목|의견) 슬라이드.\n"
              "- 각 bullet/문단 끝에 근거 리포트 번호를 (#3)처럼 표기.\n\n" + STYLE_RULES + "\n\n" + "\n\n".join(lines))
    return ask_json(ANALYSIS_MODEL, "미국 주식 리서치 헤드. 여러 증권사 리포트를 종합해 투자 아이디어 덱을 만든다.",
                    [{"type": "text", "text": prompt}], DECK, effort="high", max_tokens=64000)


# ───────────────────────── 구독 채널 브리프 ─────────────────────────

def channel_brief(posts, max_images=40):
    corpus, imgs = [], []
    for p in posts:
        corpus.append(f"## #{p['no']} [{p['title']}] {p['time']}\n{p['text'] or '(텍스트 없음 — 이미지 글)'}")
    content = [{"type": "text", "text": "\n".join(corpus)}]
    for p in posts:
        if p["photo"] and len(imgs) < max_images:
            imgs.append(p)
            content += [{"type": "text", "text": f"[#{p['no']} 첨부 이미지]"}, image_block(p["photo"])]
    content.append({"type": "text", "text": (
        "위는 투자 텔레그램 채널들의 최근 24시간 글 전부(#번호)와 텍스트가 짧은 글의 첨부 이미지다.\n"
        "이를 '투자 아이디어 브리프' 덱으로 만들어라. 채널별 나열 금지, 중복 내용은 하나의 아이디어로 합칠 것.\n"
        "구성: ① Executive Summary(아이디어 목록 표: 아이디어|한 줄 결론|방향) ② 시장 스냅샷(지수·업종·종목 표) "
        "③ 핵심 이벤트 해부 ④ 투자 아이디어 6~10개(각각 별도 슬라이드, deep 해설 필수) ⑤ 실적 상세 표 "
        "⑥ 한국 투자자 관점 ⑦ 채널 운영자 시각 비교 ⑧ 캘린더·점검 체크리스트.\n"
        "sources에는 근거 채널명을 적고, 본문 끝에 근거 글 번호를 (#12)처럼 표기.\n\n" + STYLE_RULES)})
    return ask_json(ANALYSIS_MODEL, "텔레그램 투자 채널을 읽고 투자 아이디어 브리프를 만드는 시니어 애널리스트.",
                    content, DECK, effort="high", max_tokens=64000)
