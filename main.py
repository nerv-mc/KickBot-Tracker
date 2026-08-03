import time
import os
import base64
import asyncio
import sqlite3
import httpx
import secrets
import string
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse, Response
from typing import Set, Dict, List
from get_script import SCRIPT_CONTENT

app = FastAPI(title="KickBot Tracker API")

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
KEYWORD_FILTER = ['slot', 'casino', 'stake', 'bonus']

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
# 1. SETUP DATABASE SQLITE & DUAL SPREADSHEET WEBHOOK
# ---------------------------------------------------------
DB_PATH = "/root/kick-bot-nerv/kick_drops.db"

# Spreadsheet 1: Khusus log Drops Streamer
SPREADSHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbz9yDIiHhBlRXfjwsVcmaEHbS_8wvucVR46XmBttCZV0BRqWR7CmmweFM_jRIi_PH76uA/exec"

# Spreadsheet 2: Khusus log License Key (Nama | License | Created Time | Expired Time)
LICENSE_SPREADSHEET_WEBHOOK_URL = "https://docs.google.com/spreadsheets/d/1x5wIdNkGrzNhXCmoimSarGF93etL3_hLmFBV5XRn1rc/edit?gid=0#gid=0" # Ganti URL Web App Spreadsheet Lisensi lu di sini

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE,
            expiry_date TEXT,
            status TEXT DEFAULT 'active',
            device_id TEXT DEFAULT NULL
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

def generate_vip_license(days_valid: int = 30, buyer: str = "General Buyer") -> tuple:
    alphabet = string.ascii_uppercase + string.digits
    chunk1 = "".join(secrets.choice(alphabet) for _ in range(4))
    chunk2 = "".join(secrets.choice(alphabet) for _ in range(4))
    license_key = f"VIP-KICK-{chunk1}-{chunk2}"
    
    expiry_date = datetime.now() + timedelta(days=days_valid)
    expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO licenses (license_key, expiry_date, status, device_id) VALUES (?, ?, ?, ?)",
            (license_key, expiry_str, 'active', None)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving license: {e}")
        
    return license_key, expiry_str

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

async def sync_license_to_spreadsheet(license_key: str, expiry_str: str, days: int, buyer: str):
    if not LICENSE_SPREADSHEET_WEBHOOK_URL or "GANTI_URL" in LICENSE_SPREADSHEET_WEBHOOK_URL:
        return
    try:
        wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
        formatted_wib = wib_time.strftime("%Y-%m-%d %H:%M:%S")

        payload = {
            "nama": buyer,
            "license": license_key,
            "created_time": formatted_wib,
            "expired_time": expiry_str
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(LICENSE_SPREADSHEET_WEBHOOK_URL, json=payload)
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

ACCESS_TOKEN = "MDZLYJG5ZJETN2JKZS0ZMGRKLWFIMTCTYMJJZWE3ZGFJZJE2"
CATEGORY_ID = 28
LIMIT_LIVE = 1000

known_channels = {}
LIVE_RANKING_DATA = []
OFFLINE_RANKING_DATA = []
LATEST_ALERT_DROP = None
LAST_DROP_TIMESTAMP = 0
seen_campaign_ids: Set[str] = set()

KICK_HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

def is_slots_casino_campaign(camp: dict) -> bool:
    name = camp.get('name', '')
    cat_obj = camp.get('category', {})
    cat_name = cat_obj.get('name', '') if isinstance(cat_obj, dict) else ''
    cat_slug = cat_obj.get('slug', '') if isinstance(cat_obj, dict) else ''
    text = f"{name} {cat_name} {cat_slug}".lower()
    return any(k in text for k in KEYWORD_FILTER)

# ---------------------------------------------------------
# 3. BACKGROUND TASK: FETCH DIRECT KICK API V2 & CAMPAIGNS
# ---------------------------------------------------------
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

                res_camp = await client.get(url_campaigns)
                if res_camp.status_code == 200:
                    camp_data = res_camp.json()
                    campaigns = camp_data.get("data", []) if isinstance(camp_data, dict) else camp_data
                    
                    for camp in campaigns:
                        camp_id = str(camp.get("id") or camp.get("campaign_id", ""))
                        if not camp_id or camp_id in seen_campaign_ids:
                            continue

                        if not is_slots_casino_campaign(camp):
                            continue

                        seen_campaign_ids.add(camp_id)

                        channels = camp.get("channels", []) or camp.get("streamers", [])
                        target_streamer = "kickstreamer"
                        if channels and isinstance(channels, list):
                            live_ch = next((c for c in channels if isinstance(c, dict) and (c.get("is_live") or c.get("livestream"))), None)
                            ch = live_ch or channels[0]
                            if isinstance(ch, dict):
                                target_streamer = ch.get("slug") or ch.get("username") or ch.get("channel", {}).get("slug") or "kickstreamer"
                            elif isinstance(ch, str):
                                target_streamer = ch

                        s_lower = str(target_streamer).lower()
                        camp_name = camp.get("name") or camp.get("title") or "Kick Drop Bonus"

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

        except Exception:
            pass

        await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_kick_official_api_loop())

