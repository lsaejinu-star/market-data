"""한국은행 ECOS API로 원/달러 매매기준율(서울외환시장 기준)을 받아 data/krw_official.json 으로 저장한다.

GitHub 저장소 Secrets에 ECOS_API_KEY가 있어야 동작한다. 없으면 status: no_key 로만 기록한다.
통계표 731Y001(주요국 통화의 대원화환율, 일별), 항목 0000001(원/미국달러 매매기준율).
"""

import json
import os
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))


def main():
    now = datetime.now(timezone.utc)
    out = {"fetched_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "series": "731Y001/0000001 원/미국달러 매매기준율"}
    key = os.environ.get("ECOS_API_KEY", "").strip()
    if not key:
        out["status"] = "no_key"
    else:
        end = now.astimezone(KST).strftime("%Y%m%d")
        start = (now.astimezone(KST) - timedelta(days=20)).strftime("%Y%m%d")
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/30/731Y001/D/{start}/{end}/0000001"
        try:
            data = requests.get(url, timeout=30).json()
            rows = data.get("StatisticSearch", {}).get("row", [])
            rows = sorted(rows, key=lambda r: r["TIME"])
            if len(rows) < 2:
                raise ValueError(str(data)[:200].replace(key, "***"))
            last, prev = rows[-1], rows[-2]
            lv, pv = float(last["DATA_VALUE"]), float(prev["DATA_VALUE"])
            out.update({
                "status": "ok",
                "date": f"{last['TIME'][:4]}-{last['TIME'][4:6]}-{last['TIME'][6:]}",
                "value": lv,
                "prev_date": f"{prev['TIME'][:4]}-{prev['TIME'][4:6]}-{prev['TIME'][6:]}",
                "prev_value": pv,
                "change": round(lv - pv, 2),
                "change_pct": round((lv / pv - 1) * 100, 3),
                "unit": rows[-1].get("UNIT_NAME"),
            })
        except Exception as e:
            out["status"] = f"error: {e.__class__.__name__}: {str(e)[:150]}".replace(key, "***")
    os.makedirs("data", exist_ok=True)
    with open("data/krw_official.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"ecos: {out['status']}")


if __name__ == "__main__":
    main()
