# market-data

매일 미국장 마감 후 GitHub Actions가 시세를 모아 `data/market_latest.json`에 저장합니다.
매크로 브리핑 예약 작업이 이 파일을 읽어 대시보드에 씁니다.

- 수집 항목: 미국 지수·SOX·VIX, 환율·달러인덱스, 원자재 선물, 코스피·코스닥 및 해외지수, 섹터 ETF 11개, 매그니피센트7·노키아, YTD용 ETF, 비트코인·이더리움
- 실행 시각: 평일 UTC 20:20, 21:15 (한국 05:20, 06:15)
- 각 항목의 `last_date`가 그 값의 거래일입니다. 기준일과 다르면 그날 값이 아직 없거나 휴장입니다.
- 수동 실행: Actions 탭 → market-data → Run workflow

이 저장소에는 API 키나 개인정보를 넣지 마세요.
