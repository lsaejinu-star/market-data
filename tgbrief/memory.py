"""전날 리포트 기억: (1) 전날 상세히 다룬 주제 → 오늘은 새 전개가 없으면 생략, (2) 전날 '확인할 점' → 오늘 확인 결과를 반영.

공개 저장소이므로 파일은 워크플로에서 TG_SESSION으로 암호화해 data/brief_memory.enc로 저장한다(평문은 커밋하지 않음).
TG_MEMORY: 전날 기억(복호화된 JSON) 경로, TG_MEMORY_OUT: 오늘 기억을 쓸 경로.
"""

import json
import os


def load(today):
    path = os.environ.get("TG_MEMORY")
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fp:
            m = json.load(fp)
    except (OSError, ValueError):
        return None
    if m.get("date") == today:  # 같은 날 재실행이면 그날 기억은 쓰지 않는다
        return None
    return m


def topics_text(m):
    if not m:
        return ""
    return "\n".join(f"- {t['topic']}: {t['summary']}" for t in m.get("topics", [])[:60])


def checks_text(m):
    if not m:
        return ""
    return "\n".join(f"- [{c['idea']}] 확인할 점: {c['check']}" for c in m.get("checks", [])[:15])


def build(today, nar, tg_deck, rep_deck):
    """오늘 리포트에서 다음 날을 위한 기억을 만든다."""
    topics, checks = [], []
    if nar:
        for s in nar.get("issues", []):
            topics.append({"topic": s["title"], "summary": s["key"]})
        for s in nar.get("holdings", []):
            topics.append({"topic": s["title"], "summary": s["key"]})
        for i in nar.get("ideas", []):
            topics.append({"topic": "아이디어: " + i["idea"], "summary": i["why"]})
            if i.get("check"):
                checks.append({"idea": i["idea"], "check": i["check"]})
    for deck in (tg_deck, rep_deck):
        for s in (deck or {}).get("slides", []):
            if s.get("tag") != "MORE NEWS":
                topics.append({"topic": s["title"], "summary": s["key"]})
    return {"date": today, "topics": topics, "checks": checks}


def save(m):
    path = os.environ.get("TG_MEMORY_OUT")
    if path and m:
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(m, fp, ensure_ascii=False)
