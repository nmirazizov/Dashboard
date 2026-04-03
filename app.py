import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
import datetime
import re
import os
import plotly.graph_objects as go

# --- MINIMALIST DIZAYN ---
st.set_page_config(page_title="Market Summary", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #16181a; color: #d1d4dc; }
header[data-testid="stHeader"] { background-color: #16181a; }
div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; border: 1px solid #2b2d30; }
</style>
<h3 style='text-align: left; margin-top: -40px; color: #8b92a5;'>Market Summary</h3>
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
                return pd.DataFrame()
        except:
            return pd.DataFrame()
    else:
        TICKERS = ["AMD", "NVDA", "INTC", "MU", "AAPL", "TSLA", "META", "LITE", "LLY", "NKE"]

    gap_pct = {}
    curr_price_dict = {}
    ny_tz = 'America/New_York'
    now_ny = pd.Timestamp.now(tz=ny_tz)
    
    # Kechagi kunda ishlashi uchun vaqtni orqaga suramiz
    now_ny = now_ny - pd.Timedelta(days=1)
    now_ny = now_ny.replace(hour=10, minute=30)
    
    today_ny = now_ny.date()
    days_back = 3 if now_ny.weekday() == 0 else 1
    cutoff_time = now_ny - pd.Timedelta(days=days_back)
    market_open_time = datetime.time(9, 30)

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
                    
                ticker_close = d_close[ticker].dropna()
                ticker_open = d_open[ticker].dropna()
                
                if len(ticker_close) == 0: continue
                
                dates_d = pd.to_datetime(ticker_close.index).tz_convert(ny_tz).date if ticker_close.index.tz is not None else pd.to_datetime(ticker_close.index).date
                past_closes = ticker_close[dates_d < today_ny]
                
                if len(past_closes) == 0: continue
                p_close = float(past_closes.iloc[-1])
                c_price = p_close
                
                if now_ny.time() >= market_open_time:
                    today_opens = ticker_open[dates_d == today_ny]
                    if len(today_opens) > 0:
                        c_price = float(today_opens.iloc[0])
                    else:
                        if ticker in m_close.columns:
                            ticker_m = m_close[ticker].dropna()
                            idx_ny = pd.to_datetime(ticker_m.index).tz_convert(ny_tz) if ticker_m.index.tz is not None else pd.to_datetime(ticker_m.index)
                            reg_session = ticker_m[idx_ny.time >= market_open_time]
                            if len(reg_session) > 0: c_price = float(reg_session.iloc[0])
                else:
                    if ticker in m_close.columns:
                        ticker_m = m_close[ticker].dropna()
                        if len(ticker_m) > 0: c_price = float(ticker_m.iloc[-1])
                            
                if p_close > 0:
                    gap = ((c_price - p_close) / p_close) * 100
                    if abs(gap) >= GAP_THRESHOLD:
                        gap_pct[ticker] = gap
                        curr_price_dict[ticker] = c_price
        except:
            continue

    movers = list(gap_pct.keys())
    results = []
    for ticker in movers:
        try:
            info = yf.Ticker(ticker).info
            today_open = curr_price_dict.get(ticker)
            gap_val = gap_pct.get(ticker)
            
            company_name = str(info.get('shortName', ticker)).split()[0].lower()
            company_name = re.sub(r'[^a-z0-9]', '', company_name)
            if len(company_name) < 3: company_name = ticker.lower()
            
            catalyst_url = ""
            if finnhub_client:
                news = finnhub_client.company_news(ticker, _from=(now_ny - datetime.timedelta(days=3)).strftime("%Y-%m-%d"), to=now_ny.strftime("%Y-%m-%d"))
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
                            break
                    if catalyst_url: break

            results.append({"Ticker": ticker, "Price": today_open, "Gap %": gap_val, "Link": catalyst_url})
        except:
            continue
            
    return pd.DataFrame(results)

def draw_candle_chart(ticker):
    try:
        # Day trading uchun qulay: oxirgi 5 kun, 15 daqiqalik timeframe
        data = yf.download(ticker, period="5d", interval="15m", progress=False)
        if len(data) == 0: return go.Figure()
        
        fig = go.Figure(data=[go.Candlestick(
            x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'],
            increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
        )])
        
        fig.update_layout(
            template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=40, b=0),
            title=dict(text=f"<b>{ticker}</b>", font=dict(size=24, color='#d1d4dc')),
            xaxis=dict(showgrid=False, rangeslider=dict(visible=False)),
            yaxis=dict(showgrid=True, gridcolor='#2b2d30', gridwidth=1, side='right')
        )
        return fig
    except:
        return go.Figure()

with st.spinner('Skanerlanmoqda...'):
    df = get_dashboard_data()

    col_cfg = {
        "Price": st.column_config.NumberColumn("Price", format="%.2f"),
        "Gap %": st.column_config.NumberColumn("Change", format="%+.2f%%"),
        "Link": st.column_config.LinkColumn("News")
    }

    # --- GAP UP WIDGET ---
    st.markdown("<h4 style='color: #26a69a;'>Gap Up</h4>", unsafe_allow_html=True)
    up_col, chart_col1 = st.columns([1, 2])
    
    with up_col:
        gap_up_df = df[df["Gap %"] > 0].copy().sort_values(by="Gap %", ascending=False) if not df.empty else pd.DataFrame()
        if not gap_up_df.empty:
            up_event = st.dataframe(
                gap_up_df, use_container_width=True, hide_index=True, 
                selection_mode="single_row", on_select="rerun", column_config=col_cfg
            )
            selected_up = gap_up_df.iloc[up_event.selection.rows[0]]['Ticker'] if up_event.selection.rows else "SPY"
        else:
            st.info("Gap Up yq")
            selected_up = "SPY"
            
    with chart_col1:
        st.plotly_chart(draw_candle_chart(selected_up), use_container_width=True, config={'displayModeBar': False})

    st.markdown("<hr style='border-color: #2b2d30;'>", unsafe_allow_html=True)

    # --- GAP DOWN WIDGET ---
    st.markdown("<h4 style='color: #ef5350;'>Gap Down</h4>", unsafe_allow_html=True)
    down_col, chart_col2 = st.columns([1, 2])
    
    with down_col:
        gap_down_df = df[df["Gap %"] < 0].copy().sort_values(by="Gap %", ascending=True) if not df.empty else pd.DataFrame()
        if not gap_down_df.empty:
            down_event = st.dataframe(
                gap_down_df, use_container_width=True, hide_index=True, 
                selection_mode="single_row", on_select="rerun", column_config=col_cfg
            )
            selected_down = gap_down_df.iloc[down_event.selection.rows[0]]['Ticker'] if down_event.selection.rows else "SPY"
        else:
            st.info("Gap Down yq")
            selected_down = "SPY"
            
    with chart_col2:
        st.plotly_chart(draw_candle_chart(selected_down), use_container_width=True, config={'displayModeBar': False})
