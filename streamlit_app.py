# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import json
import traceback
import streamlit.components.v1 as components

# 프로젝트 핵심 분석 모듈 임포트
from search import search_ticker_by_name
from analysis import (
    fmt_price, fmt_range, fmt_large_value, fmt_chart_val,
    get_fib_levels, get_entry_signal, get_adjacent_l_levels,
    calculate_composite_score, score_to_label, make_fib_markdown_table,
    generate_future_outlook, format_fundamental_report,
    generate_fibonacci_scenario_md, generate_news_impact_md,
    generate_strategy_and_buy_price_md
)
from damus import get_damus_data, generate_damus_report_md
from ai_analyzer import ask_gemini_qna

# ────────────────────────────────────────────────────────────
# Page Configuration & Rich CSS Styling
# ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="피보나치 AI 분석기 (FiboAnalyzer)",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 구글 번역기 오작동 방지용 Meta 태그 및 JavaScript 주입
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)
components.html(
    """
    <script>
        // 부모 창의 html lang 속성을 한국어로 강제 설정하여 번역 오인 차단
        window.parent.document.documentElement.lang = 'ko';
        
        // 부모 창의 head에 notranslate 메타 태그 추가
        var meta = window.parent.document.createElement('meta');
        meta.name = 'google';
        meta.content = 'notranslate';
        window.parent.document.head.appendChild(meta);
        
        // 부모 창의 body에 notranslate 클래스 추가
        window.parent.document.body.classList.add('notranslate');
    </script>
    """,
    height=0
)

# Custom Sleek Dark Mode Styling (Glassmorphism & Harmonious Colors)
st.markdown("""
<style>
    /* 전체 배경색 및 폰트 설정 */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+KR:wght@300;400;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Outfit', 'Noto Sans KR', sans-serif;
        background-color: #0F0F12;
        color: #E2E8F0;
    }
    
    /* 사이드바 스타일링 */
    [data-testid="stSidebar"] {
        background-color: #16161D;
        border-right: 1px solid #2D2D3A;
    }
    
    /* 카드 컴포넌트 클래스 정의 */
    .dashboard-card {
        background: rgba(30, 30, 40, 0.45);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    
    .dashboard-card:hover {
        transform: translateY(-2px);
        border-color: rgba(41, 121, 255, 0.4);
    }
    
    /* KPI 카드 스타일 */
    .kpi-title {
        color: #94A3B8;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 6px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .kpi-val {
        font-size: 26px;
        font-weight: 700;
        background: linear-gradient(45deg, #38BDF8, #818CF8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .kpi-desc {
        color: #64748B;
        font-size: 12px;
        margin-top: 4px;
    }
    
    /* 헤더 그라데이션 타이틀 */
    .title-gradient {
        background: linear-gradient(135deg, #60A5FA 10%, #3B82F6 50%, #818CF8 90%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin-bottom: 5px;
    }
</style>
""", unsafe_allow_html=True)

# 즐겨찾기 파일 경로 설정
FAVORITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favorites_web.json")

def load_favorites():
    favs = []
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
                favs = json.load(f)
        except:
            pass
    if not favs:
        favs = [
            ("BTC", "BTC-USD"),
            ("XRP", "XRP-USD"),
            ("OTLK", "OTLK"),
            ("SMR", "SMR")
        ]
    
    # 모든 자산명을 공백 및 괄호 없이 대문자 티커 포맷으로 정제
    cleaned_favs = []
    for name, val in favs:
        cleaned_name = name.split(" ")[0].upper()
        cleaned_favs.append((cleaned_name, val))
    return cleaned_favs

def save_favorites(favs):
    # 저장할 때도 정제된 리스트로 저장
    cleaned_favs = []
    for name, val in favs:
        cleaned_name = name.split(" ")[0].upper()
        cleaned_favs.append((cleaned_name, val))
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned_favs, f, ensure_ascii=False, indent=4)
    except:
        pass

# AI 추천 자산 정의
AI_RECOMMENDED = [
    ("NVDA (엔비디아)", "NVDA", "AI 생태계 하드웨어 시장 독점 및 실적 모멘텀"),
    ("SOL (솔라나)", "SOL-USD", "알트코인 트랜잭션 증가 및 빠른 단기 반등 모멘텀"),
    ("AAPL (애플)", "AAPL", "디바이스 탑재 온디바이스 AI 시장의 최대 수혜 전망"),
    ("005930 (삼성전자)", "005930.KS", "반도체 턴어라운드 및 역사적 피보나치 바닥권"),
    ("TSLA (테슬라)", "TSLA", "자율주행 및 로보택시 중장기 성장성 부각")
]

# ────────────────────────────────────────────────────────────
# Session State Initialization (React DOM NotFoundError 방지)
# ────────────────────────────────────────────────────────────
if "search_ticker" not in st.session_state:
    st.session_state.search_ticker = "BTC-USD"

if "favorites" not in st.session_state:
    st.session_state.favorites = load_favorites()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_analyzed_ticker" not in st.session_state:
    st.session_state.last_analyzed_ticker = ""

