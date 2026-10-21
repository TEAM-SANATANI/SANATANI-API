"""Core logic: Telegram helpers + ArtistBots API client.

NOTE: The ArtistBots docs unlock only after sign-in, so the endpoint path and
parameter names below are configurable via environment variables. Open your
dashboard -> Docs and adjust ARTISTBOTS_ENDPOINT / *_PARAM if they differ.
"""
import os
import re
import tempfile
import logging

import requests

log = logging.getLogger("musicbot")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# --- ArtistBots API config (adjust to match your dashboard docs) ---
API_BASE = os.environ.get("ARTISTBOTS_BASE_URL", "https://artistbotsapi.bond").rstrip("/")
API_KEY = os.environ.get("ARTISTBOTS_API_KEY", "")
API_ENDPOINT = os.environ.get("ARTISTBOTS_ENDPOINT", "/api/download")
QUERY_PARAM = os.environ.get("ARTISTBOTS_QUERY_PARAM", "query")   # title / YouTube / Spotify link
TYPE_PARAM = os.environ.get("ARTISTBOTS_TYPE_PARAM", "type")      # "audio" or "video"
QUALITY_PARAM = os.environ.get("ARTISTBOTS_QUALITY_PARAM", "quality")
KEY_PARAM = os.environ.get("ARTISTBOTS_KEY_PARAM", "api_key")
KEY_IN_HEADER = os.environ.get("ARTISTBOTS_KEY_IN_HEADER", "0") == "1"  # set 1 to send as X-API-Key header

TIMEOUT = int(os.environ.get("API_TIMEOUT", "120"))
MAX_UPLOAD_MB = 48  # Telegram bot upload limit is 50 MB

URL_RE = re.compile(r"https?://\S+")


# ---------------- Telegram helpers ----------------
def tg(method, **kwargs):
    r = requests.post(f"{TG_API}/{method}", timeout=60, **kwargs)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": r.text[:200]}


def send_text(chat_id, text, reply_to=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    return tg("sendMessage", data=data)


def edit_text(chat_id, message_id, text):
    return tg("editMessageText", data={"chat_id": chat_id, "message_id": message_id,
                                        "text": text, "parse_mode": "HTML"})


# ---------------- ArtistBots API ----------------
def call_api(query, kind="audio", quality=None):
    """Calls ArtistBots and returns (response, content_type).
    The response may be a file stream or JSON containing a download URL."""
    params = {QUERY_PARAM: query, TYPE_PARAM: kind}
    if quality:
        params[QUALITY_PARAM] = quality
    headers = {}
    if KEY_IN_HEADER:
        headers["X-API-Key"] = API_KEY
    else:
        params[KEY_PARAM] = API_KEY
    resp = requests.get(API_BASE + API_ENDPOINT, params=params, headers=headers,
                        timeout=TIMEOUT, stream=True)
    return resp


def fetch_media(query, kind="audio", quality=None):
    """Returns (file_path, title) or raises RuntimeError."""
    if not API_KEY:
        raise RuntimeError("ARTISTBOTS_API_KEY is not set.")
    resp = call_api(query, kind, quality)
    if resp.status_code != 200:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text[:150]}")

    ctype = resp.headers.get("Content-Type", "")
    title = query
    ext = "mp4" if kind == "video" else "mp3"

    if "application/json" in ctype:
        data = resp.json()
        url = (data.get("download_url") or data.get("url") or data.get("link")
               or (data.get("data") or {}).get("url"))
        title = data.get("title") or (data.get("data") or {}).get("title") or query
        if not url:
            raise RuntimeError(f"No download link in API response: {str(data)[:150]}")
        resp = requests.get(url, stream=True, timeout=TIMEOUT)
        resp.raise_for_status()

    fd, path = tempfile.mkstemp(suffix=f".{ext}")
    size = 0
    with os.fdopen(fd, "wb") as f:
        for chunk in resp.iter_content(1024 * 256):
            if chunk:
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    f.close()
                    os.remove(path)
                    raise RuntimeError("File is larger than Telegram's 50 MB limit. Try lower quality.")
                f.write(chunk)
    return path, title


def send_media(chat_id, path, title, kind):
    method, field = ("sendVideo", "video") if kind == "video" else ("sendAudio", "audio")
    with open(path, "rb") as f:
        return tg(method, data={"chat_id": chat_id, "title": title[:64], "caption": title[:200]},
                  files={field: f})


# ---------------- Update handler ----------------
HELP = (
    "🎵 <b>Music Bot</b>\n\n"
    "Send me a song name, a YouTube link or a Spotify track link and I'll send the audio.\n\n"
    "/song &lt;name or link&gt; — audio\n"
    "/video &lt;name or link&gt; [144|360|720|1080|2160] — video\n"
    "/ping — check bot is alive"
)


def handle_update(update):
    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg:
        return
    chat_id = msg["chat"]["id"]
    mid = msg["message_id"]
    text = msg["text"].strip()

    kind, quality = "audio", None
    cmd = None
    m = re.match(r"^/(\w+)(?:@\w+)?\s*(.*)$", text, re.S)
    if m:
        cmd, text = m.group(1).lower(), m.group(2).strip()

    if cmd in ("start", "help"):
        send_text(chat_id, HELP)
        return
    if cmd == "ping":
        send_text(chat_id, "🏓 Pong! Bot is alive.")
        return
    if cmd == "video":
        kind = "video"
        q = re.search(r"\s+(144|240|360|480|720|1080|1440|2160)p?$", text)
        if q:
            quality = q.group(1)
            text = text[: q.start()].strip()
    elif cmd not in (None, "song"):
        return  # unknown command

    if not text:
        send_text(chat_id, "Please send a song name or link. Example: <code>/song Kesariya</code>", mid)
        return

    status = send_text(chat_id, "🔎 Searching & downloading…", mid)
    status_id = (status.get("result") or {}).get("message_id")
    path = None
    try:
        path, title = fetch_media(text, kind, quality)
        res = send_media(chat_id, path, title, kind)
        if not res.get("ok"):
            raise RuntimeError(res.get("description", "Telegram upload failed"))
        if status_id:
            tg("deleteMessage", data={"chat_id": chat_id, "message_id": status_id})
    except Exception as e:
        log.exception("download failed")
        if status_id:
            edit_text(chat_id, status_id, f"❌ {str(e)[:300]}")
        else:
            send_text(chat_id, f"❌ {str(e)[:300]}")
    finally:
        if path and os.path.exists(path):
            os.remove(path)
