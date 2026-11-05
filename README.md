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

## 텔레그램 구독 채널 데일리 레포트 (`telegram-report` 워크플로)

내 텔레그램 계정이 **구독 중인 채널 전체**(비공개 채널 포함)의 최근 24시간 글을 모아
종류별(매크로·실적·종목·시장·크립토 등)로 요약하고, 내 텔레그램 **'저장한 메시지'** 로 보냅니다.
매일 UTC 21:47(한국 06:47)에 실행되며, Actions 탭에서 수동 실행도 됩니다.

> 이 저장소는 공개이므로 수집한 글과 레포트는 **커밋하지 않고**, 로그에는 건수만 남깁니다.

### 처음 한 번 설정

1. https://my.telegram.org → *API development tools* 에서 `api_id`, `api_hash` 발급
2. **본인 PC**에서 세션 문자열 만들기
   ```bash
   pip install telethon
   python telegram_login.py
   ```
   휴대폰 번호 → 텔레그램으로 온 인증코드(→ 2단계 비밀번호) 입력 후 출력되는 긴 문자열을 복사
3. GitHub → Settings → Secrets and variables → Actions → *New repository secret*

| Secret | 값 | 필수 |
|---|---|---|
| `TG_API_ID` | 1번의 api_id | ✅ |
| `TG_API_HASH` | 1번의 api_hash | ✅ |
| `TG_SESSION` | 2번에서 출력된 세션 문자열 | ✅ |
| `ANTHROPIC_API_KEY` | Claude API 키. 있으면 AI가 종류별로 요약, 없으면 키워드 분류(각 글 첫 줄 모음) | 선택 |
| `TG_EXCLUDE` | 레포트에서 뺄 채널(@아이디 또는 채널 이름, 쉼표 구분) | 선택 |

그룹 대화방까지 넣으려면 *Variables* 탭에 `TG_INCLUDE_GROUPS` = `1` 추가.

4. Actions → telegram-report → *Run workflow* 로 한 번 실행해 '저장한 메시지'에 레포트가 오는지 확인

### 주의
- `TG_SESSION` 은 계정 전체에 접근할 수 있는 열쇠입니다. Secrets 외의 곳에 남기지 마세요.
  유출이 의심되면 텔레그램 → 설정 → 기기 에서 해당 세션을 종료하고 2번을 다시 하면 됩니다.
- 처음 실행 시 텔레그램이 "새 기기 로그인" 알림을 보낼 수 있습니다(GitHub 서버에서 접속하기 때문).
