#!/usr/bin/env python3
"""Публикует или обновляет закреплённый пост pinned/guides.html в канале."""
import json, os, pathlib, urllib.request, urllib.parse

TOKEN = os.environ["TG_BOT_TOKEN"]
CHAT = os.environ["TG_CHAT_ID"]
ROOT = pathlib.Path(__file__).resolve().parent.parent / "pinned"
TEXT = (ROOT / "guides.html").read_text(encoding="utf-8").strip()
ID_FILE = ROOT / "message_id.txt"


def api(method, data):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=urllib.parse.urlencode(data).encode(),
    )
    try:
        r = json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        r = json.load(e)
    print(method, "ok" if r.get("ok") else r)
    return r


base = {"chat_id": CHAT, "text": TEXT, "parse_mode": "HTML", "link_preview_options": json.dumps({"is_disabled": True})}
if ID_FILE.exists():
    mid = ID_FILE.read_text().strip()
    r = api("editMessageText", {**base, "message_id": mid})
    if not r.get("ok") and "not modified" not in str(r):
        raise SystemExit(1)
else:
    r = api("sendMessage", base)
    if not r.get("ok"):
        raise SystemExit(1)
    mid = r["result"]["message_id"]
    ID_FILE.write_text(str(mid))
    api("pinChatMessage", {"chat_id": CHAT, "message_id": mid, "disable_notification": "true"})
print("message_id", mid)
