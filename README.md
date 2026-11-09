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

매일 한국시간 **06:00(GitHub 예약 지연 대비 새벽 3회 예약 후 대기)에 시작해 07:30에 메일을 보냅니다**. 텔레그램 수집 구간은 **전날 07:00 ~ 당일 06:00(KST)**, 매크로는 직전 미국장 종가 기준입니다. 리포트는 하나의 흐름(오늘의 핵심 → 시장 수치와 해설 → 텔레그램 투자 아이디어 → 보유주식·서학개미 → 리포트 갤러리 → 일정·종합 판단)으로 구성되고, 시세·금리·지표는 같은 작업 안에서 직접 수집합니다(`tgbrief/macro.py`). **Claude 구독 5시간 한도가 08:00 KST에 초기화되도록** 03:00에 1단계(`telegram-prep.yml`: 03:00 이전 글 요약·리포트 분석, 결과는 TG_SESSION으로 암호화한 1일 보관 아티팩트)를 먼저 돌리고, 06:00 2단계가 이어받아 나머지를 처리합니다(Claude 사용은 03:00~07:00 사이에 끝남). 실패하면 원인을 적은 알림 메일이 가고, 예약 실행이 07:15 이후에 시작되면 Claude 없이 간이 브리프를 보냅니다(08:00 한도 보호). Actions에서 수동 실행할 때는 기본이 시험 모드([TEST] 제목, 대기·읽음 처리 없음)입니다.

1. 본인 텔레그램 계정으로 구독 채널 글·이미지와 리포트 갤러리 이미지를 수집
2. **전수 요약**: 모든 글(본문이 이미지인 글은 이미지까지)을 한 줄씩 요약·분류해 누락을 막음
3. 투자 아이디어 브리프 작성(상세 해설·계산·So what, 등락/구성비 **차트** 포함). 본문에 쓰이지 않은 글은 '그 밖에 알아둘 소식' 슬라이드에 모두 정리
4. 리포트 갤러리 중 미국 증시 관련 리포트만 골라 상세 분석
5. 슬라이드형 HTML 메일 발송(본문 + .html 첨부) 후, **수집 구간까지의 글을 텔레그램에서 읽음 처리**

Actions 탭 → telegram-report → *Run workflow*로 수동 실행도 됩니다.

> 공개 저장소이므로 수집 원문·이미지·결과물은 커밋하지 않으며, 로그에는 건수와 사용량만 남깁니다.

### 처음 한 번 설정 (GitHub → Settings → Secrets and variables → Actions)

| Secret | 값 | 얻는 법 |
|---|---|---|
| `TG_API_ID`, `TG_API_HASH` | 텔레그램 API 키 | https://my.telegram.org → API development tools |
| `TG_SESSION` | 로그인 세션 문자열 | PC 또는 Codespace 터미널에서 `pip install telethon qrcode` 후 `python telegram_login.py` → 휴대폰 텔레그램(설정 → 기기 → 데스크톱 기기 연결)으로 QR 스캔 |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude 구독 토큰(1년 유효, Pro/Max 등 구독 필요) | 본인 PC에 Claude Code 설치 후 `claude setup-token` → 브라우저 승인 → 출력된 토큰 |
| `GMAIL_USER` | 보내는 Gmail 주소 | 예: 본인 Gmail |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 16자리 | Google 계정 → 보안 → 2단계 인증 켠 뒤 → 앱 비밀번호 |
| `MAIL_TO` | 받는 주소(쉼표로 여러 개) | 예: `lsaejinu@naver.com` |

선택(Variables 탭): `TG_CHANNELS`(기본 `auto` = 텔레그램 대화 목록의 모든 구독 채널, 비공개 채널 포함, 사기 표시 채널 제외), `TG_EXCLUDE`(빼고 싶은 채널 아이디·이름, 쉼표 구분), `TG_REPORT_CHANNEL`(기본 `report_figure_by_offset`), `TG_MAX_REPORTS`(하루 분석 리포트 상한, 기본 25). 발송·수집 시각과 읽음 처리는 워크플로의 `TG_SEND_AT`, `TG_WINDOW_START`, `TG_WINDOW_END`, `TG_MARK_READ`(1=읽음 처리)로 바꿀 수 있습니다.

### 주의
- `TG_SESSION`은 계정 전체 접근 권한입니다. Secrets 외의 곳에 남기지 마세요. 유출이 의심되면 텔레그램 → 설정 → 기기에서 세션을 종료하세요.
- 분석은 Claude Code CLI를 **구독 토큰**으로 실행하므로 API 요금은 따로 들지 않지만, **구독 사용량 한도를 함께 씁니다**. 미장 여부 선별은 `claude-haiku-5-5`, 분석은 `claude-opus-5-5`(`TG_SCREEN_MODEL`, `TG_ANALYSIS_MODEL`로 변경 가능)이며, 하루 분석 리포트 수는 `TG_MAX_REPORTS`로 제한합니다. 실행 로그 끝에 토큰 사용량이 찍힙니다.
- `CLAUDE_CODE_OAUTH_TOKEN`도 계정 권한이 있는 비밀값입니다. 1년 후 만료되면 `claude setup-token`으로 다시 발급해 교체하세요.
