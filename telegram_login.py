"""[한 번만 실행] 텔레그램 로그인 후 세션 문자열(TG_SESSION)을 출력한다.

사용법:
    pip install telethon qrcode
    python telegram_login.py          # QR 로그인(추천): 휴대폰 텔레그램으로 QR 스캔
    python telegram_login.py --code   # 전화번호 + 인증코드 방식

- api_id / api_hash 는 my.telegram.org → API development tools 에서 발급.
- QR 방식: 휴대폰 텔레그램 → 설정 → 기기 → '데스크톱 기기 연결'(Link Desktop Device)로 화면의 QR을 스캔.
- 2단계 인증 비밀번호를 쓰면 마지막에 비밀번호를 묻는다.
- 마지막에 출력되는 긴 문자열을 GitHub Secrets 의 TG_SESSION 에 붙여넣는다.

주의: 세션 문자열은 계정 전체에 접근할 수 있는 열쇠다.
      Secrets 외의 곳(채팅, 파일, 커밋)에 절대 남기지 말 것.
"""

import asyncio
import getpass
import sys

from telethon import TelegramClient
from telethon.errors import AuthTokenExpiredError, SessionPasswordNeededError
from telethon.sessions import StringSession


def show_qr(url):
    try:
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        print("(qrcode 패키지가 없어 그림 대신 주소만 표시합니다: pip install qrcode)")
    print("\n휴대폰 텔레그램 → 설정 → 기기 → '데스크톱 기기 연결'로 위 QR을 스캔하세요.")
    print("QR이 안 보이면 터미널 창을 크게(최대화) 하거나 글자를 작게(Ctrl + -) 해보세요.\n")


async def qr_login(client):
    for attempt in range(1, 11):
        if await client.is_user_authorized():
            return
        qr = await client.qr_login()
        print(f"\n===== QR #{attempt} (약 30초 안에 스캔하세요) =====")
        show_qr(qr.url)
        try:
            await qr.wait(timeout=30)
            return
        except asyncio.TimeoutError:
            print("시간이 지나 QR을 새로 만듭니다... (아래 새 QR을 스캔)")
        except AuthTokenExpiredError:
            # 계정이 다른 데이터센터에 있거나 스캔이 늦은 경우. 접속 위치가 맞춰졌으니 새 QR로 다시 시도
            print("QR이 만료됐습니다. 새 QR을 바로 다시 스캔하세요.")
        except SessionPasswordNeededError:
            await client.sign_in(password=getpass.getpass("2단계 인증 비밀번호(입력해도 화면에 안 보임): "))
            return
    raise SystemExit("QR 로그인 실패. 다시 실행하거나 python telegram_login.py --code 를 써보세요.")


async def main():
    api_id = int(input("api_id: ").strip())
    api_hash = input("api_hash: ").strip()
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    if "--code" in sys.argv:
        await client.start(phone=lambda: input("전화번호(+8210... 형식): ").strip())
    else:
        await qr_login(client)
    me = await client.get_me()
    session = client.session.save()
    await client.disconnect()
    with open("tg_session.txt", "w") as fp:
        fp.write(session)
    print()
    print(f"로그인 성공: {me.first_name}")
    print(f"세션 문자열(길이 {len(session)}자)을 tg_session.txt 파일에 저장했습니다.")
    print("왼쪽 탐색기에서 tg_session.txt 열기 → Ctrl+A → Ctrl+C 로 전체 복사 →")
    print("GitHub Secrets 의 TG_SESSION 에 붙여넣으세요. (숫자 10자리 id가 아니라 300자 이상의 긴 문자열입니다)")
    print("등록이 끝나면 파일을 지우세요:  rm tg_session.txt")

if __name__ == "__main__":
    asyncio.run(main())
