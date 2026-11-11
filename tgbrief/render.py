"""덱(JSON) → 슬라이드형 HTML."""

import html
import re
from pathlib import Path

CSS = (Path(__file__).with_name("deck.css")).read_text(encoding="utf-8")
FONT = '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">'
TONE = {"up": "r", "down": "b", "neutral": ""}


_TOK = r"(?:이미지\s*)?#\d+"
REF = re.compile(r"\s*[\(\[]\s*(?:(?:근거|원문|이미지)\s*)?" + _TOK + r"(?:\s*[,·/]\s*(?:이미지\s*)?#?\d+)*\s*[\)\]]")
UP, DOWN, LEVEL = "#EA002C", "#1D4ED8", "#2a78d6"
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # dataviz 기본 범주색(검증된 순서)


def _fmt(text, links=None):
    """본문 텍스트: 이스케이프, **굵게**, 근거 글 번호 제거."""
    t = REF.sub("", text or "")
    t = html.escape(t)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)


def _num(v, unit):
    s = f"{v:+,.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:+,.0f}"
    return s + (unit if unit in ("%", "%p", "bp") else (" " + unit if unit else ""))


def _lvl(v, unit):
    s = f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:,.0f}"
    return s + (unit if unit in ("%", "%p", "bp") else (" " + unit if unit else ""))


def chart(c):
    items = [i for i in c["items"] if isinstance(i.get("value"), (int, float))]
    if not items:
        return ""
    unit = c.get("unit", "")
    o = [f'<div class="chart"><div class="ch-t">{_fmt(c["title"])}</div>']
    if c["kind"] == "stack":
        tot = sum(max(i["value"], 0) for i in items) or 1
        o.append('<div class="stk">' + "".join(
            f'<span title="{html.escape(i["label"])} {i["value"]:g}{html.escape(unit)}" style="width:{max(i["value"],0)/tot*100:.2f}%;background:{CAT[k % len(CAT)]}"></span>'
            for k, i in enumerate(items)) + "</div><div class=\"lg\">" + "".join(
            f'<span><i style="background:{CAT[k % len(CAT)]}"></i>{_fmt(i["label"])} <b>{i["value"]:g}{html.escape(unit)}</b></span>'
            for k, i in enumerate(items)) + "</div></div>")
        return "".join(o)
    level = c["kind"] == "level"
    mx = max(abs(i["value"]) for i in items) or 1
    neg = any(i["value"] < 0 for i in items)
    pos = any(i["value"] > 0 for i in items)
    o.append('<table class="bars">')
    for i in items:
        v = i["value"]; w = abs(v) / mx * 100
        txt = _lvl(v, unit) if level else _num(v, unit)
        color = LEVEL if level else (UP if v >= 0 else DOWN)
        bar = f'<div class="b" title="{html.escape(i["label"])} {txt}" style="width:{max(w,1.5):.1f}%;background:{color}{";margin-left:auto" if v < 0 else ""}"></div>'
        left = bar if v < 0 else ""
        right = bar if v >= 0 else ""
        cells = (f'<td class="lb">{_fmt(i["label"])}</td>'
                 + (f'<td class="half neg">{left}</td>' if neg else "")
                 + (f'<td class="half pos{" ax" if neg else ""}">{right}</td>' if pos or not neg else "")
                 + f'<td class="vl {"" if level else "up" if v > 0 else "dn" if v < 0 else ""}">{txt}</td>')
        o.append(f"<tr>{cells}</tr>")
    o.append("</table></div>")
    return "".join(o)