# ---------------------------------------------------------
# 4. ADMIN & RECORD DROPS ENDPOINTS
# ---------------------------------------------------------
@app.get("/admin/generate-key")
async def api_generate_key(days: int = 30, buyer: str = "General Buyer", secret_admin_code: str = ""):
    if secret_admin_code != "yaudahadmin":
        return {"status": "error", "message": "Unauthorized"}
    
    key, expiry = generate_vip_license(days, buyer)
    
    # Kirim data ke Spreadsheet Lisensi khusus
    asyncio.create_task(sync_license_to_spreadsheet(key, expiry, days, buyer))
    
    return {
        "status": "success",
        "buyer": buyer,
        "license_key": key,
        "expires_at": expiry,
        "duration_days": days
    }

@app.post("/api/v1/record-drop")
async def record_drop(request: Request):
    global LATEST_ALERT_DROP, LAST_DROP_TIMESTAMP
    try:
        body = await request.json()
        streamer = body.get("streamer")
        value = body.get("value", "KICK-DROP")

        if not streamer or streamer == "Unknown Streamer":
            return {"status": "ignored", "message": "Invalid or empty drop payload."}

        save_drop_to_db(streamer, "KICK-DROP", value, "System")
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

# ---------------------------------------------------------
# 5. DASHBOARD UTAMA
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home_dashboard(request: Request):
    html_content = """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <title>Kick Bot - Live Tracker</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0b0f19; color: #f8fafc; margin: 0; padding: 2rem; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header-banner { background: #111827; border: 1px solid #1e293b; border-radius: 12px; padding: 1.5rem 2rem; display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
            .logo-box { display: flex; align-items: center; gap: 15px; }
            .logo-icon { background: #10b981; color: #000; font-weight: bold; font-size: 24px; width: 48px; height: 48px; border-radius: 10px; display: flex; align-items: center; justify-content: center; }
            .btn-vip { background: #6366f1; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 14px; transition: 0.2s; display: flex; align-items: center; gap: 8px; cursor: pointer; border: none; }
            .btn-vip:hover { background: #4f46e5; }

            .alert-banner { display: none; background: linear-gradient(90deg, #059669, #10b981); color: #fff; padding: 1rem 1.5rem; border-radius: 10px; margin-bottom: 1.5rem; justify-content: space-between; align-items: center; box-shadow: 0 0 20px rgba(16, 185, 129, 0.4); }
            .alert-title { font-weight: bold; font-size: 1.1rem; display: flex; align-items: center; gap: 12px; }

            .btn-streamer { background: rgba(0, 0, 0, 0.3); color: #fef08a; padding: 6px 14px; border-radius: 6px; text-decoration: none; font-weight: bold; border: 1px solid rgba(254, 240, 138, 0.4); }
            .btn-streamer:hover { background: #000; color: #fff; border-color: #fff; }

            .grid-layout { display: grid; grid-template-columns: 1.8fr 1.2fr; gap: 1.5rem; }
            .card { background: #111827; border: 1px solid #1e293b; border-radius: 12px; padding: 1.5rem; }
            .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
            .card-title { font-size: 1rem; font-weight: bold; color: #f8fafc; display: flex; align-items: center; gap: 8px; margin: 0; }
            .status-live { font-size: 12px; color: #10b981; background: rgba(16, 185, 129, 0.1); padding: 4px 10px; border-radius: 12px; font-weight: bold; }

            table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
            td { padding: 12px; border-bottom: 1px solid #1e293b; font-size: 14px; }
            .rank-num { color: #64748b; font-weight: bold; width: 30px; }
            .streamer-name { font-weight: bold; color: #f8fafc; text-decoration: none; }
            .category-tag { font-size: 11px; color: #10b981; font-weight: bold; margin-left: 6px; }
            .viewer-count { color: #10b981; font-weight: bold; text-align: right; }
            .hidden-tag { background: #f59e0b; color: #000; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: bold; margin-left: 6px; }
            .drop-badge { background: #8b5cf6; color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 12px; font-weight: bold; }

            .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.7); z-index: 1000; justify-content: center; align-items: center; }
            .modal-box { background: #111827; border: 1px solid #1e293b; border-radius: 12px; padding: 2rem; width: 100%; max-width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            .modal-title { font-size: 1.1rem; font-weight: bold; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 8px; color: #f8fafc; }
            .modal-desc { font-size: 13px; color: #94a3b8; margin-bottom: 1.2rem; }
            .modal-input { width: 100%; padding: 10px 14px; background: #080d1a; border: 1px solid #334155; color: #fff; border-radius: 8px; font-size: 14px; box-sizing: border-box; margin-bottom: 1rem; }
            .modal-buttons { display: flex; gap: 10px; justify-content: flex-end; }
            .btn-secondary { background: #1e293b; color: #94a3b8; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; }
            .btn-primary { background: #6366f1; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; }
            .btn-primary:hover { background: #4f46e5; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-banner">
                <div class="logo-box">
                    <div class="logo-icon">K</div>
                    <div>
                        <h2 style="margin:0; font-size:1.4rem;">Kick Bot - Live Tracker</h2>
                        <span style="font-size:13px; color:#64748b;">Official Kick API v2 Livestream Category Slot Harvester</span>
                    </div>
                </div>
                <button class="btn-vip" onclick="openModal()">🔑 Buka Panel Manajemen Bot &rarr;</button>
            </div>

            <div class="alert-banner" id="alert-banner">
                <div class="alert-title">
                    🚨 NEW DROP DETECTED
                    <a href="#" target="_blank" class="btn-streamer" id="alert-streamer-btn">@streamer</a>
                </div>
            </div>

            <div class="grid-layout">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">🔥 SLOTS & CASINO LIVE RANKING (TOP 20 - BY VIEW)</h3>
                        <span class="status-live" id="status-badge">Status: • Fetching Kick v2 Direct...</span>
                    </div>
                    <table>
                        <tbody id="ranking-tbody">
                            <tr><td colspan="3" style="text-align:center; color:#64748b; padding:2rem;">Memuat data Slots & Casino dari Kick API v2...</td></tr>
                        </tbody>
                    </table>
                </div>

                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">🏆 TOP DROPS STREAMER</h3>
                    </div>
                    <table id="drops-table">
                        <tbody id="drops-tbody">
                            <tr><td colspan="3" style="text-align:center; color:#64748b; padding:2rem;">Menunggu data klaim drop pertama dari bot...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="modal-overlay" id="licenseModal">
            <div class="modal-box">
                <div class="modal-title">🔑 Masukkan License Key</div>
                <div class="modal-desc">Akses Panel Manajemen Bot khusus pengguna VIP yang memiliki lisensi aktif.</div>
                <input type="text" id="licenseInput" class="modal-input" placeholder="Masukkan License Key VIP...">
                <div class="modal-buttons">
                    <button class="btn-secondary" onclick="closeModal()">Batal</button>
                    <button class="btn-primary" onclick="submitLicense()">Masuk Panel &rarr;</button>
                </div>
            </div>
        </div>

        <script>
            let lastAlertId = null;
            let alertTimer = null;

            function openModal() {
                document.getElementById('licenseModal').style.display = 'flex';
            }
            function closeModal() {
                document.getElementById('licenseModal').style.display = 'none';
            }
            function submitLicense() {
                const license = document.getElementById('licenseInput').value.trim();
                if(license) {
                    // Generate unique device token/ID local browser untuk device lock
                    let deviceId = localStorage.getItem('kick_dev_id');
                    if(!deviceId) {
                        deviceId = 'dev_' + Math.random().toString(36).substring(2) + Date.now().toString(36);
                        localStorage.setItem('kick_dev_id', deviceId);
                    }
                    window.location.href = '/panel?license=' + encodeURIComponent(license) + '&devid=' + deviceId;
                }
            }

            function formatLocalTime(utcTimeString) {
                if(!utcTimeString) return '-';
                try {
                    let parsedDate = new Date(utcTimeString.replace(' ', 'T') + 'Z');
                    if (isNaN(parsedDate.getTime())) {
                        parsedDate = new Date(utcTimeString);
                    }
                    return parsedDate.toLocaleString(undefined, {
                        year: 'numeric', month: 'short', day: 'numeric',
                        hour: '2-digit', minute: '2-digit', second: '2-digit'
                    });
                } catch(e) {
                    return utcTimeString;
                }
            }

            async function updateDashboardData() {
                try {
                    const res = await fetch('/api/v1/live-data');
                    const data = await res.json();

                    if(data.status === 'success') {
                        if(data.rankings && data.rankings.length > 0) {
                            const tbody = document.getElementById('ranking-tbody');
                            tbody.innerHTML = '';

                            data.rankings.slice(0, 20).forEach((item, index) => {
                                const tr = document.createElement('tr');
                                const viewerText = typeof item.viewers === 'number' ? item.viewers.toLocaleString() + ' Viewers' : item.viewers;

                                tr.innerHTML = `
                                    <td class="rank-num">#${index + 1}</td>
                                    <td>
                                        <div>
                                            <a href="https://kick.com/${item.channel}" target="_blank" class="streamer-name">${item.channel}</a>
                                            <span class="category-tag">[SLOTS]</span>
                                            ${item.isHidden ? '<span class="hidden-tag">LIVE (Hidden)</span>' : ''}
                                        </div>
                                        <div style="font-size:12px; color:#64748b;">${item.title || '-'}</div>
                                    </td>
                                    <td class="viewer-count">${viewerText}</td>
                                `;
                                tbody.appendChild(tr);
                            });
                        }

                        if(data.top_drops && data.top_drops.length > 0) {
                            const dropsTbody = document.getElementById('drops-tbody');
                            dropsTbody.innerHTML = '';

                            data.top_drops.forEach((item, index) => {
                                const tr = document.createElement('tr');
                                const localFormattedTime = formatLocalTime(item.last_drop_time);

                                tr.innerHTML = `
                                    <td class="rank-num">#${index + 1}</td>
                                    <td>
                                        <a href="https://kick.com/${item.streamer}" target="_blank" class="streamer-name">${item.streamer}</a>
                                        <div style="font-size:12px; color:#64748b;">Last Drops: <b style="color:#34d399;">${localFormattedTime}</b></div>
                                    </td>
                                    <td style="text-align:right;">
                                        <span class="drop-badge">${item.total_drops} Drops</span>
                                    </td>
                                `;
                                dropsTbody.appendChild(tr);
                            });
                        }

                        if(data.latest_alert && data.latest_alert.id !== lastAlertId) {
                            const currentNow = Math.floor(Date.now() / 1000);
                            const dropAgeSeconds = currentNow - data.latest_alert.timestamp;

                            if (dropAgeSeconds < 120) {
                                lastAlertId = data.latest_alert.id;
                                const banner = document.getElementById('alert-banner');
                                const streamerBtn = document.getElementById('alert-streamer-btn');

                                streamerBtn.innerText = `@${data.latest_alert.streamer}`;
                                streamerBtn.href = `https://kick.com/${data.latest_alert.streamer}`;

                                banner.style.display = 'flex';

                                if (alertTimer) clearTimeout(alertTimer);
                                const remainingMs = (120 - dropAgeSeconds) * 1000;
                                alertTimer = setTimeout(() => {
                                    banner.style.display = 'none';
                                }, remainingMs);
                            }
                        } else if (!data.latest_alert) {
                            document.getElementById('alert-banner').style.display = 'none';
                        }

                        document.getElementById('status-badge').innerText = 'Status: • Live Connected (' + new Date().toLocaleTimeString() + ')';
                    }
                } catch(e) {
                    document.getElementById('status-badge').innerText = 'Status: ⚠️ Reconnecting...';
                }
            }

            updateDashboardData();
            setInterval(updateDashboardData, 3000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ---------------------------------------------------------
# 6. PANEL VIP DENGAN VALIDASI DATABASE & DEVICE LOCK
# ---------------------------------------------------------
@app.get("/panel", response_class=HTMLResponse)
def vip_panel(request: Request, license: str = "", devid: str = ""):
    client_ip = request.client.host
    current_device = devid if devid else client_ip

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT expiry_date, device_id FROM licenses WHERE license_key = ? AND status = 'active'", (license,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html lang="id">
        <head>
            <meta charset="UTF-8">
            <title>Unauthorized License</title>
            <style>
                body { font-family: 'Segoe UI', sans-serif; background: #0b0f19; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                .box { background: #111827; border: 1px solid #1e293b; padding: 2rem; border-radius: 12px; text-align: center; max-width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
                h2 { color: #ef4444; margin-top: 0; }
                p { color: #94a3b8; font-size: 14px; margin-bottom: 1.5rem; }
                a { background: #6366f1; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 14px; }
            </style>
        </head>
        <body>
            <div class="box">
                <h2>⛔ Akses Ditolak</h2>
                <p>License key yang Anda masukkan tidak valid, sudah kedaluwarsa, atau belum terdaftar di sistem.</p>
                <a href="/">&larr; Kembali ke Beranda</a>
            </div>
        </body>
        </html>
        """, status_code=403)

    expiry_str, registered_device = row

    # Validasi Device Lock
    if not registered_device:
        cursor.execute("UPDATE licenses SET device_id = ? WHERE license_key = ?", (current_device, license))
        conn.commit()
    elif registered_device != current_device:
        conn.close()
        return HTMLResponse(content=""""
        <!DOCTYPE html>
        <html lang="id">
        <head>
            <meta charset="UTF-8">
            <title>Device Locked</title>
            <style>
                body { font-family: 'Segoe UI', sans-serif; background: #0b0f19; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                .box { background: #111827; border: 1px solid #1e293b; padding: 2rem; border-radius: 12px; text-align: center; max-width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
                h2 { color: #f59e0b; margin-top: 0; }
                p { color: #94a3b8; font-size: 14px; margin-bottom: 1.5rem; }
                a { background: #6366f1; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 14px; }
            </style>
        </head>
        <body>
            <div class="box">
                <h2>🔒 Perangkat Terkunci</h2>
                <p>License key ini sudah terikat (locked) ke perangkat/browser lain dan tidak dapat digunakan di perangkat ini (1 License = 1 Device).</p>
                <a href="/">&larr; Kembali ke Beranda</a>
            </div>
        </body>
        </html>
        """, status_code=403)

    conn.close()

    base_url = get_clean_base_url(request)
    raw_target_url = f"{base_url}/api/v1/get-script?license={license}"
    encrypted_payload = encrypt_text(raw_target_url)
    secure_tampermonkey_url = f"{base_url}/api/v1/load-secure-script?data={encrypted_payload}&devid={current_device}"

    html_content = """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <title>Panel Manajemen Bot VIP</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0b0f19; color: #f8fafc; margin: 0; padding: 2rem; }
            .container { max-width: 1100px; margin: 0 auto; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
            .btn-back { background: #1e293b; color: #94a3b8; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 14px; border: 1px solid #334155; }
            .card { background: #111827; border: 1px solid #1e293b; border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5); }
            .card-title { font-size: 1.1rem; font-weight: 600; color: #38bdf8; margin-top: 0; display: flex; align-items: center; gap: 8px; }
            .input-box { width: 100%; padding: 12px; background: #080d1a; border: 1px solid #1e293b; color: #4ade80; font-family: 'Fira Code', monospace; border-radius: 6px; font-size: 13px; box-sizing: border-box; margin-top: 8px; }
            .grid-license { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <h2 style="margin:0;">⚙️ Panel Manajemen Bot VIP</h2>
                    <span style="font-size: 13px; color: #64748b;">Pemilik Lisensi: <b style="color:#4ade80;">LICENSE_PLACEHOLDER</b></span>
                </div>
                <a href="/" class="btn-back">&larr; Kembali ke Dashboard</a>
            </div>

            <div class="grid-license">
                <div class="card">
                    <div class="card-title">📌 Status Lisensi VIP (Device Locked):</div>
                    <p id="vip-status" style="color: #4ade80; font-weight: bold; font-size: 1.1rem; margin: 8px 0;">ACTIVE & LOCKED</p>
                    <div style="font-size: 12px; color: #64748b;">Berlaku Sampai: EXPIRY_PLACEHOLDER WIB</div>
                </div>

                <div class="card">
                    <div class="card-title">⏳ Hitung Mundur Kedaluwarsa:</div>
                    <div id="countdown-timer" style="font-family: monospace; font-size: 1.2rem; font-weight: bold; color: #38bdf8; margin-top: 10px;">
                        Menghitung...
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">📌 Tampermonkey Userscript Loader URL:</div>
                <input type="text" class="input-box" value="SECURE_URL_PLACEHOLDER" readonly onclick="this.select();">
                <div style="font-size: 12px; color: #64748b; margin-top: 8px;">*URL di atas sudah terikat secara eksklusif ke perangkat browser Anda saat ini.</div>
            </div>
        </div>

        <script>
            var expiryDateString = "EXPIRY_STRING_VALUE";
            var expiryTime = new Date(expiryDateString.replace(' ', 'T')).getTime();

            function updateCountdown() {
                var now = new Date().getTime();
                var distance = expiryTime - now;
                var timerElement = document.getElementById("countdown-timer");

                if (distance < 0) {
                    timerElement.innerHTML = "EXPIRED (Lisensi Habis)";
                    timerElement.style.color = "#ef4444";
                    document.getElementById("vip-status").innerText = "INACTIVE";
                    document.getElementById("vip-status").style.color = "#ef4444";
                    return;
                }

                var days = Math.floor(distance / (1000 * 60 * 60 * 24));
                var hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                var minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                var seconds = Math.floor((distance % (1000 * 60)) / 1000);

                timerElement.innerHTML = days + " Hari " + hours + " Jam " + minutes + " Menit " + seconds + " Detik";
            }

            if (!isNaN(expiryTime)) {
                setInterval(updateCountdown, 1000);
                updateCountdown();
            } else {
                document.getElementById("countdown-timer").innerHTML = "Format waktu tidak valid";
            }
        </script>
    </body>
    </html>
    """
    
    html_content = html_content.replace("SECURE_URL_PLACEHOLDER", secure_tampermonkey_url)
    html_content = html_content.replace("EXPIRY_PLACEHOLDER", expiry_str)
    html_content = html_content.replace("EXPIRY_STRING_VALUE", expiry_str)
    html_content = html_content.replace("LICENSE_PLACEHOLDER", f"VIP User ({license})")

    return HTMLResponse(content=html_content)