# ────────────────────────────────────────────────────────────
# Sidebar & User inputs
# ────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<h2 style="color:#60A5FA; margin-bottom: 2px;">🎯 FiboAnalyzer</h2>', unsafe_allow_html=True)
    st.markdown('<p style="color:#64748B; font-size:12px; margin-bottom: 25px;">Multi-Timeframe Fibonacci & AI Agent</p>', unsafe_allow_html=True)
    
    st.subheader("🔑 API KEY 설정")
    user_api_key = st.text_input(
        "Gemini API Key", 
        type="password", 
        placeholder="AIzaSy... 형식의 키를 입력해 주세요.",
        help="Google AI Studio에서 발급받은 본인의 API 키를 입력해 주세요. 입력한 키는 서버에 저장되지 않고 브라우저에만 유지됩니다."
    )
    
    if not user_api_key:
        st.info("💡 API 키를 입력하지 않으시면 AI 뉴스 분석 및 Q&A 기능 대신 기본 분석 템플릿(폴백)으로 출력됩니다.")
        
    st.subheader("🔍 분석 조건 설정")
    
    # 즐겨찾기 리스트 (한 줄씩 삭제 기능 ❌ 연동)
    st.write("⭐ 즐겨찾기 빠른 로드")
    for idx, (name, val) in enumerate(st.session_state.favorites):
        col1, col2 = st.columns([0.8, 0.2])
        # 자산 변경 클릭 시 세션 상태를 변경하고 리프레시하여 DOM 충돌 방지
        if col1.button(name, key=f"fav_btn_{idx}_{val}", use_container_width=True):
            st.session_state.search_ticker = val
            st.rerun()
        if col2.button("❌", key=f"fav_del_{idx}_{val}", help=f"{name} 즐겨찾기 삭제"):
            st.session_state.favorites.pop(idx)
            save_favorites(st.session_state.favorites)
            st.rerun()
            
    # 티커 직접 검색 입력창 (세션 상태와 단방향 연동)
    search_query = st.text_input(
        "자산명 또는 티커 검색", 
        value=st.session_state.search_ticker,
        key="ticker_input_widget",
        help="예: BTC-USD, AAPL, 005930.KS"
    )
    
    # 텍스트 입력창 조작 시 세션 상태 갱신
    if search_query != st.session_state.search_ticker:
        st.session_state.search_ticker = search_query

    # 대상 시장 선택
    market_opt = st.selectbox(
        "대상 시장 선택",
        options=["all", "nasdaq", "binance"],
        format_func=lambda x: {"all": "전체 시장", "nasdaq": "나스닥 (NASDAQ)", "binance": "바이낸스 (Binance)"}.get(x)
    )
    
    # 즐겨찾기 추가 편집
    st.write("---")
    st.subheader("⭐ 즐겨찾기 신규 등록")
    new_fav_name = st.text_input("즐겨찾기 추가 이름", placeholder="예: 삼성전자", key="new_fav_name_widget")
    new_fav_ticker = st.text_input("즐겨찾기 추가 티커", placeholder="예: 005930.KS", key="new_fav_ticker_widget")
    
    if st.button("현재 자산 즐겨찾기 추가"):
        if new_fav_name and new_fav_ticker:
            if (new_fav_name, new_fav_ticker) not in st.session_state.favorites:
                st.session_state.favorites.append((new_fav_name, new_fav_ticker))
                save_favorites(st.session_state.favorites)
                st.success("즐겨찾기가 추가되었습니다!")
                st.rerun()
        else:
            st.error("이름과 티커를 모두 입력해 주세요.")

    # 🤖 AI 추천 자산 섹션 추가
    st.write("---")
    st.subheader("🤖 AI 추천 유망 자산")
    for name, ticker, reason in AI_RECOMMENDED:
        col_rec1, col_rec2 = st.columns([0.8, 0.2])
        col_rec1.markdown(f"**{name}**<br><span style='color:#64748B; font-size:11px;'>{reason}</span>", unsafe_allow_html=True)
        
        # 중복 체크
        is_already_fav = any(f[1] == ticker for f in st.session_state.favorites)
        if is_already_fav:
            col_rec2.button("✔️", key=f"rec_add_{ticker}", disabled=True)
        else:
            if col_rec2.button("⭐", key=f"rec_add_{ticker}", help="즐겨찾기에 추가"):
                st.session_state.favorites.append((name.split(" ")[0], ticker))
                save_favorites(st.session_state.favorites)
                st.rerun()
            
    if st.button("즐겨찾기 전체 초기화"):
        if os.path.exists(FAVORITES_FILE):
            os.remove(FAVORITES_FILE)
        st.session_state.favorites = load_favorites()
        save_favorites(st.session_state.favorites)
        st.success("즐겨찾기가 복구되었습니다.")
        st.rerun()

# ────────────────────────────────────────────────────────────
# 자산 전환에 따른 채팅 내역 초기화 (React DOM NotFoundError 방지 핵심)
# ────────────────────────────────────────────────────────────
if st.session_state.last_analyzed_ticker != st.session_state.search_ticker:
    st.session_state.last_analyzed_ticker = st.session_state.search_ticker
    # 자산 전환 시 채팅 초기화하여 DOM 구조 꼬임 방지
    st.session_state.messages = []

