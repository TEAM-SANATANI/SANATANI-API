"""Flask app: Telegram webhook + health endpoint + URL pinger.

Run modes
- Render:  gunicorn app:app   (webhook + background pinger)
- Vercel:  api/index.py imports `app` (webhook only, no pinger)
- Local:   python app.py polling
"""
import os
import sys
import time
import logging
import threading

from flask import Flask, request, jsonify

import core
from pinger import start_pinger

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)
ON_VERCEL = bool(os.environ.get("VERCEL"))
SECRET = os.environ.get("WEBHOOK_SECRET", "")  # letters, digits, _ and - only

if not ON_VERCEL:
    start_pinger()


@app.get("/")
def home():
    return "🎵 Music bot is running"


@app.get("/health")
def health():
    return jsonify(status="ok", ts=int(time.time()))


@app.post("/webhook")
def webhook():
    if SECRET and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
        return "forbidden", 403
    update = request.get_json(silent=True) or {}
    if ON_VERCEL:
        # Serverless: must finish work before the function returns.
        core.handle_update(update)
    else:
        threading.Thread(target=core.handle_update, args=(update,), daemon=True).start()
    return "ok"


def _public_url():
    if os.environ.get("PUBLIC_URL"):
        return os.environ["PUBLIC_URL"].rstrip("/")
    if os.environ.get("RENDER_EXTERNAL_URL"):
        return os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
    if os.environ.get("VERCEL_PROJECT_PRODUCTION_URL"):
        return "https://" + os.environ["VERCEL_PROJECT_PRODUCTION_URL"]
    return request.url_root.rstrip("/").replace("http://", "https://")


@app.get("/set_webhook")
def set_webhook():
    if SECRET and request.args.get("key") != SECRET:
        return "forbidden (add ?key=WEBHOOK_SECRET)", 403
    url = _public_url() + "/webhook"
    data = {"url": url, "drop_pending_updates": "true"}
    if SECRET:
        data["secret_token"] = SECRET
    return jsonify(core.tg("setWebhook", data=data), webhook_url=url)


def run_polling():
    """Local development: long polling instead of webhook."""
    core.tg("deleteWebhook")
    offset = None
    log.info("Polling started")
    while True:
        res = core.tg("getUpdates", data={"timeout": 30, "offset": offset or 0})
        for upd in res.get("result", []):
            offset = upd["update_id"] + 1
            threading.Thread(target=core.handle_update, args=(upd,), daemon=True).start()
        time.sleep(0.5)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "polling":
        run_polling()
    else:
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
