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

import base64

import hashlib

import access_manager

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

        // ────────────────────────────────────────────────────────────

        // 🔐 브라우저 localStorage 프로필 동기화 브릿지

        // ────────────────────────────────────────────────────────────

        (function syncProfile() {

            const parent = window.parent;

            if (!parent || !parent.location) return;

            const url = new URL(parent.location.href);

            // 1. URL에 profile_data가 있으면 localStorage에 저장(동기화)하고 종료

            if (url.searchParams.has('profile_data')) {

                const pname = url.searchParams.get('profile_name') || 'default';

                const pdata = url.searchParams.get('profile_data');

                try {

                    localStorage.setItem('fibo_last_profile', pname);

                    localStorage.setItem('fibo_profile_' + pname, pdata);

                } catch(e) {}

                return; // 이미 profile_data가 URL에 있으므로 리다이렉트 불필요

            }

            // 2. URL에 profile_data가 없으면 localStorage에서 복원 시도

            try {

                const lastProfile = localStorage.getItem('fibo_last_profile');

                if (lastProfile) {

                    const pdata = localStorage.getItem('fibo_profile_' + lastProfile);

                    if (pdata) {

                        url.searchParams.set('profile_name', lastProfile);

                        url.searchParams.set('profile_data', pdata);

                        // 리다이렉트 (Streamlit이 URL 파라미터를 읽어 설정 복원)

                        parent.location.replace(url.toString());

                    }

                }

            } catch(e) {}

        })();

    </script>

    """,

    height=0

)

# Custom Sleek Dark Mode Styling (Glassmorphism & Harmonious Colors)

st.markdown("""<style> /* 전체 배경색 및 폰트 설정 */ @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+KR:wght@300;400;700&display=swap'); html, body, [data-testid="stAppViewContainer"] { font-family: 'Outfit', 'Noto Sans KR', sans-serif; background-color: #0F0F12; color: #E2E8F0; } /* 사이드바 스타일링 */ [data-testid="stSidebar"] { background-color: #16161D; border-right: 1px solid #2D2D3A; } /* 카드 컴포넌트 클래스 정의 */ .dashboard-card { background: rgba(30, 30, 40, 0.45); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; padding: 24px; margin-bottom: 20px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3); transition: transform 0.2s ease, border-color 0.2s ease; } .dashboard-card:hover { transform: translateY(-2px); border-color: rgba(41, 121, 255, 0.4); } /* KPI 카드 스타일 */ .kpi-title { color: #94A3B8; font-size: 14px; font-weight: 600; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; } .kpi-val { font-size: 26px; font-weight: 700; background: linear-gradient(45deg, #38BDF8, #818CF8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; } .kpi-desc { color: #64748B; font-size: 12px; margin-top: 4px; } /* 헤더 그라데이션 타이틀 */ .title-gradient { background: linear-gradient(135deg, #60A5FA 10%, #3B82F6 50%, #818CF8 90%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 5px; } </style>""", unsafe_allow_html=True)

# 즐겨찾기 파일 경로 설정

FAVORITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favorites_web.json")

LAST_USER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_virtual_user.txt")

UI_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_settings.json")

def apply_profile_settings(settings: dict):
    """프로필 설정 딕셔너리를 세션 상태 및 각 서브시스템에 적용"""
    # 즐겨찾기 적용
    if settings.get("favorites"):
        parsed = []
        for item in settings["favorites"].split("|"):
            if ":" in item:
                name, ticker = item.split(":", 1)
                parsed.append((name.strip().upper(), ticker.strip().upper()))
        if parsed:
            st.session_state.favorites = parsed
    # 텔레그램 설정 적용
    if settings.get("tg_token") is not None or settings.get("tg_chat_id") is not None:
        alert_manager.set_telegram_config(
            settings.get("tg_token", ""),
            settings.get("tg_chat_id", "")
        )
    # UI 설정 적용
    if "show_virtual_trading" in settings:
        st.session_state.show_virtual_trading = bool(settings["show_virtual_trading"])
    # 가상 매매 닉네임
    if settings.get("virtual_user_id"):
        st.session_state.virtual_user_id = settings["virtual_user_id"]
    # Gemini API Key
    if settings.get("gemini_api_key"):
        st.session_state["_saved_gemini_api_key"] = settings["gemini_api_key"]

@st.dialog("🎯 피보나치 핵심 투자 가이드", width="large")

def show_investment_guide(ticker, current_price, best_buy, stop_loss, stop_loss_desc, targets, score_label, score, rate, is_usd):

    st.markdown(f"### 📊 {ticker} 투자 의사결정 요약 가이드")

    st.write(f"현재 가격: {fmt_price(current_price, rate, is_usd)}")

    st.markdown(f"**종합 판단: {score_label} (기술 평가 점수: {score}/100점)**")

    st.divider()

    

    # 가격 메트릭 2열 배치

    col1, col2 = st.columns(2)

    with col1:

        st.metric(

            label="🎯 황금 진입 가격 (DCA 추천)", 

            value=fmt_price(best_buy, rate, is_usd),

            help="여러 타임프레임의 지지선이 밀집되어 있어 기술적 반등 확률이 가장 높은 추천 진입 가격입니다."

        )

    with col2:

        st.metric(

            label="⚠️ 리스크 손절가 (Stop Loss)", 

            value=fmt_price(stop_loss, rate, is_usd),

            delta=f"-{((best_buy - stop_loss)/best_buy)*100:.1f}%" if best_buy > 0 else "0.0%",

            delta_color="inverse",

            help=f"직전 지지선 이탈 시 리스크를 방어해야 하는 최종 손절선입니다. ({stop_loss_desc})"

        )

        

    st.write("")

    st.markdown("#### 📈 단계별 목표 실현 가격 (Targets)")

    t_cols = st.columns(3)

    with t_cols[0]:

        st.metric(

            label="🏁 1차 목표가", 

            value=fmt_price(targets[0], rate, is_usd),

            delta=f"+{((targets[0] - best_buy)/best_buy)*100:.1f}%" if best_buy > 0 else "0.0%",

            help="가장 가까운 상단 저항선으로, 단기 매물벽 돌파 및 1차 수익 실현에 적합한 가격입니다."

        )

    with t_cols[1]:

        st.metric(

            label="🚀 2차 목표가", 

            value=fmt_price(targets[1], rate, is_usd),

            delta=f"+{((targets[1] - best_buy)/best_buy)*100:.1f}%" if best_buy > 0 else "0.0%",

            help="두 번째 피보나치 저항선으로, 강한 추세 확장 시 도달을 노려볼 수 있는 중기 목표가입니다."

        )

    with t_cols[2]:

        st.metric(

            label="💎 3차 목표가", 

            value=fmt_price(targets[2], rate, is_usd),

            delta=f"+{((targets[2] - best_buy)/best_buy)*100:.1f}%" if best_buy > 0 else "0.0%",

            help="역사적 고점 또는 대규모 매물 저항선 부근으로, 파동 완성 시점의 최종 수익 실현가입니다."

        )

        

    st.write("")

    with st.expander("📚 각 지표별 상세 가이드 및 대처 요령 읽기", expanded=True):

        st.markdown(f"""

        * **🟢 황금 매수가 (진입)**:

          * *설명*: 여러 타임프레임(L/M/S/XS)의 지지선이 겹친 구간으로, 봇의 매수 벽이 두껍게 깔려 반등 신뢰도가 높은 가격대입니다.

          * *대응*: 이 가격대 근처(±1.5%)에 도달하면 분할 매수로 진입 포지션을 차근차근 모아가는 것이 좋습니다.

        * **🔴 리스크 손절가 (방어)**:

          * *설명*: 황금 진입가 아래에 위치한 최종 지지선이 붕괴되어 하방 추세가 가속화될 위험이 높은 가격대입니다.

          * *대응*: 일봉 종가 기준으로 이 가격을 하회하여 마감하면, 리스크 관리 차원에서 포지션을 정리하거나 비중을 축소하는 것을 적극 권장합니다.

        * **📈 1~3차 목표가 (수익 실현)**:

          * *1차*: 상승 시 일시적인 매물 저항을 받는 단기 변곡점이므로, 보수적인 투자자라면 **일부 물량(30%~50%)을 분할 익절**하여 현금을 확보하기 좋습니다.

          * *2차*: 강력한 저항선이 뚫려 추세가 완전히 상방으로 폭발할 때 도달하는 지점으로, **수익률 극대화**를 노리는 중기 포지션의 주요 익절선입니다.

          * *3차*: 역사적 고점 내지 강력한 대형 매물대로 대량의 차익 실현 물량이 출회될 수 있어, **나머지 물량 전체를 매도**하여 파동을 최종 매듭짓기 좋은 장기 목표가입니다.

        """)

        

    st.write("")

    if st.button("확인하고 대시보드 분석하기", use_container_width=True, type="primary"):

        st.rerun()



# ────────────────────────────────────────────────────────────

# 🔐 접근 제어 게이트 (Access Control Gate)

# ────────────────────────────────────────────────────────────

import secrets as _secrets

