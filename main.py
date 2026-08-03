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
from fastapi.responses import HTMLResponse
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
seen_campaign_ids = set()

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
    global LATEST_ALERT_DROP, LAST_DROP_TIMESTAMP
    while True:
        try:
            endpoints = [
                "https://web.kick.com/api/v1/drops/campaigns",
                "https://kick.com/api/v1/drops/campaigns"
            ]
            
            headers_camp = {
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Authorization": f"Bearer {KICK_ACCESS_TOKEN}"
            }
            
            campaigns = []
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                for url_target in endpoints:
                    try:
                        res = await client.get(url_target, headers=headers_camp)
                        if res.status_code == 200:
                            data = res.json()
                            campaigns = data if isinstance(data, list) else data.get("data", data.get("campaigns", []))
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
                seen_campaign_ids.add(camp_id)

                camp_name = camp.get("name") or camp.get("title") or "Kick Drop Bonus"
                channels = camp.get("channels", []) or camp.get("streamers", [])
                target_streamer = "kickstreamer"
                
                if channels and isinstance(channels, list):
                    ch = channels[0]
                    if isinstance(ch, dict):
                        target_streamer = ch.get("slug") or ch.get("username") or "kickstreamer"

                s_lower = str(target_streamer).lower()
                
                # Masukin langsung ke fungsi database asli lu
                save_drop_to_db(s_lower, "KICK-DROP", camp_name, "System", "System")
                asyncio.create_task(sync_to_spreadsheet_backup(s_lower, camp_name))
                asyncio.create_task(send_telegram_alert(s_lower, camp_name))

        except Exception as e:
            print(f"Error: {e}")

        await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_kick_official_api_loop())

