#!/usr/bin/env python3
"""Публикация каруселей из instagram/ в Instagram (Instagram API with Instagram Login).

Папка: instagram/YYYY-MM-DD_HHMM_название/ со слайдами 1.jpg, 2.jpg ... (JPEG, 2-10 штук)
и caption.txt. Метка: .published_instagram. Картинки Instagram качает по публичной
ссылке raw.githubusercontent.com, репозиторий должен быть публичным.
Нужен секрет INSTAGRAM_TOKEN (токен Instagram, право instagram_business_content_publish).
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOKEN = os.environ.get("INSTAGRAM_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
API = "https://graph.instagram.com/v23.0"
TZ = timezone(timedelta(hours=7))
MAX_LATE_HOURS = 48
NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_")
ROOT = Path(__file__).resolve().parent.parent / "instagram"
MARK = ".published_instagram"


def call(method, path, params):
    params = {**params, "access_token": TOKEN}
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{API}/{path}?{data.decode()}")
    else:
        req = urllib.request.Request(f"{API}/{path}", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{path}: {e.code} {e.read().decode(errors='replace')}")


def wait_ready(cid):
    for _ in range(40):
        st = call("GET", cid, {"fields": "status_code"})
        if st.get("status_code") == "FINISHED":
            return
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {cid}: {st}")
        time.sleep(4)
    raise RuntimeError(f"container {cid}: таймаут")


def natural(p):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)]


def publish(folder):
    caption = (folder / "caption.txt").read_text(encoding="utf-8").strip()
    imgs = sorted([p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg")], key=natural)[:10]
    if len(imgs) < 2:
        raise RuntimeError("для карусели нужно минимум 2 слайда JPEG")
    base = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/instagram/{urllib.parse.quote(folder.name)}"
    kids = []
    for p in imgs:
        k = call("POST", "me/media", {"image_url": f"{base}/{urllib.parse.quote(p.name)}",
                                      "is_carousel_item": "true"})["id"]
        kids.append(k)
    for k in kids:
        wait_ready(k)
    cid = call("POST", "me/media", {"media_type": "CAROUSEL", "children": ",".join(kids),
                                    "caption": caption})["id"]
    wait_ready(cid)
    call("POST", "me/media_publish", {"creation_id": cid})


def main():
    if not TOKEN:
        print("INSTAGRAM_TOKEN не задан - Instagram пропущен")
        return
    now = datetime.now(TZ)
    failed = False
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir() or (d / MARK).exists():
            continue
        m = NAME_RE.match(d.name)
        if not m:
            continue
        when = datetime.strptime(m[1] + m[2], "%Y-%m-%d%H%M").replace(tzinfo=TZ)
        if when > now or now - when > timedelta(hours=MAX_LATE_HOURS):
            continue
        try:
            publish(d)
            (d / MARK).write_text(now.isoformat() + "\n")
            print(f"instagram опубликовано: {d.name}")
        except Exception as e:  # noqa: BLE001
            failed = True
            msg = str(e).replace("\n", " ")[:400]
            print(f"instagram ОШИБКА {d.name}: {msg}")
            print(f"::error title=instagram {d.name}::{msg}")
        break  # не больше одной карусели за запуск
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
