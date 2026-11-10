"""슬라이드별 용어 각주.

- 각 슬라이드 본문에 나온 전문용어를 슬라이드 아래 각주로 설명한다(비전공자 기준).
- 같은 리포트 안에서는 처음 나온 슬라이드에서 한 번만 설명한다.
- 누적 설명 횟수를 data/glossary.json에 저장하고, 20번 이상 설명한 용어는 더 이상 각주로 달지 않는다(이미 익숙해진 용어).
- 용어 후보: AI가 슬라이드마다 뽑은 glossary + 파이썬 수치 슬라이드용 기본 사전.
"""

import json
import os
import re
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "glossary.json"
LIMIT = int(os.environ.get("TG_GLOSSARY_LIMIT") or 20)
MAX_PER_SLIDE = 6

# 수치 슬라이드(파이썬 생성)에 자주 나오는 용어 기본 설명
SEED = {
    "VIX": "S&P500 옵션 가격으로 계산한 '공포지수'. 높을수록 투자자들이 앞으로 큰 변동을 걱정한다는 뜻(보통 20 이상이면 불안, 30 이상이면 공포).",
    "SOX": "필라델피아 반도체 지수. 엔비디아·AMD·TSMC 등 미국에 상장된 반도체 기업 30개로 구성.",
    "러셀2000": "미국 중소형주 2,000개로 만든 지수. 경기와 금리에 민감해 '위험을 감수하려는 심리'를 보여주는 지표로 쓰임.",
    "매그니피센트7": "애플·마이크로소프트·알파벳·아마존·엔비디아·메타·테슬라 7개 초대형 기술주. S&P500 시가총액의 약 3분의 1을 차지.",
    "시장폭": "지수에 속한 종목 중 오른 종목과 내린 종목의 비율. 지수가 올라도 내린 종목이 많으면 일부 대형주만 끌어올린 '좁은 상승'.",
    "동일가중": "종목 크기와 상관없이 모든 종목을 같은 비중으로 계산한 평균. 시가총액 가중 지수와 비교하면 대형주 쏠림 여부를 알 수 있음.",
    "52주 신고가": "최근 1년(52주) 중 가장 높은 가격. 신고가 종목이 많을수록 시장 전반이 강하다는 뜻.",
    "50일선": "최근 50거래일 평균 주가. 이 선 위에 있는 종목 비율이 높을수록 단기 추세가 좋은 종목이 많다는 뜻.",
    "200일선": "최근 200거래일 평균 주가. 장기 추세의 기준선으로 많이 쓰임.",
    "섹터 ETF": "특정 업종(기술·금융·에너지 등)에 속한 종목을 묶어 주식처럼 거래하는 펀드. 업종 전체의 흐름을 볼 때 씀.",
    "bp": "베이시스 포인트. 0.01%포인트. 금리가 4.00%에서 4.25%로 오르면 25bp 상승.",
    "10년-2년 스프레드": "10년 만기 국채금리에서 2년 만기 금리를 뺀 값. 마이너스(역전)면 경기침체 신호로 해석되는 경우가 많음.",
    "EFFR": "실효연방기금금리. 미국 은행끼리 하루 동안 돈을 빌려줄 때 실제로 적용된 평균 금리로, 연준 기준금리를 대표.",
    "HY OAS": "하이일드(신용등급이 낮은 회사) 채권 금리가 국채보다 얼마나 높은지(스프레드). 커질수록 기업 부도 위험을 걱정한다는 뜻.",
    "하이일드": "신용등급이 낮은(BB+ 이하) 회사가 발행한 고위험·고금리 채권.",
    "FOMC": "미국 연방공개시장위원회. 연 8회 회의를 열어 기준금리를 결정하는 연준의 핵심 기구.",
    "연방기금 선물": "앞으로의 미국 기준금리 수준에 베팅하는 선물 상품. 가격으로 시장이 예상하는 금리 인하·동결 확률을 계산할 수 있음(CME FedWatch의 원리).",
    "FedWatch": "CME가 연방기금 선물 가격으로 계산해 공개하는 'FOMC 금리 결정 확률' 도구.",
    "응찰률": "국채 입찰에서 발행 금액 대비 응찰 금액의 배수. 높을수록 수요가 강하다는 뜻.",
    "간접 응찰": "해외 중앙은행 등 외국 투자자가 주로 참여하는 응찰 방식. 비중이 높으면 해외 수요가 강하다는 뜻.",
    "달러인덱스": "유로·엔·파운드 등 주요 6개 통화 대비 달러 가치를 지수로 만든 것. 오르면 달러 강세.",
    "DXY": "달러인덱스. 주요 6개 통화 대비 달러 가치 지수. 오르면 달러 강세.",
    "근월물": "선물 중 만기가 가장 가까운 계약. 원자재 '시세'로 보통 근월물 가격을 씀.",
    "WTI": "미국 서부 텍사스산 원유. 미국 유가의 기준.",
    "브렌트": "북해산 원유. 국제 유가의 기준.",
    "CPI": "소비자물가지수. 소비자가 사는 상품·서비스 가격의 변화로 인플레이션을 재는 대표 지표.",
    "근원": "물가 지표에서 변동이 큰 에너지·식품을 뺀 값. 물가의 기조적인 흐름을 볼 때 씀.",
    "PCE": "개인소비지출 물가지수. 연준이 물가 목표(2%)의 기준으로 삼는 지표.",
    "PPI": "생산자물가지수. 기업이 파는 상품·서비스 가격 변화로, 소비자물가에 앞서 움직이는 경우가 많음.",
    "비농업고용": "농업을 제외한 미국 일자리 증감 수. 매달 첫 금요일 발표되는 핵심 고용 지표.",
    "실업수당청구": "새로 실업수당을 신청한 사람 수(주간). 고용시장 변화를 빨리 보여주는 지표.",
    "YTD": "연초 대비(Year To Date). 올해 첫 거래일부터 지금까지의 등락률.",
    "매매기준율": "은행이 외화를 사고팔 때 기준이 되는 환율. 실제 환전 환율은 여기에 수수료가 붙음.",
    "광통신": "빛(레이저)으로 데이터를 보내는 통신 기술. AI 데이터센터에서 서버 간 대용량 연결 수요가 급증하는 분야.",
    "코히어런트": "빛의 위상까지 활용해 한 번에 더 많은 데이터를 멀리 보내는 고성능 광통신 방식.",
    "광트랜시버": "전기 신호를 빛으로, 빛을 다시 전기 신호로 바꿔주는 광통신 부품. 데이터센터 서버 연결에 필수.",
}


