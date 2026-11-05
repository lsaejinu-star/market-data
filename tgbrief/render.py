"""덱(JSON) → 슬라이드형 HTML."""

import html
import re
from pathlib import Path

CSS = (Path(__file__).with_name("deck.css")).read_text(encoding="utf-8")
FONT = '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">'
TONE = {"up": "r", "down": "b", "neutral": ""}


def _fmt(text, links):
    t = html.escape(text or "")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    if links:
        t = re.sub(r"#(\d+)", lambda m: f'<a href="{links[int(m.group(1))]}" style="color:#2563eb;text-decoration:none">#{m.group(1)}</a>'
                   if int(m.group(1)) in links else m.group(0), t)
    return t


def slide(s, page, links, sid=""):
    f = lambda x: _fmt(x, links)
    o = [f'<section class="slide"{f" id={sid!r}" if sid else ""}>',
         f'<div class="sh"><div><div class="tag">{f(s["tag"])}</div><h2>{f(s["title"])}</h2></div><div class="pg">{page:02d}</div></div>',
         f'<div class="key"><span class="chip">핵심</span><span>{f(s["key"])}</span></div><div class="body">']
    if s["kpis"]:
        o.append('<div class="kpis">' + "".join(
            f'<div class="kpi {TONE.get(k["tone"], "")}"><div class="v">{f(k["v"])}</div><div class="l">{f(k["l"])}</div></div>'
            for k in s["kpis"]) + "</div>")
    if s["boxes"]:
        o.append('<div class="g2">')
        for i, b in enumerate(s["boxes"], 1):
            o.append(f'<div class="box"><h4><span class="n">{i}</span>{f(b["title"])}</h4><ul class="b">'
                     + "".join(f"<li>{f(x)}</li>" for x in b["bullets"]) + "</ul></div>")
        o.append("</div>")
    if s["table_headers"] and s["table_rows"]:
        o.append('<div style="margin-top:14px;overflow-x:auto"><table class="t"><tr>' + "".join(f"<th>{f(x)}</th>" for x in s["table_headers"]) + "</tr>"
                 + "".join("<tr>" + "".join(f"<td>{f(c)}</td>" for c in r) + "</tr>" for r in s["table_rows"]) + "</table></div>")
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


def page(title, date_label, stats, sections, notes):
    """sections: [(tag, deck, links, sid)]"""
    o = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         f"<title>{html.escape(title)}</title>{FONT}<style>{CSS}</style></head><body><div class=\"deck\">",
         '<section class="slide"><div class="cover"><div class="tag" style="color:#FF8FA3">TELEGRAM INVESTMENT BRIEF</div>'
         f'<h1>{html.escape(title)}</h1><div class="sub">{html.escape(date_label)}</div><div class="k2">'
         + "".join(f"<div><b>{html.escape(v)}</b><span>{html.escape(l)}</span></div>" for v, l in stats) + "</div></div>"
         '<div class="body"><div class="box s toc"><h4>목차</h4><ol style="margin:0;padding-left:18px">'
         + "".join(f'<li><a href="#{sid}">{html.escape(tag)}</a></li>' for tag, _, _, sid in sections)
         + '</ol></div></div><div class="src">등락 색: 상승=빨강, 하락=파랑 · 채널 글과 리포트를 재가공한 정보이며 투자 권유가 아닙니다.</div></section>']
    n = 1
    for tag, deck, links, sid in sections:
        o.append(section_cover(tag, deck, links, sid))
        for s in deck["slides"]:
            o.append(slide(s, n, links))
            n += 1
    o.append('<section class="slide"><div class="sh"><div><div class="tag">APPENDIX</div><h2>수집·분석 범위</h2></div></div><div class="body"><ul class="b">'
             + "".join(f"<li>{html.escape(x)}</li>" for x in notes) + "</ul></div></section></div></body></html>")
    return "\n".join(o)
