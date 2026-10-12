#!/usr/bin/env python3
"""Публикация постов из posts/ в Threads (текст, картинка или карусель).

Те же папки, что и для Telegram. Метка: .published_threads.
Картинки Threads качает по публичной ссылке (raw.githubusercontent.com),
поэтому репозиторий должен быть публичным.
Текст длиннее 500 символов режется по абзацам: первая часть идёт с картинками,
остальные - ответами в цепочку.
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

TOKEN = os.environ.get("THREADS_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
API = "https://graph.threads.net/v1.0"
TZ = timezone(timedelta(hours=7))
MAX_LATE_HOURS = 48
LIMIT = 500
IMG = {".jpg", ".jpeg", ".png", ".webp"}
NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_")
POSTS = Path(__file__).resolve().parent.parent / "posts"
MARK = ".published_threads"


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
    for _ in range(30):
        st = call("GET", cid, {"fields": "status,error_message"})
        if st.get("status") == "FINISHED":
            return
        if st.get("status") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {cid}: {st}")
        time.sleep(4)
    raise RuntimeError(f"container {cid}: таймаут")


def publish_container(cid):
    wait_ready(cid)
    return call("POST", "me/threads_publish", {"creation_id": cid})["id"]


def chunks(text):
    if len(text) <= LIMIT:
        return [text]
    out, cur = [], ""
    for para in text.split("\n\n"):
        while len(para) > LIMIT:
            cut = para.rfind(" ", 0, LIMIT)
            cut = cut if cut > 0 else LIMIT
            if cur:
                out.append(cur)
                cur = ""
            out.append(para[:cut])
            para = para[cut:].lstrip()
        if len(cur) + len(para) + 2 <= LIMIT:
            cur = f"{cur}\n\n{para}" if cur else para
        else:
            out.append(cur)
            cur = para
    if cur:
        out.append(cur)
    return out


def natural(p):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)]


def publish(folder):
    tf = folder / "text.md"
    text = tf.read_text(encoding="utf-8").strip() if tf.exists() else ""
    parts = chunks(text) if text else [""]
    imgs = sorted([p for p in folder.iterdir() if p.suffix.lower() in IMG], key=natural)[:20]
    tm = folder / "threads.md"
    if tm.exists():
        # отдельная текстовая ветка: части разделены строкой ---, без картинок
        parts = [x.strip() for x in tm.read_text(encoding="utf-8").split("\n---\n") if x.strip()]
        if any(len(x) > LIMIT for x in parts):
            raise RuntimeError(f"threads.md: часть длиннее {LIMIT} символов")
        imgs = [folder / "th_cover.png"] if (folder / "th_cover.png").exists() else []
    base = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/posts/{urllib.parse.quote(folder.name)}"
    first = {"text": parts[0]} if parts[0] else {}

    if not imgs:
        cid = call("POST", "me/threads", {"media_type": "TEXT", **first})["id"]
    elif len(imgs) == 1:
        cid = call("POST", "me/threads", {
            "media_type": "IMAGE", "image_url": f"{base}/{urllib.parse.quote(imgs[0].name)}", **first})["id"]
    else:
        kids = []
        for p in imgs:
            k = call("POST", "me/threads", {
                "media_type": "IMAGE", "is_carousel_item": "true",
                "image_url": f"{base}/{urllib.parse.quote(p.name)}"})["id"]
            kids.append(k)
        for k in kids:
            wait_ready(k)
        cid = call("POST", "me/threads", {
            "media_type": "CAROUSEL", "children": ",".join(kids), **first})["id"]
    post_id = publish_container(cid)
    last = post_id
    for part in parts[1:]:
        rid = call("POST", "me/threads", {"media_type": "TEXT", "text": part, "reply_to_id": last})["id"]
        last = publish_container(rid)


def main():
    if not TOKEN:
        print("THREADS_TOKEN не задан - Threads пропущен")
        return
    now = datetime.now(TZ)
    failed = False
    for d in sorted(POSTS.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or (d / MARK).exists():
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
            print(f"threads опубликовано: {d.name}")
        except Exception as e:  # noqa: BLE001
            failed = True
            msg=str(e).replace("\n"," ")[:400]
            print(f"threads ОШИБКА {d.name}: {msg}")
            print(f"::error title=threads {d.name}::{msg}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