# ────────────────────────────────────────────────────────────
# 📊 즐겨찾기 실시간 시세 가로 전광판 데이터 수집 (Marquee)
# ────────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def get_marquee_prices(favorites):
    tickers = [f[1] for f in favorites]
    if not tickers:
        return "📊 즐겨찾기에 자산을 등록해 주세요."
    try:
        data = yf.download(tickers, period="5d", interval="1d", group_by="ticker", progress=False)
        marquee_items = []
        for name, ticker in favorites:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    df = data[ticker].copy()
                else:
                    df = data.copy()
                
                # 주말/휴일 등으로 인해 데이터가 없는 날(NaN)의 행을 제거하여 정상 가격 추출
                df = df.dropna(subset=['Close'])
                
                if df.empty or len(df) < 2:
                    continue
                close_today = float(df['Close'].iloc[-1])
                close_yesterday = float(df['Close'].iloc[-2])
                diff = close_today - close_yesterday
                pct = (diff / close_yesterday) * 100
                
                is_usd = not (ticker.endswith('.KS') or ticker.endswith('.KQ'))
                price_str = f"${close_today:,.2f}" if is_usd else f"₩{close_today:,.0f}"
                
                if pct >= 0:
                    item = f"<span style='color:#FF5252; font-weight:bold;'>{name}: {price_str} ▲{pct:.2f}%</span>"
                else:
                    item = f"<span style='color:#2979FF; font-weight:bold;'>{name}: {price_str} ▼{abs(pct):.2f}%</span>"
                marquee_items.append(item)
            except Exception as ex:
                print(f"[Marquee Warning] {ticker} 파싱 실패: {ex}")
        return " &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ".join(marquee_items)
    except Exception as e:
        print(f"[Marquee Error] 시세 수집 실패: {e}")
        return "📊 실시간 시세를 수집할 수 없습니다."

# ────────────────────────────────────────────────────────────
# Plotly Interactive Chart Generator Helper Functions
# ────────────────────────────────────────────────────────────
def create_plotly_candlestick_chart(df, title, fib_levels=None, sma_cols=None, bb_cols=None, is_usd=True):
    """
    마우스 호버 시 가격 정보가 툴팁으로 실시간 연동되는 캔들스틱 + 거래량 인터랙티브 차트 생성
    """
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25]
    )

    UP_COLOR = '#FF5252'
    DOWN_COLOR = '#2979FF'

    # 1. 캔들스틱 트레이스 추가
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            increasing_line_color=UP_COLOR,
            increasing_fillcolor=UP_COLOR,
            decreasing_line_color=DOWN_COLOR,
            decreasing_fillcolor=DOWN_COLOR,
            name="캔들스틱"
        ),
        row=1, col=1
    )

    # 2. 이동평균선(SMA) 오버레이
    if sma_cols:
        colors = ['#FFCA28', '#BA68C8']
        for col, color in zip(sma_cols, colors):
            if col in df.columns:
                label_name = col.replace('SMA_', '') + '일 이평선'
                fig.add_trace(
                    go.Scatter(
                        x=df.index, y=df[col],
                        line=dict(color=color, width=1.2, dash='dot'),
                        name=label_name
                    ),
                    row=1, col=1
                )

    # 3. 볼린저 밴드 오버레이
    if bb_cols and all(c in df.columns for c in bb_cols):
        upper_vals = df[bb_cols[0]]
        lower_vals = df[bb_cols[1]]
        fig.add_trace(
            go.Scatter(
                x=df.index, y=upper_vals,
                line=dict(color='rgba(41, 182, 246, 0.25)', width=0.8),
                name="볼린저밴드 상단"
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=lower_vals,
                line=dict(color='rgba(41, 182, 246, 0.25)', width=0.8),
                fill='tonexty',
                fillcolor='rgba(41, 182, 246, 0.04)',
                name="볼린저밴드 하단"
            ),
            row=1, col=1
        )

    # 4. 피보나치 레벨 수평선 오버레이
    if fib_levels:
        fib_map = {
            '1.000 (고점)': ('#EF5350', 'solid', 0.5),
            '0.764 (1차 조정선)': ('#FFA726', 'dot', 0.3),
            '0.618 (첫 주요 지지선)': ('#66BB6A', 'dash', 0.9),
            '0.500 (절반선)': ('#FFEE58', 'dot', 0.3),
            '0.382 (두 번째 지지선)': ('#BA68C8', 'dash', 0.9),
            '0.236 (최종 지지선)': ('#29B6F6', 'dot', 0.3),
            '0.146 (심층 지지선)': ('#E91E63', 'dot', 0.3),
            '0.000 (저점)': ('#90A4AE', 'solid', 0.5),
        }
        for label, (color, dash_type, opacity) in fib_map.items():
            val = fib_levels.get(label)
            if val:
                short_lbl = label.split(' ')[0]
                fig.add_hline(
                    y=val,
                    line_dash=dash_type,
                    line_color=color,
                    line_width=1.0,
                    opacity=opacity,
                    annotation_text=f" {short_lbl} ({fmt_chart_val(val, is_usd)})",
                    annotation_position="right",
                    annotation_font_size=8,
                    annotation_font_color=color,
                    row=1, col=1
                )

    # 5. 거래량 막대그래프
    if 'Volume' in df.columns:
        vol_colors = [UP_COLOR if close >= open_val else DOWN_COLOR 
                      for close, open_val in zip(df['Close'], df['Open'])]
        fig.add_trace(
            go.Bar(
                x=df.index, y=df['Volume'],
                marker_color=vol_colors,
                opacity=0.6,
                name="거래량"
            ),
            row=2, col=1
        )
        
        vol_ma = df['Volume'].rolling(20, min_periods=1).mean()
        fig.add_trace(
            go.Scatter(
                x=df.index, y=vol_ma,
                line=dict(color='#FFEE58', width=1.0),
                name="20일 평균 거래량"
            ),
            row=2, col=1
        )

    # 레이아웃 스타일 갱신
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color='#E2E8F0')),
        template="plotly_dark",
        plot_bgcolor='#13131A',
        paper_bgcolor='#0F0F12',
        xaxis_rangeslider_visible=False,
        showlegend=False,
        margin=dict(l=20, r=60, t=40, b=20),
        hovermode="x unified"
    )
    fig.update_yaxes(title_text="가격", row=1, col=1, gridcolor='#22222A')
    fig.update_yaxes(title_text="거래량", row=2, col=1, gridcolor='#22222A')
    fig.update_xaxes(gridcolor='#22222A')

    return fig