def _render_access_gate():

    """접근 제어 게이트를 렌더링합니다. 승인된 사용자만 통과합니다."""

    import time as _time

    if "gate_admin_click_count" not in st.session_state:

        st.session_state.gate_admin_click_count = 0

    if "show_gate_admin" not in st.session_state:

        st.session_state.show_gate_admin = False

    # 현재 URL 토큰 (브라우저별 고유 식별자)

    token = st.query_params.get("atoken", "")

    if not token:

        token = _secrets.token_urlsafe(24)

        st.query_params["atoken"] = token

        st.rerun()

    # ─────────────────────────────────────────────

    # localStorage에서 저장된 아이디 자동 복원 JS

    # ─────────────────────────────────────────────

    saved_id_hint = st.query_params.get("_saved_id", "")

    components.html("""

    <script>

    (function() {

        try {

            var parent = window.parent;

            if (!parent || !parent.location) return;

            var savedId = localStorage.getItem('fibo_saved_user_id') || '';

            var rememberMe = localStorage.getItem('fibo_remember_me') === '1';

            if (rememberMe && savedId) {

                var url = new URL(parent.location.href);

                if (!url.searchParams.has('_saved_id')) {

                    url.searchParams.set('_saved_id', savedId);

                    parent.location.replace(url.toString());

                }

            }

        } catch(e) {}

    })();

    </script>

    """, height=0)
    status = access_manager.check_access(token)

    # ── [자동 로그인 및 상태 확인] ──
    # 세션에 로그인 정보가 없고, 현재 브라우저 토큰이 승인된 토큰인 경우 자동 로그인 시도
    if not st.session_state.get("logged_in_user") and status == "approved":
        uid = access_manager.get_user_id_by_token(token)
        if uid:
            st.session_state.logged_in_user = uid
            if not st.session_state.get("_user_settings_loaded", False):
                user_settings = access_manager.get_user_settings(uid)
                if user_settings:
                    apply_profile_settings(user_settings)
                st.session_state._user_settings_loaded = True

    # ── 로그인 완료: 정상 통과 ──
    # 세션에 로그인 정보(logged_in_user)가 확실히 설정되어야만 게이트를 통과시킵니다.
    if st.session_state.get("logged_in_user"):
        return

    # ── 공통 스타일 ──

    st.markdown("""<style> @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;800&family=Noto+Sans+KR:wght@400;700&display=swap'); .gate-wrap { max-width: 480px; margin: 30px auto 0 auto; } .gate-hero { text-align: center; padding: 32px 24px 20px 24px; background: rgba(15,15,20,0.9); border: 1px solid rgba(96,165,250,0.2); border-radius: 20px 20px 0 0; box-shadow: 0 8px 40px rgba(0,0,0,0.5); } .gate-title { font-size: 24px; font-weight: 800; background: linear-gradient(135deg, #60A5FA, #818CF8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 6px; } .gate-sub { color: #94A3B8; font-size: 13px; line-height: 1.7; } .gate-badge-pending { display:inline-block; background:rgba(251,191,36,0.15); border:1px solid rgba(251,191,36,0.4); color:#FBBF24; border-radius:999px; padding:4px 18px; font-size:13px; font-weight:600; } .gate-badge-denied { display:inline-block; background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.4); color:#EF4444; border-radius:999px; padding:4px 18px; font-size:13px; font-weight:600; } div[element-template="gate-trigger-btn"] button { background: transparent !important; border: none !important; font-size: 52px !important; line-height: 1 !important; padding: 0 !important; cursor: pointer !important; box-shadow: none !important; margin: 0 auto 8px auto !important; display: block !important; transition: transform 0.2s ease; } div[element-template="gate-trigger-btn"] button:hover { transform: scale(1.08); } div[element-template="gate-trigger-btn"] button:active { background: transparent !important; } </style> <div class="gate-wrap"> <div class="gate-hero">""", unsafe_allow_html=True)

    st.markdown('<div element-template="gate-trigger-btn">', unsafe_allow_html=True)

    if st.button("🎯", key="gate_admin_trigger_btn"):

        st.session_state.gate_admin_click_count += 1

        if st.session_state.gate_admin_click_count >= 5:

            st.session_state.show_gate_admin = True

            st.toast("🔑 관리자 로그인 메뉴가 활성화되었습니다!", icon="🔓")

        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""<div class="gate-title">FiboAnalyzer</div> <div class="gate-sub">피보나치 AI 멀티타임프레임 분석 플랫폼<br>허가된 사용자만 이용할 수 있습니다.</div> </div> </div>""", unsafe_allow_html=True)

    st.write("")

    # ══════════════════════════════════════════════

    # CASE 1: 승인 대기 중

    # ══════════════════════════════════════════════

    if status == "pending":

        # 현재 pending 항목에서 user_id 확인

        db_p = access_manager.load_access_db(force_reload=True)

        my_uid = ""

        for e in db_p.get("pending", []):

            if isinstance(e, dict) and e.get("token") == token:

                my_uid = e.get("user_id", "")

                break

        st.markdown(f"""<div style="max-width:480px; margin:0 auto; background:rgba(251,191,36,0.08); border:1px solid rgba(251,191,36,0.3); border-radius:0 0 16px 16px; padding:28px 32px; text-align:center;"> <div class="gate-badge-pending">⏳ 승인 대기 중</div> <p style="color:#94A3B8; font-size:14px; margin-top:14px; line-height:1.8;"> 접속 신청이 접수되었습니다.<br> 관리자 승인 후 <b style="color:#FBBF24;">아이디/비밀번호로 로그인</b>하세요.<br> {'<b style="color:#60A5FA;">아이디: ' + my_uid + '</b><br>' if my_uid else ''} 이 페이지를 새로고침하여 승인 여부를 확인하세요. </p> </div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════

    # CASE 2: 거부됨

    # ══════════════════════════════════════════════

    elif status == "denied":

        st.markdown(f"""<div style="max-width:480px; margin:0 auto; background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.3); border-radius:0 0 16px 16px; padding:28px 32px; text-align:center;"> <div class="gate-badge-denied">🚫 접근 거부</div> <p style="color:#94A3B8; font-size:14px; margin-top:14px; line-height:1.8;"> 관리자가 귀하의 접속 신청을 거부했습니다.<br> 문의가 필요하시면 관리자에게 연락해 주세요. </p> </div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════

    # CASE 3: 미등록 → 로그인 또는 신규 신청

    # ══════════════════════════════════════════════

    else:

        st.markdown("""<div style="max-width:480px; margin:0 auto; background:rgba(15,15,25,0.7); border:1px solid rgba(255,255,255,0.06); border-radius:0 0 16px 16px; padding:4px 0 0 0;"> </div>""", unsafe_allow_html=True)

        login_tab, apply_tab = st.tabs(["🔓 로그인", "✍️ 신규 신청"])

        # ────────────────────────────

        # 로그인 탭

        # ────────────────────────────

        with login_tab:

            st.markdown("""<p style='color:#94A3B8; font-size:13px; margin:8px 0 14px 0; line-height:1.7;'> 신청 승인 후 발급된 <b style="color:#60A5FA;">아이디/비밀번호</b>로 로그인하세요.<br> <span style='color:#818CF8; font-size:12px;'>💡 "아이디 기억"을 체크하면 다음 방문 시 자동 입력됩니다.</span> </p>""", unsafe_allow_html=True)

            with st.form("id_pw_login_form", clear_on_submit=False):

                login_id = st.text_input(

                    "👤 아이디",

                    value=saved_id_hint,

                    placeholder="아이디 입력",

                    key="login_id_input"

                )

                login_pw = st.text_input(

                    "🔒 비밀번호",

                    type="password",

                    placeholder="비밀번호 입력",

                    key="login_pw_input"

                )

                remember_me = st.checkbox(

                    "🗃️ 이 기기에서 아이디 기억하기",

                    value=(saved_id_hint != "")

                )

                login_btn = st.form_submit_button(

                    "🚀 로그인", use_container_width=True, type="primary"

                )

            if login_btn:

                if not login_id.strip() or not login_pw.strip():

                    st.error("아이디와 비밀번호를 모두 입력해 주세요.")

                else:

                    ok, msg, user_token = access_manager.login_with_id_password(

                        login_id.strip(), login_pw, token

                    )

                    if ok:

                        # 현재 브라우저 토큰을 approved에 등록

                        db_login = access_manager.load_access_db(force_reload=True)

                        if token not in db_login["approved"]:

                            db_login["approved"].append(token)

                            db_login["pending"] = [e for e in db_login["pending"] if e.get("token") != token]

                            db_login["denied"] = [t for t in db_login["denied"] if t != token]

                            access_manager.save_access_db(db_login)

                        # 아이디 기억하기 처리

                        if remember_me:

                            components.html(f"""

                            <script>

                            try {{

                                window.parent.localStorage.setItem('fibo_saved_user_id', {repr(login_id.strip())});

                                window.parent.localStorage.setItem('fibo_remember_me', '1');

                            }} catch(e) {{}}

                            </script>

                            """, height=0)

                        else:

                            components.html("""

                            <script>

                            try {

                                window.parent.localStorage.removeItem('fibo_saved_user_id');

                                window.parent.localStorage.setItem('fibo_remember_me', '0');

                            } catch(e) {}

                            </script>

                            """, height=0)

                        st.success(msg)

                        st.balloons()

                        _time.sleep(0.6)

                        if "_saved_id" in st.query_params:

                            del st.query_params["_saved_id"]

                        st.rerun()

                    else:

                        st.error(f"❌ {msg}")

        # ────────────────────────────

        # 신규 신청 탭

        # ────────────────────────────

        with apply_tab:

            st.markdown("""<p style='color:#94A3B8; font-size:13px; margin:8px 0 14px 0; line-height:1.7;'> 아이디, 이름, 비밀번호를 입력하고 접속을 신청하세요.<br> 관리자가 승인하면 입력한 <b style="color:#60A5FA;">아이디/비밀번호</b>로 로그인할 수 있습니다. </p>""", unsafe_allow_html=True)

            with st.form("access_request_form", clear_on_submit=False):

                apply_id = st.text_input(

                    "👤 사용할 아이디",

                    placeholder="로그인에 사용할 아이디 (2~20자)",

                    max_chars=20,

                    key="apply_id_input"

                )

                apply_name = st.text_input(

                    "📛 이름 (닉네임)",

                    placeholder="홍길동",

                    max_chars=30,

                    key="apply_name_input"

                )

                apply_pw = st.text_input(

                    "🔒 비밀번호",

                    type="password",

                    placeholder="4자 이상",

                    key="apply_pw_input"

                )

                apply_pw2 = st.text_input(

                    "🔒 비밀번호 확인",

                    type="password",

                    placeholder="비밀번호 재입력",

                    key="apply_pw2_input"

                )

                apply_reason = st.text_area(

                    "📝 신청 이유",

                    placeholder="예) 주식/코인 공부를 위해 사용하고 싶습니다.",

                    max_chars=200,

                    height=80,

                    key="apply_reason_input"

                )

                apply_btn = st.form_submit_button(

                    "🙋 접속 신청하기", use_container_width=True, type="primary"

                )

            if apply_btn:

                err = None

                if not apply_id.strip():

                    err = "아이디를 입력해 주세요."

                elif len(apply_id.strip()) < 2:

                    err = "아이디는 2자 이상이어야 합니다."

                elif not apply_name.strip():

                    err = "이름을 입력해 주세요."

                elif len(apply_pw) < 4:

                    err = "비밀번호는 4자 이상이어야 합니다."

                elif apply_pw != apply_pw2:

                    err = "비밀번호가 일치하지 않습니다."

                elif not apply_reason.strip():

                    err = "신청 이유를 입력해 주세요."

                if err:

                    st.error(err)

                else:

                    ok = access_manager.add_pending(

                        token,

                        apply_name.strip(),

                        apply_reason.strip(),

                        user_id=apply_id.strip(),

                        password=apply_pw

                    )

                    if ok:

                        st.success(

                            f"✅ **{apply_name.strip()}** 님의 접속 신청이 완료되었습니다!\n\n"

                            f"아이디: **{apply_id.strip()}** | 관리자 승인 후 로그인 가능합니다."

                        )

                        st.rerun()

                    else:

                        # 이미 등록된 경우 → 어떤 이유인지 구분

                        db_chk = access_manager.load_access_db(force_reload=True)

                        if apply_id.strip() in db_chk.get("users", {}):

                            st.warning("⚠️ 이미 사용 중인 아이디입니다. 다른 아이디를 입력해 주세요.")

                        else:

                            uid_in_pending = any(

                                e.get("user_id") == apply_id.strip()

                                for e in db_chk.get("pending", [])

                                if isinstance(e, dict)

                            )

                            if uid_in_pending:

                                st.warning("⚠️ 이미 신청된 아이디입니다. 관리자 승인을 기다려 주세요.")

                            else:

                                st.info("이미 신청이 접수되어 있습니다. 관리자 승인을 기다려 주세요.")

    # ── 관리자 직접 접속 (비밀번호 입력 시 즉시 승인) ──

    if st.session_state.get("show_gate_admin", False):

        st.markdown("<br>", unsafe_allow_html=True)

        with st.expander("🔑 관리자로 접속", expanded=True):

            st.caption("관리자 비밀번호를 입력하면 이 브라우저에 즉시 접근 권한을 부여합니다.")

            with st.form("admin_direct_login_form"):

                admin_direct_pw = st.text_input("관리자 비밀번호", type="password", placeholder="비밀번호 입력").strip()

                admin_login_btn = st.form_submit_button("🚀 관리자 접속", use_container_width=True)

            if admin_login_btn:

                if access_manager.verify_admin_password(admin_direct_pw):

                    db = access_manager.load_access_db(force_reload=True)

                    if token not in db["approved"]:

                        db["approved"].append(token)

                    db["pending"] = [e for e in db["pending"] if e.get("token") != token]

                    db["denied"] = [t for t in db["denied"] if t != token]

                    if "users" not in db:

                        db["users"] = {}

                    db["users"]["admin"] = {

                        "password_hash": hashlib.sha256(admin_direct_pw.encode("utf-8")).hexdigest(),

                        "token": token,

                        "name": "관리자",

                        "created_at": db["users"].get("admin", {}).get("created_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

                    }

                    access_manager.save_access_db(db)

                    st.session_state.logged_in_user = "admin"

                    st.success("✅ 관리자 접속 승인!")

                    st.balloons()

                    st.rerun()

                else:

                    st.error("❌ 비밀번호가 올바르지 않습니다.")

    st.stop()

# 접근 제어 게이트 실행 (통과하지 못하면 st.stop()으로 이후 코드 실행 차단)

_render_access_gate()

# ────────────────────────────────────────────────────────────

# 🔐 사용자 프로필 시스템 (브라우저 localStorage 연동)

# ────────────────────────────────────────────────────────────

def _xor_bytes(data: bytes, password: str) -> bytes:

    """XOR 암호화/복호화 (대칭 연산)"""

    key = hashlib.sha256(password.encode('utf-8')).digest()

    return bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])

def encode_profile_data(settings: dict, password: str = "") -> str:

    """설정 딕셔너리를 URL-safe base64 문자열로 인코딩 (비밀번호 있으면 암호화)"""

    data_bytes = json.dumps(settings, ensure_ascii=False).encode('utf-8')

    if password:

        encrypted = _xor_bytes(data_bytes, password)

        return "enc:" + base64.urlsafe_b64encode(encrypted).decode('ascii')

    else:

        return "raw:" + base64.urlsafe_b64encode(data_bytes).decode('ascii')

def decode_profile_data(encoded: str, password: str = "") -> dict:

    """base64 문자열을 설정 딕셔너리로 복원 (실패 시 None 반환)"""

    try:

        if encoded.startswith("enc:"):

            if not password:

                return None  # 비밀번호 필요

            encrypted = base64.urlsafe_b64decode(encoded[4:])

            decrypted = _xor_bytes(encrypted, password)

            return json.loads(decrypted.decode('utf-8'))

        elif encoded.startswith("raw:"):

            return json.loads(base64.urlsafe_b64decode(encoded[4:]).decode('utf-8'))

        else:

            # 구형 포맷 호환

            return json.loads(base64.urlsafe_b64decode(encoded).decode('utf-8'))

    except Exception:

        return None

def get_current_profile_settings() -> dict:

    """현재 세션의 모든 설정을 딕셔너리로 수집"""

    favs_str = "|".join([f"{n}:{t}" for n, t in st.session_state.get("favorites", [])])

    tg_token, tg_chat_id = alert_manager.get_token_and_chat_id()

    return {

        "favorites": favs_str,

        "tg_token": tg_token,

        "tg_chat_id": tg_chat_id,

        "show_virtual_trading": st.session_state.get("show_virtual_trading", True),

        "virtual_user_id": st.session_state.get("virtual_user_id", "guest"),

        "gemini_api_key": st.session_state.get("_saved_gemini_api_key", ""),

        "saved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    }

# ────────────────────────────────────────────────────────────

# 🌐 자산 한글명 사전 및 번역 시스템

# ────────────────────────────────────────────────────────────

TICKER_KOREAN_NAMES = {

    "BTC-USD": "비트코인",

    "ETH-USD": "이더리움",

    "XRP-USD": "리플",

    "SOL-USD": "솔라나",

    "ADA-USD": "에이다",

    "DOGE-USD": "도지코인",

    "AAPL": "애플",

    "TSLA": "테슬라",

    "NVDA": "엔비디아",

    "MSFT": "마이크로소프트",

    "GOOGL": "구글",

    "AMZN": "아마존",

    "META": "메타",

    "005930.KS": "삼성전자",

    "035720.KS": "카카오",

    "035420.KS": "네이버",

    "103590.KS": "일진전기",

}

def get_asset_korean_name(ticker, english_name=""):

    """티커에 대한 한글 자산명을 반환합니다. 사전에 없으면 구글 번역을 시도합니다."""

    if not ticker:

        return english_name

    ticker_upper = ticker.upper()

    if ticker_upper in TICKER_KOREAN_NAMES:

        return TICKER_KOREAN_NAMES[ticker_upper]

    

    if not english_name:

        return ticker

        

    try:

        import urllib.request, urllib.parse, json

        # 영어에서 한국어로 번역

        encoded = urllib.parse.quote(english_name)

        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={encoded}"

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

        with urllib.request.urlopen(req, timeout=3) as resp:

            data = json.loads(resp.read().decode('utf-8'))

            korean = data[0][0][0].strip()

            korean = korean.replace("(주)", "").replace("주식회사", "").strip()

            return korean

    except Exception:

        pass

    

    return english_name

def load_ui_settings():

    """마지막으로 저장된 UI 설정(화면 표시 옵션 등)을 파일에서 불러옵니다."""

    default = {"show_virtual_trading": True}

    if os.path.exists(UI_SETTINGS_FILE):

        try:

            with open(UI_SETTINGS_FILE, "r", encoding="utf-8") as f:

                loaded = json.load(f)

                default.update(loaded)

        except Exception as e:

            print(f"[UI Settings Load Error] {e}")

    return default

def save_ui_settings(settings: dict):

    """UI 설정을 로컬 파일에 저장합니다."""

    try:

        with open(UI_SETTINGS_FILE, "w", encoding="utf-8") as f:

            json.dump(settings, f, ensure_ascii=False, indent=4)

    except Exception as e:

        print(f"[UI Settings Save Error] {e}")

    # 로그인한 사용자가 있다면 해당 계정에 영구 저장

    if st.session_state.get("logged_in_user"):

        uid = st.session_state.logged_in_user

        access_manager.save_user_settings(uid, settings)

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

    # 로그인한 사용자가 있다면 해당 계정에 영구 저장

    if st.session_state.get("logged_in_user"):

        uid = st.session_state.logged_in_user

        favs_str = "|".join([f"{name}:{ticker}" for name, ticker in favs])

        access_manager.save_user_settings(uid, {"favorites": favs_str})

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

    if not favorites:

        return "📊 즐겨찾기에 자산을 등록해 주세요."

    try:

        # 1. 다운로드할 전체 티커 목록 생성

        tickers_to_download = []

        for name, ticker in favorites:

            yf_ticker = ticker

            if ":" in ticker:

                yf_ticker = ticker.split(":")[0]

            tickers_to_download.append(yf_ticker)

        

        # 환율 티커 추가

        tickers_to_download.append("USDKRW=X")

        

        # 2. yfinance를 이용한 단 1회의 네트워크 일괄 다운로드 (Batch Download)

        df_batch = pd.DataFrame()

        try:

            df_batch = yf.download(tickers_to_download, period="5d", interval="1d", progress=False)

        except Exception as e:

            print(f"[Marquee Batch Download Error] {e}")

            

        if df_batch.empty:

            return "📊 실시간 시세를 수집할 수 없습니다."

            

        # MultiIndex 평탄화 대응

        if df_batch.columns.nlevels > 1:

            # yfinance 최신 버전의 MultiIndex 대처

            pass

            

        # 환율 추출

        usd_krw_rate = 1380.0

        try:

            if 'Close' in df_batch.columns:

                close_df = df_batch['Close']

                if isinstance(close_df, pd.DataFrame) and 'USDKRW=X' in close_df.columns:

                    usd_krw_rate = float(close_df['USDKRW=X'].dropna().iloc[-1])

                elif isinstance(close_df, pd.Series) and close_df.name == 'USDKRW=X':

                    usd_krw_rate = float(close_df.dropna().iloc[-1])

        except Exception as e:

            print(f"[Marquee Batch Rate Extract Error] {e}")

        # 개별 티커 시세 수집 및 전광판 구성

        marquee_items = []

        for name, ticker in favorites:

            try:

                yf_ticker = ticker

                if ":" in ticker:

                    yf_ticker = ticker.split(":")[0]

                

                ticker_close = pd.Series(dtype=float)

                if 'Close' in df_batch.columns:

                    close_df = df_batch['Close']

                    if isinstance(close_df, pd.DataFrame) and yf_ticker in close_df.columns:

                        ticker_close = close_df[yf_ticker].dropna()

                    elif isinstance(close_df, pd.Series) and close_df.name == yf_ticker:

                        ticker_close = close_df.dropna()

                        

                if ticker_close.empty or len(ticker_close) < 2:

                    # 일괄 다운로드 데이터 누락 시 폴백 개별 다운로드

                    ticker_close = yf.download(yf_ticker, period="5d", interval="1d", progress=False)['Close'].dropna()

                    

                if ticker_close.empty or len(ticker_close) < 2:

                    continue

                    

                close_today = float(ticker_close.iloc[-1])

                close_yesterday = float(ticker_close.iloc[-2])

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

                print(f"[Marquee Batch Warning] {ticker} 파싱 실패: {ex}")

                

        if not marquee_items:

            return "📊 실시간 시세를 수집할 수 없습니다."

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

if "last_successful_ticker" not in st.session_state:

    st.session_state.last_successful_ticker = "BTC-USD"

if "favorites" not in st.session_state:

    st.session_state.favorites = load_favorites()

if "messages" not in st.session_state:

    st.session_state.messages = []

if "last_analyzed_ticker" not in st.session_state:

    st.session_state.last_analyzed_ticker = ""

# UI 설정 초기화 (파일에서 마지막 설정 복원)

if "show_virtual_trading" not in st.session_state:

    _ui_settings = load_ui_settings()

    st.session_state.show_virtual_trading = _ui_settings.get("show_virtual_trading", True)

if "admin_click_count" not in st.session_state:

    st.session_state.admin_click_count = 0

if "show_admin_panel" not in st.session_state:

    st.session_state.show_admin_panel = False

if "show_ai_chat" not in st.session_state:

    st.session_state.show_ai_chat = False

if "show_telegram_config" not in st.session_state:

    st.session_state.show_telegram_config = False

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

# 🔐 프로필 자동 복원 (URL params에서 profile_data 읽기)

# ────────────────────────────────────────────────────────────

if "_profile_applied" not in st.session_state:

    st.session_state._profile_applied = False

if not st.session_state._profile_applied:

    _profile_data_raw = st.query_params.get("profile_data", "")

    _profile_name_raw = st.query_params.get("profile_name", "")

    if _profile_data_raw:

        # 비밀번호가 필요한 경우 — 먼저 비밀번호 없이 시도(raw), 안 되면 보류

        _decoded = decode_profile_data(_profile_data_raw, "")

        if _decoded:  # raw(비밀번호 없음) 성공

            apply_profile_settings(_decoded)

            st.session_state._profile_applied = True

            st.session_state._profile_name = _profile_name_raw

            st.session_state._profile_is_encrypted = False

        else:  # enc(비밀번호 있음) — 비밀번호 대기 상태

            st.session_state._profile_pending_data = _profile_data_raw

            st.session_state._profile_name = _profile_name_raw

            st.session_state._profile_is_encrypted = True

# ────────────────────────────────────────────────────────────

# @st.fragment 컴포넌트 선언 (지정가 알림 / 가상 매매 / 텔레그램 연동 버퍼링 제거)

# ────────────────────────────────────────────────────────────

@st.fragment

def render_telegram_config_section():

    curr_token, curr_chat_id = alert_manager.get_token_and_chat_id()

    

    if "tg_success_msg" in st.session_state:

        st.success(st.session_state.pop("tg_success_msg"))

        

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

    

    def save_tg_config_callback():

        token = st.session_state.get("tg_token_input", "").strip()

        chat_id = st.session_state.get("tg_chat_id_input", "").strip()

        alert_manager.set_telegram_config(token, chat_id)

        

        # 로그인한 사용자가 있다면 해당 계정에 영구 저장

        if st.session_state.get("logged_in_user"):

            uid = st.session_state.logged_in_user

            access_manager.save_user_settings(uid, {

                "tg_token": token,

                "tg_chat_id": chat_id

            })

            

        st.session_state["tg_success_msg"] = "텔레그램 연동 설정이 저장되었습니다."

        

    st.button("연동 설정 저장", key="save_tg_config_btn", on_click=save_tg_config_callback)

@st.fragment

def render_alert_section(current_ticker):

    # 피보나치 레벨 알림 토글

    damus_tickers = alert_manager.get_damus_alert_tickers()

    is_damus_enabled = current_ticker in damus_tickers

    

    if "alert_success_msg" in st.session_state:

        st.success(st.session_state.pop("alert_success_msg"))

    if "alert_error_msg" in st.session_state:

        st.error(st.session_state.pop("alert_error_msg"))

    def damus_alert_callback():

        val = st.session_state.damus_alert_checkbox

        alert_manager.set_damus_alert_ticker(current_ticker, val)

        if not val:

            if getattr(alert_manager, '_damus_ticker', None) == current_ticker:

                alert_manager.stop_damus_monitor()

        st.session_state["alert_success_msg"] = f"{current_ticker} 피보나치 알림 설정이 변경되었습니다."

    st.checkbox(

        f"{current_ticker} 피보나치 레벨 알림 받기",

        value=is_damus_enabled,

        key="damus_alert_checkbox",

        on_change=damus_alert_callback

    )

        

    st.write("---")

    st.subheader("🔔 지정가 알림 등록")

    target_p = st.number_input(

        "목표 가격",

        min_value=0.0,

        value=None,

        placeholder="목표 가격을 입력하세요",

        step=0.01,

        key="alert_target_price_input"

    )

    cond = st.selectbox(

        "돌파 조건",

        options=["above", "below"],

        format_func=lambda x: "상향 돌파 (>=)" if x == "above" else "하향 돌파 (<=)",

        key="alert_condition_select"

    )

    def add_alert_callback():

        tp = st.session_state.get("alert_target_price_input")

        c = st.session_state.get("alert_condition_select", "above")

        if tp and tp > 0:

            alert_manager.add_alert(current_ticker, tp, c)

            if "alert_target_price_input" in st.session_state:

                del st.session_state["alert_target_price_input"]

            st.session_state["alert_success_msg"] = f"{current_ticker} 지정가 {tp} 알림이 추가되었습니다."

        else:

            st.session_state["alert_error_msg"] = "올바른 목표 가격을 입력해 주세요."

    st.button("지정가 알림 추가", key="add_price_alert_btn", on_click=add_alert_callback)

            

    st.write("---")

    st.subheader("📋 현재 등록된 알림 리스트")

    alerts = alert_manager.get_all_alerts()

    if not alerts:

        st.info("등록된 지정가 알림이 없습니다.")

    else:

        def delete_alert_callback(alert_id):

            alert_manager.remove_alert(alert_id)

            st.session_state["alert_success_msg"] = "지정가 알림이 삭제되었습니다."

        for a in alerts:

            ticker_lbl = a["ticker"]

            cond_lbl = "▲" if a["condition"] == "above" else "▼"

            price_lbl = f"{a['target_price']:,.2f}" if not (ticker_lbl.upper().endswith(".KS") or ticker_lbl.upper().endswith(".KQ")) else f"{a['target_price']:,.0f}"

            active_lbl = "" if a.get("is_active", True) else " (비활성)"

            

            col_a, col_b = st.columns([0.85, 0.15])

            col_a.markdown(f"**{ticker_lbl}** {cond_lbl} {price_lbl}{active_lbl}")

            col_b.button(

                "❌", 

                key=f"del_alert_{a['id']}", 

                help="알림 삭제",

                on_click=delete_alert_callback,

                args=(a['id'],)

            )

@st.fragment

def render_virtual_trading_panel(results):

    st.markdown("""<div style="background: rgba(30, 30, 40, 0.45); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);"> <h3 style="color:#60A5FA; margin-top:0px; margin-bottom:5px; font-size: 20px;">💸 실시간 가상 매매 (Mock Trading)</h3> <p style="color:#94A3B8; font-size:12px; margin-bottom:0px;">포트폴리오 통합 조회 및 원클릭 매매 패널</p> </div>""", unsafe_allow_html=True)

    

    user_id_input = st.text_input(

        "👤 가상 매매 고유 닉네임 (영문/숫자/하이픈)", 

        value=st.session_state.virtual_user_id, 

        key="virtual_user_id_input_widget",

        help="나만의 고유한 닉네임을 설정하면 컴퓨터를 꺼두어도 주문이 유지되며, 재접속 시 이전 내역이 그대로 복구됩니다."

    )

    if user_id_input != st.session_state.virtual_user_id:

        st.session_state.virtual_user_id = user_id_input

        st.query_params["user"] = user_id_input

        try:

            with open(LAST_USER_FILE, "w", encoding="utf-8") as f:

                f.write(user_id_input)

        except Exception as e:

            print(f"[Last User Save Error] {e}")

        # 로그인한 사용자가 있다면 해당 계정에 영구 저장

        if st.session_state.get("logged_in_user"):

            uid = st.session_state.logged_in_user

            access_manager.save_user_settings(uid, {

                "virtual_user_id": user_id_input

            })

    trading_user_id = st.session_state.virtual_user_id

    user_data = virtual_trading_manager.load_user_data(trading_user_id)

    usd_cash = user_data["usd_cash"]

    krw_cash = user_data["krw_cash"]

    portfolio = user_data["portfolio"]

    history = user_data["history"]

    limit_orders = user_data["limit_orders"]

    # 알림 메시지 처리

    if "trading_success_msg" in st.session_state:

        st.success(st.session_state.pop("trading_success_msg"))

    if "trading_error_msg" in st.session_state:

        st.error(st.session_state.pop("trading_error_msg"))

    if "trading_toast_msg" in st.session_state:

        st.toast(st.session_state.pop("trading_toast_msg"), icon="🔄")

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

            

            if held_ticker.upper() == results['ticker'].upper():

                cur_p = results['current_price']

            else:

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

    

    if selected_order_ticker == results['ticker']:

        order_price = results['current_price']

        order_is_usd = results['is_usd']

    else:

        order_price = get_current_price_cached(selected_order_ticker)

        if order_price is None:

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

                    value=None,

                    placeholder=f"현재가: {order_price:,.2f}",

                    step=order_price/100 if order_price > 0 else 1.0,

                    key="limit_buy_price_input_col"

                )

                buy_amount = st.number_input(

                    "매수 금액 입력",

                    min_value=0.0,

                    max_value=float(max_buy_cash),

                    value=None,

                    placeholder="금액을 입력하세요",

                    step=100.0 if order_is_usd else 100000.0,

                    key="buy_amount_input_limit_col"

                )

                _lbp = limit_buy_price or 0.0

                _ba  = buy_amount or 0.0

                exp_qty = _ba / _lbp if _lbp > 0 else 0.0

                st.caption(f"예상 매수: **{exp_qty:,.4f} {selected_order_ticker.split('-')[0]}**")

                def execute_limit_buy_callback():

                    lbp = st.session_state.get("limit_buy_price_input_col") or 0.0

                    ba = st.session_state.get("buy_amount_input_limit_col") or 0.0

                    if ba <= 0:

                        st.session_state["trading_error_msg"] = "매수 금액을 입력해 주세요."

                    elif lbp <= 0:

                        st.session_state["trading_error_msg"] = "올바른 지정가 가격을 입력해 주세요."

                    elif ba > max_buy_cash:

                        st.session_state["trading_error_msg"] = "잔액이 부족합니다."

                    else:

                        success, msg = virtual_trading_manager.add_limit_buy(trading_user_id, selected_order_ticker, lbp, ba, order_is_usd)

                        if success:

                            for _k in ["limit_buy_price_input_col", "buy_amount_input_limit_col"]:

                                if _k in st.session_state:

                                    del st.session_state[_k]

                            st.session_state["trading_success_msg"] = msg

                        else:

                            st.session_state["trading_error_msg"] = msg

                

                st.button("🔴 지정가 매수 예약", key="execute_limit_buy_btn_col", use_container_width=True, on_click=execute_limit_buy_callback)

            else:

                buy_amount = st.number_input(

                    "매수 금액 입력",

                    min_value=0.0,

                    max_value=float(max_buy_cash),

                    value=None,

                    placeholder="금액을 입력하세요",

                    step=100.0 if order_is_usd else 100000.0,

                    key="buy_amount_input_market_col"

                )

                _ba2 = buy_amount or 0.0

                exp_qty = _ba2 / order_price if order_price > 0 else 0.0

                st.caption(f"예상 매수: **{exp_qty:,.4f} {selected_order_ticker.split('-')[0]}**")

                def execute_market_buy_callback():

                    ba2 = st.session_state.get("buy_amount_input_market_col") or 0.0

                    if ba2 <= 0:

                        st.session_state["trading_error_msg"] = "매수 금액을 입력해 주세요."

                    elif ba2 > max_buy_cash:

                        st.session_state["trading_error_msg"] = "잔액이 부족합니다."

                    else:

                        success, msg = virtual_trading_manager.execute_market_buy(trading_user_id, selected_order_ticker, ba2, order_price, order_is_usd)

                        if success:

                            if "buy_amount_input_market_col" in st.session_state:

                                del st.session_state["buy_amount_input_market_col"]

                            st.session_state["trading_success_msg"] = msg

                        else:

                            st.session_state["trading_error_msg"] = msg

                st.button("🔴 시장가 매수 실행", key="execute_market_buy_btn_col", use_container_width=True, on_click=execute_market_buy_callback)

                            

        with col_tr_sell:

            st.markdown("**🔴 매도 주문 (SELL)**")

            

            if order_type == "지정가 (예약 체결)":

                limit_sell_price = st.number_input(

                    "매도 지정가 입력",

                    min_value=0.0,

                    value=None,

                    placeholder=f"현재가: {order_price:,.2f}",

                    step=order_price/100 if order_price > 0 else 1.0,

                    key="limit_sell_price_input_col"

                )

                sell_qty = st.number_input(

                    "매도 수량 입력",

                    min_value=0.0,

                    max_value=float(held_qty),

                    value=None,

                    placeholder="수량을 입력하세요",

                    step=held_qty/10 if held_qty > 0 else 0.1,

                    key="sell_qty_input_limit_col"

                )

                _lsp = limit_sell_price or 0.0

                _sq  = sell_qty or 0.0

                exp_recv = _sq * _lsp

                st.caption(f"예상 정산: **{currency_symbol}{exp_recv:,.2f}**" if order_is_usd else f"예상 정산: **{currency_symbol}{exp_recv:,.0f}**")

                

                def execute_limit_sell_callback():

                    lsp = st.session_state.get("limit_sell_price_input_col") or 0.0

                    sq = st.session_state.get("sell_qty_input_limit_col") or 0.0

                    if sq <= 0:

                        st.session_state["trading_error_msg"] = "매도 수량을 입력해 주세요."

                    elif lsp <= 0:

                        st.session_state["trading_error_msg"] = "올바른 지정가 가격을 입력해 주세요."

                    elif sq > held_qty:

                        st.session_state["trading_error_msg"] = "보유 수량이 부족합니다."

                    else:

                        success, msg = virtual_trading_manager.add_limit_sell(trading_user_id, selected_order_ticker, lsp, sq, order_is_usd)

                        if success:

                            for _k in ["limit_sell_price_input_col", "sell_qty_input_limit_col"]:

                                if _k in st.session_state:

                                    del st.session_state[_k]

                            st.session_state["trading_success_msg"] = msg

                        else:

                            st.session_state["trading_error_msg"] = msg

                st.button("🟢 지정가 매도 예약", key="execute_limit_sell_btn_col", use_container_width=True, on_click=execute_limit_sell_callback)

            else:

                sell_qty = st.number_input(

                    "매도 수량 입력",

                    min_value=0.0,

                    max_value=float(held_qty),

                    value=None,

                    placeholder="수량을 입력하세요",

                    step=held_qty/10 if held_qty > 0 else 0.1,

                    key="sell_qty_input_market_col"

                )

                _sq2 = sell_qty or 0.0

                exp_recv = _sq2 * order_price

                st.caption(f"예상 정산: **{currency_symbol}{exp_recv:,.2f}**" if order_is_usd else f"예상 정산: **{currency_symbol}{exp_recv:,.0f}**")

                

                def execute_market_sell_callback():

                    sq2 = st.session_state.get("sell_qty_input_market_col") or 0.0

                    if sq2 <= 0:

                        st.session_state["trading_error_msg"] = "매도 수량을 입력해 주세요."

                    elif sq2 > held_qty:

                        st.session_state["trading_error_msg"] = "보유 수량이 부족합니다."

                    else:

                        success, msg = virtual_trading_manager.execute_market_sell(trading_user_id, selected_order_ticker, sq2, order_price, order_is_usd)

                        if success:

                            if "sell_qty_input_market_col" in st.session_state:

                                del st.session_state["sell_qty_input_market_col"]

                            st.session_state["trading_success_msg"] = msg

                        else:

                            st.session_state["trading_error_msg"] = msg

                st.button("🟢 시장가 매도 실행", key="execute_market_sell_btn_col", use_container_width=True, on_click=execute_market_sell_callback)

        # ⏳ 통합 대기 중인 지정가 주문 목록 (전체 자산)

        st.markdown("#### ⏳ 대기 중인 지정가 주문 목록")

        if not limit_orders:

            st.caption("대기 중인 지정가 주문이 없습니다.")

        else:

            def cancel_order_callback(order_id):

                success, msg = virtual_trading_manager.cancel_limit_order(trading_user_id, order_id)

                if success:

                    st.session_state["trading_toast_msg"] = msg

                else:

                    st.session_state["trading_error_msg"] = msg

            for idx, order in enumerate(limit_orders):

                o_curr = "$" if order["is_usd"] else "₩"

                col_o1, col_o2 = st.columns([0.75, 0.25])

                with col_o1:

                    st.markdown(f"📌 **{order['ticker']}** | {order['type'].split('(')[0].strip()}\n* 목표가: {o_curr}{order['target_price']:,.2f} | 수량: {order['qty']:,.4f}")

                with col_o2:

                    st.button(

                        "취소 ❌", 

                        key=f"cancel_order_col_{order['id']}_{idx}", 

                        use_container_width=True,

                        on_click=cancel_order_callback,

                        args=(order["id"],)

                    )

                            

        # 매매 이력 로그 및 리셋

        with st.expander("📜 가상 거래 내역 및 계좌 관리"):

            if history:

                history_df = pd.DataFrame(history[::-1])

                st.dataframe(history_df, use_container_width=True, hide_index=True)

            else:

                st.caption("거래 내역이 없습니다.")

            

            st.write("---")

            def reset_account_callback():

                virtual_trading_manager.reset_user_data(trading_user_id)

                st.session_state["trading_toast_msg"] = "가상 계좌가 초기 상태로 재설정되었습니다!"

            st.button(

                "🔄 가상 계좌 초기화 (자산 리셋)", 

                key="reset_virtual_trading_btn_col", 

                use_container_width=True,

                on_click=reset_account_callback

            )

# ────────────────────────────────────────────────────────────

# Sidebar & User inputs

# ────────────────────────────────────────────────────────────

with st.sidebar:

    # 👤 로그인 사용자 상태 표시 및 로그아웃 버튼

    if st.session_state.get("logged_in_user"):

        uid = st.session_state.logged_in_user

        users_db = access_manager.get_user_accounts()

        user_name = users_db.get(uid, {}).get("name", uid)

        

        col_user, col_logout = st.columns([0.6, 0.4])

        col_user.markdown(f"👤 **{user_name}** 님")

        if col_logout.button("🔓 로그아웃", key="user_logout_btn_sidebar", use_container_width=True):

            token = st.query_params.get("atoken", "")

            if token:

                access_manager.revoke_user(token)

            st.session_state.logged_in_user = None

            st.session_state._user_settings_loaded = False

            if "favorites" in st.session_state:

                del st.session_state["favorites"]

            st.toast("로그아웃 되었습니다.")

            st.rerun()

        st.write("---")

    st.markdown('<h2 style="color:#60A5FA; margin-bottom: 2px;">🎯 FiboAnalyzer</h2>', unsafe_allow_html=True)

    st.markdown('<p style="color:#64748B; font-size:12px; margin-bottom: 25px;">Multi-Timeframe Fibonacci & AI Agent</p>', unsafe_allow_html=True)

    # ────────────────────────────────────────────────────────────

    # 👤 사용자 프로필 관리 (설정 영구 저장 / 재부팅 시 복원)

    # ────────────────────────────────────────────────────────────

    with st.expander("👤 내 프로필 저장 / 불러오기", expanded=bool(st.session_state.get("_profile_is_encrypted"))):

        # 프로필 상태 배지 표시

        _pname = st.session_state.get("_profile_name", "")

        _papplied = st.session_state.get("_profile_applied", False)

        _penc = st.session_state.get("_profile_is_encrypted", False)

        if _papplied and _pname:

            st.success(f"✅ **{_pname}** 프로필이 복원되었습니다.")

        elif _penc and _pname:

            st.warning(f"🔐 **{_pname}** 프로필이 암호화되어 있습니다. 비밀번호를 입력 후 불러오기를 눌러 주세요.")

        _prof_name_in = st.text_input(

            "프로필 이름 (ID)",

            value=_pname or "myprofile",

            placeholder="내 프로필",

            key="profile_name_widget"

        )

        _prof_pwd_in = st.text_input(

            "비밀번호 (선택 — 없으면 평문 저장)",

            type="password",

            placeholder="비워두면 암호화 없음",

            key="profile_pwd_widget"

        )

        _col_load, _col_save = st.columns(2)

        # 🔐 불러오기: 암호화된 pending 데이터가 있으면 비밀번호로 복호화

        with _col_load:

            if st.button("🔐 불러오기", key="profile_load_btn", use_container_width=True):

                _pending = st.session_state.get("_profile_pending_data", "")

                if _pending:

                    _decoded = decode_profile_data(_pending, _prof_pwd_in)

                    if _decoded:

                        apply_profile_settings(_decoded)

                        st.session_state._profile_applied = True

                        st.session_state._profile_is_encrypted = False

                        st.session_state._profile_name = _prof_name_in

                        st.session_state.pop("_profile_pending_data", None)

                        st.toast("✅ 프로필이 복원되었습니다!", icon="✅")

                        st.rerun()

                    else:

                        st.error("❌ 비밀번호가 틀렸습니다.")

                else:

                    st.info("불러올 프로필이 없습니다. 먼저 저장하거나 가져오기를 사용하세요.")

        # 💾 저장하기: 현재 설정 → URL params → JS가 localStorage에 동기화

        with _col_save:

            if st.button("💾 저장하기", key="profile_save_btn", use_container_width=True):

                _settings = get_current_profile_settings()

                _encoded = encode_profile_data(_settings, _prof_pwd_in)

                st.query_params["profile_name"] = _prof_name_in

                st.query_params["profile_data"] = _encoded

                st.session_state._profile_name = _prof_name_in

                st.session_state._profile_applied = True

                st.session_state._profile_is_encrypted = bool(_prof_pwd_in)

                st.toast(f"💾 **{_prof_name_in}** 프로필이 저장되었습니다! (브라우저에 기억됨)", icon="💾")

        st.write("---")

        st.caption("📋 내보내기 코드 — 다른 기기/브라우저에서 설정 복원 시 사용")

        if st.button("📋 내보내기 코드 생성", key="profile_export_btn", use_container_width=True):

            _exp_settings = get_current_profile_settings()

            st.session_state._export_code = encode_profile_data(_exp_settings, _prof_pwd_in)

        if st.session_state.get("_export_code"):

            st.text_area(

                "아래 코드를 복사하세요:",

                value=st.session_state._export_code,

                height=80,

                key="export_code_display_widget"

            )

            st.caption("⚠️ 이 코드를 안전한 곳에 보관하세요.")

        st.write("---")

        st.caption("📥 가져오기 — 다른 기기의 내보내기 코드를 붙여넣어 설정 복원")

        _import_code = st.text_area(

            "설정 코드 붙여넣기:",

            height=80,

            key="import_code_widget",

            placeholder="enc:... 또는 raw:... 로 시작하는 코드를 붙여넣으세요"

        )

        if st.button("📥 설정 복원", key="profile_import_btn", use_container_width=True):

            if _import_code.strip():

                _imp_decoded = decode_profile_data(_import_code.strip(), _prof_pwd_in)

                if _imp_decoded:

                    apply_profile_settings(_imp_decoded)

                    # URL params에도 저장하여 localStorage 동기화 트리거

                    st.query_params["profile_name"] = _prof_name_in

                    st.query_params["profile_data"] = _import_code.strip()

                    st.session_state._profile_applied = True

                    st.session_state._profile_name = _prof_name_in

                    st.session_state._export_code = ""

                    st.toast("✅ 설정이 복원되었습니다!", icon="✅")

                    st.rerun()

                else:

                    st.error("❌ 코드를 해독하지 못했습니다. 비밀번호를 확인해 주세요.")

            else:

                st.warning("코드를 먼저 붙여넣어 주세요.")

    st.write("")

    st.subheader("🔑 API KEY 설정")

    user_api_key_val = st.session_state.get("_saved_gemini_api_key", "")

    user_api_key = st.text_input(

        "Gemini API Key",

        type="password",

        value=user_api_key_val,

        placeholder="AIzaSy... 형식의 키를 입력해 주세요.",

        help="Google AI Studio에서 발급받은 본인의 API 키를 입력해 주세요. 프로필 저장 시 함께 저장됩니다."

    )

    # API 키가 입력되거나 변경되면 세션에 기억하고 로그인 시 DB에 저장

    if user_api_key != user_api_key_val:

        st.session_state["_saved_gemini_api_key"] = user_api_key

        if st.session_state.get("logged_in_user"):

            uid = st.session_state.logged_in_user

            access_manager.save_user_settings(uid, {

                "gemini_api_key": user_api_key

            })

            

    if not user_api_key:

        st.info("💡 API 키를 입력하지 않으시면 AI 뉴스 분석 및 Q&A 기능 대신 기본 분석 템플릿(폴백)으로 출력됩니다.")

        

    st.subheader("🔍 분석 조건 설정")

    

    # 즐겨찾기 리스트

    st.write("⭐ 즐겨찾기 빠른 로드")

    for idx, (name, val) in enumerate(st.session_state.favorites):

        ko_name = get_asset_korean_name(val, name)

        display_name = f"{val}({ko_name})" if ko_name and ko_name.upper() != val.upper() else val

        # 자산 변경 클릭 시 세션 상태를 변경하고 리프레시하여 DOM 충돌 방지

        if st.button(display_name, key=f"fav_btn_{idx}_{val}", use_container_width=True):

            st.session_state.search_ticker = val

            st.rerun()

            

    # 티커 직접 검색 입력창 — placeholder로 현재 티커 표시, 입력창은 항상 공백

    search_query = st.text_input(

        "자산명 또는 티커 검색",

        value="",

        placeholder=f"현재: {st.session_state.search_ticker}  |  새 티커 입력 후 Enter",

        key="ticker_input_widget",

        help="예: BTC-USD, AAPL, 005930.KS"

    )

    # 텍스트 입력창 조작 시 세션 상태 갱신 (빈 값은 무시)

    if search_query and search_query.strip() and search_query.strip().upper() != st.session_state.search_ticker.upper():

        st.session_state.search_ticker = search_query.strip().upper()

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

    tg_btn_label = "🔔 텔레그램 알림 설정 닫기 ✖" if st.session_state.show_telegram_config else "🔔 텔레그램 알림 설정 열기 🔓"

    if st.button(tg_btn_label, key="toggle_telegram_config_btn", use_container_width=True):

        st.session_state.show_telegram_config = not st.session_state.show_telegram_config

        st.rerun()

    if st.session_state.show_telegram_config:

        with st.expander("🚨 텔레그램 알림 설정", expanded=True):

            st.subheader("🔑 텔레그램 연동 설정")

            render_telegram_config_section()

            

            st.write("---")

            render_alert_section(st.session_state.search_ticker)

    # ────────────────────────────────────────────────────────────

    # 🛡️ 관리자 패널 (접근 제어 관리) - 5회 클릭 시에만 표시됨

    # ────────────────────────────────────────────────────────────

    if st.session_state.show_admin_panel:

        st.write("---")

        col_admin_title, col_admin_close = st.columns([0.65, 0.35])

        col_admin_title.subheader("🛡️ 관리자 패널")

        if col_admin_close.button("닫기 ✖", key="close_admin_panel_btn", use_container_width=True):

            st.session_state.show_admin_panel = False

            st.session_state.admin_click_count = 0

            st.rerun()

        # 관리자 인증 세션 초기화

        if "admin_authenticated" not in st.session_state:

            st.session_state.admin_authenticated = False

        if not st.session_state.admin_authenticated:

            st.markdown("🔑 **관리자 비밀번호를 입력하세요**")

            admin_pw = st.text_input("비밀번호", type="password", key="admin_pw_input_sidebar", label_visibility="collapsed", placeholder="관리자 비밀번호")

            if st.button("🔓 인증", key="admin_auth_btn"):

                if access_manager.verify_admin_password(admin_pw):

                    st.session_state.admin_authenticated = True

                    st.rerun()

                else:

                    st.error("❌ 비밀번호가 올바르지 않습니다.")

        else:

            # 로그아웃 버튼

            col_admin_hdr, col_admin_logout = st.columns([0.7, 0.3])

            col_admin_hdr.markdown("✅ **관리자 인증됨**")

            if col_admin_logout.button("로그아웃", key="admin_logout_btn"):

                st.session_state.admin_authenticated = False

                st.rerun()

            # ── 탭 구분 ──

            tab_pending, tab_approved, tab_accounts, tab_devopt = st.tabs(["📋 대기", "✅ 승인됨", "👥 계정 관리", "⚙️ 개발자 옵션"])

            # ── 탭1: 승인 대기 목록 ──

            with tab_pending:

                pending_list = access_manager.get_pending_list()

                if not pending_list:

                    st.info("현재 승인 대기 중인 신청이 없습니다.")

                else:

                    st.markdown(f"**총 {len(pending_list)}건의 신청이 대기 중입니다.**")

                    for entry in pending_list:

                        with st.container():

                            st.markdown(f"👤 **{entry.get('name', '?')}**  |  🕐 {entry.get('requested_at', '')}")

                            st.caption(f"📝 {entry.get('reason', '')}")

                            st.code(entry.get('token', ''), language=None)

                            col_ap, col_dn = st.columns(2)

                            tok = entry.get("token", "")

                            if col_ap.button("✅ 승인", key=f"approve_{tok[:8]}"):

                                access_manager.approve_user(tok)

                                st.success(f"'{entry.get('name')}' 님을 승인했습니다.")

                                st.rerun()

                            if col_dn.button("❌ 거부", key=f"deny_{tok[:8]}"):

                                access_manager.deny_user(tok)

                                st.warning(f"'{entry.get('name')}' 님을 거부했습니다.")

                                st.rerun()

                            st.write("---")

            # ── 탭2: 승인된 사용자 목록 ──

            with tab_approved:

                approved_list = access_manager.get_approved_list()

                if not approved_list:

                    st.info("승인된 사용자가 없습니다.")

                else:

                    st.markdown(f"**총 {len(approved_list)}명이 승인되어 있습니다.**")

                    for i, tok in enumerate(approved_list):

                        uid = access_manager.get_user_id_by_token(tok)

                        col_uid, col_tok, col_rev = st.columns([0.25, 0.5, 0.25])

                        col_uid.markdown(f"**{uid}**" if uid else "*(토큰 전용)*")

                        col_tok.code(tok[:20] + "…", language=None)

                        if col_rev.button("🚫 박탈", key=f"revoke_{i}_{tok[:6]}"):

                            access_manager.revoke_user(tok)

                            st.warning("접근 권한을 박탈했습니다.")

                            st.rerun()

            # ── 탭3: 계정 관리 (아이디/비밀번호) ──

            with tab_accounts:

                st.markdown("#### 👤 새 계정 만들기")

                st.caption("아이디와 비밀번호로 로그인할 수 있는 계정을 생성합니다. 이 계정으로 로그인하면 자동으로 접근 승인됩니다.")

                with st.form("admin_create_account_form", clear_on_submit=True):
                    new_uid = st.text_input("아이디", placeholder="예) user01 (2~20자)", key="admin_new_uid")
                    new_name = st.text_input("이름 (닉네임)", placeholder="홍길동", key="admin_new_name")
                    create_btn = st.form_submit_button("✅ 계정 생성", use_container_width=True, type="primary")

                if create_btn:
                    if not new_uid.strip():
                        st.error("아이디를 입력해 주세요.")
                    elif len(new_uid.strip()) < 2:
                        st.error("아이디는 2자 이상이어야 합니다.")
                    else:
                        import secrets as _sec
                        new_tok = _sec.token_urlsafe(24)
                        # 비밀번호는 빈 값("")으로 계정 선 생성 (최초 로그인 시 등록)
                        ok_c, msg_c = access_manager.create_user_account(new_uid.strip(), "", new_tok, name=new_name.strip())
                        if ok_c:
                            st.success(msg_c)
                            st.caption(f"🔑 계정 토큰: `{new_tok}`")
                        else:
                            st.error(msg_c)

                st.write("---")

                st.markdown("#### 📋 등록된 계정 목록")

                users = access_manager.get_user_accounts()

                if not users:

                    st.info("등록된 계정이 없습니다. 위에서 새 계정을 만들어 주세요.")

                else:

                    for uid_key, uinfo in users.items():

                        col_u1, col_u2, col_u3 = st.columns([0.4, 0.35, 0.25])

                        col_u1.markdown(f"**👤 {uid_key}**")

                        col_u2.caption(f"생성: {uinfo.get('created_at','')}")

                        if col_u3.button("🗑️ 삭제", key=f"del_user_{uid_key}"):

                            access_manager.delete_user_account(uid_key)

                            st.warning(f"'{uid_key}' 계정이 삭제되었습니다.")

                            st.rerun()

                st.write("---")

                st.markdown("#### 🔑 사용자 비밀번호 초기화 (관리자)")

                st.caption("사용자가 비밀번호를 잊었을 때 관리자가 새 비밀번호를 설정합니다.")

                with st.form("admin_reset_pw_form", clear_on_submit=True):

                    reset_uid = st.text_input("아이디", placeholder="비밀번호를 초기화할 아이디", key="admin_reset_uid")

                    reset_new_pw = st.text_input("새 비밀번호", type="password", placeholder="4자 이상", key="admin_reset_new_pw")

                    reset_btn = st.form_submit_button("🔄 비밀번호 초기화", use_container_width=True)

                if reset_btn:

                    if not reset_uid.strip() or not reset_new_pw:

                        st.error("아이디와 새 비밀번호를 모두 입력해 주세요.")

                    elif len(reset_new_pw) < 4:

                        st.error("새 비밀번호는 4자 이상이어야 합니다.")

                    else:

                        db_users = access_manager.load_access_db(force_reload=True)

                        if reset_uid.strip() not in db_users.get("users", {}):

                            st.error("존재하지 않는 아이디입니다.")

                        else:

                            import hashlib as _hl

                            db_users["users"][reset_uid.strip()]["password_hash"] = _hl.sha256(reset_new_pw.encode("utf-8")).hexdigest()

                            access_manager.save_access_db(db_users)

                            st.success(f"✅ '{reset_uid.strip()}' 비밀번호가 초기화되었습니다.")

            # ── 탭4: 개발자 옵션 ──

            with tab_devopt:

                st.markdown("#### 🔐 관리자 비밀번호 변경")

                old_pw = st.text_input("현재 비밀번호", type="password", key="devopt_old_pw")

                new_pw = st.text_input("새 비밀번호", type="password", key="devopt_new_pw", placeholder="최소 6자 이상")

                new_pw2 = st.text_input("새 비밀번호 확인", type="password", key="devopt_new_pw2")

                if st.button("🔄 비밀번호 변경", key="devopt_change_pw_btn"):

                    if new_pw != new_pw2:

                        st.error("새 비밀번호가 일치하지 않습니다.")

                    else:

                        ok, msg = access_manager.change_admin_password(old_pw, new_pw)

                        if ok:

                            st.success(msg)

                            # 세션 재인증 해제 (새 비밀번호로 다시 로그인하도록)

                            st.session_state.admin_authenticated = False

                            st.rerun()

                        else:

                            st.error(msg)

                st.write("---")

                st.markdown("#### 🗄️ 접근 DB 직접 관리")

                if st.button("🔄 DB 강제 새로고침", key="devopt_reload_db_btn"):

                    access_manager.load_access_db(force_reload=True)

                    st.success("접근 DB를 디스크에서 다시 읽었습니다.")

                db = access_manager.load_access_db(force_reload=True)

                st.json(db, expanded=False)

                st.write("---")

                st.markdown("#### 🔑 내 접속 토큰 확인")

                my_token = st.query_params.get("atoken", "(토큰 없음)")

                st.code(my_token, language=None)

                st.caption("이 토큰을 직접 approved 목록에 추가하려면 아래 버튼을 누르세요.")

                if st.button("🚀 내 토큰 즉시 승인", key="devopt_self_approve_btn"):

                    if my_token and my_token != "(토큰 없음)":

                        db2 = access_manager.load_access_db(force_reload=True)

                        if my_token not in db2["approved"]:

                            db2["approved"].append(my_token)

                            # pending에서도 제거

                            db2["pending"] = [e for e in db2["pending"] if e.get("token") != my_token]

                            access_manager.save_access_db(db2)

                        st.success("✅ 토큰이 승인 목록에 추가되었습니다. 페이지를 새로고침하면 정상 접속됩니다.")

    # 사이드바 최하단 저작권 표시 및 5회 클릭 시 관리자 패널 활성화 트리거

    st.write("---")

    st.markdown("""<style> div[element-template="copyright-btn"] button { background: transparent !important; border: none !important; color: #475569 !important; padding: 0 !important; font-size: 11px !important; text-align: center !important; cursor: pointer !important; box-shadow: none !important; } div[element-template="copyright-btn"] button:hover { color: #64748B !important; } div[element-template="copyright-btn"] button:active { background: transparent !important; color: #94A3B8 !important; } </style>""", unsafe_allow_html=True)

    with st.container(key="copyright_container"):

        st.markdown('<div element-template="copyright-btn" style="text-align: center; margin-top: 15px;">', unsafe_allow_html=True)

        if st.button("© 2026 FiboAnalyzer. All rights reserved.", key="copyright_click_btn", use_container_width=True):

            st.session_state.admin_click_count += 1

            if st.session_state.admin_click_count >= 5:

                st.session_state.show_admin_panel = True

                st.toast("🛡️ 관리자 패널이 활성화되었습니다!", icon="🔓")

            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

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

def create_plotly_candlestick_chart(df, title, fib_levels=None, sma_cols=None, bb_cols=None, is_usd=True,

                                    l_levels=None, m_levels=None, s_levels=None, xs_levels=None, t_levels=None,

                                    show_l=False, show_m=False, show_s=False, show_xs=False, show_t=False):

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

    # 하방 호환성 처리

    if fib_levels and not (l_levels or m_levels or s_levels or xs_levels or t_levels):

        l_levels = fib_levels

        show_l = True

    def draw_single_scale_fib(levels, scale_prefix, base_color):

        if not levels:

            return

        fib_style_map = {

            '1.000 (고점)': ('solid', 0.5),

            '0.764 (1차 조정선)': ('dot', 0.4),

            '0.618 (첫 주요 지지선)': ('dash', 0.8),

            '0.500 (절반선)': ('dot', 0.4),

            '0.382 (두 번째 지지선)': ('dash', 0.8),

            '0.236 (최종 지지선)': ('dot', 0.4),

            '0.146 (심층 지지선)': ('dot', 0.4),

            '0.000 (저점)': ('solid', 0.5),

        }

        for label, (dash_type, opacity) in fib_style_map.items():

            val = levels.get(label)

            if val:

                short_lbl = label.split(' ')[0]

                fig.add_hline(

                    y=val,

                    line_dash=dash_type,

                    line_color=base_color,

                    line_width=1.0,

                    opacity=opacity,

                    annotation_text=f" {scale_prefix} {short_lbl} ({fmt_chart_val(val, is_usd)})",

                    annotation_position="right",

                    annotation_font_size=8,

                    annotation_font_color=base_color,

                    row=1, col=1

                )

    if show_l and l_levels:

        draw_single_scale_fib(l_levels, "L", "#29B6F6")  # 하늘색

    if show_m and m_levels:

        draw_single_scale_fib(m_levels, "M", "#FFEE58")  # 노란색

    if show_s and s_levels:

        draw_single_scale_fib(s_levels, "S", "#66BB6A")  # 초록색

    if show_xs and xs_levels:

        draw_single_scale_fib(xs_levels, "XS", "#BA68C8")  # 보라색

    if show_t and t_levels:

        draw_single_scale_fib(t_levels, "T", "#F48FB1")  # 분홍색

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

        hovermode="x unified",

        dragmode=False  # 마우스 드래그 줌/이동 방지 (오직 상단 모드바 버튼으로만 조작)

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

    # ✅ L Size: 역사적 최고점(1.0) 및 최저점(0.0) 기준으로 피보나치 계산 (전체 역사 범위 적용)

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

        # 시간 주기 기반 중첩 (Time-based Multi-Timeframe)

        # ✅ 각 분석 범위 내의 실제 최고점(1.0)과 최저점(0.0) 기준으로 피보나치 계산

        # M Size (최근 180봉)

        m_high = float(df_m['High'].max())

        m_low = float(df_m['Low'].min())

        m_levels = get_fib_levels(m_high, m_low)

        m_signal = get_entry_signal(current_price, m_levels, current_rsi)

        # S Size (최근 30봉)

        s_high = float(df_s['High'].max())

        s_low = float(df_s['Low'].min())

        s_levels = get_fib_levels(s_high, s_low)

        s_signal = get_entry_signal(current_price, s_levels, current_rsi)

        # XS Size (최근 7봉)

        xs_high = float(df_xs['High'].max())

        xs_low = float(df_xs['Low'].min())

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

    # 5. 현재가의 각 피보나치 레벨별 백분율 위치 연산

    l_pos = (current_price - l_low) / (l_high - l_low) * 100 if (l_high - l_low) > 0 else 0

    m_pos = (current_price - m_low) / (m_high - m_low) * 100 if (m_high - m_low) > 0 else 0

    s_pos = (current_price - s_low) / (s_high - s_low) * 100 if (s_high - s_low) > 0 else 0

    xs_pos = (current_price - xs_low) / (xs_high - xs_low) * 100 if (xs_high - xs_low) > 0 else 0

    t_pos = (current_price - t_low) / (t_high - t_low) * 100 if (t_high - t_low) > 0 else 0

    def get_nearest_fib_label(pos_pct):

        ratio = pos_pct / 100.0

        fib_milestones = {

            0.0: "0.000 (저점)",

            0.146: "0.146 (심층 지지선)",

            0.236: "0.236 (최종 지지선)",

            0.382: "0.382 (두 번째 지지선)",

            0.500: "0.500 (절반선)",

            0.618: "0.618 (첫 주요 지지선)",

            0.764: "0.764 (1차 조정선)",

            1.000: "1.000 (고점)"

        }

        nearest_ratio = min(fib_milestones.keys(), key=lambda x: abs(x - ratio))

        nearest_label = fib_milestones[nearest_ratio].split(' ')[0]

        return f"{pos_pct:.1f}% ({nearest_label} 부근)"

    # 6. 기술 점수 및 판단

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

    # ── 손절가(Stop Loss) 및 1~3차 목표가(Target Prices) 동적 계산 ──

    all_fib_prices = sorted(list(set(

        list(l_levels.values()) + 

        list(m_levels.values()) + 

        list(s_levels.values()) + 

        list(xs_levels.values())

    )))

    

    # 1. 손절가 계산 (황금가격보다 한 단계 아래 지지선에서 2% 추가 조정 고려)

    lower_prices = [p for p in all_fib_prices if p < best_buy * 0.999]

    if lower_prices:

        support_below = lower_prices[-1]

        stop_loss = support_below * 0.98

        stop_loss_desc = "하단 지지선 이탈(-2%) 기준"

    else:

        stop_loss = best_buy * 0.93

        stop_loss_desc = "진입가 대비 -7% 고정 비율 기준"

        

    # 2. 1~3차 목표가 계산 (스케일별 저항 매물대 매칭)

    targets = []

    

    # 1차 목표가: 단기/초단기(S/XS) 저항대 중 best_buy보다 큰 가장 가까운 가격

    s_xs_highs = sorted([p for p in set(list(s_levels.values()) + list(xs_levels.values())) if p > best_buy * 1.001])

    if s_xs_highs:

        targets.append(s_xs_highs[0])

    else:

        higher_prices = [p for p in all_fib_prices if p > best_buy * 1.001]

        targets.append(higher_prices[0] if higher_prices else best_buy * 1.05)

        

    # 2차 목표가: 중기(M) 저항대 중 1차 목표가보다 큰 가장 가까운 가격

    m_highs = sorted([p for p in m_levels.values() if p > targets[0] * 1.001])

    if m_highs:

        targets.append(m_highs[0])

    else:

        m_fallback = sorted([p for p in all_fib_prices if p > targets[0] * 1.001])

        targets.append(m_fallback[0] if m_fallback else targets[0] * 1.08)

        

    # 3차 목표가: 장기(L) 최종 목표가 (L의 전고점 또는 그 이상의 대파동 저항선)

    l_high_val = l_levels.get('1.000 (고점)', best_buy * 1.25)

    l_highs = sorted([p for p in l_levels.values() if p > targets[1] * 1.001])

    if l_highs:

        targets.append(l_highs[0])

    elif l_high_val > targets[1] * 1.001:

        targets.append(l_high_val)

    else:

        targets.append(targets[1] * 1.15)

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

    

    # 뉴스 영향 분석 제외

    news_impact_md = ""

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

| 스케일 구분 | 분석 범위 설명 | 최근 고점 (High) | 최근 저점 (Low) | 현재가 피보나치 위치 | 진입 신호 |

| :--- | :--- | :--- | :--- | :--- | :--- |

| **L Size (All-Time)** | 전체 역사 범위 | {fmt_price(l_high, rate, is_usd)} | {fmt_price(l_low, rate, is_usd)} | **{get_nearest_fib_label(l_pos)}** | **{l_signal}** |

| **M Size (Nested L)** | L의 인접 피보나치 레벨 사이 | {fmt_price(m_high, rate, is_usd)} | {fmt_price(m_low, rate, is_usd)} | **{get_nearest_fib_label(m_pos)}** | **{m_signal}** |

| **S Size (Nested M)** | M의 인접 피보나치 레벨 사이 | {fmt_price(s_high, rate, is_usd)} | {fmt_price(s_low, rate, is_usd)} | **{get_nearest_fib_label(s_pos)}** | **{s_signal}** |

| **XS Size (Nested S)** | S의 인접 피보나치 레벨 사이 | {fmt_price(xs_high, rate, is_usd)} | {fmt_price(xs_low, rate, is_usd)} | **{get_nearest_fib_label(xs_pos)}** | **{xs_signal}** |

| **Y Size (Yesterday)** | 어제 하루 범위 | {fmt_price(t_high, rate, is_usd)} | {fmt_price(t_low, rate, is_usd)} | **{get_nearest_fib_label(t_pos)}** | **{t_signal}** |

---

## 3. 타임프레임별 피보나치 상세 레벨

### 🌐 L Size (All-Time) 상세 레벨

<details open>

<summary><b>🌐 L Size 상세 레벨 표 열기/접기</b></summary>

{make_fib_markdown_table(l_levels, current_price, rate, is_usd)}

</details>

### 📅 M Size (Nested L) 상세 레벨

<details open>

<summary><b>📅 M Size 상세 레벨 표 열기/접기</b></summary>

{make_fib_markdown_table(m_levels, current_price, rate, is_usd)}

</details>

### 📆 S Size (Nested M) 상세 레벨

<details open>

<summary><b>📆 S Size 상세 레벨 표 열기/접기</b></summary>

{make_fib_markdown_table(s_levels, current_price, rate, is_usd)}

</details>

### ⏰ XS Size (Nested S) 상세 레벨

<details open>

<summary><b>⏰ XS Size 상세 레벨 표 열기/접기</b></summary>

{make_fib_markdown_table(xs_levels, current_price, rate, is_usd)}

</details>

### ⏳ Y Size (Yesterday) 상세 레벨

<details open>

<summary><b>⏳ Y Size 상세 레벨 표 열기/접기</b></summary>

{make_fib_markdown_table(t_levels, current_price, rate, is_usd)}

</details>

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

        'best_buy': best_buy,

        'stop_loss': stop_loss,

        'stop_loss_desc': stop_loss_desc,

        'target_prices': targets,

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

        'l_pos': l_pos,

        'm_pos': m_pos,

        's_pos': s_pos,

        'xs_pos': xs_pos,

        't_pos': t_pos,

        't_signal': t_signal,

        'report_markdown': full_report_content,

        'damus_data': damus_data

    }

# ────────────────────────────────────────────────────────────

# Main Page Render Layout

# ────────────────────────────────────────────────────────────

# 1. 최상단 실시간 시세 흐르는 전광판 (Marquee) 주입

marquee_html = f"""<div style="background-color: #121216; border: 1px solid #282834; border-radius: 10px; padding: 10px; overflow: hidden; white-space: nowrap; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.45);"> <marquee scrollamount="4" behavior="scroll" direction="left" onmouseover="this.stop();" onmouseout="this.start();" style="font-family:'Outfit','Noto Sans KR',sans-serif; font-size:13px;"> {get_marquee_prices(st.session_state.favorites, data_source=data_source)} </marquee> </div>"""

st.markdown(marquee_html, unsafe_allow_html=True)

# 실행 및 데이터 표시 (React DOM Crash 방지를 위해 하나의 전체 컨테이너 내에서 안전하게 가동)

main_container = st.container(key="fibo_dashboard_main_container")

with main_container:

    try:

        with st.spinner("🎯 실시간 시장 정보 및 보조지표를 연산하는 중입니다..."):

            results = fetch_and_analyze_data(st.session_state.search_ticker, market_opt, api_key=user_api_key, nest_mode=nest_mode, data_source=data_source)

            st.session_state.last_successful_ticker = results['ticker']

            # ── [투자 가이드 팝업 자동 트리거 세팅] ──

            if "last_shown_popup_ticker" not in st.session_state:

                st.session_state.last_shown_popup_ticker = None

            if "trigger_popup" not in st.session_state:

                st.session_state.trigger_popup = False

            if st.session_state.last_shown_popup_ticker != results['ticker']:

                st.session_state.trigger_popup = True

                st.session_state.last_shown_popup_ticker = results['ticker']

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

                    st.markdown(f"""<div style="background: rgba(30, 41, 59, 0.45); border-left: 5px solid #3B82F6; border-radius: 12px; padding: 16px 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.25);"> <div style="color: #94A3B8; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">🔍 분석 대상 자산 검증 (입력된 검색어: "{st.session_state.search_ticker}")</div> <div style="display: flex; align-items: baseline; margin-top: 5px;"> <span style="color: #FFFFFF; font-size: 22px; font-weight: 700;">{results['asset_name']}</span> <span style="color: #38BDF8; font-size: 16px; font-weight: 600; margin-left: 10px;">({results['ticker']})</span> </div> </div>""", unsafe_allow_html=True)

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

                            # 야후 파이낸스 영문명을 우선 한글로 변환하여 저장

                            ko_name = get_asset_korean_name(results['ticker'], results['asset_name'])

                            short_name = ko_name if ko_name else results['asset_name'].split(" ")[0]

                            if len(short_name) > 12:

                                short_name = short_name[:12]

                            st.session_state.favorites.append((short_name, results['ticker']))

                            save_favorites(st.session_state.favorites)

                            get_marquee_prices.clear()

                            st.toast(f"⭐ {results['asset_name']} 즐겨찾기 등록 완료!", icon="⭐")

                            st.rerun()

            st.write("")

            

        # ────────────────────────────────────────────────────────────

        # 1. 4구역 KPI 핵심 카드 섹션

        # ────────────────────────────────────────────────────────────

        if st.session_state.show_virtual_trading:

            left_col, right_col = st.columns([0.62, 0.38], gap="medium")

        else:

            left_col = st.container()

        

        with left_col:

            col1, col2, col3, col4 = st.columns(4)

            

            with col1:

                st.markdown(f"""<div class="dashboard-card"> <div class="kpi-title">💵 현재 실시간 가격</div> <div class="kpi-val">{fmt_price(results['current_price'], results['rate'], results['is_usd'])}</div> <div class="kpi-desc">환율 1$ = {results['rate']:,.2f}원 적용</div> </div>""", unsafe_allow_html=True)

                

            with col2:

                st.markdown(f"""<div class="dashboard-card"> <div class="kpi-title">🎯 종합 기술 점수</div> <div class="kpi-val">{results['composite_score']} / 100점</div> <div class="kpi-desc">최종 판단: {results['score_label']}</div> </div>""", unsafe_allow_html=True)

                

            with col3:

                st.markdown(f"""<div class="dashboard-card"> <div class="kpi-title">💡 최적의 분할매수(DCA) 타점</div> <div class="kpi-val">{results['best_buy_str']}</div> <div class="kpi-desc">{results.get('best_buy_desc', '역사적 피보나치 기준')}</div> </div>""", unsafe_allow_html=True)

                

            with col4:

                st.markdown(f"""<div class="dashboard-card"> <div class="kpi-title">📢 컨센서스 / 최종의견</div> <div class="kpi-val">{results['rec_ko']}</div> <div class="kpi-desc">애널리스트 및 지표 가중치 종합</div> </div>""", unsafe_allow_html=True)

            # ────────────────────────────────────────────────────────────

            # 실시간 가상매매 / AI 대화창 열기 및 닫기 토글 버튼

            # ────────────────────────────────────────────────────────────

            col_btns = st.columns(3)

            with col_btns[0]:

                vt_btn_label = "💸 가상매매 패널 닫기 ✖" if st.session_state.show_virtual_trading else "💸 가상매매 패널 열기 🔓"

                if st.button(vt_btn_label, key=f"toggle_virtual_trading_main_btn_{results['ticker']}", use_container_width=True):

                    st.session_state.show_virtual_trading = not st.session_state.show_virtual_trading

                    save_ui_settings({"show_virtual_trading": st.session_state.show_virtual_trading})

                    st.rerun()

            with col_btns[1]:

                chat_btn_label = "💬 AI 금융비서 닫기 ✖" if st.session_state.show_ai_chat else "💬 AI 금융비서 열기 🔓"

                if st.button(chat_btn_label, key=f"toggle_ai_chat_main_btn_{results['ticker']}", use_container_width=True):

                    st.session_state.show_ai_chat = not st.session_state.show_ai_chat

                    st.rerun()

            with col_btns[2]:

                if st.button("🎯 투자 가이드 팝업 열기", key=f"reopen_guide_popup_btn_{results['ticker']}", use_container_width=True):

                    st.session_state.trigger_popup = True

                    st.rerun()

            st.write("")

    

            # ────────────────────────────────────────────────────────────

            # 2. Plotly 인터랙티브 차트 시각화 섹션 (탭 적용)

            # ────────────────────────────────────────────────────────────

            st.subheader("📈 멀티 타임프레임 차트 및 피보나치 작도")

            

            # 그래프 영역 전체를 접고 펼 수 있도록 st.expander로 감쌉니다.

            with st.expander("📈 피보나치 차트 및 지표 시각화 열기/접기", expanded=True):

                # 가로형 라디오 탭 셀렉션 (모바일 줌 버그 극복을 위한 조건부 remount 렌더링)

                chart_options = [

                    "🌐 All-Time (L)", "📅 180일 스윙 (M)", "📆 30일 단기 (S)", "⏰ 7일 초단기 (XS)", "⏳ Yesterday (Y)", "💜 RSI 14", "💛 MACD", "🥔 Damus 알고리즘"

                ]

                active_chart_tab = st.radio(

                    "🎯 차트 및 피보나치 타임프레임 선택",

                    options=chart_options,

                    horizontal=True,

                    label_visibility="visible",

                    key=f"chart_tab_selector_{results['ticker']}",

                    help="""💡 피보나치 타임프레임별 설명:

- 🌐 L (장기 대파동): 전체 역사적 최고점/최저점 기준으로 분석한 대파동 피보나치 레벨입니다. 역사적인 장기 지지 및 저항 구간을 판별하는 데 사용됩니다.

- 📅 M (중기 스윙): 최근 180일 또는 L 스케일 사이의 범위를 기준으로 산출된 중기 스윙 투자 분석용 피보나치 레벨입니다.

- 📆 S (단기 변곡): 최근 30일 또는 M 스케일 사이의 중첩 범위를 기준으로 한 단기 매매용 피보나치 지지 및 저항 레벨입니다.

- ⏰ XS (초단기 극세): 최근 7~14일 또는 S 스케일 사이의 미세한 변동 범위를 기준으로 추출한 초단기 및 데이트레이딩용 피보나치 레벨입니다.

- ⏳ Y (어제 하루 범위): 어제 단 하루의 고점과 저점을 기준으로 계산한 초단기 당일 변곡 및 지지선입니다."""

                )

                

                # 피보나치 분석 모드(시간 주기 vs 가격 레벨) 접이식 활용 가이드 노출

                with st.expander("💡 피보나치 분석 모드(시간 주기 vs 가격 레벨) 활용 가이드", expanded=False):

                    st.markdown("""

                    ### 🎯 어떤 분석 모드를 신뢰하고 사용해야 하나요?

                    사이드바의 **분석 조건 설정**에서 피보나치 중첩 모드를 변경해가며 아래 가이드를 활용해 보세요.

                    

                    1. 🌐 **시간 주기 기반 중첩 (Time-based)**

                       - **추천 상황**: 상승세가 강력하거나 큰 폭의 하락 조정을 겪는 **추세적 장세**

                       - **작동 원리**: 정해진 시간 주기(180일, 30일 등) 내의 실제 최고점/최저점을 기준으로 분석합니다. 전 세계 트레이더와 대형 알고리즘들이 가장 널리 관측하는 대중적 지지선이므로 신뢰도가 높습니다.

                       

                    2. 📐 **가격 레벨 기반 수학적 중첩 (Price-based / Fractal)**

                       - **추천 상황**: 좁은 가격 구간에 갇혀 위아래로 출렁이는 지루한 **횡보 및 박스권 장세**

                       - **작동 원리**: 장기 피보나치 라인 사이의 내부 횡보 가격 범위를 정밀한 프랙탈 수학적 공식으로 쪼개어 중첩 분석합니다. 눈으로 잘 확인되지 않는 미세한 숨겨진 매물대 지지선을 찾아냅니다.

                    

                    🔥 **극강의 신뢰 타점 찾는 꿀팁**: 

                    두 모드를 번갈아 설정해 보았을 때, **양쪽 모드 모두에서 일치하거나 매우 겹쳐서 나타나는 가격대**가 있다면 그 지점이 기술적 분석상 가장 확실하고 확률이 높은 **최적의 분할매수(DCA) 진입 타점**이 됩니다.

                    """)

                # 피보나치 레벨 표시 설정 (라디오 탭 선택에 따라 자동 지정)

                show_l = (active_chart_tab == "🌐 All-Time (L)")

                show_m = (active_chart_tab == "📅 180일 스윙 (M)")

                show_s = (active_chart_tab == "📆 30일 단기 (S)")

                show_xs = (active_chart_tab == "⏰ 7일 초단기 (XS)")

                show_t = (active_chart_tab == "⏳ Yesterday (Y)")

                # 활성화된 탭의 차트만 단독 렌더링하여 탭 전환 시 줌이 강제 초기화(원복)되도록 처리

                if active_chart_tab == "🌐 All-Time (L)":

                    l_actual_high = float(results['l_high'])

                    l_actual_low = float(results['l_low'])

                    fig_l = create_plotly_candlestick_chart(

                        df=results['df_all'].copy(),

                        title=f"L Size: All-Time / 고점: {fmt_chart_val(l_actual_high, results['is_usd'])} / 저점: {fmt_chart_val(l_actual_low, results['is_usd'])} / 현재가 위치: {results['l_pos']:.1f}%",

                        is_usd=results['is_usd'],

                        l_levels=results['l_levels'], m_levels=results['m_levels'], s_levels=results['s_levels'], xs_levels=results['xs_levels'], t_levels=results['t_levels'],

                        show_l=show_l, show_m=show_m, show_s=show_s, show_xs=show_xs, show_t=show_t

                    )

                    with st.expander("🌐 All-Time (L) 피보나치 차트 접기/펼치기", expanded=True):

                        st.plotly_chart(fig_l, use_container_width=True, key=f"plotly_chart_l_size_{results['ticker']}", config={'scrollZoom': False})

                    

                elif active_chart_tab == "📅 180일 스윙 (M)":

                    m_actual_high = float(results['m_high'])

                    m_actual_low = float(results['m_low'])

                    fig_m = create_plotly_candlestick_chart(

                        df=results['df_m'],

                        title=f"M Size (최근 180봉) / 고점: {fmt_chart_val(m_actual_high, results['is_usd'])} / 저점: {fmt_chart_val(m_actual_low, results['is_usd'])} / 현재가 위치: {results['m_pos']:.1f}%",

                        sma_cols=['SMA_5', 'SMA_20'],

                        bb_cols=['BB_Upper', 'BB_Lower'],

                        is_usd=results['is_usd'],

                        l_levels=results['l_levels'], m_levels=results['m_levels'], s_levels=results['s_levels'], xs_levels=results['xs_levels'], t_levels=results['t_levels'],

                        show_l=show_l, show_m=show_m, show_s=show_s, show_xs=show_xs, show_t=show_t

                    )

                    with st.expander("📅 180일 스윙 (M) 피보나치 차트 접기/펼치기", expanded=True):

                        st.plotly_chart(fig_m, use_container_width=True, key=f"plotly_chart_m_size_{results['ticker']}", config={'scrollZoom': False})

                    

                elif active_chart_tab == "📆 30일 단기 (S)":

                    s_actual_high = float(results['s_high'])

                    s_actual_low = float(results['s_low'])

                    fig_s = create_plotly_candlestick_chart(

                        df=results['df_s'],

                        title=f"S Size (최근 30봉) / 고점: {fmt_chart_val(s_actual_high, results['is_usd'])} / 저점: {fmt_chart_val(s_actual_low, results['is_usd'])} / 현재가 위치: {results['s_pos']:.1f}%",

                        sma_cols=['SMA_5', 'SMA_20'],

                        is_usd=results['is_usd'],

                        l_levels=results['l_levels'], m_levels=results['m_levels'], s_levels=results['s_levels'], xs_levels=results['xs_levels'], t_levels=results['t_levels'],

                        show_l=show_l, show_m=show_m, show_s=show_s, show_xs=show_xs, show_t=show_t

                    )

                    with st.expander("📆 30일 단기 (S) 피보나치 차트 접기/펼치기", expanded=True):

                        st.plotly_chart(fig_s, use_container_width=True, key=f"plotly_chart_s_size_{results['ticker']}", config={'scrollZoom': False})

                    

                elif active_chart_tab == "⏰ 7일 초단기 (XS)":

                    xs_actual_high = float(results['xs_high'])

                    xs_actual_low = float(results['xs_low'])

                    fig_xs = create_plotly_candlestick_chart(

                        df=results['df_xs'],

                        title=f"XS Size (최근 14봉) / 고점: {fmt_chart_val(xs_actual_high, results['is_usd'])} / 저점: {fmt_chart_val(xs_actual_low, results['is_usd'])} / 현재가 위치: {results['xs_pos']:.1f}%",

                        is_usd=results['is_usd'],

                        l_levels=results['l_levels'], m_levels=results['m_levels'], s_levels=results['s_levels'], xs_levels=results['xs_levels'], t_levels=results['t_levels'],

                        show_l=show_l, show_m=show_m, show_s=show_s, show_xs=show_xs, show_t=show_t

                    )

                    with st.expander("⏰ 7일 초단기 (XS) 피보나치 차트 접기/펼치기", expanded=True):

                        st.plotly_chart(fig_xs, use_container_width=True, key=f"plotly_chart_xs_size_{results['ticker']}", config={'scrollZoom': False})

                    

                elif active_chart_tab == "⏳ Yesterday (Y)":

                    t_actual_high = float(results['t_high'])

                    t_actual_low = float(results['t_low'])

                    fig_t = create_plotly_candlestick_chart(

                        df=results['df_all'].tail(7).copy(),

                        title=f"Y Size (어제 하루 범위) / 고점: {fmt_chart_val(t_actual_high, results['is_usd'])} / 저점: {fmt_chart_val(t_actual_low, results['is_usd'])} / 현재가 위치: {results['t_pos']:.1f}%",

                        is_usd=results['is_usd'],

                        l_levels=results['l_levels'], m_levels=results['m_levels'], s_levels=results['s_levels'], xs_levels=results['xs_levels'], t_levels=results['t_levels'],

                        show_l=show_l, show_m=show_m, show_s=show_s, show_xs=show_xs, show_t=show_t

                    )

                    with st.expander("⏳ Yesterday (Y) 피보나치 차트 접기/펼치기", expanded=True):

                        st.plotly_chart(fig_t, use_container_width=True, key=f"plotly_chart_t_size_{results['ticker']}", config={'scrollZoom': False})

                    

                elif active_chart_tab == "💜 RSI 14":

                    fig_rsi = create_plotly_rsi_chart(results['df_m'])

                    with st.expander("💜 RSI 14 지표 접기/펼치기", expanded=True):

                        st.plotly_chart(fig_rsi, use_container_width=True, key=f"plotly_chart_rsi_14_{results['ticker']}")

                    

                elif active_chart_tab == "💛 MACD":

                    fig_macd = create_plotly_macd_chart(results['df_m'])

                    with st.expander("💛 MACD 지표 접기/펼치기", expanded=True):

                        st.plotly_chart(fig_macd, use_container_width=True, key=f"plotly_chart_macd_{results['ticker']}")

                    

                elif active_chart_tab == "🥔 Damus 알고리즘":

                    if results['damus_data']:

                        from damus import generate_damus_chart

                        fig_damus = generate_damus_chart(results['damus_data'])

                        with st.expander("🥔 Damus 알고리즘 차트 접기/펼치기", expanded=True):

                            st.plotly_chart(fig_damus, use_container_width=True, key=f"plotly_chart_damus_alg_{results['ticker']}")

                    else:

                        st.info("Damus 데이터를 생성할 수 없습니다.")

            st.write("---")

            st.subheader("📑 피보나치 중첩 분석 종합 보고서")

            st.markdown(results['report_markdown'], unsafe_allow_html=True)

    

            # ────────────────────────────────────────────────────────────

            # 4. 실시간 AI Q&A 인터랙티브 채팅 섹션 (안전한 컨테이너 감싸기) (토글식 개편)

            # ────────────────────────────────────────────────────────────

            if st.session_state.show_ai_chat:

                st.write("---")

                col_chat_title, col_chat_close = st.columns([0.8, 0.2])

                col_chat_title.subheader("🤖 AI 금융비서와 실시간 대화")

                if col_chat_close.button("대화창 닫기 ✖", key=f"close_ai_chat_btn_{results['ticker']}", use_container_width=True):

                    st.session_state.show_ai_chat = False

                    st.rerun()

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

        if st.session_state.show_virtual_trading:

            with right_col:

                col_vt_title, col_vt_close = st.columns([0.75, 0.25])

                col_vt_title.markdown("### 💸 실시간 가상매매")

                if col_vt_close.button("닫기 ✖", key="close_virtual_trading_right_btn", use_container_width=True):

                    st.session_state.show_virtual_trading = False

                    save_ui_settings({"show_virtual_trading": False})

                    st.rerun()

                render_virtual_trading_panel(results)

        # ── [투자 가이드 팝업 모달 실행 트리거] ──

        if st.session_state.get("trigger_popup", False):

            st.session_state.trigger_popup = False

            show_investment_guide(

                results['ticker'],

                results['current_price'],

                results['best_buy'],

                results['stop_loss'],

                results['stop_loss_desc'],

                results['target_prices'],

                results['score_label'],

                results['composite_score'],

                results['rate'],

                results['is_usd']

            )

    except Exception as e:

        import traceback

        print(f"[Dashboard Error] {traceback.format_exc()}")

        fallback_ticker = st.session_state.get("last_successful_ticker", "BTC-USD")

        st.session_state.search_ticker = fallback_ticker

        st.session_state.last_analyzed_ticker = fallback_ticker

        st.toast(f"⚠️ 데이터를 불러오지 못해 이전 티커({fallback_ticker})로 복구합니다.", icon="⚠️")

        st.rerun()

