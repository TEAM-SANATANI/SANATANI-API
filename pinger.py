"""URL pinger: keeps free Render web services awake by hitting a URL on an interval.

Render free instances sleep after ~15 minutes without traffic, so we ping every
10 minutes by default. Not needed (and not started) on Vercel.
"""
import os
import time
import logging
import threading

import requests

log = logging.getLogger("pinger")


def _resolve_urls():
    urls = os.environ.get("PING_URLS") or os.environ.get("PING_URL")
    if urls:
        return [u.strip() for u in urls.split(",") if u.strip()]
    render_url = os.environ.get("RENDER_EXTERNAL_URL")  # set automatically by Render
    if render_url:
        return [render_url.rstrip("/") + "/health"]
    return []


def _loop(urls, interval):
    while True:
        for url in urls:
            try:
                r = requests.get(url, timeout=20)
                log.info("ping %s -> %s", url, r.status_code)
            except Exception as e:
                log.warning("ping %s failed: %s", url, e)
        time.sleep(interval)


def start_pinger():
    urls = _resolve_urls()
    if not urls:
        log.info("pinger: no URL configured, skipping")
        return None
    interval = int(os.environ.get("PING_INTERVAL", "600"))
    t = threading.Thread(target=_loop, args=(urls, interval), daemon=True, name="url-pinger")
    t.start()
    log.info("pinger started for %s every %ss", urls, interval)
    return t
