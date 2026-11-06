"""Gmail SMTP로 브리프 발송 — 본문은 비우고 .html 파일만 첨부."""

import os
import smtplib
from email.message import EmailMessage


def send(subject, html_body, filename):
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    to = [x.strip() for x in os.environ["MAIL_TO"].split(",") if x.strip()]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to)
    msg.set_content("")
    msg.add_attachment(html_body.encode("utf-8"), maintype="text", subtype="html", filename=filename)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, pw)
        s.send_message(msg)
