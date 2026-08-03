import time
import os
import base64
import asyncio
import sqlite3
import httpx
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse, Response
from typing import Dict, List, Set
from get_script import SCRIPT_CONTENT

app = FastAPI(title="KickBot Tracker & Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# KONFIGURASI TELEGRAM BOT & CHANNEL ALERT
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = "7993820592:AAEY5ekIXdi0AyCCCNUZhQpLrV1quFmAX54"
TELEGRAM_CHAT_ID = "@kickbot_tracker"
WIB_TZ = ZoneInfo("Asia/Jakarta")

async def send_telegram_alert(streamer: str, value: str):
    if not TELEGRAM_BOT_TOKEN or "GANTI_TOKEN" in TELEGRAM_BOT_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
        formatted_wib = wib_time.strftime("%d %b %Y - %H:%M:%S")

        message_text = (
            f"🚨 <b>NEW KICK DROP DETECTED!</b>\n\n"
            f"👤 <b>Streamer:</b> @{streamer}\n"
            f"🎁 <b>Event/Value:</b> {value}\n"
            f"⏰ <b>Detected:</b> {formatted_wib} WIB\n\n"
            f"⚡ <i>Pantau leaderboard & pergerakan streamer Slots real-time 24/7 di:</i>\n"
            f"👉 <b><a href='https://kickbot-tracker.online/'>kickbot-tracker.online</a></b>"
        )
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "📺 Tonton Stream Kick", "url": f"https://kick.com/{streamer}"},
                        {"text": "🌐 Buka Live Tracker", "url": "https://kickbot-tracker.online/"}
                    ]
                ]
            }
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
    except Exception:
        pass

# ---------------------------------------------------------
# 1. SETUP DATABASE SQLITE & BACKUP SPREADSHEET
# ---------------------------------------------------------
DB_PATH = "/root/kick-bot-nerv/kick_drops.db"
SPREADSHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbz9yDIiHhBlRXfjwsVcmaEHbS_8wvucVR46XmBttCZV0BRqWR7CmmweFM_jRIi_PH76uA/exec"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id TEXT,
            streamer TEXT NOT NULL,
            code TEXT,
            value TEXT,
            claimed_by TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_drop_to_db(streamer: str, code: str = "KICK-DROP", value: str = "N/A", claimed_by: str = "System", bot_id: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO drops (bot_id, streamer, code, value, claimed_by) VALUES (?, ?, ?, ?, ?)",
        (bot_id, streamer, code, value, claimed_by)
    )
    conn.commit()
    conn.close()

