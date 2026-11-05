"""Gmail SMTP로 HTML 메일 발송 (본문 + 같은 내용의 .html 첨부)."""

import os
import smtplib
from email.message import EmailMessage


def send(subject, html_body, filename):
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    to = [x.strip() for x in os.environ["MAIL_TO"].split(",") if x.strip()]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to)
    msg.set_content("HTML 메일입니다. 첨부된 .html 파일을 열면 원래 디자인으로 볼 수 있습니다.")
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(html_body.encode("utf-8"), maintype="text", subtype="html", filename=filename)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, pw)
        s.send_message(msg)
