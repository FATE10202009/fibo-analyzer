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
import datetime


# 프로젝트 핵심 분석 모듈 임포트
from search import search_ticker_by_name
from analysis import (
    fmt_price, fmt_range, fmt_large_value, fmt_chart_val,
    get_fib_levels, get_entry_signal, get_t_signal, get_adjacent_l_levels,
    calculate_composite_score, score_to_label, make_fib_markdown_table,
    generate_future_outlook, format_fundamental_report,
    generate_fibonacci_scenario_md, generate_news_impact_md,
    generate_strategy_and_buy_price_md
)
from damus import get_damus_data, generate_damus_report_md
from ai_analyzer import ask_gemini_qna
from notifier import alert_manager
import google_finance as gf
from virtual_trading import virtual_trading_manager

# 텔레그램 목표가 모니터링 스레드 가동
if not alert_manager.running:
    alert_manager.start_monitor()

# 가상 매매 24시간 매칭 엔진 가동
virtual_trading_manager.start_matching_engine()


@st.cache_data(ttl=20)
def get_current_price_cached(ticker):
    try:
        ticker_obj = yf.Ticker(ticker)
        if hasattr(ticker_obj, 'fast_info') and 'lastPrice' in ticker_obj.fast_info:
            return float(ticker_obj.fast_info['lastPrice'])
        
        hist = ticker_obj.history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception as e:
        print(f"[Cache Price] 가격 조회 실패 ({ticker}): {e}")
    return None


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
LAST_USER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_virtual_user.txt")

def load_favorites():
    # 1. URL 쿼리 파라미터에서 먼저 즐겨찾기 복원 시도
    if "favs" in st.query_params:
        try:
            favs_raw = st.query_params["favs"]
            if favs_raw:
                parsed = []
                for item in favs_raw.split("|"):
                    if ":" in item:
                        name, ticker = item.split(":", 1)
                        parsed.append((name.strip().upper(), ticker.strip().upper()))
                if parsed:
                    return parsed
        except Exception as e:
            print(f"[Query Params Load Error] {e}")

    # 2. 쿼리 파라미터에 없으면 서버의 로컬 파일에서 시도
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
        cleaned_favs.append((cleaned_name, val.upper()))
    return cleaned_favs

def save_favorites(favs):
    # [2번 방식 개량 - URL 쿼리 파라미터 활용]
    # 다른 사용자에게 영향을 주지 않고, 서버가 재배포(업로드)로 리셋되어도 내 즐겨찾기가 유지되도록
    # 브라우저 URL의 쿼리 파라미터(st.query_params)에 즐겨찾기를 저장합니다.
    try:
        favs_str = "|".join([f"{name}:{ticker}" for name, ticker in favs])
        st.query_params["favs"] = favs_str
    except Exception as e:
        print(f"[Query Params Save Error] {e}")
    
    # 로컬 파일에도 동시에 저장하여 브라우저 재접속(URL 파라미터 없음) 시 복구되도록 합니다.
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[Favorites File Save Error] {e}")


# AI 추천 자산 정의
AI_RECOMMENDED = [
    ("NVDA (엔비디아)", "NVDA", "AI 생태계 하드웨어 시장 독점 및 실적 모멘텀"),
    ("SOL (솔라나)", "SOL-USD", "알트코인 트랜잭션 증가 및 빠른 단기 반등 모멘텀"),
    ("AAPL (애플)", "AAPL", "디바이스 탑재 온디바이스 AI 시장의 최대 수혜 전망"),
    ("005930 (삼성전자)", "005930.KS", "반도체 턴어라운드 및 역사적 피보나치 바닥권"),
    ("TSLA (테슬라)", "TSLA", "자율주행 및 로보택시 중장기 성장성 부각")
]

