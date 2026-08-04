# backend/main.py
import time
import asyncio
import sqlite3
import httpx
import os
import time
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request
from typing import Set
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse  # <-- Pastikan ini ada
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="KickBot Tracker API")
app.mount("/static", StaticFiles(directory="static"), name="static")
# Konfigurasi CORS agar frontend terpisah bisa mengakses backend ini
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ubah ke domain frontend Anda nanti saat production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TELEGRAM_BOT_TOKEN = "GANTI_TOKEN"
TELEGRAM_CHAT_ID = "GANTI_CHAT_ID"

async def send_telegram_alert(streamer: str, value: str):
    if not TELEGRAM_BOT_TOKEN or "GANTI_TOKEN" in TELEGRAM_BOT_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
        drop_time_formatted = wib_time.strftime("%H:%M:%S")
        expired_time_formatted = (wib_time + timedelta(minutes=10)).strftime("%H:%M:%S")

        stream_url = f"https://kick.com/{streamer}"
        message_text = (
            f"<b>[KICK DROP DETECTED!]</b>\n\n"
            f"👤 <a href='{stream_url}'>@{streamer}</a>\n"
            f"🎁 <b>Value:</b> {value}\n"
            f"⏰ <b>Waktu Rilis:</b> {drop_time_formatted} - <b>Hangus:</b> {expired_time_formatted} WIB\n\n"
            f"<b>JOIN!!</b>"
        )
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
    except Exception:
        pass

# ---------------------------------------------------------
# ROUTE UTAMA UNTUK DASHBOARD FRONTEND
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home_dashboard():
    index_path = os.path.join("templates", "dashboard.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>File templates/dashboard.html tidak ditemukan!</h3>"


# ---------------------------------------------------------
# SETUP DATABASE SQLITE & SPREADSHEET WEBHOOK
# ---------------------------------------------------------
DB_PATH = "kick_drops.db"
SPREADSHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbz9yDIiHhBlRXfjwsVcmaEHbS_8wvucVR46XmBttCZV0BRqWR7CmmweFM_jRIi_PH76uA/exec"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            streamer TEXT NOT NULL,
            code TEXT NOT NULL,
            value TEXT,
            claimed_by TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_drop_to_db(streamer: str, code: str, value: str = "N/A", claimed_by: str = "System"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO drops (streamer, code, value, claimed_by) VALUES (?, ?, ?, ?)",
        (streamer, code, value, claimed_by)
    )
    conn.commit()
    conn.close()

async def sync_to_spreadsheet_backup(streamer: str, value: str):
    if not SPREADSHEET_WEBHOOK_URL:
        return
    try:
        wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
        payload = {"timestamp": wib_time.strftime("%Y-%m-%d %H:%M:%S"), "streamer": streamer, "value": value}
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(SPREADSHEET_WEBHOOK_URL, json=payload)
    except Exception:
        pass

# ---------------------------------------------------------
# KICK API CONFIGURATION
# ---------------------------------------------------------
ACCESS_TOKEN = "MDZLYJG5ZJETN2JKZS0ZMGRKLWFIMTCTYMJJZWE3ZGFJZJE2"
CATEGORY_ID = 28
LIMIT_LIVE = 1000
KEYWORD_FILTER = ["slots", "casino", "bonus"]

known_channels = {}
LIVE_RANKING_DATA = []
OFFLINE_RANKING_DATA = []
LATEST_ALERT_DROP = None
LAST_DROP_TIMESTAMP = 0
seen_campaign_ids: Set[str] = set()

KICK_HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://kick.com/",
    "User-Agent": "Mozilla/5.0"
}

def is_slots_casino_campaign(camp: dict) -> bool:
    name = camp.get('name', '')
    cat_obj = camp.get('category', {})
    cat_name = cat_obj.get('name', '') if isinstance(cat_obj, dict) else ''
    cat_slug = cat_obj.get('slug', '') if isinstance(cat_obj, dict) else ''
    text = f"{name} {cat_name} {cat_slug}".lower()
    return any(k in text for k in KEYWORD_FILTER)

