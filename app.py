import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
import datetime
import re
import os

# --- FON RANGI ---
st.set_page_config(page_title="Dashboard", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #2b2d30; }
header[data-testid="stHeader"] { background-color: #2b2d30; }
</style>
<h3 style='text-align: center; margin-top: -40px;'>Dashboard</h3>
""", unsafe_allow_html=True)

FINNHUB_API_KEY = "d76mohpr01qtg3ne69ugd76mohpr01qtg3ne69v0"
try:
    finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
except:
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
                st.error("CSV faylda 'Ticker' ustuni yq.")
                return pd.DataFrame()
        except Exception as e:
            return pd.DataFrame()
    else:
        TICKERS = ["AMD", "NVDA", "INTC", "MU", "AAPL", "TSLA", "META", "LITE", "LLY", "NKE"]

    gap_pct = {}
    curr_price_dict = {}
    ny_tz = 'America/New_York'
    now_ny = pd.Timestamp.now(tz=ny_tz)
    cutoff_time = now_ny - pd.Timedelta(days=3)

    chunk_size = 100
    for i in range(0, len(TICKERS), chunk_size):
        chunk = TICKERS[i:i + chunk_size]
        try:
            d_data = yf.download(chunk, period="5d", progress=False)
            m_data = yf.download(chunk, period="1d", interval="1m", prepost=True, progress=False)
            
            if len(chunk) == 1:
                d_close = d_data['Close'].to_frame(name=chunk[0])
                d_open = d_data['Open'].to_frame(name=chunk[0])
                m_close = m_data['Close'].to_frame(name=chunk[0])
            else:
                d_close = d_data['Close']
                d_open = d_data['Open']
                m_close = m_data['Close']
                
            for ticker in chunk:
                if ticker not in d_close.columns: continue
                    
                d_c = d_close[ticker].dropna()
                d_o = d_open[ticker].dropna()
                if len(d_c) < 2: continue
                
                # Kunlarni aniqlash
                d_dates = pd.to_datetime(d_c.index).tz_localize(None).date
                last_date = d_dates[-1]
                
                p_close = 0.0
                c_price = 0.0
                
                m_c = m_close[ticker].dropna() if ticker in m_close.columns else pd.Series()
                
                # --- FINVIZ 99.99% MANTIQ ---
                if not m_c.empty:
                    idx_ny = pd.to_datetime(m_c.index).tz_convert(ny_tz) if m_c.index.tz else pd.to_datetime(m_c.index).tz_localize('UTC').tz_convert(ny_tz)
                    latest_m_date = idx_ny[-1].date()
                    latest_time = idx_ny[-1].time()
                    
                    if latest_m_date > last_date:
                        # Premarket (Yangi kun boshlangan, lekin Daily bar hali yq)
                        p_close = float(d_c.iloc[-1])
                        c_price = float(m_c.iloc[-1])
                    elif latest_m_date == last_date:
                        # Bozor faoliyati boshlangan
                        if latest_time >= datetime.time(9, 30):
                            # Finviz qoidasi: 09:30 dan keyin faqat rasmiy Open va Kechagi Close olinadi
                            p_close = float(d_c.iloc[-2])
                            c_price = float(d_o.iloc[-1])
                        else:
                            # Premarket Live
                            p_close = float(d_c.iloc[-2])
                            c_price = float(m_c.iloc[-1])
                    else:
                        # Bayram / Dam olish kunlari
                        p_close = float(d_c.iloc[-2])
                        c_price = float(d_o.iloc[-1])
                else:
                    # Premarket datasi yq bo'lsa
                    p_close = float(d_c.iloc[-2])
                    c_price = float(d_o.iloc[-1])
                    
                if p_close > 0 and c_price > 0:
                    gap = ((c_price - p_close) / p_close) * 100
                    if abs(gap) >= GAP_THRESHOLD:
                        gap_pct[ticker] = gap
                        curr_price_dict[ticker] = c_price
        except Exception as e:
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
            if len(company_name) < 3: 
                company_name = ticker.lower()
            
            catalyst_url = ""
            news_time_str = "-"
            
            if finnhub_client:
                end_date = now_ny.strftime("%Y-%m-%d")
                start_date = (now_ny - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
                news = finnhub_client.company_news(ticker, _from=start_date, to=end_date)
                
                for article in reversed(news):
                    ts = article.get('datetime', 0)
                    if ts == 0: continue
                    
                    ny_time = pd.to_datetime(ts, unit='s', utc=True).tz_convert('America/New_York')
                    if ny_time < cutoff_time: continue
                        
                    headline = article['headline'].lower()
                    if ticker.lower() not in headline and company_name not in headline: continue
                    
                    for keyword in CATALYST_KEYWORDS:
                        if re.search(rf'\b{keyword}\b', headline):
                            catalyst_url = article.get('url', "")
                            news_time_str = ny_time.strftime('%H:%M')
                            break
                    if catalyst_url: break

            results.append({
                "Ticker": ticker, "Sector": sector, "Industry": industry,
                "Price": today_open, "Gap %": gap_val, "Time": news_time_str, "Link": catalyst_url 
            })
        except Exception as e:
            continue
            
    return pd.DataFrame(results)

with st.spinner('Skanerlanmoqda...'):
    df = get_dashboard_data()

    if not df.empty:
        gap_up_df = df[df["Gap %"] > 0].copy().sort_values(by="Gap %", ascending=False)
        gap_down_df = df[df["Gap %"] < 0].copy().sort_values(by="Gap %", ascending=True)

        def color_green(val): return 'color: #28a745; font-weight: bold;' if pd.notnull(val) else ''
        def color_red(val): return 'color: #dc3545; font-weight: bold;' if pd.notnull(val) else ''

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("<h5 style='text-align: center; color: #28a745;'>Gap Up</h5>", unsafe_allow_html=True)
            if not gap_up_df.empty:
                styled_up = gap_up_df.style.map(color_green, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'})
                st.dataframe(styled_up, width='stretch', height=700, hide_index=True, column_config={"Link": st.column_config.LinkColumn("Link", display_text="🔗 News")})
            else:
                st.info("Gap Up yq")

        with col2:
            st.markdown("<h5 style='text-align: center; color: #dc3545;'>Gap Down</h5>", unsafe_allow_html=True)
            if not gap_down_df.empty:
                styled_down = gap_down_df.style.map(color_red, subset=['Gap %']).format({'Price': '{:.2f}', 'Gap %': '{:+.2f}%'})
                st.dataframe(styled_down, width='stretch', height=700, hide_index=True, column_config={"Link": st.column_config.LinkColumn("Link", display_text="🔗 News")})
            else:
                st.info("Gap Down yq")
    else:
        st.info("Ma'lumot topilmadi.")