# ────────────────────────────────────────────────────────────
# 📊 즐겨찾기 실시간 시세 가로 전광판 데이터 수집 (Marquee)
# ────────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def get_marquee_prices(favorites, data_source="google"):
    tickers = [f[1] for f in favorites]
    if not tickers:
        return "📊 즐겨찾기에 자산을 등록해 주세요."
    try:
        # 실시간 적용 환율 조회
        usd_krw_rate = 1380.0
        try:
            if data_source == "google":
                rate_df = gf.download_google_finance("USDKRW=X")
                if rate_df.empty:
                    rate_df = yf.download("USDKRW=X", period="5d", interval="1d", progress=False)
            else:
                rate_df = yf.download("USDKRW=X", period="5d", interval="1d", progress=False)
                
            if not rate_df.empty:
                if rate_df.columns.nlevels > 1:
                    rate_df.columns = rate_df.columns.droplevel(1)
                rate_df = rate_df.dropna(subset=['Close'])
                if not rate_df.empty:
                    usd_krw_rate = float(rate_df['Close'].iloc[-1])
        except Exception as e:
            print(f"[Marquee] 환율 로드 실패: {e}")

        # 개별 티커 시세 수집
        marquee_items = []
        for name, ticker in favorites:
            try:
                df = pd.DataFrame()
                if data_source == "google":
                    df = gf.download_google_finance(ticker)
                    if df.empty:
                        yf_ticker = ticker
                        if ":" in ticker:
                            yf_ticker = ticker.split(":")[0]
                        df = yf.download(yf_ticker, period="5d", interval="1d", progress=False)
                else:
                    yf_ticker = ticker
                    if ":" in ticker:
                        yf_ticker = ticker.split(":")[0]
                    df = yf.download(yf_ticker, period="5d", interval="1d", progress=False)
                    
                if df.empty:
                    continue
                    
                if df.columns.nlevels > 1:
                    df.columns = df.columns.droplevel(1)
                df = df.dropna(subset=['Close'])
                
                if df.empty or len(df) < 2:
                    continue
                close_today = float(df['Close'].iloc[-1])
                close_yesterday = float(df['Close'].iloc[-2])
                diff = close_today - close_yesterday
                pct = (diff / close_yesterday) * 100
                
                is_usd = not (ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'))
                price_str = fmt_price(close_today, usd_krw_rate, is_usd)
                
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
# 지정가 매수/매도 감시 및 체결 핵심 엔진 (Mock Limit Order Engine)
# ────────────────────────────────────────────────────────────
def process_limit_orders(current_ticker=None, current_price=None):
    # 백그라운드 스레드 외에도, 사용자 웹 렌더링 시 즉각적으로 체결 여부를 판단하여 반응성을 높입니다.
    try:
        virtual_trading_manager.process_all_users()
    except Exception as e:
        print(f"[Limit Order Process Error] {e}")


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

# 가상 매매(모의 투자) 사용자 ID 초기화
if "virtual_user_id" not in st.session_state:
    if "user" in st.query_params:
        st.session_state.virtual_user_id = st.query_params["user"]
    else:
        # 로컬 파일에서 마지막으로 사용된 닉네임 로드 시도
        last_user = "guest"
        if os.path.exists(LAST_USER_FILE):
            try:
                with open(LAST_USER_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        last_user = content
            except:
                pass
        st.session_state.virtual_user_id = last_user


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
    
    # 즐겨찾기 리스트
    st.write("⭐ 즐겨찾기 빠른 로드")
    for idx, (name, val) in enumerate(st.session_state.favorites):
        # 자산 변경 클릭 시 세션 상태를 변경하고 리프레시하여 DOM 충돌 방지
        if st.button(name, key=f"fav_btn_{idx}_{val}", use_container_width=True):
            st.session_state.search_ticker = val
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
    
    # 피보나치 중첩 모드 선택
    nest_mode = st.selectbox(
        "피보나치 중첩 모드 선택",
        options=["time", "price"],
        format_func=lambda x: "시간 주기 기반 (기존)" if x == "time" else "가격 레벨 기반 (수학적 중첩)",
        help="시간 주기에 따른 최저/최고점을 기준으로 분석할지, 장기 L 레벨 사이에 갇힌 영역을 수학적으로 쪼개어 중첩할지 선택합니다."
    )
    
    # 데이터 소스 선택
    data_source = st.selectbox(
        "📊 데이터 소스 선택",
        options=["google", "yahoo"],
        format_func=lambda x: "Google Finance (권장)" if x == "google" else "Yahoo Finance",
        help="데이터 수집에 사용할 금융 데이터 소스를 선택합니다."
    )
    

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
                get_marquee_prices.clear()
                st.rerun()
            
    if st.button("즐겨찾기 전체 초기화"):
        if os.path.exists(FAVORITES_FILE):
            try:
                os.remove(FAVORITES_FILE)
            except:
                pass
        if "favs" in st.query_params:
            try:
                del st.query_params["favs"]
            except:
                pass
        st.session_state.favorites = [
            ("BTC", "BTC-USD"),
            ("XRP", "XRP-USD"),
            ("OTLK", "OTLK"),
            ("SMR", "SMR")
        ]
        get_marquee_prices.clear()
        st.success("즐겨찾기가 복구되었습니다.")
        st.rerun()

    # ────────────────────────────────────────────────────────────
    # 🚨 텔레그램 알림 설정
    # ────────────────────────────────────────────────────────────
    st.write("---")
    with st.expander("🚨 텔레그램 알림 설정"):
        st.subheader("🔑 텔레그램 연동 설정")
        curr_token, curr_chat_id = alert_manager.get_token_and_chat_id()
        
        tg_token = st.text_input(
            "텔레그램 봇 토큰",
            value=curr_token,
            type="password",
            placeholder="Bot Token 입력",
            key="tg_token_input"
        )
        tg_chat_id = st.text_input(
            "텔레그램 Chat ID",
            value=curr_chat_id,
            placeholder="Chat ID 입력",
            key="tg_chat_id_input"
        )
        if st.button("연동 설정 저장", key="save_tg_config_btn"):
            alert_manager.set_telegram_config(tg_token.strip(), tg_chat_id.strip())
            st.success("텔레그램 연동 설정이 저장되었습니다.")
            st.rerun()
            
        st.write("---")
        st.subheader("🎯 피보나치 알림 설정")
        current_ticker = st.session_state.search_ticker
        
        # 피보나치 레벨 알림 토글
        damus_tickers = alert_manager.get_damus_alert_tickers()
        is_damus_enabled = current_ticker in damus_tickers
        
        checked = st.checkbox(
            f"{current_ticker} 피보나치 레벨 알림 받기",
            value=is_damus_enabled,
            key="damus_alert_checkbox"
        )
        if checked != is_damus_enabled:
            alert_manager.set_damus_alert_ticker(current_ticker, checked)
            if not checked:
                # 모니터 중인 티커와 같으면 중지
                if getattr(alert_manager, '_damus_ticker', None) == current_ticker:
                    alert_manager.stop_damus_monitor()
            st.success(f"{current_ticker} 피보나치 알림 설정이 변경되었습니다.")
            st.rerun()
            
        st.write("---")
        st.subheader("🔔 지정가 알림 등록")
        target_p = st.number_input(
            "목표 가격",
            value=0.0,
            step=0.01,
            key="alert_target_price_input"
        )
        cond = st.selectbox(
            "돌파 조건",
            options=["above", "below"],
            format_func=lambda x: "상향 돌파 (>=)" if x == "above" else "하향 돌파 (<=)",
            key="alert_condition_select"
        )
        if st.button("지정가 알림 추가", key="add_price_alert_btn"):
            if target_p > 0:
                alert_manager.add_alert(current_ticker, target_p, cond)
                st.success(f"{current_ticker} 지정가 {target_p} 알림이 추가되었습니다.")
                st.rerun()
            else:
                st.error("올바른 목표 가격을 입력해 주세요.")
                
        st.write("---")
        st.subheader("📋 현재 등록된 알림 리스트")
        alerts = alert_manager.get_all_alerts()
        if not alerts:
            st.info("등록된 지정가 알림이 없습니다.")
        else:
            for a in alerts:
                # a: {"id": "xxx", "ticker": "xxx", "target_price": xxx, "condition": "xxx", "is_active": True/False}
                ticker_lbl = a["ticker"]
                cond_lbl = "▲" if a["condition"] == "above" else "▼"
                price_lbl = f"{a['target_price']:,.2f}" if not (ticker_lbl.upper().endswith(".KS") or ticker_lbl.upper().endswith(".KQ")) else f"{a['target_price']:,.0f}"
                active_lbl = "" if a.get("is_active", True) else " (비활성)"
                
                col_a, col_b = st.columns([0.85, 0.15])
                col_a.markdown(f"**{ticker_lbl}** {cond_lbl} {price_lbl}{active_lbl}")
                if col_b.button("❌", key=f"del_alert_{a['id']}", help="알림 삭제"):
                    alert_manager.remove_alert(a["id"])
                    st.success("지정가 알림이 삭제되었습니다.")
                    st.rerun()


# ────────────────────────────────────────────────────────────
# 자산 전환에 따른 채팅 내역 초기화 (React DOM NotFoundError 방지 핵심)
# ────────────────────────────────────────────────────────────
if st.session_state.last_analyzed_ticker != st.session_state.search_ticker:
    st.session_state.last_analyzed_ticker = st.session_state.search_ticker
    # 자산 전환 시 채팅 초기화하여 DOM 구조 꼬임 방지
    st.session_state.messages = []



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
def fetch_and_analyze_data(query, market, api_key=None, nest_mode="time", data_source="google"):
    ticker = search_ticker_by_name(query, market)
    if ticker is None:
        raise ValueError(f"'{query}'에 해당하는 자산을 찾지 못했습니다. 올바른 티커를 입력해 주세요.")

    yf_ticker = ticker
    if ":" in ticker:
        yf_ticker = ticker.split(":")[0]

    # L Size (All-Time) 분석을 위해 과거 전체 일봉 데이터(yfinance)를 우선적으로 가져옵니다.
    try:
        df_all = yf.download(yf_ticker, period='max', interval='1d')
    except Exception as e:
        print(f"[yfinance download Error] {e}")

    # yfinance 다운로드 실패 시 Google Finance 과거 데이터로 대체 (단, 최근 30여일 데이터만 제공됨)
    if df_all.empty:
        try:
            df_all = gf.download_google_finance(ticker)
        except Exception as e:
            print(f"[GoogleFinance download Error] {e}")

    if df_all.empty:
        raise ValueError(f"'{ticker}' 데이터가 존재하지 않거나 가져오는 데 실패했습니다.")

    # 1. 데이터 소스 선택에 따른 실시간 정보 수집
    if data_source == "google":
        try:
            info = gf.get_ticker_info(ticker)
            news_list = gf.get_ticker_news(ticker)
            # Google Finance에서 제공하는 실시간 현재가 반영
            if info.get('currentPrice') is not None:
                current_price = info['currentPrice']
                df_all.loc[df_all.index[-1], 'Close'] = current_price
                if current_price > df_all.loc[df_all.index[-1], 'High']:
                    df_all.loc[df_all.index[-1], 'High'] = current_price
                if current_price < df_all.loc[df_all.index[-1], 'Low']:
                    df_all.loc[df_all.index[-1], 'Low'] = current_price
        except Exception as e:
            print(f"[GoogleFinance Info/News Error] {e}")
            try:
                t_obj = yf.Ticker(yf_ticker)
                info = t_obj.info
                news_list = t_obj.news
            except:
                pass
    else:
        try:
            t_obj = yf.Ticker(yf_ticker)
            info = t_obj.info
            try:
                news_list = t_obj.news
            except Exception as ne:
                print(f"[Warning] Ticker.news 로드 실패: {ne}")
        except Exception as e:
            print(f"[Warning] Ticker.info 로드 실패: {e}")

    # MultiIndex 대응 컬럼 평탄화
    if df_all.columns.nlevels > 1:
        df_all.columns = df_all.columns.droplevel(1)

    # 결측치(NaN)가 포함된 행 제거 (주로 불완전한 당일 거래일 데이터 유입 방지)
    df_all = df_all.dropna(subset=['Close', 'High', 'Low', 'Open'])

    # 통화 판단
    is_usd = True
    if ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'):
        is_usd = False

    # 실시간 적용 환율
    rate = 1.0
    if is_usd:
        try:
            rate_df = pd.DataFrame()
            if data_source == "google":
                rate_df = gf.download_google_finance("USDKRW=X")
                if rate_df.empty:
                    rate_df = yf.download("USDKRW=X", period="1d")
            else:
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
    df_s = df_all.tail(30).copy()
    df_xs = df_all.tail(7).copy()

    if nest_mode == "price":
        # 가격 레벨 기반 수학적 중첩 (Fractal Price Nesting)
        m_high, m_low = get_adjacent_l_levels(current_price, l_levels)
        m_levels = get_fib_levels(m_high, m_low)
        m_signal = get_entry_signal(current_price, m_levels, current_rsi)

        s_high, s_low = get_adjacent_l_levels(current_price, m_levels)
        s_levels = get_fib_levels(s_high, s_low)
        s_signal = get_entry_signal(current_price, s_levels, current_rsi)

        xs_high, xs_low = get_adjacent_l_levels(current_price, s_levels)
        xs_levels = get_fib_levels(xs_high, xs_low)
        xs_signal = get_entry_signal(current_price, xs_levels, current_rsi)
    else:
        # 기존 시간 주기 기반 중첩 (Time-based Multi-Timeframe)
        m_low_idx = df_m['Low'].idxmin()
        m_low = float(df_m['Low'].min())
        m_high = float(df_m.loc[m_low_idx:]['High'].max())
        m_levels = get_fib_levels(m_high, m_low)
        m_signal = get_entry_signal(current_price, m_levels, current_rsi)

        s_low_idx = df_s['Low'].idxmin()
        s_low = float(df_s['Low'].min())
        s_high = float(df_s.loc[s_low_idx:]['High'].max())
        s_levels = get_fib_levels(s_high, s_low)
        s_signal = get_entry_signal(current_price, s_levels, current_rsi)

        xs_low_idx = df_xs['Low'].idxmin()
        xs_low = float(df_xs['Low'].min())
        xs_high = float(df_xs.loc[xs_low_idx:]['High'].max())
        xs_levels = get_fib_levels(xs_high, xs_low)
        xs_signal = get_entry_signal(current_price, xs_levels, current_rsi)

    # T Size (Yesterday's Range)
    if len(df_all) >= 2:
        t_high = float(df_all['High'].iloc[-2])
        t_low = float(df_all['Low'].iloc[-2])
    else:
        t_high = float(df_all['High'].iloc[-1])
        t_low = float(df_all['Low'].iloc[-1])
    t_levels = get_fib_levels(t_high, t_low)
    t_signal = get_t_signal(current_price, t_levels, current_rsi)

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

    # 다중 타임프레임 지지선 수집 및 최적 DCA 가격 연산
    candidates = []
    # L Size (All-Time)
    for k in ['0.764 (1차 조정선)', '0.618 (첫 주요 지지선)', '0.500 (절반선)', '0.382 (두 번째 지지선)', '0.236 (최종 지지선)', '0.000 (저점)']:
        if k in l_levels:
            candidates.append((l_levels[k], 'L ' + k.split(' ')[0]))
    # M Size (Nested L)
    for k in ['0.764 (1차 조정선)', '0.618 (첫 주요 지지선)', '0.500 (절반선)', '0.382 (두 번째 지지선)', '0.000 (저점)']:
        if k in m_levels:
            candidates.append((m_levels[k], 'M ' + k.split(' ')[0]))
    # S Size (Nested M)
    for k in ['0.618 (첫 주요 지지선)', '0.500 (절반선)', '0.382 (두 번째 지지선)', '0.000 (저점)']:
        if k in s_levels:
            candidates.append((s_levels[k], 'S ' + k.split(' ')[0]))
    # XS Size (Nested S)
    for k in ['0.618 (첫 주요 지지선)', '0.382 (두 번째 지지선)', '0.000 (저점)']:
        if k in xs_levels:
            candidates.append((xs_levels[k], 'XS ' + k.split(' ')[0]))

    # 현재가보다 낮은 지지선만 유효한 매수 후보로 간주 (마진 0.5% 적용)
    valid_candidates = [c for c in candidates if c[0] < current_price * 0.995]
    
    if not valid_candidates:
        best_buy = current_price
        best_buy_desc = "현재가 기준 (하단 지지선 없음)"
    else:
        # 지지선 가격 기준 내림차순 정렬 (현재가와 가장 가까운 지지선이 맨 앞)
        valid_candidates.sort(key=lambda x: x[0], reverse=True)
        
        # 추세 강도(종합 점수)에 따라 추천 지지선 깊이 차별화
        if composite_score >= 75:
            # 강한 상승 추세: 가장 가까운 1차 지지선 추천
            best_buy, best_buy_source = valid_candidates[0]
            best_buy_desc = f"{best_buy_source} 지지선 기준 (강세 추세)"
        elif composite_score >= 50:
            # 보통 추세: 조금 더 아래의 2차 지지선 추천
            idx = min(1, len(valid_candidates) - 1)
            best_buy, best_buy_source = valid_candidates[idx]
            best_buy_desc = f"{best_buy_source} 지지선 기준 (보통 추세)"
        else:
            # 약세/하락 추세: 깊은 3차 지지선 또는 장기 L 지지선 추천
            l_supports = [c for c in valid_candidates if c[1].startswith('L ')]
            if l_supports:
                best_buy, best_buy_source = l_supports[0]
            else:
                idx = min(2, len(valid_candidates) - 1)
                best_buy, best_buy_source = valid_candidates[idx]
            best_buy_desc = f"{best_buy_source} 지지선 기준 (약세 조정대응)"

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

- **분석 기준**: 역사적 대파동(L), 중기 파동(M), 단기 변곡(S), 초단기 극세(XS) 중첩 및 어제 하루 범위 돌파(T)
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
| **T Size (Yesterday)** | 어제 하루 범위 | {fmt_price(t_high, rate, is_usd)} | {fmt_price(t_low, rate, is_usd)} | **{t_signal}** |

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

### ⏳ T Size (Yesterday) 상세 레벨
{make_fib_markdown_table(t_levels, current_price, rate, is_usd)}

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
        'asset_name': info.get('longName') or info.get('shortName') or info.get('name') or ticker,
        'current_price': current_price,
        'current_rsi': current_rsi,
        'composite_score': composite_score,
        'score_label': score_label,
        'best_buy_str': best_buy_str,
        'best_buy_desc': best_buy_desc,
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
        't_levels': t_levels,
        'l_high': l_high, 'l_low': l_low,
        'm_high': m_high, 'm_low': m_low,
        's_high': s_high, 's_low': s_low,
        'xs_high': xs_high, 'xs_low': xs_low,
        't_high': t_high, 't_low': t_low,
        't_signal': t_signal,
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
        {get_marquee_prices(st.session_state.favorites, data_source=data_source)}
    </marquee>
</div>
"""
st.markdown(marquee_html, unsafe_allow_html=True)

# 실행 및 데이터 표시 (React DOM Crash 방지를 위해 하나의 전체 컨테이너 내에서 안전하게 가동)
main_container = st.container(key="fibo_dashboard_main_container")

with main_container:
    try:
        with st.spinner("🎯 실시간 시장 정보 및 보조지표를 연산하는 중입니다..."):
            results = fetch_and_analyze_data(st.session_state.search_ticker, market_opt, api_key=user_api_key, nest_mode=nest_mode, data_source=data_source)
            process_limit_orders(results['ticker'], results['current_price'])
            
            # 피보나치 실시간 알림 스레드 시작/중지 자동 제어
            current_damus_tickers = alert_manager.get_damus_alert_tickers()
            if results['ticker'] in current_damus_tickers:
                token, chat_id = alert_manager.get_token_and_chat_id()
                if token and chat_id:
                    if getattr(alert_manager, '_damus_ticker', None) != results['ticker'] or not alert_manager._damus_running:
                        alert_manager.start_damus_monitor(results['ticker'], results['is_usd'], check_interval_sec=60)
            else:
                if getattr(alert_manager, '_damus_ticker', None) == results['ticker'] and alert_manager._damus_running:
                    alert_manager.stop_damus_monitor()
            
            # 검색 및 불러온 자산 검증 카드 및 즐겨찾기 토글 버튼 표시
            is_favorited = any(f[1].upper() == results['ticker'].upper() for f in st.session_state.favorites)
            
            with st.container():
                col_info, col_star = st.columns([0.75, 0.25], vertical_alignment="center")
                with col_info:
                    st.markdown(f"""
                    <div style="background: rgba(30, 41, 59, 0.45); border-left: 5px solid #3B82F6; border-radius: 12px; padding: 16px 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.25);">
                        <div style="color: #94A3B8; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">🔍 분석 대상 자산 검증 (입력된 검색어: "{st.session_state.search_ticker}")</div>
                        <div style="display: flex; align-items: baseline; margin-top: 5px;">
                            <span style="color: #FFFFFF; font-size: 22px; font-weight: 700;">{results['asset_name']}</span>
                            <span style="color: #38BDF8; font-size: 16px; font-weight: 600; margin-left: 10px;">({results['ticker']})</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_star:
                    star_icon = "⭐" if is_favorited else "☆"
                    star_help = "즐겨찾기 해제" if is_favorited else "즐겨찾기 등록"
                    if st.button(f"{star_icon} {star_help}", key="toggle_favorite_btn", use_container_width=True):
                        if is_favorited:
                            st.session_state.favorites = [f for f in st.session_state.favorites if f[1].upper() != results['ticker'].upper()]
                            save_favorites(st.session_state.favorites)
                            get_marquee_prices.clear()
                            st.toast(f"❌ {results['asset_name']} 즐겨찾기 해제 완료!", icon="⭐")
                            st.rerun()
                        else:
                            short_name = results['asset_name'].split(" ")[0]
                            if len(short_name) > 8:
                                short_name = short_name[:8]
                            st.session_state.favorites.append((short_name, results['ticker']))
                            save_favorites(st.session_state.favorites)
                            get_marquee_prices.clear()
                            st.toast(f"⭐ {results['asset_name']} 즐겨찾기 등록 완료!", icon="⭐")
                            st.rerun()
            st.write("")
            
        # ────────────────────────────────────────────────────────────
        # 1. 4구역 KPI 핵심 카드 섹션
        # ────────────────────────────────────────────────────────────
        left_col, right_col = st.columns([0.62, 0.38], gap="medium")
        
        with left_col:
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
                    <div class="kpi-desc">{results.get('best_buy_desc', '역사적 피보나치 기준')}</div>
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
            
            # 탭 렌더링 (RSI 14, MACD, Damus, 및 가상 매매 탭 추가)
            tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
                "🌐 All-Time (L)", "📅 180일 스윙 (M)", "📆 30일 단기 (S)", "⏰ 7일 초단기 (XS)", "💜 RSI 14", "💛 MACD", "🥔 Damus 알고리즘"
            ])
            
            # L Size 차트 연산 및 렌더링
            with tab1:
                fig_l = create_plotly_candlestick_chart(
                    df=results['df_all'].copy(),
                    title=f"L Size: All-Time / 고점: {fmt_chart_val(results['l_high'], results['is_usd'])} / 저점: {fmt_chart_val(results['l_low'], results['is_usd'])}",
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
                    st.plotly_chart(fig_damus, use_container_width=True, key="plotly_chart_damus_alg")
                else:
                    st.info("Damus 데이터를 생성할 수 없습니다.")
    
            # 가상 매매 탭 렌더링
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


        with right_col:
            # 💸 실시간 가상 매매 (Mock Trading) 패널 상시 노출
            st.markdown("""
            <div style="background: rgba(30, 30, 40, 0.45); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);">
                <h3 style="color:#60A5FA; margin-top:0px; margin-bottom:5px; font-size: 20px;">💸 실시간 가상 매매 (Mock Trading)</h3>
                <p style="color:#94A3B8; font-size:12px; margin-bottom:0px;">포트폴리오 통합 조회 및 원클릭 매매 패널</p>
            </div>
            """, unsafe_allow_html=True)
            
            # 사용자 닉네임 입력 추가
            user_id_input = st.text_input(
                "👤 가상 매매 고유 닉네임 (영문/숫자/하이픈)", 
                value=st.session_state.virtual_user_id, 
                key="virtual_user_id_input_widget",
                help="나만의 고유한 닉네임을 설정하면 컴퓨터를 꺼두어도 주문이 유지되며, 재접속 시 이전 내역이 그대로 복구됩니다."
            )

            # 입력한 닉네임 세션 및 URL 파라미터 동기화
            if user_id_input != st.session_state.virtual_user_id:
                st.session_state.virtual_user_id = user_id_input
                st.query_params["user"] = user_id_input
                # 로컬 파일에 마지막 닉네임 저장
                try:
                    with open(LAST_USER_FILE, "w", encoding="utf-8") as f:
                        f.write(user_id_input)
                except Exception as e:
                    print(f"[Last User Save Error] {e}")
                st.rerun()

            trading_user_id = st.session_state.virtual_user_id
            user_data = virtual_trading_manager.load_user_data(trading_user_id)

            usd_cash = user_data["usd_cash"]
            krw_cash = user_data["krw_cash"]
            portfolio = user_data["portfolio"]
            history = user_data["history"]
            limit_orders = user_data["limit_orders"]

            # 보유 현금량 정보 표시
            col_cash1, col_cash2 = st.columns(2)
            col_cash1.metric("💵 가상 USD 잔액", f"${usd_cash:,.2f}")
            col_cash2.metric("💵 가상 KRW 잔액", f"₩{krw_cash:,.0f}")

            # 📦 종합 보유 자산 현황
            st.markdown("#### 📦 종합 보유 자산 현황")
            if not portfolio:
                st.info("현재 보유 중인 가상 자산이 없습니다.")
            else:
                portfolio_rows = []
                for held_ticker, holding_item in portfolio.items():
                    qty = holding_item["qty"]
                    avg_p = holding_item["avg_price"]
                    held_is_usd = holding_item.get("is_usd", True)
                    
                    cur_p = get_current_price_cached(held_ticker)
                    if cur_p is None:
                        cur_p = avg_p # fallback
                        
                    buy_amt = qty * avg_p
                    val_amt = qty * cur_p
                    pnl_amt = val_amt - buy_amt
                    pct = (pnl_amt / buy_amt * 100) if buy_amt > 0 else 0.0
                    
                    symbol = "$" if held_is_usd else "₩"
                    
                    portfolio_rows.append({
                        "자산": held_ticker,
                        "보유 수량": f"{qty:,.4f}",
                        "매수 평단": f"{symbol}{avg_p:,.2f}" if held_is_usd else f"{symbol}{avg_p:,.0f}",
                        "현재가": f"{symbol}{cur_p:,.2f}" if held_is_usd else f"{symbol}{cur_p:,.0f}",
                        "평가 금액": f"{symbol}{val_amt:,.2f}" if held_is_usd else f"{symbol}{val_amt:,.0f}",
                        "평가 손익 (수익률)": f"{symbol}{pnl_amt:+,.2f} ({pct:+.2f}%)" if held_is_usd else f"{symbol}{pnl_amt:+,.0f} ({pct:+.2f}%)"
                    })
                
                df_portfolio = pd.DataFrame(portfolio_rows)
                st.dataframe(df_portfolio, use_container_width=True, hide_index=True)

            # ⚡ 가상 거래 주문 설정
            st.markdown("#### ⚡ 가상 거래 주문 설정")
            
            # 주문 대상 자산 선택 리스트 구성
            asset_opts = [results['ticker']]
            for name, fav_t in st.session_state.favorites:
                if fav_t not in asset_opts:
                    asset_opts.append(fav_t)
            for port_t in portfolio.keys():
                if port_t not in asset_opts:
                    asset_opts.append(port_t)
                    
            selected_order_ticker = st.selectbox(
                "주문 자산 선택",
                options=asset_opts,
                index=0,
                key="virtual_order_ticker_select_box",
                help="기본적으로 현재 분석 중인 자산이 선택되어 있으며, 보유 중이거나 즐겨찾기인 다른 자산도 선택할 수 있습니다."
            )
            
            # 선택된 자산에 대한 현재가 및 화폐 단위 판단
            if selected_order_ticker == results['ticker']:
                order_price = results['current_price']
                order_is_usd = results['is_usd']
            else:
                order_price = get_current_price_cached(selected_order_ticker)
                if order_price is None:
                    # 포트폴리오에 평단가가 있으면 그것으로 대체
                    order_price = portfolio.get(selected_order_ticker, {}).get("avg_price", 0.0)
                order_is_usd = not (selected_order_ticker.upper().endswith('.KS') or selected_order_ticker.upper().endswith('.KQ'))
                
            currency_symbol = "$" if order_is_usd else "₩"
            
            if order_price == 0.0:
                st.warning("⚠️ 선택한 자산의 실시간 시세를 가져올 수 없어 주문을 진행할 수 없습니다.")
            else:
                st.markdown(f"**{selected_order_ticker}** 현재 시세: **{currency_symbol}{order_price:,.2f}**" if order_is_usd else f"**{selected_order_ticker}** 현재 시세: **{currency_symbol}{order_price:,.0f}**")
                
                order_type = st.radio(
                    "주문 유형", 
                    ["시장가 (즉시 체결)", "지정가 (예약 체결)"], 
                    horizontal=True, 
                    key="virtual_order_type_select_sidebar"
                )
                
                # 주문 대상 자산에 대한 보유 수량 정보
                selected_holding = portfolio.get(selected_order_ticker, {"qty": 0.0, "avg_price": 0.0, "is_usd": order_is_usd})
                held_qty = selected_holding["qty"]
                
                col_tr_buy, col_tr_sell = st.columns(2)
                
                with col_tr_buy:
                    st.markdown("**🟢 매수 주문 (BUY)**")
                    max_buy_cash = usd_cash if order_is_usd else krw_cash
                    
                    if order_type == "지정가 (예약 체결)":
                        limit_buy_price = st.number_input(
                            "매수 지정가 입력", 
                            min_value=0.0, 
                            value=order_price, 
                            step=order_price/100, 
                            key="limit_buy_price_input_col"
                        )
                        buy_amount = st.number_input(
                            "매수 금액 입력", 
                            min_value=0.0, 
                            max_value=float(max_buy_cash), 
                            value=0.0, 
                            step=100.0 if order_is_usd else 100000.0, 
                            key="buy_amount_input_limit_col"
                        )
                        exp_qty = buy_amount / limit_buy_price if limit_buy_price > 0 else 0.0
                        st.caption(f"예상 매수: **{exp_qty:,.4f} {selected_order_ticker.split('-')[0]}**")
                        
                        if st.button("🔴 지정가 매수 예약", key="execute_limit_buy_btn_col", use_container_width=True):
                            if buy_amount <= 0:
                                st.error("매수 금액을 입력해 주세요.")
                            elif limit_buy_price <= 0:
                                st.error("올바른 지정가 가격을 입력해 주세요.")
                            elif buy_amount > max_buy_cash:
                                st.error("잔액이 부족합니다.")
                            else:
                                success, msg = virtual_trading_manager.add_limit_buy(trading_user_id, selected_order_ticker, limit_buy_price, buy_amount, order_is_usd)
                                if success:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                    else:
                        buy_amount = st.number_input(
                            "매수 금액 입력", 
                            min_value=0.0, 
                            max_value=float(max_buy_cash), 
                            value=0.0, 
                            step=100.0 if order_is_usd else 100000.0, 
                            key="buy_amount_input_market_col"
                        )
                        exp_qty = buy_amount / order_price if order_price > 0 else 0.0
                        st.caption(f"예상 매수: **{exp_qty:,.4f} {selected_order_ticker.split('-')[0]}**")
                        
                        if st.button("🔴 시장가 매수 실행", key="execute_market_buy_btn_col", use_container_width=True):
                            if buy_amount <= 0:
                                st.error("매수 금액을 입력해 주세요.")
                            elif buy_amount > max_buy_cash:
                                st.error("잔액이 부족합니다.")
                            else:
                                success, msg = virtual_trading_manager.execute_market_buy(trading_user_id, selected_order_ticker, buy_amount, order_price, order_is_usd)
                                if success:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                                    
                with col_tr_sell:
                    st.markdown("**🔴 매도 주문 (SELL)**")
                    
                    if order_type == "지정가 (예약 체결)":
                        limit_sell_price = st.number_input(
                            "매도 지정가 입력", 
                            min_value=0.0, 
                            value=order_price, 
                            step=order_price/100, 
                            key="limit_sell_price_input_col"
                        )
                        sell_qty = st.number_input(
                            "매도 수량 입력", 
                            min_value=0.0, 
                            max_value=float(held_qty), 
                            value=0.0, 
                            step=held_qty/10 if held_qty > 0 else 0.1, 
                            key="sell_qty_input_limit_col"
                        )
                        exp_recv = sell_qty * limit_sell_price
                        st.caption(f"예상 정산: **{currency_symbol}{exp_recv:,.2f}**" if order_is_usd else f"예상 정산: **{currency_symbol}{exp_recv:,.0f}**")
                        
                        if st.button("🟢 지정가 매도 예약", key="execute_limit_sell_btn_col", use_container_width=True):
                            if sell_qty <= 0:
                                st.error("매도 수량을 입력해 주세요.")
                            elif limit_sell_price <= 0:
                                st.error("올바른 지정가 가격을 입력해 주세요.")
                            elif sell_qty > held_qty:
                                st.error("보유 수량이 부족합니다.")
                            else:
                                success, msg = virtual_trading_manager.add_limit_sell(trading_user_id, selected_order_ticker, limit_sell_price, sell_qty, order_is_usd)
                                if success:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                    else:
                        sell_qty = st.number_input(
                            "매도 수량 입력", 
                            min_value=0.0, 
                            max_value=float(held_qty), 
                            value=0.0, 
                            step=held_qty/10 if held_qty > 0 else 0.1, 
                            key="sell_qty_input_market_col"
                        )
                        exp_recv = sell_qty * order_price
                        st.caption(f"예상 정산: **{currency_symbol}{exp_recv:,.2f}**" if order_is_usd else f"예상 정산: **{currency_symbol}{exp_recv:,.0f}**")
                        
                        if st.button("🟢 시장가 매도 실행", key="execute_market_sell_btn_col", use_container_width=True):
                            if sell_qty <= 0:
                                st.error("매도 수량을 입력해 주세요.")
                            elif sell_qty > held_qty:
                                st.error("보유 수량이 부족합니다.")
                            else:
                                success, msg = virtual_trading_manager.execute_market_sell(trading_user_id, selected_order_ticker, sell_qty, order_price, order_is_usd)
                                if success:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)

            # ⏳ 통합 대기 중인 지정가 주문 목록 (전체 자산)
            st.markdown("#### ⏳ 대기 중인 지정가 주문 목록")
            if not limit_orders:
                st.caption("대기 중인 지정가 주문이 없습니다.")
            else:
                for idx, order in enumerate(limit_orders):
                    o_curr = "$" if order["is_usd"] else "₩"
                    col_o1, col_o2 = st.columns([0.75, 0.25])
                    with col_o1:
                        st.markdown(f"📌 **{order['ticker']}** | {order['type'].split('(')[0].strip()}\n* 목표가: {o_curr}{order['target_price']:,.2f} | 수량: {order['qty']:,.4f}")
                    with col_o2:
                        if st.button("취소 ❌", key=f"cancel_order_col_{order['id']}_{idx}", use_container_width=True):
                            success, msg = virtual_trading_manager.cancel_limit_order(trading_user_id, order["id"])
                            if success:
                                st.toast(msg, icon="❌")
                                st.rerun()
                            else:
                                st.error(msg)
                                
            # 매매 이력 로그 및 리셋
            with st.expander("📜 가상 거래 내역 및 계좌 관리"):
                if history:
                    history_df = pd.DataFrame(history[::-1])
                    st.dataframe(history_df, use_container_width=True, hide_index=True)
                else:
                    st.caption("거래 내역이 없습니다.")
                
                st.write("---")
                if st.button("🔄 가상 계좌 초기화 (자산 리셋)", key="reset_virtual_trading_btn_col", use_container_width=True):
                    virtual_trading_manager.reset_user_data(trading_user_id)
                    st.toast("가상 계좌가 초기 상태로 재설정되었습니다!", icon="🔄")
                    st.rerun()

    except Exception as e:
        st.error(f"❌ 데이터 분석 중 오류가 발생했습니다.")
        st.code(traceback.format_exc())
