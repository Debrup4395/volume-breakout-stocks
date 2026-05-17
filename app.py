import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Volume Breakout Stocks",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st_autorefresh(interval=1_800_000, key="auto_refresh")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.status-badge {
    display: inline-block; background: #1a2744; border: 1px solid #2b6cb0;
    border-radius: 20px; padding: 5px 14px; font-size: 12px;
    color: #90cdf4; font-family: 'Space Mono', monospace;
}
.final-banner {
    background: linear-gradient(135deg, #0d2137 0%, #1a3a2a 100%);
    border: 1px solid #2f855a; border-radius: 12px;
    padding: 16px 22px; margin-bottom: 18px;
}
.final-banner h3 { color: #68d391; margin: 0 0 4px 0; font-size: 18px; }
.final-banner p  { color: #a0aec0; margin: 0; font-size: 13px; }
.stock-pill {
    display: inline-block; background: #1a3a2a; border: 1px solid #2f855a;
    color: #68d391; font-family: 'Space Mono', monospace;
    font-size: 12px; font-weight: 700; padding: 4px 10px;
    border-radius: 6px; margin: 3px;
}
</style>
""", unsafe_allow_html=True)

SPREADSHEET_ID = "19ypIjxHKDOqwJC9tsmAFkDZ0BNjmf7u1tdWHG5jn8zY"

COLS_250 = [
    "NSE Code", "Turnover", "Close Price", "CMP",
    "50 DMA", "100 DMA", "200 DMA",
    "Output", "Diff from 200 DMA (%)", "CAR Rating"
]
COLS_FINAL = [
    "NSE Code", "Turnover", "Previous Close", "CMP",
    "Diff from 200 DMA (%)", "CAR Rating"
]

@st.cache_resource
def get_gspread_client():
    creds_raw  = st.secrets["GCP_CREDENTIALS"]
    creds_dict = json.loads(creds_raw) if isinstance(creds_raw, str) else dict(creds_raw)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=1800, show_spinner=False)
def load_all_data():
    client = get_gspread_client()
    book   = client.open_by_key(SPREADSHEET_ID)
    ws250       = book.worksheet("Top 250 Stocks")
    vals250     = ws250.get("A1:J251")
    status_cell = ws250.acell("K2").value or ""
    try:
        ws_final   = book.worksheet("Final List")
        vals_final = ws_final.get_all_values()
    except Exception:
        vals_final = []
    return vals250, vals_final, status_cell

def parse_top250(all_values):
    if not all_values or len(all_values) < 2:
        return pd.DataFrame()
    rows = [r + [""] * (10 - len(r)) for r in all_values[1:]]
    df   = pd.DataFrame(rows, columns=COLS_250)
    df   = df[df["NSE Code"].str.strip() != ""]
    for col in ["Turnover","Close Price","CMP","50 DMA","100 DMA","200 DMA","Diff from 200 DMA (%)"]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors="coerce")
    df["Turnover (Cr)"] = (df["Turnover"] / 1e7).round(2)
    df.drop(columns=["Turnover"], inplace=True)
    return df[["NSE Code","Turnover (Cr)","Close Price","CMP",
               "50 DMA","100 DMA","200 DMA","Output","Diff from 200 DMA (%)","CAR Rating"]].reset_index(drop=True)

def parse_final_list(all_values):
    if not all_values or len(all_values) < 2:
        return pd.DataFrame()
    # Skip header row if first cell looks like a header
    start = 1 if all_values[0][0].strip().upper() in ("NSE CODE","A","") else 0
    rows  = [r + [""] * (6 - len(r)) for r in all_values[start:] if r and r[0].strip()]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=COLS_FINAL)
    df = df[df["NSE Code"].str.strip() != ""]
    df = df[~df["NSE Code"].str.contains("कोई", na=False)]
    for col in ["Turnover","Previous Close","CMP","Diff from 200 DMA (%)"]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",",""), errors="coerce")
    df["Turnover (Cr)"] = (df["Turnover"] / 1e7).round(2)
    df.drop(columns=["Turnover"], inplace=True)
    return df[["NSE Code","Turnover (Cr)","Previous Close","CMP","Diff from 200 DMA (%)","CAR Rating"]].reset_index(drop=True)

def style_output(val):
    if "Bull" in str(val): return "background-color:#1a3a2a;color:#68d391;font-weight:600"
    if "Bear" in str(val): return "background-color:#3a1a1a;color:#fc8181;font-weight:600"
    return "background-color:#3a3520;color:#f6e05e"
def style_diff(val):
    try:    return "color:#68d391" if float(val) >= 0 else "color:#fc8181"
    except: return ""
def style_car(val):
    if "Buy"   in str(val): return "color:#63b3ed;font-weight:600"
    if "Avoid" in str(val): return "color:#718096"
    return "color:#a0aec0"
def style_nse(val):
    return "font-family:'Space Mono',monospace;font-weight:700;color:#e2e8f0"

FMT_250   = {"Turnover (Cr)":"{:,.0f}","Close Price":"{:.2f}","CMP":"{:.2f}",
             "50 DMA":"{:.2f}","100 DMA":"{:.2f}","200 DMA":"{:.2f}","Diff from 200 DMA (%)":"{:.2f}"}
FMT_FINAL = {"Turnover (Cr)":"{:,.0f}","Previous Close":"{:.2f}","CMP":"{:.2f}","Diff from 200 DMA (%)":"{:.2f}"}

# ── HEADER ───────────────────────────────────
st.markdown("## 📈 Volume Breakout Stocks &nbsp;<span style='font-size:14px;color:#718096'>NSE Top 250 by Turnover</span>", unsafe_allow_html=True)

with st.spinner("Fetching data from Google Sheets…"):
    try:
        vals250, vals_final, status_cell = load_all_data()
        df_full  = parse_top250(vals250)
        df_final = parse_final_list(vals_final)
        data_ok  = True
    except Exception as e:
        st.error(f"❌ Could not load data: {e}")
        st.info("Make sure `GCP_CREDENTIALS` is added in Streamlit → Settings → Secrets.")
        data_ok = False

if not data_ok or df_full.empty:
    st.warning("No data. Run the GitHub Actions update first.")
    st.stop()

if status_cell:
    st.markdown(f'<span class="status-badge">🕒 {status_cell}</span>', unsafe_allow_html=True)
st.markdown("")

# ── SIDEBAR ──────────────────────────────────
with st.sidebar:
    st.markdown("### 🔍 Filters (Top 250 tab)")
    search_q     = st.text_input("Search Symbol", placeholder="e.g. RELIANCE")
    output_opts  = df_full["Output"].dropna().unique().tolist()
    selected_out = st.multiselect("Signal", output_opts, default=output_opts)
    car_opts     = df_full["CAR Rating"].dropna().unique().tolist()
    selected_car = st.multiselect("CAR Rating", car_opts, default=car_opts)
    min_t = float(df_full["Turnover (Cr)"].min())
    max_t = float(df_full["Turnover (Cr)"].max())
    turn_min = st.slider("Min Turnover (Cr)", min_t, max_t, min_t, step=1.0)
    st.markdown("---")
    if st.button("🔄 Force Refresh"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Auto-refreshes every 30 min.")

# ── TABS ─────────────────────────────────────
tab_final, tab_250 = st.tabs(["⭐ Final List  (Bull + Buy)", "📊 Top 250 Stocks"])

# ══ TAB 1: FINAL LIST ════════════════════════
with tab_final:
    if df_final.empty:
        st.info("No stocks currently match: **In Bull Run** + **Buy/Average Out**.")
    else:
        n = len(df_final)
        st.markdown(f"""
        <div class="final-banner">
          <h3>⭐ {n} stocks — In Bull Run + Buy/Average Out</h3>
          <p>Sorted by Turnover (highest first) · Filtered from NSE Top 250 · Updates every 30 min</p>
        </div>""", unsafe_allow_html=True)

        pills = "".join(f'<span class="stock-pill">{r["NSE Code"]}</span>' for _, r in df_final.iterrows())
        st.markdown(pills, unsafe_allow_html=True)
        st.markdown("---")

        styled_f = (
            df_final.style
              .applymap(style_nse,  subset=["NSE Code"])
              .applymap(style_diff, subset=["Diff from 200 DMA (%)"])
              .applymap(style_car,  subset=["CAR Rating"])
              .format(FMT_FINAL, na_rep="—")
              .set_properties(**{"font-size": "14px"})
        )
        st.dataframe(styled_f, use_container_width=True, height=min(60 + n * 38, 600))

        csv_f = df_final.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download Final List CSV", csv_f,
            f"final_list_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")

# ══ TAB 2: TOP 250 ═══════════════════════════
with tab_250:
    df = df_full.copy()
    if search_q:      df = df[df["NSE Code"].str.contains(search_q.upper(), na=False)]
    if selected_out:  df = df[df["Output"].isin(selected_out)]
    if selected_car:  df = df[df["CAR Rating"].isin(selected_car)]
    df = df[df["Turnover (Cr)"] >= turn_min]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📊 Showing",    len(df))
    c2.metric("🟢 Bull Run",   int((df["Output"] == "In Bull Run").sum()))
    c3.metric("🔴 Bear Run",   int((df["Output"] == "In Bear Run").sum()))
    c4.metric("⭐ Buy/Avg Out", int((df["CAR Rating"] == "Buy/Average Out").sum()))
    st.markdown("---")

    styled_250 = (
        df.style
          .applymap(style_nse,    subset=["NSE Code"])
          .applymap(style_output, subset=["Output"])
          .applymap(style_diff,   subset=["Diff from 200 DMA (%)"])
          .applymap(style_car,    subset=["CAR Rating"])
          .format(FMT_250, na_rep="—")
          .set_properties(**{"font-size": "13px"})
    )
    st.dataframe(styled_250, use_container_width=True, height=620)

    csv_250 = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download Top 250 CSV", csv_250,
        f"top250_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")

st.caption("NSE BhavCopy + Google Finance. For informational purposes only — not investment advice.")
