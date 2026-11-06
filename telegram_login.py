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
from telethon.errors import SessionPasswordNeededError
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
    while True:
        qr = await client.qr_login()
        show_qr(qr.url)
        try:
            await qr.wait(timeout=60)
            return
        except asyncio.TimeoutError:
            print("1분이 지나 QR을 새로 만듭니다...\n")
        except SessionPasswordNeededError:
            await client.sign_in(password=getpass.getpass("2단계 인증 비밀번호(입력해도 화면에 안 보임): "))
            return


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
    print()
    print(f"로그인 성공: {me.first_name} (id {me.id})")
    print("아래 한 줄 전체를 GitHub Secrets 의 TG_SESSION 값으로 등록하세요:")
    print()
    print(session)
    print()


if __name__ == "__main__":
    asyncio.run(main())
