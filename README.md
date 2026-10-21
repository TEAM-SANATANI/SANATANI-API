# Telegram Music Bot (SanataniBots API)

Send a song name, YouTube link or Spotify track link → bot replies with audio (or video via `/video`).

## Files
| File | Purpose |
|---|---|
| `core.py` | Telegram helpers + SanataniBots API client + command handling |
| `app.py` | Flask app: `/webhook`, `/health`, `/set_webhook`, starts the URL pinger |
| `pinger.py` | Background URL pinger (keeps Render free tier awake) |
| `api/index.py` | Vercel entrypoint |
| `render.yaml`, `vercel.json` | Deploy configs |

## 1. Get keys
1. `@BotFather` → `/newbot` → copy **BOT_TOKEN**.
2. Sanatanibotsapi → Sign in with Google → **API Key** → copy it.
3. Open **Docs** on the dashboard and confirm the endpoint + parameter names. If they differ from the defaults in `.env.example`, change the `SANATANIBOTS_*` env vars (no code edits needed).

## 2. Run locally
```bash
pip install -r requirements.txt
cp .env.example .env   # then: export $(grep -v '^#' .env | xargs)
python app.py polling
```

## 3. Deploy on Render
1. Push this folder to a GitHub repo.
2. Render → **New → Blueprint** → select the repo (it reads `render.yaml`).
3. Fill `BOT_TOKEN` and `SANATANIBOTS_API_KEY` when prompted.
4. After deploy, open once: `https://YOUR-APP.onrender.com/set_webhook?key=WEBHOOK_SECRET`
   (WEBHOOK_SECRET is shown in Render → Environment).
5. The built-in pinger hits `/health` every 10 minutes using `RENDER_EXTERNAL_URL`, so the free instance doesn't sleep.

## 4. Deploy on Vercel
```bash
npm i -g vercel
vercel            # first deploy
vercel env add BOT_TOKEN
vercel env add SANATANIBOTS_API_KEY
vercel env add WEBHOOK_SECRET
vercel --prod
```
Then open `https://YOUR-PROJECT.vercel.app/set_webhook?key=WEBHOOK_SECRET`.

⚠️ A Telegram bot can only have **one webhook**. Use Render *or* Vercel as the live one (call `/set_webhook` on whichever you want active); keep the other as a backup.

⚠️ Vercel functions have time limits (10 s on Hobby by default, up to 60 s configured here where your plan allows) and no background threads, so there is no pinger there and large/slow downloads can time out. **Render is the better primary host for this bot.**

## Commands
- `/song <name or link>` or just send text
- `/video <name or link> [144|360|720|1080|2160]`
- `/ping`, `/help`

## Notes
- Telegram bots can upload files up to 50 MB; bigger files return an error (try lower video quality).
- Free SanataniBots plan: 100 requests/day (25 video). Paid plans are listed on their Pricing page.
- Use this only for content you have the right to download, and follow YouTube's Terms of Service.
