import gspread
import sqlite3
import asyncio
from google.oauth2.service_account import Credentials
import config

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_file(config.GSHEET_CREDENTIALS_FILE, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"⚠️ [GSHEETS] Credentials file belum dipasang/error: {e}")
        return None

async def sync_db_to_gsheet_loop(interval_seconds=600):
    """Task Background: Backup SQLite ke Google Sheets tiap 10 Menit"""
    await asyncio.sleep(15)
    
    while True:
        try:
            client = get_gsheet_client()
            if client:
                sheet = client.open(config.GSHEET_NAME).sheet1
                
                conn = sqlite3.connect(config.DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT bot_id, streamer, claim_time, license_key FROM drop_history ORDER BY id DESC LIMIT 500")
                rows = cursor.fetchall()
                conn.close()

                header = ["Bot ID", "Streamer", "Claim Time", "License Key"]
                data_to_sync = [header] + [list(row) for row in rows]

                sheet.clear()
                sheet.update('A1', data_to_sync)
                print("📊 [GSHEETS] Backup SQLite ke Google Sheets Berhasil!")
        except Exception as e:
            print(f"⚠️ [GSHEETS BACKUP ERROR]: {e}")

        await asyncio.sleep(interval_seconds)
