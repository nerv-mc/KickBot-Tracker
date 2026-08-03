import time
import os
import base64
import asyncio
import sqlite3
import httpx
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Set

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
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO drops (bot_id, streamer, code, value, claimed_by) VALUES (?, ?, ?, ?, ?)",
            (bot_id, streamer, code, value, claimed_by)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Insert Error: {e}")

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

KICK_ACCESS_TOKEN = "MWI5ZDI4NDMTNDNJMI0ZY2FILTHHODUTMZRMZJQ5NTRIOGVK"
CATEGORY_ID = 28
LIMIT_LIVE = 1000

known_channels = {}
LIVE_RANKING_DATA = []
OFFLINE_RANKING_DATA = []
LATEST_ALERT_DROP = None
LAST_DROP_TIMESTAMP = 0

seen_campaign_ids: Set[str] = set()
KEYWORD_FILTER = ['slot', 'casino', 'stake', 'bonus']

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
            endpoints = [
                "https://web.kick.com/api/v1/drops/campaigns",
                "https://kick.com/api/v2/channels/drops/campaigns",
                "https://kick.com/api/v1/drops/campaigns"
            ]
            
            headers_camp = {
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Referer": "https://kick.com/drops/all-campaigns",
                "Origin": "https://kick.com",
                "Authorization": f"Bearer {KICK_ACCESS_TOKEN}"
            }
            
            campaigns = []
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client_camp:
                for url_target in endpoints:
                    try:
                        res_camp = await client_camp.get(url_target, headers=headers_camp)
                        if res_camp.status_code == 200:
                            resp_json = res_camp.json()
                            if isinstance(resp_json, list):
                                campaigns = resp_json
                            elif isinstance(resp_json, dict):
                                campaigns = resp_json.get("data", resp_json.get("campaigns", []))
                            if campaigns:
                                break
                    except Exception:
                        continue

            for camp in campaigns:
                if not isinstance(camp, dict):
                    continue
                
                camp_id = str(camp.get("id") or camp.get("campaign_id", ""))
                if not camp_id or camp_id in seen_campaign_ids:
                    continue

                camp_name = camp.get("name") or camp.get("title") or "Kick Drop Bonus"
                text_check = f"{camp_name} {camp.get('category', {}).get('name', '')}".lower()
                
                keywords = ['slot', 'casino', 'stake', 'bonus']
                if not any(k in text_check for k in keywords):
                    pass

                seen_campaign_ids.add(camp_id)
                
                channels = camp.get("channels", []) or camp.get("streamers", []) or camp.get("participants", [])
                target_streamer = "kickstreamer"
                
                if channels and isinstance(channels, list):
                    live_ch = next((c for c in channels if isinstance(c, dict) and (c.get("is_live") or c.get("livestream"))), None)
                    ch = live_ch or channels[0]
                    if isinstance(ch, dict):
                        target_streamer = (
                            ch.get("slug") or 
                            ch.get("username") or 
                            ch.get("channel", {}).get("slug") or 
                            (ch.get("user", {}).get("username") if isinstance(ch.get("user"), dict) else None) or
                            "kickstreamer"
                        )
                    elif isinstance(ch, str):
                        target_streamer = ch

                s_lower = str(target_streamer).lower()

                save_drop_to_db(s_lower, "KICK-DROP", camp_name, "System", "System")
                asyncio.create_task(sync_to_spreadsheet_backup(s_lower, camp_name))
                asyncio.create_task(send_telegram_alert(s_lower, camp_name))

                LATEST_ALERT_DROP = {
                    "id": int(time.time() * 1000),
                    "streamer": s_lower,
                    "value": camp_name,
                    "timestamp": int(time.time())
                }
                LAST_DROP_TIMESTAMP = time.time()

        except Exception as e:
            print(f"Error loop fetch kick drops: {e}")

        await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_kick_official_api_loop())

# ---------------------------------------------------------
# 4. ENDPOINTS UTAMA & RECORD DROPS
# ---------------------------------------------------------
@app.get("/")
async def root():
    return {"status": "online", "message": "KickBot Tracker API is running smoothly!"}

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