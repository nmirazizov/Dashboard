import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
import datetime
import re
import os
import requests
import pytz

# --- FON RANGI ---
st.set_page_config(page_title="Dashboard", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #2b2d30; }
header[data-testid="stHeader"] { background-color: #2b2d30; }
</style>
<h3 style='text-align: center; margin-top: -40px;'>Dashboard</h3>
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

@st.cache_data(ttl=60)
def get_dashboard_data():
    if os.path.exists("tickers.csv"):
        try:
            df_csv = pd.read_csv("tickers.csv")
            if "Ticker" in df_csv.columns:
                TICKERS = df_csv["Ticker"].dropna().astype(str).tolist()
            else:
                return pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    else:
        TICKERS = ["AMD", "NVDA", "INTC", "MU", "AAPL", "TSLA", "META", "LITE", "LLY", "NKE"]

    gap_pct = {}
    curr_price_dict = {}
    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.datetime.now(ny_tz)
    
    # --- BUGUNGI KUN FILTRI: Faqat bugungi sanadagi yangiliklar ---
    today_start_ny = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)

    url = "https://data.alpaca.markets/v2/stocks/snapshots"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "accept": "application/json"
    }

    chunk_size = 100
    for i in range(0, len(TICKERS), chunk_size):
        chunk = TICKERS[i:i + chunk_size]
        try:
            res = requests.get(url, headers=headers, params={"symbols": ",".join(chunk), "feed": "iex"})
            if res.status_code == 200:
                data = res.json()
                for ticker, snap in data.items():
                    if not snap: continue
                    
                    prevDailyBar = snap.get('prevDailyBar')
                    latestTrade = snap.get('latestTrade')
                    dailyBar = snap.get('dailyBar')
                    
                    if not prevDailyBar: continue
                    
                    prev_close = float(prevDailyBar.get('c', 0))
                    current_price = 0.0
                    
                    if dailyBar and dailyBar.get('o', 0) > 0:
                        current_price = float(dailyBar.get('o'))
                    elif latestTrade and latestTrade.get('p', 0) > 0:
                        current_price = float(latestTrade.get('p'))
                        
                    if prev_close > 0 and current_price > 0:
                        gap = ((current_price - prev_close) / prev_close) * 100
                        if abs(gap) >= GAP_THRESHOLD:
                            gap_pct[ticker] = gap
                            curr_price_dict[ticker] = current_price
        except Exception:
            continue

    movers = list(gap_pct.keys())
    results = []
    
    for ticker in movers:
        try:
            info = yf.Ticker(ticker).info
            today_open = curr_price_dict.get(ticker)
            gap_val = gap_pct.get(ticker)
            
            sector = info.get('sector', '-')
            industry = info.get('industry', '-')
            
            company_name = str(info.get('shortName', ticker)).split()[0].lower()
            company_name = re.sub(r'[^a-z0-9]', '', company_name)
            
            catalyst_url = ""
            news_time_str = "-"
            
            if finnhub_client:
                # Finnhub API uchun bugungi sanani formatlash
                fetch_date = now_ny.strftime("%Y-%m-%d")
                news = finnhub_client.company_news(ticker, _from=fetch_date, to=fetch_date)
                
                for article in reversed(news):
                    ts = article.get('datetime', 0)
                    if ts == 0: continue
                    
                    article_ny_time = datetime.datetime.fromtimestamp(ts, tz=pytz.utc).astimezone(ny_tz)
                    
                    # Faqat bugungi yarim tundan keyingi xabarlarni oladi
                    if article_ny_time < today_start_ny: continue
                    
                    headline = article['headline'].lower()
                    if ticker.lower() not in headline and company_name not in headline: continue
                    
                    for keyword in CATALYST_KEYWORDS:
                        if re.search(rf'\b{keyword}\b', headline):
                            catalyst_url = article.get('url', "")
                            news_time_str = article_ny_time.strftime('%H:%M')
                            break
                    if catalyst_url: break

            results.append({
                "Ticker": ticker, "Sector": sector, "Industry": industry,
                "Price": today_open, "Gap %": gap_val, "Time": news_time_str, "Link": catalyst_url 
            })
        except Exception:
            continue
            
    return pd.DataFrame(results)

# --- GLOBAL TIME CHECK ---
ny_tz_main = pytz.timezone('America/New_York')
now_ny_main = datetime.datetime.now(ny_tz_main)

# Dam olish kuni ogohlantirishi
if now_ny_main.date().weekday() >= 5 or now_ny_main.date() == datetime.date(2026, 4, 3):
    st.warning(f"Eslatma: Bugun ({now_ny_main.strftime('%Y-%m-%d')}) birja yopiq yoki dam olish kuni.")

with st.spinner('Skanerlanmoqda...'):
    df = get_dashboard_data()

    if not df.empty:
        # Catalyst bor-yo'qligini aniqlash
        gap_up_df = df[df["Gap %"] > 0].copy().sort_values(by="Gap %", ascending=False)
        gap_down_df = df[df["Gap %"] < 0].copy().sort_values(by="Gap %", ascending=True)

        def color_green(val): return 'color: #28a745; font-weight: bold;' if pd.notnull(val) else ''
        def color_red(val): return 'color: #dc3545; font-weight: bold;' if pd.notnull(val) else ''

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("<h4 style='text-align: center; color: #28a745;'>Gap Up</h4>", unsafe_allow_html=True)
            
            # With Catalyst
            st.markdown("<h6 style='text-align: center; color: #28a745;'>Today's Catalyst Only</h6>", unsafe_allow_html=True)
            gap_up_cat = gap_up_df[gap_up_df["Link"] != ""]
            if not gap_up_cat.empty:
                st.dataframe(gap_up_cat.style.map(color_green, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', height=350, hide_index=True, column_config={"Link": st.column_config.LinkColumn("Link", display_text="🔗 News")})
            else:
                st.info("Bugungi catalyst topilmadi")

            # Without Catalyst
            st.markdown("<h6 style='text-align: center; color: #28a745; margin-top: 20px;'>No Today's News</h6>", unsafe_allow_html=True)
            gap_up_no_cat = gap_up_df[gap_up_df["Link"] == ""]
            if not gap_up_no_cat.empty:
                st.dataframe(gap_up_no_cat.style.map(color_green, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', height=350, hide_index=True)

        with col2:
            st.markdown("<h4 style='text-align: center; color: #dc3545;'>Gap Down</h4>", unsafe_allow_html=True)
            
            # With Catalyst
            st.markdown("<h6 style='text-align: center; color: #dc3545;'>Today's Catalyst Only</h6>", unsafe_allow_html=True)
            gap_down_cat = gap_down_df[gap_down_df["Link"] != ""]
            if not gap_down_cat.empty:
                st.dataframe(gap_down_cat.style.map(color_red, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', height=350, hide_index=True, column_config={"Link": st.column_config.LinkColumn("Link", display_text="🔗 News")})
            else:
                st.info("Bugungi catalyst topilmadi")

            # Without Catalyst
            st.markdown("<h6 style='text-align: center; color: #dc3545; margin-top: 20px;'>No Today's News</h6>", unsafe_allow_html=True)
            gap_down_no_cat = gap_down_df[gap_down_df["Link"] == ""]
            if not gap_down_no_cat.empty:
                st.dataframe(gap_down_no_cat.style.map(color_red, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', height=350, hide_index=True)
    else:
        st.info("Ma'lumot topilmadi.")