def slide(s, page, links, sid=""):
    f = lambda x: _fmt(x, links)
    o = [f'<section class="slide"{f" id={sid!r}" if sid else ""}>',
         f'<div class="sh"><div><div class="tag">{f(s["tag"])}</div><h2>{f(s["title"])}</h2></div><div class="pg">{page:02d}</div></div>',
         f'<div class="key"><span class="chip">핵심</span><span>{f(s["key"])}</span></div><div class="body">']
    if s["kpis"]:
        o.append('<div class="kpis">' + "".join(
            f'<div class="kpi {TONE.get(k["tone"], "")}"><div class="v">{f(k["v"])}</div><div class="l">{f(k["l"])}</div></div>'
            for k in s["kpis"]) + "</div>")
    def charts():
        if s.get("charts"):
            o.append('<div class="charts">' + "".join(chart(c) for c in s["charts"]) + "</div>")

    def boxes():
        if s["boxes"]:
            o.append('<div class="g2">')
            for i, b in enumerate(s["boxes"], 1):
                o.append(f'<div class="box{" idea" if b["title"].startswith("💡") else ""}"><h4><span class="n">{i}</span>{f(b["title"])}</h4><ul class="b">'
                         + "".join(f"<li>{f(x)}</li>" for x in b["bullets"]) + "</ul></div>")
            o.append("</div>")

    # 투자 아이디어 박스가 있으면 차트보다 먼저 보여준다
    if s["boxes"] and s["boxes"][0]["title"].startswith("💡"):
        boxes(); charts()
    else:
        charts(); boxes()
    if s["table_headers"] and s["table_rows"]:
        tbl = ('<div style="margin-top:14px;overflow-x:auto"><table class="t"><tr>' + "".join(f"<th>{f(x)}</th>" for x in s["table_headers"]) + "</tr>"
               + "".join("<tr>" + "".join(f"<td>{f(c)}</td>" for c in r) + "</tr>" for r in s["table_rows"]) + "</table></div>")
        if s.get("fold_table"):  # 긴 수치표는 접어 둔다(눌러서 펼침)
            tbl = f'<details class="fold"><summary>수치표 펼치기 ({len(s["table_rows"])}행)</summary>{tbl}</details>'
        o.append(tbl)
    if s["deep"] or s["calc"] or s["so_what"]:
        o.append('<div class="deep"><div class="dh">🔍 상세 해설</div>')
        o += [f'<p><b class="ld">{f(d["lead"])}</b> {f(d["text"])}</p>' for d in s["deep"]]
        if s["calc"]:
            o.append('<div class="calc"><div class="ct">🧮 숫자로 따져보기</div><ul class="b">' + "".join(f"<li>{f(c)}</li>" for c in s["calc"]) + "</ul></div>")
        if s["so_what"]:
            o.append(f'<div class="sw">💡 <b>So what</b> — {f(s["so_what"])}</div>')
        o.append("</div>")
    o.append(f'</div><div class="src">근거: {f(s["sources"])}</div></section>')
    return "\n".join(o)


def section_cover(tag, deck, links, sid):
    f = lambda x: _fmt(x, links)
    return (f'<section class="slide" id="{sid}"><div class="cover"><div class="tag" style="color:#FF8FA3">{html.escape(tag)}</div>'
            f'<h1>{f(deck["headline"])}</h1></div><div class="body"><div class="box s"><h4>3분 요약</h4><ol style="margin:0;padding-left:20px">'
            + "".join(f"<li style='margin:6px 0'>{f(x)}</li>" for x in deck["summary"]) + "</ol></div></div></section>")


def page(title, date_label, stats, sections, notes, kicker="DAILY INVESTMENT BRIEF"):
    """sections: [(tag, deck, links, sid)]. deck에 summary가 없으면 섹션 표지 없이 첫 슬라이드에 앵커를 단다."""
    o = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         f"<title>{html.escape(title)}</title>{FONT}<style>{CSS}</style></head><body><div class=\"deck\">",
         f'<section class="slide"><div class="cover"><div class="tag" style="color:#FF8FA3">{html.escape(kicker)}</div>'
         f'<h1>{html.escape(title)}</h1><div class="sub">{html.escape(date_label)}</div><div class="k2">'
         + "".join(f"<div><b>{html.escape(v)}</b><span>{html.escape(l)}</span></div>" for v, l in stats) + "</div></div>"
         '<div class="body"><div class="box s toc"><h4>목차</h4><ol style="margin:0;padding-left:18px">'
         + "".join(f'<li><a href="#{sid}">{html.escape(tag)}</a></li>' for tag, _, _, sid in sections)
         + '</ol></div></div><div class="src">등락 색: 상승=빨강, 하락=파랑 · 채널 글과 리포트를 재가공한 정보이며 투자 권유가 아닙니다.</div></section>']
    n = 1
    for tag, deck, links, sid in sections:
        first = None
        if deck.get("summary"):
            o.append(section_cover(tag, deck, links, sid))
        else:
            first = sid
        for s in deck["slides"]:
            o.append(slide(s, n, links, first or ""))
            first = None
            n += 1
    o.append('<section class="slide"><div class="sh"><div><div class="tag">APPENDIX</div><h2>수집·분석 범위</h2></div></div><div class="body"><ul class="b">'
             + "".join(f"<li>{html.escape(x)}</li>" for x in notes) + "</ul></div></section></div></body></html>")
    return "\n".join(o)