async def sync_to_spreadsheet_backup(streamer: str, value: str):
    if not SPREADSHEET_WEBHOOK_URL:
        return
    try:
        wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
        formatted_wib = wib_time.strftime("%Y-%m-%d %H:%M:%S")

        payload = {
            "timestamp": formatted_wib,
            "streamer": streamer,
            "value": value
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(SPREADSHEET_WEBHOOK_URL, json=payload)
    except Exception:
        pass

# ---------------------------------------------------------
# 2. SETUP ENKRIPSI & KICK API
# ---------------------------------------------------------
SECRET_KEY = b"u1pA8e9X0xYz_K7b-LmNoPqRsTuVwXyZ1234567890A="
cipher = Fernet(SECRET_KEY)

def encrypt_text(plain_text: str) -> str:
    encrypted_bytes = cipher.encrypt(plain_text.encode("utf-8"))
    return base64.urlsafe_b64encode(encrypted_bytes).decode("utf-8")

def decrypt_text(encrypted_text: str) -> str:
    decoded_bytes = base64.urlsafe_b64decode(encrypted_text.encode("utf-8"))
    return cipher.decrypt(decoded_bytes).decode("utf-8")

def get_clean_base_url(request: Request) -> str:
    host = request.headers.get("host", "kickbot-tracker.online")
    return f"https://{host}"

ACCESS_TOKEN = "YJJHNZY3NJETNMU5MS0ZNDUXLWI3NDUTMZQZNDFMYJFLMZVI"
CATEGORY_ID = 28
LIMIT_LIVE = 1000

known_channels = {}
LIVE_RANKING_DATA = []
OFFLINE_RANKING_DATA = []
LATEST_ALERT_DROP = None
LAST_DROP_TIMESTAMP = 0

# Variabel tambahan dari py ke 2 untuk manajemen bot & campaign drops
bot_assignments: Dict[str, dict] = {}
daily_blacklisted_streamers: Dict[str, Set[str]] = {}
blacklisted_pending_until: Dict[str, float] = {}
seen_campaign_ids: Set[str] = set()

ALL_REGISTERED_BOTS = [
    "RestyFadilah12", "Asnbumai", "Inisaripudin", 
    "Suraptbegg", "Distriyana", "Widiastusi1219"
]
KEYWORD_FILTER = ['slot', 'casino', 'stake', 'bonus']

KICK_HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

def get_today_wib_str() -> str:
    return datetime.now(WIB_TZ).strftime("%Y-%m-%d")

def add_to_daily_blacklist_with_delay(streamer: str, delay_minutes: int = 10):
    s_lower = streamer.lower()
    unlock_time = time.time() + (delay_minutes * 60)
    blacklisted_pending_until[s_lower] = unlock_time

def is_blacklisted_today(streamer: str) -> bool:
    s_lower = streamer.lower()
    today = get_today_wib_str()
    if s_lower in daily_blacklisted_streamers.get(today, set()):
        return True
    if s_lower in blacklisted_pending_until:
        unlock_time = blacklisted_pending_until[s_lower]
        if time.time() >= unlock_time:
            if today not in daily_blacklisted_streamers:
                daily_blacklisted_streamers[today] = set()
            daily_blacklisted_streamers[today].add(s_lower)
            del blacklisted_pending_until[s_lower]
            return True
        else:
            return False
    return False

def is_slots_casino_campaign(camp: dict) -> bool:
    name = camp.get('name', '')
    cat_obj = camp.get('category', {})
    cat_name = cat_obj.get('name', '') if isinstance(cat_obj, dict) else ''
    cat_slug = cat_obj.get('slug', '') if isinstance(cat_obj, dict) else ''
    text = f"{name} {cat_name} {cat_slug}".lower()
    return any(k in text for k in KEYWORD_FILTER)

# ---------------------------------------------------------
# 3. BACKGROUND TASK: FETCH DIRECT TO KICK API & CAMPAIGNS
# ---------------------------------------------------------
async def fetch_kick_official_api_loop():
    global LIVE_RANKING_DATA, OFFLINE_RANKING_DATA, known_channels, LATEST_ALERT_DROP, LAST_DROP_TIMESTAMP
    while True:
        try:
            # 1. Cek Kampanye Drop Real-Time (diadaptasi dari py ke 2)
            url_camp = "https://web.kick.com/api/v1/drops/campaigns"
            headers_camp = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            async with httpx.AsyncClient(timeout=10.0) as client_camp:
                res_camp = await client_camp.get(url_camp, headers=headers_camp)
                if res_camp.status_code == 200:
                    campaigns = res_camp.json().get("data", [])
                    for camp in campaigns:
                        camp_id = str(camp.get("id"))
                        if camp_id in seen_campaign_ids:
                            continue
                        if not is_slots_casino_campaign(camp):
                            continue

                        seen_campaign_ids.add(camp_id)
                        channels = camp.get("channels", [])
                        target_streamer = None
                        if channels:
                            live_ch = next((c for c in channels if c.get("is_live") or c.get("livestream")), None)
                            ch = live_ch or channels[0]
                            target_streamer = ch.get("slug") or ch.get("username") or (ch.get("user", {}).get("username") if isinstance(ch.get("user"), dict) else None)

                        if target_streamer:
                            s_lower = target_streamer.lower()
                            camp_name = camp.get("name", "Slots Drop")
                            add_to_daily_blacklist_with_delay(s_lower, delay_minutes=10)

                            save_drop_to_db(s_lower, "KICK-DROP", camp_name, "System")
                            asyncio.create_task(sync_to_spreadsheet_backup(s_lower, camp_name))
                            asyncio.create_task(send_telegram_alert(s_lower, camp_name))

                            LATEST_ALERT_DROP = {
                                "id": int(time.time() * 1000),
                                "streamer": s_lower,
                                "value": camp_name,
                                "timestamp": int(time.time())
                            }
                            LAST_DROP_TIMESTAMP = time.time()

            # 2. Fetch Livestreams Ranking v2
            url = f"https://api.kick.com/public/v2/livestreams?category_id={CATEGORY_ID}&limit={LIMIT_LIVE}"
            async with httpx.AsyncClient(headers=KICK_HEADERS, timeout=15.0, follow_redirects=True) as client:
                res = await client.get(url)

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

                        last_known = 0
                        if channel in known_channels and isinstance(known_channels[channel].get("lastViewers"), int):
                            last_known = known_channels[channel]["lastViewers"]

                        sort_value = last_known if is_hidden else (raw_viewers or 0)

                        live_list.append({
                            "channel": channel,
                            "title": s.get("title") or "-",
                            "viewers": f"HIDDEN (~{last_known:,})" if is_hidden else (raw_viewers or 0),
                            "sortValue": sort_value,
                            "language": s.get("language_code") or "-",
                            "status": "LIVE (Hidden)" if is_hidden else "LIVE",
                            "isHidden": is_hidden
                        })

                        currently_live.add(channel)

                        known_channels[channel] = {
                            "lastSeen": now,
                            "lastTitle": s.get("title") or "-",
                            "lastViewers": known_channels[channel]["lastViewers"] if is_hidden and channel in known_channels else (raw_viewers or 0),
                            "wasLive": True
                        }

                    offline_list = []
                    for ch, info in known_channels.items():
                        if ch not in currently_live and info.get("wasLive"):
                            offline_list.append({
                                "channel": ch,
                                "status": "Offline",
                                "lastTitle": info.get("lastTitle", "-"),
                                "lastViewers": info.get("lastViewers", 0),
                                "offlineSince": f"{round((now - info.get('lastSeen', now)) / 60000)} menit lalu"
                            })

                    live_list.sort(key=lambda x: x["sortValue"], reverse=True)
                    offline_list.sort(key=lambda x: known_channels.get(x["channel"], {}).get("lastSeen", 0), reverse=True)

                    LIVE_RANKING_DATA = live_list
                    OFFLINE_RANKING_DATA = offline_list[:50]

        except Exception:
            pass

        await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_kick_official_api_loop())

