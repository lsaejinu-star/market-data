"""본인 텔레그램 계정으로 채널 글·이미지를 수집하고, 처리 후 읽음 처리한다."""

import io
import os
from datetime import timedelta, timezone

from PIL import Image
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto

KST = timezone(timedelta(hours=9))
MAX_IMG_EDGE = 1568  # Claude 이미지 권장 최대 변 길이


def _client():
    return TelegramClient(StringSession(os.environ["TG_SESSION"]),
                          int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])


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


async def _fetch(client, username, since, until, photo_text_max=None):
    """[since, until) 구간 글. photo_text_max가 있으면 본문이 그보다 짧은 글의 이미지만 받는다."""
    ent = await client.get_entity(username)
    title = getattr(ent, "title", username)
    posts, max_id, n_media_only = [], 0, 0
    async for m in client.iter_messages(ent, offset_date=until):  # until 이전 글부터 최신순
        if m.date < since:
            break
        max_id = max(max_id, m.id)
        text = (m.message or "").strip()
        photo = None
        if isinstance(m.media, MessageMediaPhoto) and (photo_text_max is None or len(text) < photo_text_max):
            raw = await m.download_media(file=bytes)
            photo = _shrink(raw) if raw else None
        if not text and photo is None:
            n_media_only += 1  # 영상·투표·스티커 등
            continue
        posts.append({"channel": username, "title": title, "id": m.id, "group": m.grouped_id or m.id,
                      "time": m.date.astimezone(KST).strftime("%m-%d %H:%M"),
                      "text": text, "photo": photo, "url": _link(ent, m.id)})
    posts.reverse()
    return posts, max_id, n_media_only


async def collect(channels, report_channel, since, until):
    brief, reports, errors, read_marks, media_only = [], [], [], {}, 0
    async with _client() as client:
        for ch in channels:
            try:
                ps, mid, mo = await _fetch(client, ch, since, until, photo_text_max=120)
                brief += ps
                media_only += mo
                if mid:
                    read_marks[ch] = mid
            except Exception as e:  # 채널 하나 실패해도 계속
                errors.append(f"{ch}: {e.__class__.__name__}")
        if report_channel:
            try:
                reports, mid, _ = await _fetch(client, report_channel, since, until)
                if mid:
                    read_marks[report_channel] = mid
            except Exception as e:
                errors.append(f"{report_channel}: {e.__class__.__name__}")
    for i, p in enumerate(brief, 1):
        p["no"] = i
    return brief, reports, errors, read_marks, media_only


async def mark_read(read_marks):
    """분석·발송이 끝난 글까지만 읽음 처리(수집 구간 이후에 올라온 글은 안 읽은 상태로 남는다)."""
    done = 0
    async with _client() as client:
        for ch, max_id in read_marks.items():
            try:
                await client.send_read_acknowledge(await client.get_entity(ch), max_id=max_id)
                done += 1
            except Exception:
                pass
    return done