# 📊 RSI 14 인터랙티브 차트 생성 함수
def create_plotly_rsi_chart(df):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df['RSI_14'],
            line=dict(color='#CE93D8', width=1.5),
            name="RSI 14"
        )
    )
    # 70 및 30 기준선 추가
    fig.add_hline(y=70, line_dash="dash", line_color="#EF5350", line_width=1.0)
    fig.add_hline(y=30, line_dash="dash", line_color="#66BB6A", line_width=1.0)
    # 과매수/과매도 배경 영역 색칠
    fig.add_hrect(y0=70, y1=100, fillcolor="#EF5350", opacity=0.04, line_width=0)
    fig.add_hrect(y0=0, y1=30, fillcolor="#66BB6A", opacity=0.04, line_width=0)
    
    fig.update_layout(
        title="RSI 14 보조지표 (최근 180봉)",
        template="plotly_dark",
        plot_bgcolor='#13131A',
        paper_bgcolor='#0F0F12',
        margin=dict(l=20, r=40, t=40, b=20),
        hovermode="x unified",
        yaxis=dict(range=[0, 100], gridcolor='#22222A', title_text="RSI 값"),
        xaxis=dict(gridcolor='#22222A')
    )
    return fig

# 📊 MACD 인터랙티브 차트 생성 함수
def create_plotly_macd_chart(df):
    fig = go.Figure()
    # MACD Histogram (양수: 하늘색, 음수: 빨간색)
    hist_colors = ['#29B6F6' if v >= 0 else '#EF5350' for v in df['MACD_Hist']]
    fig.add_trace(
        go.Bar(
            x=df.index, y=df['MACD_Hist'],
            marker_color=hist_colors,
            opacity=0.7,
            name="MACD 히스토그램"
        )
    )
    # MACD Line & Signal Line
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df['MACD'],
            line=dict(color='#FFB74D', width=1.2),
            name="MACD"
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df['MACD_Signal'],
            line=dict(color='#EF5350', width=1.2),
            name="시그널"
        )
    )
    # 기준선 (0)
    fig.add_hline(y=0, line_color="#555555", line_width=0.8)
    
    fig.update_layout(
        title="MACD (12/26/9) (최근 180봉)",
        template="plotly_dark",
        plot_bgcolor='#13131A',
        paper_bgcolor='#0F0F12',
        margin=dict(l=20, r=40, t=40, b=20),
        hovermode="x unified",
        yaxis=dict(gridcolor='#22222A', title_text="수치"),
        xaxis=dict(gridcolor='#22222A')
    )
    return fig