async def fetch_kick_official_api_loop():
    global LIVE_RANKING_DATA, OFFLINE_RANKING_DATA, known_channels, LATEST_ALERT_DROP, LAST_DROP_TIMESTAMP
    while True:
        try:
            url_live = f"https://api.kick.com/public/v2/livestreams?category_id={CATEGORY_ID}&limit={LIMIT_LIVE}"
            url_campaigns = "https://web.kick.com/api/v1/drops/campaigns"

            async with httpx.AsyncClient(headers=KICK_HEADERS, timeout=15.0, follow_redirects=True) as client:
                res = await client.get(url_live)
                if res.status_code == 200:
                    json_data = res.json()
                    data = json_data.get("data", [])
                    now = int(time.time() * 1000)
                    currently_live = set()
                    live_list = []

                    for s in data:
                        channel_info = s.get("channel", {}) or {}
                        broadcaster_info = s.get("broadcaster_user", {}) or {}
                        channel = channel_info.get("slug") or broadcaster_info.get("username") or "unknown"
                        raw_viewers = s.get("viewer_count")
                        is_hidden = (raw_viewers == 0 or raw_viewers is None)
                        last_known = known_channels.get(channel, {}).get("lastViewers", 0) if channel in known_channels else 0
                        sort_value = last_known if is_hidden else (raw_viewers or 0)

                        live_list.append({
                            "channel": channel,
                            "title": s.get("title") or "-",
                            "viewers": f"HIDDEN (~{last_known:,})" if is_hidden else (raw_viewers or 0),
                            "sortValue": sort_value,
                            "isHidden": is_hidden
                        })
                        currently_live.add(channel)
                        known_channels[channel] = {
                            "lastSeen": now,
                            "lastTitle": s.get("title") or "-",
                            "lastViewers": last_known if is_hidden else (raw_viewers or 0),
                            "wasLive": True
                        }

                    live_list.sort(key=lambda x: x["sortValue"], reverse=True)
                    LIVE_RANKING_DATA = live_list

                res_camp = await client.get(url_campaigns)
                if res_camp.status_code == 200:
                    camp_data = res_camp.json()
                    campaigns = camp_data.get("data", []) if isinstance(camp_data, dict) else camp_data
                    for camp in campaigns:
                        camp_id = str(camp.get("id") or camp.get("campaign_id", ""))
                        if not camp_id or camp_id in seen_campaign_ids or not is_slots_casino_campaign(camp):
                            continue
                        seen_campaign_ids.add(camp_id)

                        channels = camp.get("channels", []) or camp.get("streamers", [])
                        target_streamer = "kickstreamer"
                        if channels and isinstance(channels, list):
                            ch = channels[0]
                            if isinstance(ch, dict):
                                target_streamer = ch.get("slug") or ch.get("username") or "kickstreamer"

                        s_lower = str(target_streamer).lower()
                        camp_name = camp.get("name") or camp.get("title") or "Kick Drop Bonus"

                        save_drop_to_db(s_lower, "KICK-DROP", camp_name, "System")
                        asyncio.create_task(sync_to_spreadsheet_backup(s_lower, camp_name))
                        asyncio.create_task(send_telegram_alert(s_lower, camp_name))

                        LATEST_ALERT_DROP = {"id": int(time.time() * 1000), "streamer": s_lower, "value": camp_name, "timestamp": int(time.time())}
                        LAST_DROP_TIMESTAMP = time.time()
        except Exception:
            pass
        await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_kick_official_api_loop())

@app.get("/api/v1/live-data")
def get_live_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # TOP DROPS STREAMER dibatasi 50 sesuai permintaan sebelumnya
    cursor.execute("""
        SELECT streamer, count(*) as total_drops, max(timestamp) as last_drop_time
        FROM drops GROUP BY streamer ORDER BY total_drops DESC LIMIT 50
    """)
    rows = cursor.fetchall()
    
    cursor.execute("SELECT streamer, value, timestamp FROM drops ORDER BY id DESC LIMIT 5")
    raw_drops = [{"streamer": r[0], "value": r[1], "timestamp": r[2]} for r in cursor.fetchall()]
    conn.close()

    top_drops_streamers = [{"streamer": r[0], "total_drops": r[1], "last_drop_time": r[2]} for r in rows]

    global LATEST_ALERT_DROP, LAST_DROP_TIMESTAMP
    active_alert = LATEST_ALERT_DROP
    if active_alert and (time.time() - LAST_DROP_TIMESTAMP > 120):
        active_alert = None

    return {
        "status": "success",
        "rankings": LIVE_RANKING_DATA,
        "top_drops": top_drops_streamers,
        "drops": raw_drops,
        "latest_alert": active_alert
    }