def load():
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(db):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(db, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def _text(s):
    parts = [s.get("title", ""), s.get("key", ""), s.get("so_what", "")]
    parts += [k.get("v", "") + " " + k.get("l", "") for k in s.get("kpis", [])]
    parts += [c.get("title", "") + " " + " ".join(i.get("label", "") for i in c.get("items", [])) for c in s.get("charts", [])]
    for b in s.get("boxes", []):
        parts += [b.get("title", "")] + b.get("bullets", [])
    parts += s.get("table_headers", []) + [" ".join(r) for r in s.get("table_rows", [])]
    parts += [d.get("lead", "") + " " + d.get("text", "") for d in s.get("deep", [])]
    parts += s.get("calc", [])
    return " ".join(p for p in parts if p)


def _hit(term, text):
    if re.fullmatch(r"[A-Za-z0-9&\-\. ]+", term):  # 영문 약어는 단어 경계로
        return re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", text) is not None
    return term in text


def annotate(sections):
    """sections의 모든 슬라이드에 s['footnotes']=[(용어, 설명)]를 단다. 갱신된 누적 DB를 돌려준다."""
    db = load()
    used = set()
    for _, deck, _, _ in sections:
        for s in deck.get("slides", []):
            text = _text(s)
            cands = [(g["term"].strip(), g["desc"].strip()) for g in s.get("glossary", []) if g.get("term") and g.get("desc")]
            cands += [(t, d) for t, d in SEED.items() if _hit(t, text)]
            notes = []
            for term, desc in cands:
                key = term.lower()
                if key in used or not term or len(notes) >= MAX_PER_SLIDE:
                    continue
                ent = db.get(key) or {"term": term, "desc": desc, "count": 0}
                if ent["count"] >= LIMIT:
                    continue  # 이미 20번 이상 설명한 용어
                used.add(key)
                ent["count"] += 1
                ent.setdefault("desc", desc)
                db[key] = ent
                notes.append((term, ent["desc"]))
            s["footnotes"] = notes
    return db
