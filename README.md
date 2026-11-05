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

## 텔레그램 데일리 투자 브리프 (`telegram-report` 워크플로, `tgbrief/`)

매일 한국시간 06:47에 본인 텔레그램 계정으로 **구독 채널 글**과 **리포트 갤러리 이미지**를 수집하고,
Claude가 ① 리포트 중 미국 증시 관련만 골라 상세 분석, ② 채널 글을 투자 아이디어 브리프로 재구성해
슬라이드형 HTML로 만들어 메일로 보냅니다. Actions 탭 → telegram-report → *Run workflow*로 수동 실행도 됩니다.

> 공개 저장소이므로 수집 원문·이미지·결과물은 커밋하지 않으며, 로그에는 건수와 사용량만 남깁니다.

### 처음 한 번 설정 (GitHub → Settings → Secrets and variables → Actions)

| Secret | 값 | 얻는 법 |
|---|---|---|
| `TG_API_ID`, `TG_API_HASH` | 텔레그램 API 키 | https://my.telegram.org → API development tools |
| `TG_SESSION` | 로그인 세션 문자열 | 본인 PC에서 `pip install telethon` 후 `python telegram_login.py` |
| `ANTHROPIC_API_KEY` | Claude API 키 | https://platform.claude.com → API Keys (결제수단 등록 필요) |
| `GMAIL_USER` | 보내는 Gmail 주소 | 예: 본인 Gmail |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 16자리 | Google 계정 → 보안 → 2단계 인증 켠 뒤 → 앱 비밀번호 |
| `MAIL_TO` | 받는 주소(쉼표로 여러 개) | 예: 회사 메일 |

선택(Variables 탭): `TG_CHANNELS`(쉼표 구분 채널 아이디, 기본 13개), `TG_REPORT_CHANNEL`(기본 `report_figure_by_offset`).

### 주의
- `TG_SESSION`은 계정 전체 접근 권한입니다. Secrets 외의 곳에 남기지 마세요. 유출이 의심되면 텔레그램 → 설정 → 기기에서 세션을 종료하세요.
- 리포트 이미지 분석에는 Claude API 비용이 듭니다. 미장 여부 선별은 `claude-haiku-5-5`, 분석은 `claude-opus-5-5`를 씁니다(`TG_SCREEN_MODEL`, `TG_ANALYSIS_MODEL` 환경변수로 변경 가능). 실행 로그 끝에 토큰 사용량이 찍힙니다.
