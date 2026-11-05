"""본인 텔레그램 계정으로 채널 글·이미지를 수집한다 (최근 N시간)."""

import io
import os
from datetime import datetime, timedelta, timezone

from PIL import Image
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto

KST = timezone(timedelta(hours=9))
MAX_IMG_EDGE = 1568  # Claude 이미지 권장 최대 변 길이


def _shrink(data: bytes) -> bytes:
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((MAX_IMG_EDGE, MAX_IMG_EDGE))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


def _link(ent, msg_id):
    if getattr(ent, "username", None):
        return f"https://t.me/{ent.username}/{msg_id}"
    return f"https://t.me/c/{ent.id}/{msg_id}"


async def _fetch(client, username, since, want_photos, photo_text_max=None, max_photos=400):
    ent = await client.get_entity(username)
    title = getattr(ent, "title", username)
    posts, n_photos = [], 0
    async for m in client.iter_messages(ent):
        if m.date < since:
            break
        text = (m.message or "").strip()
        photo = None
        if isinstance(m.media, MessageMediaPhoto) and want_photos and n_photos < max_photos:
            if photo_text_max is None or len(text) < photo_text_max:
                raw = await m.download_media(file=bytes)
                if raw:
                    photo = _shrink(raw)
                    n_photos += 1
        if not text and photo is None:
            continue
        posts.append({
            "channel": username, "title": title, "id": m.id,
            "group": m.grouped_id or m.id,
            "time": m.date.astimezone(KST).strftime("%m-%d %H:%M"),
            "text": text, "photo": photo, "url": _link(ent, m.id),
        })
    posts.reverse()
    return posts


async def collect(channels, report_channel, hours):
    client = TelegramClient(StringSession(os.environ["TG_SESSION"]),
                            int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    brief, reports, errors = [], [], []
    async with client:
        for ch in channels:
            try:
                # 브리프용: 글 전부 + 글이 짧은 이미지 글의 이미지(표·차트가 본문인 경우)
                brief += await _fetch(client, ch, since, True, photo_text_max=120, max_photos=40)
            except Exception as e:  # 채널 하나 실패해도 계속
                errors.append(f"{ch}: {e.__class__.__name__}")
        if report_channel:
            try:
                reports = await _fetch(client, report_channel, since, True)
            except Exception as e:
                errors.append(f"{report_channel}: {e.__class__.__name__}")
    for i, p in enumerate(brief, 1):
        p["no"] = i
    return brief, reports, errors
