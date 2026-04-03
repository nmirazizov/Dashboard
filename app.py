import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
import datetime
import re
import os
import requests
import pytz

# --- SAHIFA SOZLAMALARI ---
st.set_page_config(page_title="Live Dashboard", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #2b2d30; }
header[data-testid="stHeader"] { background-color: #2b2d30; }
</style>
<h3 style='text-align: center; margin-top: -40px;'>Post-Market & Pre-Market Dashboard</h3>
""", unsafe_allow_html=True)

# --- KALITLAR ---
ALPACA_API_KEY = "PK55BI3HEWGNMUZGMSXMHXT4NX"
ALPACA_SECRET_KEY = "4MeXpeZNQkM9TRyrMokm8b8CVbqd6V1zUASCXWgdsJwg"

FINNHUB_API_KEY = "d76mohpr01qtg3ne69ugd76mohpr01qtg3ne69v0"
try:
    finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
except Exception:
    finnhub_client = None

CATALYST_KEYWORDS = ["upgrade", "downgrade", "fda", "partnership", "product", "earnings", "guidance"]
GAP_THRESHOLD = 5.0

@st.cache_data(ttl=30)
def get_dashboard_data():
    if os.path.exists("tickers.csv"):
        try:
            df_csv = pd.read_csv("tickers.csv")
            TICKERS = df_csv["Ticker"].dropna().astype(str).tolist()
        except Exception: return pd.DataFrame()
    else:
        TICKERS = ["AMD", "NVDA", "INTC", "MU", "AAPL", "TSLA", "META", "LITE", "LLY", "NKE"]

    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.datetime.now(ny_tz)
    today_date = now_ny.date()
    
    # Qat'iy chegara: Kecha soat 16:00:01 (NY vaqti)
    cutoff_limit_ny = (now_ny - datetime.timedelta(days=1)).replace(hour=16, minute=0, second=1, microsecond=0)

    gap_pct = {}
    curr_price_dict = {}
    
    url = "https://data.alpaca.markets/v2/stocks/snapshots"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "accept": "application/json"
    }

    # 1. GAP-larni ushlash (Kecha 16:00:01 dan keyingi barcha harakatlar)
    chunk_size = 100
    for i in range(0, len(TICKERS), chunk_size):
        chunk = TICKERS[i:i + chunk_size]
        try:
            res = requests.get(url, headers=headers, params={"symbols": ",".join(chunk), "feed": "iex"})
            if res.status_code == 200:
                data = res.json()
                for ticker, snap in data.items():
                    if not snap: continue
                    dailyBar = snap.get('dailyBar')
                    prevDailyBar = snap.get('prevDailyBar')
                    if not dailyBar or not prevDailyBar: continue
                    
                    bar_time = pd.to_datetime(dailyBar['t']).tz_convert(ny_tz)
                    
                    # FILTR: Agar Gap kecha 16:00:01 gacha yopilgan bo'lsa - kk emas
                    if bar_time < cutoff_limit_ny:
                        continue

                    prev_close = float(prevDailyBar.get('c', 0))
                    current_price = float(dailyBar.get('o', 0))
                    if prev_close > 0 and current_price > 0:
                        gap = ((current_price - prev_close) / prev_close) * 100
                        if abs(gap) >= GAP_THRESHOLD:
                            gap_pct[ticker] = gap
                            curr_price_dict[ticker] = current_price
        except Exception: continue

    results = []
    for ticker in gap_pct.keys():
        try:
            catalyst_url = ""
            news_time_display = "-"
            
            if finnhub_client:
                start_search = cutoff_limit_ny.strftime("%Y-%m-%d")
                news = finnhub_client.company_news(ticker, _from=start_search, to=today_date.strftime("%Y-%m-%d"))
                
                for article in reversed(news):
                    ts = article.get('datetime', 0)
                    article_ny_time = datetime.datetime.fromtimestamp(ts, tz=pytz.utc).astimezone(ny_tz)
                    
                    # Qat'iy chegara: Faqat 16:00:01 dan keyingi xabarlar
                    if article_ny_time < cutoff_limit_ny:
                        continue
                    
                    headline = article['headline'].lower()
                    found_keyword = False
                    for keyword in CATALYST_KEYWORDS:
                        if re.search(rf'\b{keyword}\b', headline):
                            found_keyword = True
                            break
                    
                    if found_keyword:
                        catalyst_url = article.get('url', "")
                        # Har doim Sana + Vaqt shaklida ko'rsatish (Sizning xohishingizga ko'ra modify)
                        news_time_display = article_ny_time.strftime('%b-%d %H:%M')
                        break
                    if catalyst_url: break

            info = yf.Ticker(ticker).info
            results.append({
                "Ticker": ticker, 
                "Sector": info.get('sector', '-'), 
                "Industry": info.get('industry', '-'),
                "Price": curr_price_dict.get(ticker), 
                "Gap %": gap_pct.get(ticker), 
                "Time (NY)": news_time_display, 
                "Link": catalyst_url 
            })
        except Exception: continue
            
    return pd.DataFrame(results)

# --- DISPLAY ---
df = get_dashboard_data()
ny_tz_main = pytz.timezone('America/New_York')
now_ny_main = datetime.datetime.now(ny_tz_main)

if not df.empty:
    col1, col2 = st.columns(2)
    def color_green(val): return 'color: #28a745; font-weight: bold;'
    def color_red(val): return 'color: #dc3545; font-weight: bold;'

    with col1:
        st.markdown("<h4 style='color: #28a745;'>Gap Up</h4>", unsafe_allow_html=True)
        up_df = df[df["Gap %"] > 0].sort_values(by="Gap %", ascending=False)
        
        st.write("**With Catalyst (Post-Market 16:00:01+)**")
        st.dataframe(up_df[up_df["Link"] != ""].style.map(color_green, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', hide_index=True, column_config={"Link": st.column_config.LinkColumn("Link", display_text="🔗 News")})
        
        st.write("**Without Catalyst**")
        st.dataframe(up_df[up_df["Link"] == ""].style.map(color_green, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', hide_index=True)

    with col2:
        st.markdown("<h4 style='color: #dc3545;'>Gap Down</h4>", unsafe_allow_html=True)
        down_df = df[df["Gap %"] < 0].sort_values(by="Gap %", ascending=True)
        
        st.write("**With Catalyst (Post-Market 16:00:01+)**")
        st.dataframe(down_df[down_df["Link"] != ""].style.map(color_red, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', hide_index=True, column_config={"Link": st.column_config.LinkColumn("Link", display_text="🔗 News")})
        
        st.write("**Without Catalyst**")
        st.dataframe(down_df[down_df["Link"] == ""].style.map(color_red, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', hide_index=True)
else:
    st.info(f"Yangi gap-lar topilmadi (NY 16:00:01 dan keyingi harakatlar kutilmoqda).")
