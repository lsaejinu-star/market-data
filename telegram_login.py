"""[본인 PC에서 한 번만 실행] 텔레그램 로그인 후 세션 문자열(TG_SESSION)을 출력한다.

사용법:
    pip install telethon
    python telegram_login.py

- my.telegram.org → API development tools 에서 받은 api_id / api_hash 를 입력한다.
- 휴대폰 번호와 텔레그램으로 온 인증코드(2단계 인증 비밀번호가 있으면 그것도)를 입력한다.
- 마지막에 출력되는 긴 문자열을 GitHub Secrets 의 TG_SESSION 에 붙여넣는다.

주의: 세션 문자열은 계정 전체에 접근할 수 있는 열쇠다.
      Secrets 외의 곳(채팅, 파일, 커밋)에 절대 남기지 말 것.
"""

from telethon.sessions import StringSession
from telethon.sync import TelegramClient


def main():
    api_id = int(input("api_id: ").strip())
    api_hash = input("api_hash: ").strip()
    with TelegramClient(StringSession(), api_id, api_hash) as client:
        me = client.get_me()
        session = client.session.save()
    print()
    print(f"로그인 성공: {me.first_name} (id {me.id})")
    print("아래 한 줄 전체를 GitHub Secrets 의 TG_SESSION 값으로 등록하세요:")
    print()
    print(session)
    print()


if __name__ == "__main__":
    main()
