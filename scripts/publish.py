#!/usr/bin/env python3
"""Публикация постов из posts/ в Telegram-канал по расписанию.

Папка поста: posts/YYYY-MM-DD_HHMM_название/ (время по UTC+7).
Внутри: text.md (подпись) и картинки/видео (1.png, 2.png ...).
Опционально meta.json: {"parse_mode": "HTML"}.
После публикации в папке создаётся файл .published.
"""
import json
import os
import re
import sys
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOKEN = os.environ.get("TG_BOT_TOKEN", "")
CHAT = os.environ.get("TG_CHAT_ID", "")
TZ = timezone(timedelta(hours=7))
MAX_LATE_HOURS = 48
IMG = {".jpg", ".jpeg", ".png", ".webp"}
VID = {".mp4", ".mov"}
NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_")
POSTS = Path(__file__).resolve().parent.parent / "posts"


def api(method, fields, files=None):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n".encode()
        body += (v if isinstance(v, str) else json.dumps(v)).encode() + b"\r\n"
    for name, path in (files or {}).items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                 f"filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
        body += path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method}: {e.code} {e.read().decode(errors='replace')}")


def natural(p):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)]


def publish(folder):
    text_file = folder / "text.md"
    text = text_file.read_text(encoding="utf-8").strip() if text_file.exists() else ""
    meta = {}
    if (folder / "meta.json").exists():
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    pm = {"parse_mode": meta["parse_mode"]} if meta.get("parse_mode") else {}
    media = sorted([p for p in folder.iterdir() if p.suffix.lower() in IMG | VID], key=natural)[:10]
    base = {"chat_id": CHAT}

    docs = sorted([p for p in folder.iterdir() if p.suffix.lower() == ".pdf"], key=natural)
    if not media:
        api("sendMessage", {**base, "text": text, **pm})
        for d in docs:
            api("sendDocument", base, {"document": d})
        return

    caption_in_media = bool(text) and len(text) <= 1024
    if len(media) == 1:
        p = media[0]
        is_vid = p.suffix.lower() in VID
        f = {"video" if is_vid else "photo": p}
        extra = {"caption": text, **pm} if caption_in_media else {}
        api("sendVideo" if is_vid else "sendPhoto", {**base, **extra}, f)
    else:
        items, files = [], {}
        for i, p in enumerate(media):
            key = f"f{i}"
            files[key] = p
            it = {"type": "video" if p.suffix.lower() in VID else "photo", "media": f"attach://{key}"}
            if i == 0 and caption_in_media:
                it["caption"] = text
                it.update(pm)
            items.append(it)
        api("sendMediaGroup", {**base, "media": items}, files)
    if text and not caption_in_media:
        api("sendMessage", {**base, "text": text, **pm})
    for d in docs:
        api("sendDocument", base, {"document": d})


def main():
    if not TOKEN or not CHAT:
        sys.exit("Нет TG_BOT_TOKEN или TG_CHAT_ID")
    now = datetime.now(TZ)
    due = []
    for d in sorted(POSTS.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or (d / ".published").exists():
            continue
        m = NAME_RE.match(d.name)
        if not m:
            print(f"пропуск {d.name}: имя не по формату YYYY-MM-DD_HHMM_название")
            continue
        when = datetime.strptime(m[1] + m[2], "%Y-%m-%d%H%M").replace(tzinfo=TZ)
        if when > now:
            continue
        if now - when > timedelta(hours=MAX_LATE_HOURS):
            print(f"пропуск {d.name}: просрочен больше {MAX_LATE_HOURS} ч")
            continue
        due.append(d)
    if not due:
        print("нечего публиковать")
        return
    failed = False
    for d in due:
        try:
            publish(d)
            (d / ".published").write_text(now.isoformat() + "\n")
            print(f"опубликовано: {d.name}")
        except Exception as e:  # noqa: BLE001
            failed = True
            print(f"ОШИБКА {d.name}: {e}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
