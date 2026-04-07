import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
import datetime
import re
import os
import pytz

# --- SAHIFA SOZLAMALARI ---
st.set_page_config(page_title="Stable Dashboard", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #2b2d30; }
header[data-testid="stHeader"] { background-color: #2b2d30; }
</style>
<h3 style='text-align: center; margin-top: -40px;'>YFinance Stable Dashboard</h3>
""", unsafe_allow_html=True)

# --- KALITLAR ---
FINNHUB_API_KEY = "d76mohpr01qtg3ne69ugd76mohpr01qtg3ne69v0"
try:
    finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
except Exception:
    finnhub_client = None

CATALYST_KEYWORDS = ["upgrade", "downgrade", "fda", "partnership", "product", "earnings", "guidance", "contract", "acquisition", "clinical", "report"]

@st.cache_data(ttl=60)
def get_stable_data():
    if os.path.exists("tickers.csv"):
        try:
            df_csv = pd.read_csv("tickers.csv")
            TICKERS = df_csv["Ticker"].dropna().astype(str).tolist()
        except Exception: return pd.DataFrame()
    else:
        TICKERS = ["AAOI", "AMD", "NVDA", "INTC", "MU", "AAPL", "TSLA", "META", "LITE", "NFLX"]

    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.datetime.now(ny_tz)
    
    # Qat'iy chegara: Kecha soat 16:00:01 NY
    cutoff_limit_ny = (now_ny - datetime.timedelta(days=1)).replace(hour=16, minute=0, second=1, microsecond=0)

    results = []
    
    for ticker in TICKERS:
        try:
            stock = yf.Ticker(ticker)
            fast_info = stock.fast_info
            
            prev_close = fast_info.get('previous_close', 0)
            current_price = fast_info.get('last_price', 0)
            
            if prev_close <= 0 or current_price <= 0: continue
            
            gap = ((current_price - prev_close) / prev_close) * 100
            
            # Qat'iy 5% Gap filtri
            if abs(gap) < 5.0:
                continue

            catalyst_url = ""
            news_time_display = "-"
            
            if finnhub_client:
                fetch_date = now_ny.strftime("%Y-%m-%d")
                yesterday_date = (now_ny - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                news = finnhub_client.company_news(ticker, _from=yesterday_date, to=fetch_date)
                
                for article in reversed(news):
                    ts = article.get('datetime', 0)
                    article_ny_time = datetime.datetime.fromtimestamp(ts, tz=pytz.utc).astimezone(ny_tz)
                    
                    # Faqat 16:00:01 dan keyingi scan
                    if article_ny_time < cutoff_limit_ny: continue
                    
                    headline = article['headline'].lower()
                    if any(k in headline for k in CATALYST_KEYWORDS):
                        catalyst_url = article.get('url', "")
                        news_time_display = article_ny_time.strftime('%b-%d %H:%M')
                        break

            info = stock.info
            results.append({
                "Ticker": ticker,
                "Sector": info.get('sector', '-'),
                "Industry": info.get('industry', '-'),
                "Price": current_price,
                "Gap %": gap,
                "Time (NY)": news_time_display,
                "Link": catalyst_url 
            })
        except Exception: continue
            
    return pd.DataFrame(results)

# --- DISPLAY ---
with st.spinner('Skan qilinmoqda...'):
    df = get_stable_data()

if not df.empty:
    col1, col2 = st.columns(2)
    
    def color_green(val): return 'color: #28a745; font-weight: bold;'
    def color_red(val): return 'color: #dc3545; font-weight: bold;'

    with col1:
        st.markdown("<h4 style='color: #28a745;'>Gap Up</h4>", unsafe_allow_html=True)
        up_df = df[df["Gap %"] >= 5.0].sort_values(by="Gap %", ascending=False)
        
        st.markdown("##### With Catalyst")
        st.dataframe(up_df[up_df["Link"] != ""].style.map(color_green, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', hide_index=True, column_config={"Link": st.column_config.LinkColumn("Link", display_text="🔗 News")})
        
        st.markdown("##### Without Catalyst")
        st.dataframe(up_df[up_df["Link"] == ""].style.map(color_green, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', hide_index=True)

    with col2:
        st.markdown("<h4 style='color: #dc3545;'>Gap Down</h4>", unsafe_allow_html=True)
        down_df = df[df["Gap %"] <= -5.0].sort_values(by="Gap %", ascending=True)
        
        st.markdown("##### With Catalyst")
        st.dataframe(down_df[down_df["Link"] != ""].style.map(color_red, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', hide_index=True, column_config={"Link": st.column_config.LinkColumn("Link", display_text="🔗 News")})
        
        st.markdown("##### Without Catalyst")
        st.dataframe(down_df[down_df["Link"] == ""].style.map(color_red, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'}), width='stretch', hide_index=True)
else:
    st.info("Hozircha 5% Gap topilmadi.")