@app.get("/api/v1/load-secure-script", response_class=PlainTextResponse)
def load_secure_script(request: Request, data: str, devid: str = ""):
    try:
        decrypted_url = decrypt_text(data)
        if "get-script?license=" in decrypted_url:
            license_key = decrypted_url.split("get-script?license=")[1].split("&")[0]
            client_ip = request.client.host
            current_device = devid if devid else client_ip
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT expiry_date, device_id FROM licenses WHERE license_key = ? AND status = 'active'", (license_key,))
            row = cursor.fetchone()

            if row:
                expiry_str, registered_device = row
                
                # Cek Kedaluwarsa
                expiry_time = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S").timestamp()
                if datetime.now().timestamp() > expiry_time:
                    conn.close()
                    return PlainTextResponse(content="// Access Denied: License Key has expired.", media_type="text/javascript")

                # Cek Device Lock
                if not registered_device:
                    cursor.execute("UPDATE licenses SET device_id = ? WHERE license_key = ?", (current_device, license_key))
                    conn.commit()
                elif registered_device != current_device:
                    conn.close()
                    return PlainTextResponse(content="// Access Denied: License Key is locked to another device.", media_type="text/javascript")

                conn.close()
                return PlainTextResponse(content=SCRIPT_CONTENT, media_type="text/javascript")
            conn.close()
    except Exception:
        pass
    
    return PlainTextResponse(content="// Access Denied: Invalid or Expired License Key", media_type="text/javascript")

@app.get("/api/v1/get-script")
def get_raw_script(license: str):
    return {"status": "ok", "license": license}

@app.get("/kickbot.user.js")
async def get_userscript():
    return Response(content=SCRIPT_CONTENT, media_type="text/javascript")