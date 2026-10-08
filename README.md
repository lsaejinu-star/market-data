# market-data

매일 미국장 마감 후 GitHub Actions가 데이터를 모아 `data/` 폴더에 저장합니다.
매크로 브리핑 예약 작업이 이 파일들을 읽어 대시보드에 씁니다.

| 파일 | 내용 | 스크립트 |
|---|---|---|
| `data/market_latest.json` | 미국 지수·SOX·VIX, 환율·DXY, 원자재 선물, 코스피·해외지수, 섹터 ETF, 매그니피센트7·노키아, YTD용 ETF, 코인 | `fetch_market.py` |
| `data/macro_latest.json` | FRED: CPI·PCE·PPI(전월비·전년비), 실업률, 비농업고용, 실업수당청구, EFFR, 국채금리, 10-2 스프레드, HY 스프레드 | `fetch_macro.py` |
| `data/breadth_latest.json` | S&P500 기준 시장폭: 상승/하락 종목 수, 52주 신고가/신저가, 50·200일선 위 비율, 상승·하락 상위 10 | `fetch_breadth.py` |
| `data/telegram/<채널>.json` | 텔레그램 공개 채널 최근 26시간 게시물(정확한 게시 시각 포함) | `fetch_telegram.py` |
| `data/news_latest.json` | 국채 입찰 결과·예정(TreasuryDirect), 연준·ECB·BOE·BOJ·한국은행 공식 RSS, 보유주식(GOOGL·NOK) 뉴스 헤드라인 | `fetch_news.py` |
| `data/krw_official.json` | 원/달러 매매기준율(한국은행 ECOS). Secrets에 `ECOS_API_KEY`가 있어야 동작 | `fetch_ecos.py` |
| `data/history_ytd.json` | 대시보드 YTD 차트용 약 14개월 시계열(매일 전체 재생성) | `fetch_history.py` |

시세 파일의 `theme_etfs` 그룹에는 하위 테마 ETF(SMH·IGV·XBI·KRE·ITA·URA·GRID·PAVE)가 들어 있습니다.

- 실행 시각: 평일 UTC 20:20, 21:15 (한국 05:20, 06:15)
- 각 수집은 독립적으로 돌아서 하나가 실패해도 나머지는 저장됩니다.
- 수동 실행: Actions 탭 → market-data → Run workflow

이 저장소에는 API 키나 개인정보를 넣지 마세요.