# ---------------------------------------------------------
# 4. ENDPOINTS UNTUK RECORD DROPS & TELEGRAM BROADCAST
# ---------------------------------------------------------
@app.post("/api/v1/record-drop")
@app.post("/record-drop")
async def record_drop(request: Request):
    global LATEST_ALERT_DROP, LAST_DROP_TIMESTAMP
    try:
        body = await request.json()
        streamer = body.get("streamer")
        value = body.get("value", "KICK-DROP")
        bot_id = body.get("bot_id", "System")

        if not streamer or streamer == "Unknown Streamer":
            return {"status": "ignored", "message": "Invalid or empty drop payload."}

        save_drop_to_db(streamer, "KICK-DROP", value, bot_id, bot_id)
        asyncio.create_task(sync_to_spreadsheet_backup(streamer, value))
        asyncio.create_task(send_telegram_alert(streamer, value))

        LATEST_ALERT_DROP = {
            "id": int(time.time() * 1000),
            "streamer": streamer,
            "value": value,
            "timestamp": int(time.time())
        }
        LAST_DROP_TIMESTAMP = time.time()

        return {"status": "success", "message": "Drop recorded & broadcasted!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/live-data")
def get_live_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT streamer, count(*) as total_drops, max(timestamp) as last_drop_time
        FROM drops
        GROUP BY streamer
        ORDER BY total_drops DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    
    cursor.execute("SELECT streamer, value, timestamp FROM drops ORDER BY id DESC LIMIT 5")
    raw_drops = [{"streamer": r[0], "value": r[1], "timestamp": r[2]} for r in cursor.fetchall()]
    conn.close()

    top_drops_streamers = []
    for r in rows:
        top_drops_streamers.append({
            "streamer": r[0],
            "total_drops": r[1],
            "last_drop_time": r[2]
        })

    global LATEST_ALERT_DROP, LAST_DROP_TIMESTAMP
    active_alert = LATEST_ALERT_DROP
    if active_alert and (time.time() - LAST_DROP_TIMESTAMP > 120):
        active_alert = None

    return {
        "status": "success",
        "rankings": LIVE_RANKING_DATA,
        "offline": OFFLINE_RANKING_DATA,
        "top_drops": top_drops_streamers,
        "drops": raw_drops,
        "alert_drop": active_alert,
        "latest_alert": active_alert
    }