# ---------------------------------------------------------
# 4. ENDPOINTS DASHBOARD HTML & API
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    return """<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kick Bot - Live Tracker</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-[#0b0e14] text-gray-200 font-sans min-h-screen p-4 md:p-6">
    <header class="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center bg-[#131722] p-5 rounded-2xl border border-gray-800/80 mb-8 shadow-xl">
        <div class="flex items-center space-x-4 mb-4 md:mb-0">
            <div class="w-12 h-12 bg-green-500 rounded-xl flex items-center justify-center font-bold text-black text-2xl shadow-lg shadow-green-500/20">K</div>
            <div>
                <h1 class="text-xl font-bold text-white tracking-wide">Kick Bot - Live Tracker</h1>
                <p class="text-xs text-gray-400">Official Kick API v2 Livestream Category Slot Harvester</p>
            </div>
        </div>
        <button onclick="openLicenseModal()" class="bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs md:text-sm px-6 py-3 rounded-xl transition duration-200 flex items-center space-x-2 shadow-lg shadow-indigo-600/30">
            <i class="fa-solid fa-key"></i>
            <span>Buka Panel Manajemen Bot →</span>
        </button>
    </header>

    <main class="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-8">
        <section class="lg:col-span-2 bg-[#131722] p-6 rounded-2xl border border-gray-800/80 shadow-xl">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
                <h2 class="text-base font-bold text-white flex items-center space-x-2">
                    <span class="text-red-500">🔥</span>
                    <span>CATEGORY SLOTS LIVE RANKING (TOP 15 REAL-TIME)</span>
                </h2>
                <span class="text-[11px] text-gray-400 bg-gray-900/80 px-3 py-1 rounded-full border border-gray-800 w-max">
                    Status: <span class="text-green-400 font-bold">● Live Connected</span>
                </span>
            </div>
            <div id="streamer-list" class="space-y-3"></div>
        </section>

        <section class="bg-[#131722] p-6 rounded-2xl border border-gray-800/80 shadow-xl flex flex-col">
            <div>
                <h2 class="text-base font-bold text-white mb-1 flex items-center space-x-2">
                    <span class="text-amber-400">🏆</span>
                    <span>TOP DROPS STREAMER</span>
                </h2>
                <p class="text-xs text-gray-400 mb-6">Streamer dengan histori penerimaan drop terbanyak hari ini.</p>
            </div>
            <div id="top-drops-list" class="space-y-3 my-auto">
                <div class="flex flex-col items-center justify-center py-12 text-center">
                    <div class="w-16 h-16 bg-indigo-900/20 text-indigo-400 rounded-full flex items-center justify-center text-3xl mb-3 border border-indigo-800/40">🏆</div>
                    <p class="text-xs font-medium text-gray-400">Menunggu data klaim drop pertama dari bot...</p>
                </div>
            </div>
        </section>
    </main>

    <div id="licenseModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm hidden items-center justify-center p-4 z-50">
        <div class="bg-[#131722] border border-gray-800 p-6 rounded-2xl max-w-md w-full shadow-2xl">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-lg font-bold text-white flex items-center space-x-2"><span>🔑 Masukkan License Key</span></h3>
                <button onclick="closeLicenseModal()" class="text-gray-500 hover:text-white text-lg">✕</button>
            </div>
            <p class="text-xs text-gray-400 mb-6">Akses Panel Manajemen Bot khusus pengguna VIP yang memiliki lisensi aktif.</p>
            <input type="text" id="licenseInput" placeholder="Contoh: VIP-KICK-2026" class="w-full bg-[#181e2b] border border-gray-700 text-white rounded-xl px-4 py-3 mb-4 focus:outline-none focus:border-indigo-500 text-sm">
            <div class="flex space-x-3">
                <button onclick="closeLicenseModal()" class="w-1/2 bg-gray-800 hover:bg-gray-700 text-gray-300 font-semibold py-2.5 rounded-xl text-sm transition">Batal</button>
                <button onclick="submitLicense()" class="w-1/2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-2.5 rounded-xl text-sm transition shadow-lg shadow-indigo-600/30">Masuk Panel →</button>
            </div>
        </div>
    </div>

    <script>
        const streamerData = [
            { rank: 1, name: "hstikkytokky", tag: "FN", title: "WE BACK COMPUTER TOP", viewers: "6,717", priority: true },
            { rank: 2, name: "schneckyrii", tag: "FN", title: "$45,000 BONUS HUNT CELEBRATION", viewers: "3,042", priority: true },
            { rank: 3, name: "cdmatthews", tag: "SLOTS", title: "BONUS HUNT & GIVEAWAYS ACTIVE", viewers: "2,216", priority: false },
            { rank: 4, name: "eddie", tag: "STAKE", title: "WEEKLY STAKE DROPS & STREAM", viewers: "1,850", priority: true },
            { rank: 5, name: "trainwreckstv", tag: "SLOTS", title: "NON STOP SLOTS SESSION", viewers: "1,200", priority: false }
        ];

        function renderStreamers() {
            const container = document.getElementById('streamer-list');
            container.innerHTML = streamerData.map(s => `
                <div class="bg-[#181e2b] p-4 rounded-xl flex items-center justify-between border border-gray-800/80 hover:border-gray-700 transition">
                    <div class="flex items-center space-x-4">
                        <span class="font-bold text-gray-500 text-xs w-5">#${s.rank}</span>
                        <span class="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse"></span>
                        <div>
                            <h3 class="font-bold text-white text-sm">${s.name} <span class="text-green-400 text-xs">[${s.tag}]</span></h3>
                            <p class="text-xs text-gray-500 truncate max-w-[200px] sm:max-w-xs">${s.title}</p>
                        </div>
                    </div>
                    <div class="flex items-center space-x-3">
                        <span class="text-xs font-semibold text-green-400">${s.viewers} Viewers</span>
                        ${s.priority ? `<span class="hidden sm:inline-block bg-indigo-900/50 text-indigo-300 border border-indigo-700/50 text-[10px] font-bold px-2 py-1 rounded-md">🔥 Priority</span>` : ''}
                    </div>
                </div>
            `).join('');
        }
        renderStreamers();

        function openLicenseModal() {
            document.getElementById('licenseModal').classList.remove('hidden');
            document.getElementById('licenseModal').classList.add('flex');
        }

        function closeLicenseModal() {
            document.getElementById('licenseModal').classList.add('hidden');
            document.getElementById('licenseModal').classList.remove('flex');
        }

        function submitLicense() {
            const key = document.getElementById('licenseInput').value.trim();
            if (key) {
                window.location.href = `/panel?license=${encodeURIComponent(key)}`;
            }
        }
    </script>
</body>
</html>"""

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