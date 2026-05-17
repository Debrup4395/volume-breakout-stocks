import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import requests
import zipfile
import io
from datetime import datetime, timedelta
import os
import json
import sys

# ─────────────────────────────────────────────
# 1. SMART SCHEDULE CHECK
#    Skip runs outside market window to save
#    GitHub Actions minutes.
#    Market hours (IST): 09:00 – 16:30
# ─────────────────────────────────────────────
ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)

# Skip weekends
if ist_now.weekday() >= 5:
    print(f"INFO: Weekend ({ist_now.strftime('%A')}). Skipping run.")
    sys.exit(0)

# Only run between 09:00 and 16:30 IST (bhavcopy available after ~15:40)
if not (9 <= ist_now.hour < 17):
    print(f"INFO: Outside market window ({ist_now.strftime('%H:%M')} IST). Skipping run.")
    sys.exit(0)

print(f"INFO: Running at {ist_now.strftime('%d-%b-%Y %H:%M')} IST")

# ─────────────────────────────────────────────
# 2. CREDENTIALS SETUP
# ─────────────────────────────────────────────
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    print("CRITICAL: GCP_CREDENTIALS secret missing!")
    sys.exit(1)

creds_dict = json.loads(creds_json)
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = "19ypIjxHKDOqwJC9tsmAFkDZ0BNjmf7u1tdWHG5jn8zY"
worksheet = client.open_by_key(SPREADSHEET_ID).worksheet("Top 250 Stocks")

# ─────────────────────────────────────────────
# 3. NSE BHAVCOPY FETCHER
# ─────────────────────────────────────────────
def fetch_bhavcopy_for_date(date_obj):
    date_str = date_obj.strftime("%Y%m%d")
    url = (
        f"https://nsearchives.nseindia.com/content/cm/"
        f"BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
    )
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.nseindia.com/'
    }

    try:
        print(f"  → Checking {date_str}…")
        resp = requests.get(url, headers=headers, timeout=25)

        if resp.status_code != 200:
            print(f"  ✗ HTTP {resp.status_code}")
            return None

        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                df = pd.read_csv(f)

        # Normalize column names
        df.columns = [c.strip() for c in df.columns]

        sym_col      = next((c for c in ['TckrSymb', 'SYMBOL']          if c in df.columns), None)
        close_col    = next((c for c in ['ClsPric',  'CLOSE']           if c in df.columns), None)
        series_col   = next((c for c in ['SctySrs',  'SERIES']          if c in df.columns), None)
        turnover_col = next((c for c in ['TtlTrfVal','TtlTrdVal','TURNOVER_LACS','TURNOVER']
                             if c in df.columns), None)

        if not all([sym_col, close_col, turnover_col]):
            print(f"  ✗ Required columns missing. Found: {df.columns.tolist()}")
            return None

        # Keep only EQ series
        if series_col:
            df = df[df[series_col].astype(str).str.strip() == 'EQ']

        # Remove ETFs / indices
        df = df[~df[sym_col].astype(str).str.contains(
            r'BEES|ETF|GOLD|LIQUID|NIFTY|SENSEX', case=False, na=False
        )]

        df[turnover_col] = pd.to_numeric(df[turnover_col], errors='coerce')
        df[close_col]    = pd.to_numeric(df[close_col],    errors='coerce')
        df = df.dropna(subset=[turnover_col, close_col])

        df_top = df.sort_values(by=turnover_col, ascending=False).head(250)
        print(f"  ✓ Got {len(df_top)} stocks from {date_str}")
        return df_top[[sym_col, turnover_col, close_col]].values.tolist()

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None


# ─────────────────────────────────────────────
# 4. FIND LATEST AVAILABLE BHAVCOPY
# ─────────────────────────────────────────────
data_to_insert = None
fetched_date_str = ""

print("Searching for latest NSE bhavcopy…")
for i in range(7):
    test_date = ist_now - timedelta(days=i)
    if test_date.weekday() >= 5:
        continue
    data_to_insert = fetch_bhavcopy_for_date(test_date)
    if data_to_insert:
        fetched_date_str = test_date.strftime('%d-%b-%Y')
        break

# ─────────────────────────────────────────────
# 5. UPDATE GOOGLE SHEET
# ─────────────────────────────────────────────
if data_to_insert:
    try:
        worksheet.batch_clear(['A2:C251'])
        worksheet.update('A2', data_to_insert)

        ist_now_str = ist_now.strftime('%d-%b %H:%M')
        status_msg  = f"Data Date: {fetched_date_str} | Last Update: {ist_now_str} (IST)"
        worksheet.update('K2', [[status_msg]])

        print(f"\n✅ SUCCESS — Sheet updated for {fetched_date_str} at {ist_now_str} IST")
    except Exception as e:
        print(f"\n❌ Google Sheets write error: {e}")
        sys.exit(1)
else:
    print("\n⚠️  No bhavcopy found for last 7 trading days. Sheet not updated.")
    sys.exit(1)
