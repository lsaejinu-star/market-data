"""작업이 실패했을 때 사용자에게 짧은 알림 메일을 보낸다.

사용: python -m tgbrief.notify <단계 이름> <로그 파일>
Gmail은 텔레그램·Claude와 별개라 대부분의 실패에서 알림이 간다.
"""

import html
import sys
from datetime import datetime

from .collect import KST
from .mailer import send

CAUSES = [
    ("TG_SESSION", "텔레그램 로그인 세션 문제(만료·기기에서 로그아웃). telegram_login.py로 다시 발급해 TG_SESSION Secret을 교체해 주세요."),
    ("AuthKey", "텔레그램 로그인 세션 문제(만료·기기에서 로그아웃). telegram_login.py로 다시 발급해 TG_SESSION Secret을 교체해 주세요."),
    ("CLAUDE_CODE_OAUTH_TOKEN", "Claude 토큰 문제. 'claude setup-token'으로 새로 발급해 CLAUDE_CODE_OAUTH_TOKEN Secret을 교체해 주세요."),
    ("authentication", "Claude 토큰 인증 실패(만료 가능). 'claude setup-token'으로 새로 발급해 Secret을 교체해 주세요."),
    ("rate_limit", "Claude 구독 사용량 한도에 걸렸습니다. 한도가 풀린 뒤 Actions에서 수동 실행하면 됩니다."),
    ("usage limit", "Claude 구독 사용량 한도에 걸렸습니다. 한도가 풀린 뒤 Actions에서 수동 실행하면 됩니다."),
    ("FloodWait", "텔레그램이 잠시 접속을 제한했습니다(요청 과다). 보통 다음 날 자동으로 풀립니다."),
]


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "브리프"
    try:
        log = open(sys.argv[2], encoding="utf-8", errors="replace").read() if len(sys.argv) > 2 else ""
    except OSError:
        log = ""
    cause = next((msg for key, msg in CAUSES if key.lower() in log.lower()), "원인 미상 — 아래 로그 끝부분을 확인하거나 GitHub Actions 실행 기록을 열어 보세요.")
    tail = "\n".join(log.strip().splitlines()[-40:]) or "(로그 없음)"
    now = datetime.now(KST)
    body = (f"<p><b>{html.escape(stage)}</b> 단계가 실패했습니다 ({now:%Y-%m-%d %H:%M} KST).</p>"
            f"<p><b>추정 원인:</b> {html.escape(cause)}</p>"
            "<p>실행 기록: https://github.com/lsaejinu-star/market-data/actions</p>"
            f"<pre style='font-size:12px;white-space:pre-wrap;background:#f4f5f7;padding:10px'>{html.escape(tail)}</pre>")
    send(f"[투자 브리프] ⚠️ {stage} 실패 ({now:%m/%d})", body, None)


if __name__ == "__main__":
    main()
