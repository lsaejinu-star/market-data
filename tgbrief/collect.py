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


class _Client:
    """로그인된 세션만 허용(미로그인이면 전화번호를 묻지 않고 바로 명확한 오류)."""

    def __init__(self):
        sess = (os.environ.get("TG_SESSION") or "").strip()
        if len(sess) < 100:
            raise RuntimeError(f"TG_SESSION 값이 비었거나 너무 짧음(길이 {len(sess)}). "
                               "telegram_login.py 마지막에 출력된 긴 문자열 한 줄 전체를 등록하세요.")
        self.c = TelegramClient(StringSession(sess), int(os.environ["TG_API_ID"].strip()),
                                os.environ["TG_API_HASH"].strip())

    async def __aenter__(self):
        await self.c.connect()
        if not await self.c.is_user_authorized():
            await self.c.disconnect()
            raise RuntimeError("TG_SESSION 이 로그인되지 않은 세션임(로그인 미완료·기기에서 로그아웃됨·api_id 불일치). "
                               "telegram_login.py 를 다시 실행해 '로그인 성공'이 뜬 뒤 출력된 문자열로 교체하세요.")
        return self.c

    async def __aexit__(self, *exc):
        await self.c.disconnect()


def _client():
    return _Client()


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


async def _fetch(client, target, since, until, photo_text_max=None):
    """[since, until) 구간 글. target은 채널 사용자명 또는 엔티티.
    photo_text_max가 있으면 본문이 그보다 짧은 글의 이미지만 받는다."""
    ent = await client.get_entity(target) if isinstance(target, str) else target
    username = getattr(ent, "username", None) or str(ent.id)
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


def _norm(name):
    return (name or "").lstrip("@").lower()


async def _resolve_channels(client, channels, report_channel):
    """구독 채널 목록. channels에 'auto'가 있으면 텔레그램 대화 목록의 모든 구독 채널(비공개 포함)을 쓴다.
    사기(SCAM)·가짜(FAKE) 표시 채널, 리포트 채널, TG_EXCLUDE에 적은 채널은 제외."""
    exclude = {_norm(x) for x in (os.environ.get("TG_EXCLUDE") or "").split(",") if x.strip()}
    exclude.add(_norm(report_channel))
    names = [c for c in channels if c.lower() != "auto"]
    targets, seen = [], set()
    if len(names) != len(channels):
        async for d in client.iter_dialogs():
            ent = d.entity
            if not getattr(ent, "broadcast", False):  # 방송형 채널만(그룹 대화방·개인 대화 제외)
                continue
            if getattr(ent, "scam", False) or getattr(ent, "fake", False):
                continue
            if _norm(getattr(ent, "username", "")) in exclude or _norm(getattr(ent, "title", "")) in exclude:
                continue
            targets.append(ent)
            seen.add(ent.id)
    for n in names:  # 명시한 채널(그룹 포함)은 그대로 추가
        if _norm(n) in exclude:
            continue
        try:
            ent = await client.get_entity(n)
        except Exception:
            targets.append(n)  # 실패는 _fetch에서 오류로 집계
            continue
        if ent.id not in seen:
            targets.append(ent)
            seen.add(ent.id)
    return targets


async def collect(channels, report_channel, since, until):
    """반환: brief, reports, errors, read_marks{채널 id: 마지막 글 id}, media_only, 수집 채널 수"""
    brief, reports, errors, read_marks, media_only = [], [], [], {}, 0
    async with _client() as client:
        targets = await _resolve_channels(client, channels, report_channel)
        for t in targets:
            label = t if isinstance(t, str) else (getattr(t, "username", None) or getattr(t, "title", t.id))
            try:
                ent = await client.get_entity(t) if isinstance(t, str) else t
                ps, mid, mo = await _fetch(client, ent, since, until, photo_text_max=120)
                brief += ps
                media_only += mo
                if mid:
                    read_marks[ent.id] = mid
            except Exception as e:  # 채널 하나 실패해도 계속
                errors.append(f"{label}: {e.__class__.__name__}")
        if report_channel:
            try:
                ent = await client.get_entity(report_channel)
                reports, mid, _ = await _fetch(client, ent, since, until)
                if mid:
                    read_marks[ent.id] = mid
            except Exception as e:
                errors.append(f"{report_channel}: {e.__class__.__name__}")
    for i, p in enumerate(brief, 1):
        p["no"] = i
    return brief, reports, errors, read_marks, media_only, len(targets)


async def mark_read(read_marks):
    """분석·발송이 끝난 글까지만 읽음 처리(수집 구간 이후에 올라온 글은 안 읽은 상태로 남는다).
    비공개 채널도 처리하도록 대화 목록으로 엔티티를 다시 찾는다. 반환: (성공 수, 실패 목록)"""
    done, failed = 0, []
    async with _client() as client:
        ents = {}
        async for d in client.iter_dialogs():
            ents[d.entity.id] = d.entity
        for cid, max_id in read_marks.items():
            ent = ents.get(cid)
            try:
                if ent is None:
                    raise LookupError("대화 목록에 없음")
                await client.send_read_acknowledge(ent, max_id=max_id)
                done += 1
            except Exception as e:
                failed.append(f"{getattr(ent, 'title', cid)}: {e.__class__.__name__}")
    return done, failed