# 📊 실시간 주가 및 보조지표 연산 핵심 비즈니스 로직 함수
@st.cache_data(show_spinner=False, ttl=60)
def fetch_and_analyze_data(query, market, api_key=None):
    ticker = search_ticker_by_name(query, market)
    if ticker is None:
        raise ValueError(f"'{query}'에 해당하는 자산을 찾지 못했습니다. 올바른 티커를 입력해 주세요.")

    # 1. 일봉 데이터 다운로드
    df_all = yf.download(ticker, period='max', interval='1d')
    if df_all.empty:
        raise ValueError(f"'{ticker}' 데이터가 존재하지 않거나 가져오는 데 실패했습니다.")

    # MultiIndex 대응 컬럼 평탄화
    if df_all.columns.nlevels > 1:
        df_all.columns = df_all.columns.droplevel(1)

    # 2. info 및 뉴스 로드
    info = {}
    news_list = []
    try:
        t_obj = yf.Ticker(ticker)
        info = t_obj.info
        try:
            news_list = t_obj.news
        except Exception as ne:
            print(f"[Warning] Ticker.news 로드 실패: {ne}")
    except Exception as e:
        print(f"[Warning] Ticker.info 로드 실패: {e}")

    # 통화 판단
    is_usd = True
    if ticker.endswith('.KS') or ticker.endswith('.KQ'):
        is_usd = False

    # 실시간 적용 환율
    rate = 1.0
    if is_usd:
        try:
            rate_df = yf.download("USDKRW=X", period="1d")
            if rate_df.columns.nlevels > 1:
                rate_df.columns = rate_df.columns.droplevel(1)
            rate = float(rate_df['Close'].iloc[-1])
        except:
            rate = 1380.0

    # 3. 보조지표 계산 (RSI, SMA, MACD, 볼린저 밴드)
    delta = df_all['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df_all['RSI_14'] = 100 - (100 / (1 + rs))

    df_all['SMA_5'] = df_all['Close'].rolling(window=5).mean()
    df_all['SMA_20'] = df_all['Close'].rolling(window=20).mean()

    # MACD (12/26/9)
    ema12 = df_all['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df_all['Close'].ewm(span=26, adjust=False).mean()
    df_all['MACD'] = ema12 - ema26
    df_all['MACD_Signal'] = df_all['MACD'].ewm(span=9, adjust=False).mean()
    df_all['MACD_Hist'] = df_all['MACD'] - df_all['MACD_Signal']

    # 볼린저밴드 (20일, 2σ)
    df_all['BB_Mid'] = df_all['Close'].rolling(20).mean()
    df_all['BB_Std'] = df_all['Close'].rolling(20).std()
    df_all['BB_Upper'] = df_all['BB_Mid'] + 2 * df_all['BB_Std']
    df_all['BB_Lower'] = df_all['BB_Mid'] - 2 * df_all['BB_Std']

    # 거래량 이동평균
    vol_ma20 = df_all['Volume'].rolling(20).mean()

    # 현재가 기준 각 지표 데이터
    current_price = float(df_all['Close'].iloc[-1])
    current_rsi = float(df_all['RSI_14'].iloc[-1])
    current_sma5 = float(df_all['SMA_5'].iloc[-1])
    current_sma20 = float(df_all['SMA_20'].iloc[-1])
    current_macd = float(df_all['MACD'].iloc[-1])
    current_macd_signal = float(df_all['MACD_Signal'].iloc[-1])
    current_macd_hist = float(df_all['MACD_Hist'].iloc[-1])
    current_bb_upper = float(df_all['BB_Upper'].iloc[-1])
    current_bb_lower = float(df_all['BB_Lower'].iloc[-1])
    current_vol = float(df_all['Volume'].iloc[-1]) if 'Volume' in df_all.columns else 0
    vol_ma20_val = float(vol_ma20.iloc[-1]) if vol_ma20.iloc[-1] > 0 else 1
    vol_ratio = current_vol / vol_ma20_val if vol_ma20_val > 0 else 1.0

    bb_band_width = current_bb_upper - current_bb_lower
    bb_pct = (current_price - current_bb_lower) / bb_band_width if bb_band_width > 0 else 0.5

    df_52w = df_all.tail(252)
    week52_high = float(df_52w['High'].max())
    week52_low = float(df_52w['Low'].min())
    week52_position = (current_price - week52_low) / (week52_high - week52_low) * 100 if (week52_high - week52_low) > 0 else 50

    # 4. 피보나치 중첩 분석 (L, M, S, XS)
    l_high = float(df_all['High'].max())
    l_low = float(df_all['Low'].min())
    l_levels = get_fib_levels(l_high, l_low)
    l_signal = get_entry_signal(current_price, l_levels, current_rsi)

    df_m = df_all.tail(180).copy()
    m_low_idx = df_m['Low'].idxmin()
    m_low = float(df_m['Low'].min())
    m_high = float(df_m.loc[m_low_idx:]['High'].max())
    m_levels = get_fib_levels(m_high, m_low)
    m_signal = get_entry_signal(current_price, m_levels, current_rsi)

    df_s = df_all.tail(30).copy()
    s_low_idx = df_s['Low'].idxmin()
    s_low = float(df_s['Low'].min())
    s_high = float(df_s.loc[s_low_idx:]['High'].max())
    s_levels = get_fib_levels(s_high, s_low)
    s_signal = get_entry_signal(current_price, s_levels, current_rsi)

    df_xs = df_all.tail(7).copy()
    xs_low_idx = df_xs['Low'].idxmin()
    xs_low = float(df_xs['Low'].min())
    xs_high = float(df_xs.loc[xs_low_idx:]['High'].max())
    xs_levels = get_fib_levels(xs_high, xs_low)
    xs_signal = get_entry_signal(current_price, xs_levels, current_rsi)

    # 5. 기술 점수 및 판단
    signals = [l_signal, m_signal, s_signal, xs_signal]
    composite_score = calculate_composite_score(signals, current_rsi, current_macd_hist, bb_pct, vol_ratio)
    score_label = score_to_label(composite_score)

    # 단기 의견
    if current_sma5 > current_sma20:
        trend_opinion = "단기 강세 추세 (5/20일 골든크로스 및 정배열)"
    else:
        trend_opinion = "단기 약세 추세 (5/20일 데드크로스 및 역배열)"

    # 적정 매수가
    l_0618 = l_levels.get('0.618 (첫 주요 지지선)', 0)
    l_0500 = l_levels.get('0.500 (절반선)', 0)
    l_0382 = l_levels.get('0.382 (두 번째 지지선)', 0)
    l_0236 = l_levels.get('0.236 (최종 지지선)', 0)
    l_0146 = l_levels.get('0.146 (심층 지지선)', 0)
    xs_0618 = xs_levels.get('0.618 (첫 주요 지지선)', 0)

    if current_price > l_0618 * 1.02:
        best_buy = l_0618
    elif current_price > l_0500 * 1.02:
        best_buy = l_0500
    elif current_price > l_0382 * 1.02:
        best_buy = l_0382
    elif current_price > l_0236 * 1.02:
        best_buy = l_0236
    elif current_price > l_0146 * 1.02:
        best_buy = l_0146
    elif current_rsi <= 30:
        best_buy = xs_0618
    else:
        best_buy = l_levels.get('0.000 (저점)', current_price)

    best_buy_str = fmt_price(best_buy, rate, is_usd)

    # 6. 애널리스트 투자의견 매핑
    rec = info.get('recommendationKey') if info else None
    if rec and rec.lower() != 'none':
        rec_ko = {
            'buy': '매수 (Buy)',
            'strong_buy': '적극 매수 (Strong Buy)',
            'hold': '보유 (Hold)',
            'underperform': '비중 축소 (Underperform)',
            'sell': '매도 (Sell)',
            'neutral': '중립 (Neutral)'
        }.get(rec.lower(), rec)
    else:
        rec_ko = score_label

    # 7. 마크다운 보고서 조립 (사용자 제공 API 키 주입)
    strategy_md = generate_strategy_and_buy_price_md(
        ticker, current_price, l_levels, m_levels, s_levels, xs_levels,
        current_rsi, rate, is_usd, composite_score, vol_ratio, current_macd_hist,
        week52_position, bb_pct, current_sma5, current_sma20
    )
    fib_scenario_md = generate_fibonacci_scenario_md(
        ticker, current_price, l_levels, m_levels, s_levels, xs_levels,
        current_rsi, rate, is_usd, vol_ratio, "추세 모멘텀 분석 중"
    )
    future_outlook_md = generate_future_outlook(ticker, info, rate)
    
    # 뉴스 영향 마크다운 및 AI 분석 수집 (사용자 API 키 전달)
    news_impact_md, ai_result = generate_news_impact_md(ticker, news_list, api_key=api_key)

    # Damus 레벨 연산
    damus_data = get_damus_data(ticker, is_usd, "1d")
    damus_report_md = generate_damus_report_md(damus_data, rate)

    # 최종 종합 리포트 조립
    full_report_content = f"""
# 📊 {ticker} 멀티 타임프레임 피보나치 중첩 분석 리포트

- **분석 기준**: 역사적 대파동(L), 중기 파동(M), 단기 변곡(S), 초단기 극세(XS) 중첩
- **적용 환율**: 1달러 = {rate:,.2f}원 (원화 환산 가격 표시)

---

## 1. 현재 시장 및 지표 요약
- **현재 가격**: {fmt_price(current_price, rate, is_usd)}
- **RSI (14)**: {current_rsi:.2f} ({'과매수' if current_rsi >= 70 else '과매도' if current_rsi <= 30 else '중립'})
- **이동평균선**: 5일선 {fmt_price(current_sma5, rate, is_usd)} / 20일선 {fmt_price(current_sma20, rate, is_usd)}
- **단기 추세**: {trend_opinion}

---

## 2. 타임프레임별 피보나치 진입점 비교
| 스케일 구분 | 분석 범위 설명 | 최근 고점 (High) | 최근 저점 (Low) | 진입 신호 |
| :--- | :--- | :--- | :--- | :--- |
| **L Size (All-Time)** | 전체 역사 범위 | {fmt_price(l_high, rate, is_usd)} | {fmt_price(l_low, rate, is_usd)} | **{l_signal}** |
| **M Size (Nested L)** | L의 인접 피보나치 레벨 사이 | {fmt_price(m_high, rate, is_usd)} | {fmt_price(m_low, rate, is_usd)} | **{m_signal}** |
| **S Size (Nested M)** | M의 인접 피보나치 레벨 사이 | {fmt_price(s_high, rate, is_usd)} | {fmt_price(s_low, rate, is_usd)} | **{s_signal}** |
| **XS Size (Nested S)** | S의 인접 피보나치 레벨 사이 | {fmt_price(xs_high, rate, is_usd)} | {fmt_price(xs_low, rate, is_usd)} | **{xs_signal}** |

---

## 3. 타임프레임별 피보나치 상세 레벨

### 🌐 L Size (All-Time) 상세 레벨
{make_fib_markdown_table(l_levels, current_price, rate, is_usd)}

### 📅 M Size (Nested L) 상세 레벨
{make_fib_markdown_table(m_levels, current_price, rate, is_usd)}

### 📆 S Size (Nested M) 상세 레벨
{make_fib_markdown_table(s_levels, current_price, rate, is_usd)}

### ⏰ XS Size (Nested S) 상세 레벨
{make_fib_markdown_table(xs_levels, current_price, rate, is_usd)}

---

## 4. 보조지표 정밀 평가
- **52주 가격 위치**: 52주 변동폭 내 **{week52_position:.1f}%** 지점 위치 (고가: {fmt_price(week52_high, rate, is_usd)} / 저가: {fmt_price(week52_low, rate, is_usd)})
- **볼린저 밴드 %B**: {bb_pct*100:.1f}% 지점 위치

---

## 5. ★ 종합 기술 분석 점수
> ## 🎯 **종합 점수: {composite_score} / 100점**
> ### 📢 **최종 판단: {score_label}**

---

{strategy_md}

{fib_scenario_md}

{damus_report_md}

{future_outlook_md}

---

{news_impact_md}

---
*본 리포트는 기술적 분석 보조지표를 바탕으로 자동 생성된 정보이며, 투자 참고용으로만 사용하시기 바랍니다.*
"""

    return {
        'ticker': ticker,
        'current_price': current_price,
        'current_rsi': current_rsi,
        'composite_score': composite_score,
        'score_label': score_label,
        'best_buy_str': best_buy_str,
        'rec_ko': rec_ko,
        'is_usd': is_usd,
        'rate': rate,
        'df_all': df_all,
        'df_m': df_m,
        'df_s': df_s,
        'df_xs': df_all.tail(14).copy(),  # 최근 14봉
        'l_levels': l_levels,
        'm_levels': m_levels,
        's_levels': s_levels,
        'xs_levels': xs_levels,
        'l_high': l_high, 'l_low': l_low,
        'm_high': m_high, 'm_low': m_low,
        's_high': s_high, 's_low': s_low,
        'xs_high': xs_high, 'xs_low': xs_low,
        'report_markdown': full_report_content,
        'damus_data': damus_data
    }

# ────────────────────────────────────────────────────────────
# Main Page Render Layout

# ────────────────────────────────────────────────────────────
# 1. 최상단 실시간 시세 흐르는 전광판 (Marquee) 주입
marquee_html = f"""
<div style="background-color: #121216; border: 1px solid #282834; border-radius: 10px; padding: 10px; overflow: hidden; white-space: nowrap; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.45);">
    <marquee scrollamount="4" behavior="scroll" direction="left" onmouseover="this.stop();" onmouseout="this.start();" style="font-family:'Outfit','Noto Sans KR',sans-serif; font-size:13px;">
        {get_marquee_prices(st.session_state.favorites)}
    </marquee>
</div>
"""
st.markdown(marquee_html, unsafe_allow_html=True)

# 실행 및 데이터 표시 (React DOM Crash 방지를 위해 하나의 전체 컨테이너 내에서 안전하게 가동)
main_container = st.container(key="fibo_dashboard_main_container")

with main_container:
    try:
        with st.spinner("🎯 실시간 시장 정보 및 보조지표를 연산하는 중입니다..."):
            results = fetch_and_analyze_data(st.session_state.search_ticker, market_opt, api_key=user_api_key)
            
        # ────────────────────────────────────────────────────────────
        # 1. 4구역 KPI 핵심 카드 섹션
        # ────────────────────────────────────────────────────────────
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="dashboard-card">
                <div class="kpi-title">💵 현재 실시간 가격</div>
                <div class="kpi-val">{fmt_price(results['current_price'], results['rate'], results['is_usd'])}</div>
                <div class="kpi-desc">환율 1$ = {results['rate']:,.2f}원 적용</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
            <div class="dashboard-card">
                <div class="kpi-title">🎯 종합 기술 점수</div>
                <div class="kpi-val">{results['composite_score']} / 100점</div>
                <div class="kpi-desc">최종 판단: {results['score_label']}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col3:
            st.markdown(f"""
            <div class="dashboard-card">
                <div class="kpi-title">💡 최적의 분할매수(DCA) 타점</div>
                <div class="kpi-val">{results['best_buy_str']}</div>
                <div class="kpi-desc">역사적 피보나치 주요 지지대 기준</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col4:
            st.markdown(f"""
            <div class="dashboard-card">
                <div class="kpi-title">📢 컨센서스 / 최종의견</div>
                <div class="kpi-val">{results['rec_ko']}</div>
                <div class="kpi-desc">애널리스트 및 지표 가중치 종합</div>
            </div>
            """, unsafe_allow_html=True)

        # ────────────────────────────────────────────────────────────
        # 2. Plotly 인터랙티브 차트 시각화 섹션 (탭 적용)
        # ────────────────────────────────────────────────────────────
        st.subheader("📈 멀티 타임프레임 차트 및 피보나치 작도 (마우스 오버 가격 확인)")
        
        # 탭 렌더링 (RSI 14 및 MACD Plotly 탭 복구)
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "🌐 All-Time (L)", "📅 180일 스윙 (M)", "📆 30일 단기 (S)", "⏰ 7일 초단기 (XS)", "💜 RSI 14", "💛 MACD", "🥔 Damus 알고리즘"
        ])
        
        # L Size 차트 연산 및 렌더링
        with tab1:
            fig_l = create_plotly_candlestick_chart(
                df=results['df_all'].tail(1000).copy(),
                title=f"L Size: All-Time (최근 1000봉) / 고점: {fmt_chart_val(results['l_high'], results['is_usd'])} / 저점: {fmt_chart_val(results['l_low'], results['is_usd'])}",
                fib_levels=results['l_levels'],
                is_usd=results['is_usd']
            )
            st.plotly_chart(fig_l, use_container_width=True, key="plotly_chart_l_size")
            
        # M Size 차트 연산 및 렌더링
        with tab2:
            fig_m = create_plotly_candlestick_chart(
                df=results['df_m'],
                title=f"M Size: Nested in L (최근 180봉) / 고점: {fmt_chart_val(results['m_high'], results['is_usd'])} / 저점: {fmt_chart_val(results['m_low'], results['is_usd'])}",
                fib_levels=results['m_levels'],
                sma_cols=['SMA_5', 'SMA_20'],
                bb_cols=['BB_Upper', 'BB_Lower'],
                is_usd=results['is_usd']
            )
            st.plotly_chart(fig_m, use_container_width=True, key="plotly_chart_m_size")
            
        # S Size 차트 연산 및 렌더링
        with tab3:
            fig_s = create_plotly_candlestick_chart(
                df=results['df_s'],
                title=f"S Size: Nested in M (최근 30봉) / 고점: {fmt_chart_val(results['s_high'], results['is_usd'])} / 저점: {fmt_chart_val(results['s_low'], results['is_usd'])}",
                fib_levels=results['s_levels'],
                sma_cols=['SMA_5', 'SMA_20'],
                is_usd=results['is_usd']
            )
            st.plotly_chart(fig_s, use_container_width=True, key="plotly_chart_s_size")
            
        # XS Size 차트 연산 및 렌더링
        with tab4:
            fig_xs = create_plotly_candlestick_chart(
                df=results['df_xs'],
                title=f"XS Size: Nested in S (최근 14봉) / 고점: {fmt_chart_val(results['xs_high'], results['is_usd'])} / 저점: {fmt_chart_val(results['xs_low'], results['is_usd'])}",
                fib_levels=results['xs_levels'],
                is_usd=results['is_usd']
            )
            st.plotly_chart(fig_xs, use_container_width=True, key="plotly_chart_xs_size")
            
        # RSI 14 Plotly 차트 렌더링
        with tab5:
            fig_rsi = create_plotly_rsi_chart(results['df_m'])
            st.plotly_chart(fig_rsi, use_container_width=True, key="plotly_chart_rsi_14")
            
        # MACD Plotly 차트 렌더링
        with tab6:
            fig_macd = create_plotly_macd_chart(results['df_m'])
            st.plotly_chart(fig_macd, use_container_width=True, key="plotly_chart_macd")
            
        # Damus 알고리즘 시각화
        with tab7:
            if results['damus_data']:
                from damus import generate_damus_chart
                fig_damus = generate_damus_chart(results['damus_data'])
                st.pyplot(fig_damus)
            else:
                st.info("Damus 데이터를 생성할 수 없습니다.")

        # ────────────────────────────────────────────────────────────
        # 3. 상세 분석 종합 리포트 마크다운 섹션
        # ────────────────────────────────────────────────────────────
        st.write("---")
        st.subheader("📑 피보나치 중첩 분석 종합 보고서")
        st.markdown(results['report_markdown'], unsafe_allow_html=True)

        # ────────────────────────────────────────────────────────────
        # 4. 실시간 AI Q&A 인터랙티브 채팅 섹션 (안전한 컨테이너 감싸기)
        # ────────────────────────────────────────────────────────────
        st.write("---")
        st.subheader("🤖 FiboAnalyzer AI 금융비서와 실시간 대화")
        st.markdown("<p style='color:#64748B; font-size:13px;'>현재 보고서의 수치, 피보나치 지지선 및 지표 정보를 토대로 자유롭게 금융 비서에게 물어보세요.</p>", unsafe_allow_html=True)
        
        # 채팅 영역용 고유 서브컨테이너 생성 (React DOM 충돌 차단)
        chat_container = st.container(key=f"chat_section_container_{results['ticker']}")
        
        with chat_container:
            # 웰컴 메시지 부재 시 삽입
            if not st.session_state.messages:
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": f"🤖 안녕하세요! **{results['ticker']}** 분석 보고서를 완벽히 학습했습니다. 궁금한 지지 구간이나 향후 투자 전략에 대해 질문해 주세요!"
                })
                
            # 이전 메시지 렌더링
            for idx, msg in enumerate(st.session_state.messages):
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    
            # 사용자 질문 받기 (고유 키 적용)
            if user_query := st.chat_input("질문을 입력해 주세요. (예: 1차 매수 타점 가격은 원화로 얼마인가요?)", key=f"chat_input_field_{results['ticker']}"):
                # 1. 사용자 입력 메시지 표시 및 저장
                with st.chat_message("user"):
                    st.markdown(user_query)
                st.session_state.messages.append({"role": "user", "content": user_query})
                
                # 2. Gemini API 호출하여 응답 얻기
                with st.chat_message("assistant"):
                    with st.spinner("금융 비서가 분석 리포트를 확인하고 답변을 작성 중입니다..."):
                        try:
                            # 대화 이력을 ai_analyzer용 포맷으로 가공
                            chat_history = []
                            for m in st.session_state.messages[:-1]: # 현재 질문 전까지의 기록
                                role_str = "사용자" if m["role"] == "user" else "AI비서"
                                chat_history.append((role_str, m["content"]))
                                
                            # ask_gemini_qna 호출 (사용자 API 키 전달)
                            answer = ask_gemini_qna(
                                ticker=results['ticker'],
                                report_text=results['report_markdown'],
                                question=user_query,
                                chat_history=chat_history,
                                api_key=user_api_key
                            )
                            st.markdown(answer)
                        except Exception as ex:
                            answer = f"답변 호출 중 오류가 발생했습니다: {ex}"
                            st.error(answer)
                            
                st.session_state.messages.append({"role": "assistant", "content": answer})

    except Exception as e:
        st.error(f"❌ 데이터 분석 중 오류가 발생했습니다.")
        st.code(traceback.format_exc())
