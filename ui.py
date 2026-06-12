# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import pandas as pd
import yfinance as yf
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# 모듈 임포트
from config import (
    BG_DARK, BG_PANEL, BG_CARD, TEXT_LIGHT, TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN,
    load_favorites, save_favorites
)
from search import search_ticker_by_name
from analysis import (
    fmt_price, fmt_range, fmt_large_value, fmt_chart_val,
    get_fib_levels, get_entry_signal, get_t_signal, get_adjacent_l_levels,
    calculate_composite_score, score_to_label, make_fib_markdown_table,
    generate_figures, format_fundamental_report, generate_future_outlook,
    generate_fibonacci_scenario_md, generate_news_impact_md,
    generate_strategy_and_buy_price_md
)
from notifier import alert_manager
from ai_analyzer import ask_gemini_qna


# 자산명을 영어 대문자로 가공하는 헬퍼 함수
def format_asset_name(ticker):
    if not ticker:
        return ""
    t = ticker.upper()
    if t.endswith("-USD"):
        t = t[:-4]
    return t

import requests
from html.parser import HTMLParser

class YahooTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.current_row = []
        self.rows = []
        self.current_data = ""

    def handle_starttag(self, tag, attrs):
        if tag == 'tbody':
            self.in_tbody = True
        elif tag == 'tr' and self.in_tbody:
            self.in_tr = True
            self.current_row = []
        elif tag == 'td' and self.in_tr:
            self.in_td = True
            self.current_data = ""

    def handle_endtag(self, tag):
        if tag == 'tbody':
            self.in_tbody = False
        elif tag == 'tr' and self.in_tr:
            self.in_tr = False
            self.rows.append(self.current_row)
        elif tag == 'td' and self.in_td:
            self.in_td = False
            self.current_row.append(" ".join(self.current_data.split()))

    def handle_data(self, data):
        if self.in_td:
            self.current_data += data

def parse_yahoo_movers(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    results = []
    try:
        r = requests.get(url, headers=headers, timeout=10)
        parser = YahooTableParser()
        parser.feed(r.text)
        
        for row in parser.rows:
            if len(row) >= 4:
                symbol = row[0]
                change_data = row[3]
                parts = change_data.split()
                if len(parts) >= 3:
                    price_str = parts[0]
                    pct_str = parts[2].replace('(', '').replace(')', '').replace('%', '')
                    try:
                        price = float(price_str.replace(',', ''))
                        pct = float(pct_str.replace('+', '').replace(',', ''))
                        results.append((symbol, price, pct))
                    except ValueError:
                        pass
    except Exception as e:
        print(f"Error for {url}: {e}")
    return results

# 전역 Tkinter root 객체를 전달받거나 관리하기 위한 바인딩 변수
_app_root = None

def update_ui_success(results):
    if _app_root:
        _app_root.update_ui_success(results)

def update_ui_error(results):
    if _app_root:
        _app_root.update_ui_error(results)

# 4. 백그라운드 스레드 데이터 분석 처리
def run_analysis_async(search_query, market_opt="all", interval="1d", session_id=None):
    ticker = search_query
    try:
        ticker = search_ticker_by_name(search_query, market_opt)
        if ticker is None:
            market_label = {'all': '전체', 'nasdaq': '나스닥', 'binance': '바이낸스'}.get(market_opt, '전체')
            raise Exception(
                f"'{search_query}'에 해당하는 자산을 [{market_label}] 시장에서 찾지 못했습니다.\n\n"
                f"💡 검색 팁:\n"
                f"  • 영어 이름으로 검색해 보세요\n"
                f"  • 정확한 티커를 아신다면 직접 입력하세요\n"
                f"  • 다른 시장 옵션(전체/나스닥/바이낸스)을 선택해 보세요"
            )

        # 피보나치 분석용 일봉 데이터 다운로드 (간격 '1d' 영구 고정)
        df_all = yf.download(ticker, period='max', interval='1d')

        if df_all.empty:
            raise Exception(f"'{ticker}' 데이터가 존재하지 않거나 가져오는데 실패했습니다.")

        # Ticker info 및 뉴스 가져오기 (1~5년 전망 및 보고서용)
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

        if df_all.columns.nlevels > 1:
            df_all.columns = df_all.columns.droplevel(1)

        is_usd = True
        if ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'):
            is_usd = False

        rate = 1.0
        if is_usd:
            try:
                rate_df = yf.download("USDKRW=X", period="1d")
                if rate_df.columns.nlevels > 1:
                    rate_df.columns = rate_df.columns.droplevel(1)
                rate = float(rate_df['Close'].iloc[-1])
            except:
                rate = 1380.0

        # 보조지표 계산 — RSI, SMA, MACD, 볼린저밴드, 거래량
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

        # 거래량 이동평균 (20일)
        vol_ma20 = df_all['Volume'].rolling(20).mean()

        # 최근 정보
        current_price = float(df_all['Close'].iloc[-1])
        current_rsi = float(df_all['RSI_14'].iloc[-1])
        current_sma5 = float(df_all['SMA_5'].iloc[-1])
        current_sma20 = float(df_all['SMA_20'].iloc[-1])
        current_macd = float(df_all['MACD'].iloc[-1])
        current_macd_signal = float(df_all['MACD_Signal'].iloc[-1])
        current_macd_hist = float(df_all['MACD_Hist'].iloc[-1])
        current_bb_upper = float(df_all['BB_Upper'].iloc[-1])
        current_bb_lower = float(df_all['BB_Lower'].iloc[-1])
        current_bb_mid = float(df_all['BB_Mid'].iloc[-1])
        current_vol = float(df_all['Volume'].iloc[-1]) if 'Volume' in df_all.columns else 0
        vol_ma20_val = float(vol_ma20.iloc[-1]) if vol_ma20.iloc[-1] > 0 else 1
        vol_ratio = current_vol / vol_ma20_val if vol_ma20_val > 0 else 1.0

        bb_band_width = current_bb_upper - current_bb_lower
        bb_pct = (current_price - current_bb_lower) / bb_band_width if bb_band_width > 0 else 0.5

        df_52w = df_all.tail(252)
        week52_high = float(df_52w['High'].max())
        week52_low = float(df_52w['Low'].min())
        week52_position = (current_price - week52_low) / (week52_high - week52_low) * 100 if (week52_high - week52_low) > 0 else 50

        # L Size (All-Time)
        l_high = float(df_all['High'].max())
        l_low = float(df_all['Low'].min())
        l_levels = get_fib_levels(l_high, l_low)
        l_signal = get_entry_signal(current_price, l_levels, current_rsi)

        df_m = df_all.tail(180).copy()
        df_s = df_all.tail(30).copy()
        df_xs = df_all.tail(7).copy()

        nest_mode = "time"
        if _app_root and hasattr(_app_root, "nest_mode_var"):
            nest_mode = _app_root.nest_mode_var.get()

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

        # 종합 기술 점수
        signals = [l_signal, m_signal, s_signal, xs_signal]
        composite_score = calculate_composite_score(signals, current_rsi, current_macd_hist, bb_pct, vol_ratio)
        score_label = score_to_label(composite_score)

        # 전망 의견
        if current_sma5 > current_sma20:
            if current_price > current_sma5:
                trend_opinion = "단기 강세 추세 (5일/20일 이평선 정배열 및 현재가 이평선 상회)"
            else:
                trend_opinion = "단기 상승세 유지 중이나 일시적 숨고르기"
        else:
            if current_price < current_sma20:
                trend_opinion = "단기 약세 추세 (5일/20일 이평선 역배열 및 현재가 이평선 하회)"
            else:
                trend_opinion = "하락 추세에서의 기술적 반등 시도 중"

        if current_rsi >= 70:
            rsi_opinion = "RSI가 과매수 상태(70 이상)로, 단기 조정 가능성이 높습니다."
        elif current_rsi <= 30:
            rsi_opinion = "RSI가 과매도 상태(30 이하)로, 강한 기술적 반등 가능성이 있습니다."
        else:
            rsi_opinion = f"RSI 수치 {current_rsi:.1f}로 중립적인 추세를 유지하고 있습니다."

        if current_macd > current_macd_signal and current_macd_hist > 0:
            macd_opinion = f"MACD 골든크로스 형성 (MACD: {current_macd:.4f} > Signal: {current_macd_signal:.4f}) — 상승 모멘텀 확인"
        elif current_macd < current_macd_signal and current_macd_hist < 0:
            macd_opinion = f"MACD 데드크로스 형성 (MACD: {current_macd:.4f} < Signal: {current_macd_signal:.4f}) — 하락 모멘텀 주의"
        else:
            macd_opinion = f"MACD 크로스 전환 구간 (Hist: {current_macd_hist:+.4f}) — 추세 전환 여부 관찰 필요"

        if bb_pct >= 1.0:
            bb_opinion = f"볼린저 상단 밴드 돌파 ({bb_pct*100:.0f}%) — 강한 단기 과매수, 조정 경계"
        elif bb_pct >= 0.8:
            bb_opinion = f"볼린저 상단 밴드 근접 ({bb_pct*100:.0f}%) — 단기 과열 구간 진입"
        elif bb_pct <= 0.0:
            bb_opinion = f"볼린저 하단 밴드 하회 ({bb_pct*100:.0f}%) — 강한 단기 과매도, 반등 가능"
        elif bb_pct <= 0.2:
            bb_opinion = f"볼린저 하단 밴드 근접 ({bb_pct*100:.0f}%) — 과매도 구간, 분할 매수 고려"
        else:
            bb_opinion = f"볼린저밴드 중립 구간 ({bb_pct*100:.0f}%) — 뚜렷한 방향성 없음"

        if vol_ratio >= 2.0:
            vol_opinion = f"⚡ 거래량 급증 (평균 대비 {vol_ratio:.1f}배) — 현재 신호의 신뢰도 높음"
        elif vol_ratio >= 1.5:
            vol_opinion = f"📈 거래량 증가 (평균 대비 {vol_ratio:.1f}배)"
        elif vol_ratio < 0.5:
            vol_opinion = f"📉 거래량 부진 (평균 대비 {vol_ratio:.1f}배) — 현재 신호의 신뢰도 낮음"
        else:
            vol_opinion = f"거래량 보통 (평균 대비 {vol_ratio:.1f}배)"

        interval_label = {
            '1d': '일봉 (Daily)',
            '1h': '1시간봉 (Hourly)',
            '15m': '15분봉 (15 Minutes)',
            '5m': '5분봉 (5 Minutes)'
        }.get(interval, interval)

        report_text = f"""📊 {ticker} 멀티 타임프레임 분석 (달러 기준 / 원화 병기)

● 생성 일시: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
● 분석 간격: {interval_label}
● 분석 기준: L(All-time), M(L의 인접레벨), S(M의 인접레벨), XS(S레벨 중첩)
{"* 실시간 적용 환율: 1달러 = " + f"{rate:,.2f}원" if is_usd else "* 원화 표시 자산"}


-------------------------------------
1. 현재 가격 정보 (USD / KRW)
-------------------------------------
* 현재 가격: {fmt_price(current_price, rate, is_usd)}
* RSI (14) : {current_rsi:.2f} ({'과매수' if current_rsi >= 70 else '과매도' if current_rsi <= 30 else '중립'})
* 5일 이평선: {fmt_price(current_sma5, rate, is_usd)}
* 20일 이평선: {fmt_price(current_sma20, rate, is_usd)}
* 단기 추세: {trend_opinion}

-------------------------------------
2. 타임프레임별 진입 신호 요약
-------------------------------------
* L (All-Time): {l_signal}
  (범위: {fmt_range(l_low, l_high, rate, is_usd)})

* M (Nested L): {m_signal}
  (범위: {fmt_range(m_low, m_high, rate, is_usd)})

* S (Nested M): {s_signal}
  (범위: {fmt_range(s_low, s_high, rate, is_usd)})

* XS (Nested S): {xs_signal}
  (범위: {fmt_range(xs_low, xs_high, rate, is_usd)})

* T Size (Yesterday): {t_signal}
  (어제 범위: {fmt_range(t_low, t_high, rate, is_usd)})

-------------------------------------
3. 신규 보조지표 분석
-------------------------------------
* MACD    : {macd_opinion}
* 볼린저밴드: {bb_opinion}
* 거래량   : {vol_opinion}
* 52주 위치: {week52_position:.1f}% (52주 고가: {fmt_price(week52_high, rate, is_usd)} / 저가: {fmt_price(week52_low, rate, is_usd)})
"""
        # 장기 보유 DCA 타점별 가격 및 현재가 대비 이격률 연산
        l_0618 = l_levels.get('0.618 (첫 주요 지지선)', 0)
        l_0500 = l_levels.get('0.500 (절반선)', 0)
        l_0382 = l_levels.get('0.382 (두 번째 지지선)', 0)
        l_0236 = l_levels.get('0.236 (최종 지지선)', 0)
        
        def get_dca_status_str(target_price, cur_price, r, usd):
            p_str = fmt_price(target_price, r, usd)
            if target_price <= 0:
                return "분석 데이터 없음"
            if cur_price > target_price:
                diff_pct = ((target_price / cur_price) - 1) * 100
                return f"**{p_str}** (현재가 대비 **{diff_pct:.1f}%** 조정 시 도달)"
            else:
                diff_pct = ((cur_price / target_price) - 1) * 100
                return f"**{p_str}** (현재가가 이미 지지선 아래에 위치, 현재가 대비 **+{diff_pct:.1f}%** 상단에 있음)"
                
        dca_1st_str = get_dca_status_str(l_0618, current_price, rate, is_usd)
        dca_2nd_str = get_dca_status_str(l_0500, current_price, rate, is_usd)
        dca_3rd_str = get_dca_status_str(l_0382, current_price, rate, is_usd)
        dca_4th_str = get_dca_status_str(l_0236, current_price, rate, is_usd)

        # 단기/장기 전략 및 적절한 매수가 섹션 생성
        strategy_md = generate_strategy_and_buy_price_md(
            ticker, current_price, l_levels, m_levels, s_levels, xs_levels,
            current_rsi, rate, is_usd, composite_score, vol_ratio, current_macd_hist,
            week52_position, bb_pct, current_sma5, current_sma20
        )

        fib_scenario_md = generate_fibonacci_scenario_md(ticker, current_price, l_levels, m_levels, s_levels, xs_levels, current_rsi, rate, is_usd, vol_ratio, macd_opinion)
        future_outlook_md = '\n' + generate_future_outlook(ticker, info, rate)
        news_impact_md, ai_result = generate_news_impact_md(ticker, news_list)
        
        from damus import get_damus_data, generate_damus_chart, generate_damus_report_md
        damus_data = get_damus_data(ticker, is_usd, interval)
        damus_report_md = generate_damus_report_md(damus_data, rate)

        full_report_content = f"""# 📊 {ticker} 멀티 타임프레임 피보나치 중첩 분석 리포트

- **생성 일시**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
- **분석 간격**: {interval_label}
- **분석 기준**: All-time(역사적), M(L레벨 중첩), S(M레벨 중첩), XS(S레벨 중첩)

- **적용 통화**: 미국 달러 (USD / $) 및 대한민국 원화 (KRW / \\) 병기{" (적용 환율: 1달러 = " + f"{rate:,.2f}원)" if is_usd else ""}

---

## 1. 현재 시장 및 지표 요약
- **현재 가격**: {fmt_price(current_price, rate, is_usd)}
- **RSI (14)**: {current_rsi:.2f} ({'과매수' if current_rsi >= 70 else '과매도' if current_rsi <= 30 else '중립'})
- **이동평균선**: 5일선 {fmt_price(current_sma5, rate, is_usd)} / 20일선 {fmt_price(current_sma20, rate, is_usd)}
- **단기 추세**: {trend_opinion}

---

## 2. 타임프레임별 피보나치 진입점 비교

### 🎯 멀티 프레임 진입 신호 요약 (중첩 구조)
| 스케일 구분 | 분석 범위 설명 | 최근 고점 (High) | 최근 저점 (Low) | 진입 신호 |
| :--- | :--- | :--- | :--- | :--- |
| **L Size (All-Time)** | 전체 역사 범위 | {fmt_price(l_high, rate, is_usd)} | {fmt_price(l_low, rate, is_usd)} | **{l_signal}** |
| **M Size (Nested L)** | L의 인접 피보나치 레벨 사이 | {fmt_price(m_high, rate, is_usd)} | {fmt_price(m_low, rate, is_usd)} | **{m_signal}** |
| **S Size (Nested M)** | M의 인접 피보나치 레벨 사이 | {fmt_price(s_high, rate, is_usd)} | {fmt_price(s_low, rate, is_usd)} | **{s_signal}** |
| **XS Size (Nested S)** | S의 인접 피보나치 레벨 사이 | {fmt_price(xs_high, rate, is_usd)} | {fmt_price(xs_low, rate, is_usd)} | **{xs_signal}** |
| **T Size (Yesterday)** | 어제 일봉 범위 | {fmt_price(t_high, rate, is_usd)} | {fmt_price(t_low, rate, is_usd)} | **{t_signal}** |

---

## 3. 각 타임프레임별 세부 피보나치 레벨

### 🌐 L Size (All-Time) 상세 레벨
<details open>
<summary><b>🌐 L Size 상세 레벨 표 열기/접기</b></summary>
{make_fib_markdown_table(l_levels, current_price, rate, is_usd)}
</details>

### 📊 T Size (Yesterday's Range) 상세 레벨
<details open>
<summary><b>⏳ T Size 상세 레벨 표 열기/접기</b></summary>
{make_fib_markdown_table(t_levels, current_price, rate, is_usd)}
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

---

## 4. 신규 보조지표 정밀 분석
- **MACD (12/26/9)**: {macd_opinion}
- **볼린저밴드 (20일, 2σ)**: {bb_opinion}
- **거래량 (Volume) 분석**: {vol_opinion}
- **52주 가격 범위 및 위치**: 현재 52주 변동폭 내 **{week52_position:.1f}%** 지점 위치 (52주 고가: {fmt_price(week52_high, rate, is_usd)} / 저가: {fmt_price(week52_low, rate, is_usd)})

---

## 5. ★ 종합 기술 분석 점수 (Technical Score)
> ## 🎯 **종합 점수: {composite_score} / 100점**
> ### 📢 **최종 판단: {score_label}**

### 📊 항목별 평가 구성 및 가중치
* **피보나치 중첩 신호 (4개 스케일 가중합산)**: 40점 만점 (L: 16점, M: 12점, S: 8점, XS: 4점)
* **RSI (상대강도지표)**: 20점 만점
* **MACD (추세 모멘텀)**: 20점 만점
* **볼린저밴드 %B (과열 상태)**: 10점 만점
* **거래량 신뢰도 (평균 대비 증감)**: 10점 만점

---

## 6. 기술 분석 종합 전략 의견
- **이평선 및 강도지표 종합**: {rsi_opinion}
- **52주 위치 관점**: {week52_position:.1f}% 구간에 위치하여 {'고점 부담이 있는' if week52_position >= 80 else '저점 매력도가 높은' if week52_position <= 30 else '비교적 적정한'} 가격대로 분석됩니다.
{strategy_md}
{fib_scenario_md}{future_outlook_md}
---

## 11. 💸 장기 보유 투자자를 위한 최적의 분할매수(DCA) 전략
장기적인 관점에서 자산을 적립식으로 모아가는 투자자들을 위한 피보나치 기반 분할매수(DCA) 진입점 가이드라인입니다. 현재 시장 가격과 역사적 피보나치 지지 레벨의 이격도를 실시간으로 반영하여 설계되었습니다.

### ① 1차 분할 매수 타점: **L Size 0.618 지지선 부근** (장기 상승 추세의 첫 조정 국면)
- **목표 가격대**: {dca_1st_str}
- **추천 진입 비중**: 총 투자 예정 자금의 **25% ~ 30%**
- **전략적 의미**: 강력한 장기 상승 추세를 그리는 우량 자산이 역사적 최고점 대비 첫 번째로 의미 있게 숨고르기를 하는 구간입니다. 장기 상승 추세가 유지되는 한, 이 부근에서 1차적인 하방 경직성을 확보하고 재차 반등할 확률이 매우 높습니다.

### ② 2차 분할 매수 타점: **L Size 0.500 절반선 부근** (시장 평균 밸류에이션 매력 구간)
- **목표 가격대**: {dca_2nd_str}
- **추천 진입 비중**: 총 투자 예정 자금의 **35% ~ 40%**
- **전략적 의미**: 시장 참여자들의 강한 심리적 지지선이자 피보나치 되돌림의 정중앙선입니다. 고점 대비 약 50% 수준의 조정을 거친 시점으로, 장기 가치 대비 가격 매력도가 극대화되는 시기입니다. 중기 변곡점 지지 신호(M Size)와 중첩될 경우 비중을 가장 크게 확대하기 좋은 최적의 영역입니다.

### ③ 3차 분할 매수 타점: **L Size 0.382 지지선 부근** (역발상 매수 및 과매도 심층 조정 국면)
- **목표 가격대**: {dca_3rd_str}
- **추천 진입 비중**: 총 투자 예정 자금의 **20% ~ 25%**
- **전략적 의미**: 공포 심리가 시장을 지배하고 뉴스상으로 온갖 악재가 도배되는 투매(Panic Sell) 국면에서 도달하는 지점입니다. 역사적으로 강력한 저평가 상태로 간주되며, 평단가를 획기적으로 낮출 수 있는 절호의 기회입니다.

### ④ 4차(최종) 매수 타점: **L Size 0.236 이하 레드존 영역** (역사적 바닥 및 분할 매수 마지노선)
- **목표 가격대**: {dca_4th_str} 및 그 이하 영역
- **추천 진입 비중**: 남은 잔여 자금 전체 (**10% ~ 15%**)
- **전략적 의미**: 역사적 최저점 수준의 깊은 조정 상태로, 장기 투자 관점에서 자산의 본질적 가치 훼손이 없는 한 실패하기 극히 어려운 역사적 바닥 구간입니다. 극심한 시장 소외 국면에서 중장기 턴어라운드를 겨냥한 최종 물량 매집 단계입니다.

> 💡 **장기 보유 분할매수(DCA) 3대 실행 원칙**
> 1. **가격과 시간의 이중 분할**: 설정한 피보나치 지지 가격대에 도달했을 때 일시불로 전액 매수하기보다는, 해당 가격 밴드 내에서 **최소 2~4주에 걸쳐 분량을 쪼개어 매수(Time-averaging)**하는 것이 변동성 제어에 훨씬 유리합니다.
> 2. **시장 보조지표 크로스 체크**: 분할 매수 타점에 진입하는 날의 일봉 **RSI가 30 근처이거나 그 이하(과매도)**인 상태, 또는 **MACD 히스토그램의 하락 모멘텀이 눈에 띄게 둔화되는 시점(음봉 크기 감소)**에 매수 버튼을 누르면 단기 반등 신뢰도가 한층 더 극대화됩니다.
> 3. **멘탈 관리 및 포지션 빌딩**: 장기 투자는 단기 파동에 일희일비하지 않고 '평단가 관리'와 '수량 확보'에 집중하는 게임입니다. 역사적 피보나치 되돌림선은 시장의 거대한 닻(Anchor) 역할을 하므로, 계획된 분할 매수 밴드 외에 뇌동매매를 삼가십시오.

---

## 12. 피보나치 조정대(Fibonacci Retracement)의 의미와 분석적 가치��규 보조지표 정밀 분석
- **MACD (12/26/9)**: {macd_opinion}
- **볼린저밴드 (20일, 2σ)**: {bb_opinion}
- **거래량 (Volume) 분석**: {vol_opinion}
- **52주 가격 범위 및 위치**: 현재 52주 변동폭 내 **{week52_position:.1f}%** 지점 위치 (52주 고가: {fmt_price(week52_high, rate, is_usd)} / 저가: {fmt_price(week52_low, rate, is_usd)})

---

## 5. ★ 종합 기술 분석 점수 (Technical Score)
> ## 🎯 **종합 점수: {composite_score} / 100점**
> ### 📢 **최종 판단: {score_label}**

### 📊 항목별 평가 구성 및 가중치
* **피보나치 중첩 신호 (4개 스케일 가중합산)**: 40점 만점 (L: 16점, M: 12점, S: 8점, XS: 4점)
* **RSI (상대강도지표)**: 20점 만점
* **MACD (추세 모멘텀)**: 20점 만점
* **볼린저밴드 %B (과열 상태)**: 10점 만점
* **거래량 신뢰도 (평균 대비 증감)**: 10점 만점

---

## 6. 기술 분석 종합 전략 의견
- **이평선 및 강도지표 종합**: {rsi_opinion}
- **52주 위치 관점**: {week52_position:.1f}% 구간에 위치하여 {'고점 부담이 있는' if week52_position >= 80 else '저점 매력도가 높은' if week52_position <= 30 else '비교적 적정한'} 가격대로 분석됩니다.
{fib_scenario_md}
{damus_report_md}
{future_outlook_md}
---

## 9. 💸 장기 보유 투자자를 위한 최적의 분할매수(DCA) 전략
장기적인 관점에서 자산을 적립식으로 모아가는 투자자들을 위한 피보나치 기반 분할매수(DCA) 진입점 가이드라인입니다.

### ① 1차 분할 매수 타점: **L Size 0.618 지지선 부근** (고점 대비 약 38.2% 하락 조정)
- **목표 가격대**: L Size 0.618 첫 주요 지지선 ({fmt_price(l_levels.get('0.618 (첫 주요 지지선)', 0), rate, is_usd)}) 전후
- **추천 비중**: 총 투자 예정 자금의 **30%**
- **전략적 의미**: 강력한 장기 상승 추세를 그리는 우량 자산이 첫 번째로 유의미하게 숨고르기를 하는 구간입니다. 추세가 유지되는 한 이 부근에서 단기 바닥을 다진 뒤 재차 고점 돌파를 시도할 확률이 높습니다.

### ② 2차 분할 매수 타점: **L Size 0.500 절반선 및 M Size 중첩선** (고점 대비 약 50% 하락 조정)
- **목표 가격대**: L Size 0.500 절반선 ({fmt_price(l_levels.get('0.500 (절반선)', 0), rate, is_usd)}) 전후
- **추천 비중**: 총 투자 예정 자금의 **40%**
- **전략적 의미**: 시장 참여자들의 강한 심리적 마지노선이자 장기 피보나치 비율의 중심선입니다. 밸류에이션 매력이 극대화되는 시점으로, 신뢰도 높은 이평선 지지 혹은 중기 변곡점 지지가 중첩될 경우 비중을 가장 크게 늘려가기 최적인 구간입니다.

### ③ 3차 분할 매수 타점: **L Size 0.382 이하 ~ 0.146 레드존 영역** (고점 대비 약 61.8% ~ 85.4% 폭락)
- **목표 가격대**: L Size 0.382 두 번째 지지선 ({fmt_price(l_levels.get('0.382 (두 번째 지지선)', 0), rate, is_usd)}) 및 그 이하 레드존 영역
- **추천 비중**: 총 투자 예정 자금의 **30%**
- **전략적 의미**: 시장 전체의 투매(Panic Sell), 악재 도배 및 일봉 RSI 과매도(30 이하)가 중첩되는 역사적 저평가 국면입니다. 평단가를 획기적으로 낮출 수 있는 마지막 기회이며, 장기 가치 상승을 믿는 투자자에게는 최적의 역발상(Contrarian) 매수 기회입니다.

> 💡 **DCA 실행 원칙**
> - **시간의 분할**: 특정 가격대에 도달했다고 해서 한 번에 일시불 매수하기보다, 해당 라인을 터치하기 시작한 시점부터 **주 단위 혹은 월 단위로 기간을 쪼개어 매수(Time-averaging)**하는 것이 변동성 방어에 훨씬 유리합니다.
> - **지표의 확인**: 매수 시점에 일봉 **RSI가 30 근처이거나 MACD 히스토그램이 하락세가 둔화되는(연한 붉은색 또는 초록색 전환) 시점**에 분할 매수 버튼을 누르면 진입 신뢰도가 한층 더 극대화됩니다.

---

## 10. 피보나치 조정대(Fibonacci Retracement)의 의미와 분석적 가치

### 💡 피보나치 조정대란?
피보나치 조정대는 이탈리아의 수학자 피보나치가 발견한 피보나치 수열과 그 비율(황금 비율)을 기반으로 한 기술적 분석 도구입니다. 시장 가격이 급격하게 움직인 후 원래 방향으로 돌아가기 전에 **어느 지점에서 지지(Support)를 받거나 저항(Resistance)에 부딪힐 것인지를 예측**하는 데 널리 활용됩니다.

### 📊 피보나치 주요 비율의 의미
* **0.236**: 추세가 매우 강할 때 나타나는 아주 얕은 조정 구간입니다.
* **0.382**: 강한 추세 진행 중 흔히 나타나는 첫 번째 유의미한 되돌림 및 지지 구간입니다.
* **0.500 (50%)**: 공식 피보나치 비율은 아니지만 시장 참여자들의 심리적 마지노선이자 피보나치 비율 사이의 중간 지점으로 매우 중요하게 작용합니다.
* **0.618 (황금 비율)**: **가장 신뢰도가 높은 황금 비율(Golden Ratio) 구간**입니다. 강력한 지지선 역할을 하며, 이 수준에서 반들을 성공하지 못하고 하향 돌파될 경우 추세가 완전히 꺾인 것으로 간주됩니다.
* **0.786**: 심층 조정의 최종 지지선으로, 이 마저도 이탈하게 되면 이전 고점이나 저점까지 완연히 되돌아갈 확률이 매우 높아집니다.

### 🌐 멀티 타임프레임 중첩(Nested) 분석의 의미
본 분석 보고서에서 제공하는 멀티 타임프레임 피보나치 중첩 분석은 다음과 같은 강점이 있습니다:
1. **신뢰도 증폭**: 역사적(L), 중기(M), 단기(S), 초단기(XS)로 쪼개어 연산할 때, **서로 다른 스케일의 피보나치 비율들이 서로 겹치거나 인접한 구간은 매우 강력한 지지/저항선**으로 작동합니다.
2. **다각도 진입 전략**: 단기 투자자(XS, S 레벨 참고)와 장기 투자자(L, M 레벨 참고) 모두에게 적합한 합리적인 진입 가격과 이탈 포인트를 명확히 제공합니다.

{news_impact_md}---
*본 리포트는 기술적 분석 보조지표를 바탕으로 자동 생성된 정보이며, 투자 참고용으로만 사용하시기 바랍니다.*
"""
        import os as _os
        _base_dir = _os.path.dirname(_os.path.abspath(__file__))
        report_path = _os.path.join(_base_dir, f"{ticker}_technical_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(full_report_content)
            
        df_m = df_all.tail(180).copy()
        df_s = df_all.tail(30).copy()
        figs = generate_figures(ticker, df_all, df_m, df_s, l_levels, m_levels, s_levels, xs_levels, l_high, l_low, m_high, m_low, s_high, s_low, xs_high, xs_low, is_usd)
        if damus_data:
            figs['DAMUS'] = generate_damus_chart(damus_data)
        plt.close('all')  # 배치 처리 시 matplotlib 메모리 누수 방지

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

        # 향후 전망 도출
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
            if ' ' in score_label:
                rec_ko = score_label.split(' ')[1]
            else:
                rec_ko = score_label

        results = {
            'status': 'success',
            'ticker': ticker,
            'report_text': report_text,
            'figs': figs,
            'current_price': current_price,
            'current_rsi': current_rsi,
            'report_path': report_path,
            'rate': rate,
            'is_usd': is_usd,
            'df_all': df_all,
            'damus_today_1h': damus_data['df_today_1h'] if (damus_data and len(damus_data.get('df_today_1h', [])) >= 2) else (damus_data['df_1h'].tail(24) if damus_data else None),
            # 대시보드 카드용 추가 필드
            'composite_score': composite_score,
            'current_macd': current_macd,
            'current_macd_signal': current_macd_signal,
            'current_macd_hist': current_macd_hist,
            'best_buy_str': best_buy_str,
            'best_buy_desc': best_buy_desc,
            'rec_ko': rec_ko,
            # AI 및 요약 진단 데이터
            'session_id': session_id,
            'ai_result': ai_result,
            'future_outlook_md': future_outlook_md,
            'score_label': score_label,
            'trend_opinion': trend_opinion,
            'macd_opinion': macd_opinion,
            'bb_opinion': bb_opinion,
            'vol_opinion': vol_opinion
        }

        
        # 안전한 스레드 간 root.after 호출
        if _app_root:
            _app_root.root.after(0, update_ui_success, results)
        
    except Exception as e:
        results = {
            'status': 'error',
            'ticker': ticker,
            'error_msg': str(e),
            'session_id': session_id
        }
        if _app_root:
            _app_root.root.after(0, update_ui_error, results)

def start_analysis_thread(ticker, market_opt="all", interval="1d", session_id=None):
    thread = threading.Thread(target=run_analysis_async, args=(ticker, market_opt, interval, session_id))
    thread.daemon = True
    thread.start()


# 세로 스크롤 프레임 헬퍼 클래스
class ScrollableFrame(tk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, bg=kwargs.get('bg', BG_PANEL), bd=0, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=kwargs.get('bg', BG_PANEL))
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.bind('<Enter>', lambda _: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind('<Leave>', lambda _: self.canvas.unbind_all("<MouseWheel>"))
        
        self.bind("<Destroy>", lambda _: self.canvas.unbind_all("<MouseWheel>"))
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
    def _on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except:
            pass

# 5. Tkinter GUI Application 클래스 정의
class FiboAnalyzerApp:
    def __init__(self, root_window):
        global _app_root
        _app_root = self
        self.root = root_window
        self.root.title("🎯 FiboAnalyzer분석")
        self.root.geometry("1400x880")
        self.root.configure(bg=BG_DARK)
        
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0) # 하단 상태표시줄
        self.root.columnconfigure(0, weight=1)
        
        self.current_ticker = "BTC-USD"
        self.favorites = load_favorites()
        self.ticker_buttons = {}
        self.last_report_text = "분석이 완료되지 않았습니다."
        self.analysis_session_id = 0
        
        # 목표가 알림 백그라운드 모니터 시작
        alert_manager.start_monitor()
        
        self.create_layout()
        self.load_favorites_ui()
        
        self.select_tab("BTC-USD")
        
        self.show_status_bar_prices = True
        self.status_marquee_text = "📊 실시간 시세 로드 중...               "
        self.fetch_status_bar_prices_async()
        self.marquee_step()

        # ★ 현재 가격 자동 갱신 (30초마다)
        self._start_price_auto_refresh()

        # ★ 하단 시세 표시 설정 로드
        self._statusbar_show_favorites = True
        self._statusbar_show_yahoo_gainers = True
        self._statusbar_show_yahoo_losers = True
        self._statusbar_show_nasdaq_gainers = True
        self._statusbar_show_nasdaq_losers = True

        # 작업표시줄(Taskbar) 실시간 시세 스크롤을 위한 변수 및 이벤트 바인딩
        self.is_minimized = False
        self.taskbar_scroll_job = None
        self.taskbar_scroll_index = 0
        self.taskbar_text = " ★ 실시간 시세를 로드 중입니다...   "
        self.root.bind("<Unmap>", self.on_minimize)
        self.root.bind("<Map>", self.on_restore)

        # 한글 즐겨찾기 티커를 실제 티커로 마이그레이션하는 백그라운드 태스크
        def migrate_korean_favorites():
            import time
            time.sleep(2)  # 화면 로딩 완료 시간을 벌기 위해 2초 대기
            has_korean = False
            migrated = []
            for name, ticker in self.favorites:
                if any('\uac00' <= char <= '\ud7a3' for char in ticker):
                    try:
                        actual = search_ticker_by_name(ticker)
                        if actual:
                            migrated.append((name, actual))
                            has_korean = True
                            continue
                    except Exception as e:
                        print(f"[Migration Warning] {ticker} -> Ticker 변환 실패: {e}")
                migrated.append((name, ticker))
            if has_korean:
                self.favorites = migrated
                save_favorites(self.favorites)
                if self.root.winfo_exists():
                    self.root.after(0, self.load_favorites_ui)
                    self.root.after(0, self.update_favorite_button_state)
                    self.root.after(0, self.fetch_status_bar_prices_async)

        t_mig = threading.Thread(target=migrate_korean_favorites)
        t_mig.daemon = True
        t_mig.start()

    def create_layout(self):
        self.content_area = tk.Frame(self.root, bg=BG_DARK)
        self.content_area.grid(row=0, column=0, sticky='nsew')
        
        
        self.content_area.rowconfigure(0, weight=0) 
        self.content_area.rowconfigure(1, weight=1) 
        self.content_area.columnconfigure(0, weight=1)
        
        # Top Bar
        self.top_bar = tk.Frame(self.content_area, bg=BG_PANEL, height=65, padx=20)
        self.top_bar.grid(row=0, column=0, sticky='ew')
        self.top_bar.pack_propagate(False)
        
        self.title_label = tk.Label(self.top_bar, text="데이터 분석 로드 중...", font=("Segoe UI", 13, "bold"), fg='#FFFFFF', bg=BG_PANEL)

        # ── 🔍 상단 우측 티커 검색 영역 ───────────────────────────────
        search_top_frame = tk.Frame(self.top_bar, bg=BG_PANEL)
        search_top_frame.pack(side=tk.RIGHT, padx=(15, 5), pady=12)
        
        self.search_entry = tk.Entry(search_top_frame, font=("Segoe UI", 10), bg=BG_CARD, fg=TEXT_LIGHT, bd=1, relief=tk.FLAT, insertbackground='white', width=12)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 3), ipady=3)
        self.search_entry.bind("<Return>", lambda event: self.perform_search())
        
        search_btn = tk.Button(
            search_top_frame, 
            text="검색", 
            font=("Segoe UI", 9, "bold"), 
            bg='#1A73E8', 
            fg='white', 
            activebackground='#1557B0',
            bd=0, 
            padx=8, 
            pady=3,
            cursor='hand2',
            command=self.perform_search
        )
        search_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.market_var = tk.StringVar(value="all")
        rb_all = tk.Radiobutton(search_top_frame, text="전체", variable=self.market_var, value="all", bg=BG_PANEL, fg=TEXT_LIGHT, selectcolor=BG_PANEL, activebackground=BG_PANEL, activeforeground=TEXT_LIGHT, font=("Segoe UI", 8, "bold"), cursor='hand2')
        rb_nas = tk.Radiobutton(search_top_frame, text="나스닥", variable=self.market_var, value="nasdaq", bg=BG_PANEL, fg=TEXT_LIGHT, selectcolor=BG_PANEL, activebackground=BG_PANEL, activeforeground=TEXT_LIGHT, font=("Segoe UI", 8, "bold"), cursor='hand2')
        rb_bin = tk.Radiobutton(search_top_frame, text="바이낸스", variable=self.market_var, value="binance", bg=BG_PANEL, fg=TEXT_LIGHT, selectcolor=BG_PANEL, activebackground=BG_PANEL, activeforeground=TEXT_LIGHT, font=("Segoe UI", 8, "bold"), cursor='hand2')
        rb_all.pack(side=tk.LEFT, padx=2)
        rb_nas.pack(side=tk.LEFT, padx=2)
        rb_bin.pack(side=tk.LEFT, padx=2)
        
        # 피보나치 중첩 모드 선택 라디오 버튼 추가
        self.nest_mode_var = tk.StringVar(value="time")
        
        def on_nest_mode_change():
            if getattr(self, "current_ticker", None):
                self.refresh_current_ticker()
                
        tk.Label(search_top_frame, text=" | 피보나치:", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=BG_PANEL).pack(side=tk.LEFT, padx=(5, 2))
        rb_nest_time = tk.Radiobutton(search_top_frame, text="시간", variable=self.nest_mode_var, value="time", bg=BG_PANEL, fg=TEXT_LIGHT, selectcolor=BG_PANEL, activebackground=BG_PANEL, activeforeground=TEXT_LIGHT, font=("Segoe UI", 8, "bold"), cursor='hand2', command=on_nest_mode_change)
        rb_nest_price = tk.Radiobutton(search_top_frame, text="가격", variable=self.nest_mode_var, value="price", bg=BG_PANEL, fg=TEXT_LIGHT, selectcolor=BG_PANEL, activebackground=BG_PANEL, activeforeground=TEXT_LIGHT, font=("Segoe UI", 8, "bold"), cursor='hand2', command=on_nest_mode_change)
        rb_nest_time.pack(side=tk.LEFT, padx=2)
        rb_nest_price.pack(side=tk.LEFT, padx=2)
        

        
        self.add_fav_btn = tk.Button(
            self.top_bar,
            text="☆",
            font=("Segoe UI", 14, "bold"),
            bg='#333333',
            fg='#A0A0A0',
            activebackground='#444444',
            bd=0,
            padx=10,
            pady=3,
            cursor='hand2',
            command=self.toggle_favorite
        )
        self.add_fav_btn.pack(side=tk.RIGHT, padx=5, pady=18)
        
        # ── 📊 분석 메뉴 드롭다운 (메뉴 객체만 생성 — 버튼은 우측 사이드바에 배치) ─
        self.analysis_menu = tk.Menu(self.root, tearoff=0, bg=BG_PANEL, fg=TEXT_LIGHT, 
                                     activebackground=ACCENT_BLUE, activeforeground='white', bd=1, relief=tk.SOLID)
        self.analysis_menu.add_command(label="🔍 기업/자산 기본 분석", command=self.show_fundamental_analysis_popup)
        self.analysis_menu.add_command(label="📋 기술적 피보나치 분석", command=self.show_technical_analysis_popup)
        self.analysis_menu.add_command(label="💎 피보나치 알고리즘 리포트", command=self.show_damus_analysis_popup)
        self.analysis_menu.add_command(label="⛓️ 실시간 온체인 분석", command=self.show_onchain_analysis_popup)

        self.tools_menu = tk.Menu(self.root, tearoff=0, bg=BG_PANEL, fg=TEXT_LIGHT, 
                                  activebackground=ACCENT_BLUE, activeforeground='white', bd=1, relief=tk.SOLID)
        self.tools_menu.add_command(label="📈 성과 백테스트", command=self.show_backtest_popup)
        self.tools_menu.add_command(label="📊 일괄 백테스트 랭킹", command=self.show_group_backtest_popup)
        self.tools_menu.add_command(label="💡 추천 자산 포트폴리오", command=self.show_recommendations_popup)
        self.tools_menu.add_command(label="🔔 알림 설정 (텔레그램)", command=self.show_alert_settings_popup)
        self.tools_menu.add_separator()
        self.tools_menu.add_command(label="💾 모든 보고서 일괄 저장", command=self.show_save_all_reports_popup)

        # Top Bar 우측 버튼들은 제거 — 모두 우측 사이드바(_build_right_sidebar)로 이동
        
        self.status_label = tk.Label(
            self.top_bar,
            text="●",
            font=("Segoe UI", 14),
            fg='#555555',
            bg=BG_PANEL,
            anchor='w'
        )
        self.status_label.pack(side=tk.LEFT, padx=(10, 5))

        # ── 📂 즐겨찾기 자산 선택 드롭다운 ────────────────────────────
        self.fav_combo = ttk.Combobox(
            self.top_bar, 
            state="readonly", 
            style='Dark.TCombobox',
            font=("Segoe UI", 11, "bold"), 
            width=10
        )
        self.fav_combo.pack(side=tk.LEFT, padx=10)
        
        def on_fav_select(event):
            selected = self.fav_combo.get()
            if selected:
                ticker = selected
                for _, fav_ticker in self.favorites:
                    if format_asset_name(fav_ticker) == selected:
                        ticker = fav_ticker
                        break
                self.select_tab(ticker)
                
        self.fav_combo.bind("<<ComboboxSelected>>", on_fav_select)
        

        
        self.title_label.pack(side=tk.LEFT, fill=tk.X, expand=True, anchor='w')

        
        # Workspace Frame
        self.workspace = tk.Frame(self.content_area, bg=BG_DARK, padx=15, pady=15)
        self.workspace.grid(row=1, column=0, sticky='nsew')
        self.workspace.rowconfigure(0, weight=0)  # 지표 카드 행
        self.workspace.rowconfigure(1, weight=0)  # 컨트롤 바 행
        self.workspace.rowconfigure(2, weight=1)  # 차트 행
        self.workspace.columnconfigure(0, weight=0)  # 좌측 즐겨찾기 사이드바 열 (고정)
        self.workspace.columnconfigure(1, weight=1)  # 차트 열 (확장)
        self.workspace.columnconfigure(2, weight=0)  # AI 비서 열 (고정/접이식)
        self.workspace.columnconfigure(3, weight=0)  # 우측 메뉴 사이드바 열 (고정)

        # ── A. 핵심 지표 대시보드 카드 ─────────────────────────────────
        self._build_indicator_cards()

        # ── B. 좌측 즐겨찾기 사이드바 ─────────────────────────────────
        self._sidebar_collapsed = False
        self._build_sidebar()
        
        # 🤖 AI 비서 우측 패널 생성
        self._build_ai_panel()

        # ── C. 신규 컨트롤 바 생성 및 위젯 배치 ────────────────────────
        self.control_bar = tk.Frame(self.workspace, bg=BG_DARK, height=40)
        self.control_bar.grid(row=1, column=1, sticky='ew', pady=(0, 6))

        # ⏳ 봉 간격 (Timeframe) 선택 영역
        interval_top_frame = tk.Frame(self.control_bar, bg=BG_DARK)
        self.interval_var = tk.StringVar(value="1d")
        
        def on_interval_change():
            if self.current_ticker:
                self.select_tab(self.current_ticker)
                
        lbl_interval = tk.Label(interval_top_frame, text="⏳ 간격:", font=("Segoe UI", 9, "bold"), fg=TEXT_MUTED, bg=BG_DARK)
        lbl_interval.pack(side=tk.LEFT, padx=(0, 5))
        
        rb_1d = tk.Radiobutton(interval_top_frame, text="일봉", variable=self.interval_var, value="1d", command=on_interval_change,
                               bg=BG_DARK, fg=TEXT_LIGHT, selectcolor=BG_DARK, activebackground=BG_DARK, activeforeground=TEXT_LIGHT, font=("Segoe UI", 8, "bold"), cursor='hand2')
        rb_1h = tk.Radiobutton(interval_top_frame, text="1시간봉", variable=self.interval_var, value="1h", command=on_interval_change,
                               bg=BG_DARK, fg=TEXT_LIGHT, selectcolor=BG_DARK, activebackground=BG_DARK, activeforeground=TEXT_LIGHT, font=("Segoe UI", 8, "bold"), cursor='hand2')
        rb_15m = tk.Radiobutton(interval_top_frame, text="15분봉", variable=self.interval_var, value="15m", command=on_interval_change,
                                bg=BG_DARK, fg=TEXT_LIGHT, selectcolor=BG_DARK, activebackground=BG_DARK, activeforeground=TEXT_LIGHT, font=("Segoe UI", 8, "bold"), cursor='hand2')
        rb_5m = tk.Radiobutton(interval_top_frame, text="5분봉", variable=self.interval_var, value="5m", command=on_interval_change,
                               bg=BG_DARK, fg=TEXT_LIGHT, selectcolor=BG_DARK, activebackground=BG_DARK, activeforeground=TEXT_LIGHT, font=("Segoe UI", 8, "bold"), cursor='hand2')
                               
        rb_1d.pack(side=tk.LEFT, padx=2)
        rb_1h.pack(side=tk.LEFT, padx=2)
        rb_15m.pack(side=tk.LEFT, padx=2)
        rb_5m.pack(side=tk.LEFT, padx=2)
        interval_top_frame.pack(side=tk.LEFT, pady=5)

        # 🔄 보고서 갱신 버튼
        refresh_btn = tk.Button(
            self.control_bar, 
            text="🔄 보고서 갱신", 
            font=("Segoe UI", 9, "bold"), 
            bg='#1A73E8', 
            fg='white', 
            activebackground='#1557B0',
            bd=0, 
            padx=12, 
            pady=4,
            cursor='hand2',
            command=self.refresh_current_ticker
        )
        refresh_btn.pack(side=tk.RIGHT, padx=5, pady=5)


        # Chart Panel Frame
        self.chart_frame = tk.Frame(self.workspace, bg=BG_PANEL, bd=1, relief=tk.SOLID, highlightthickness=0)
        self.chart_frame.grid(row=2, column=1, sticky='nsew')

        # 사이드바 접힌 상태에서 항상 보이는 외부 토글 버튼 (chart_frame 위에 place 고정)
        self._ext_toggle_btn = tk.Button(
            self.chart_frame,
            text='►',
            font=('Segoe UI', 8, 'bold'),
            bg='#1A237E', fg='#90CAF9',
            activebackground='#283593',
            bd=0, padx=5, pady=6, cursor='hand2',
            command=self._toggle_sidebar
        )
        # 처음에는 사이드바가 펼쳐져 있으므로 숨김
        self._ext_toggle_btn.place_forget()

        # 🗂️ 우측 메뉴 사이드바 생성
        self._right_sidebar_collapsed = False
        self._build_right_sidebar()

        
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background=BG_DARK, borderwidth=0)
        style.configure('TNotebook.Tab', background=BG_PANEL, foreground=TEXT_LIGHT, borderwidth=0, padding=[15, 6], font=("Segoe UI", 10, "bold"))
        style.map('TNotebook.Tab', background=[('selected', BG_CARD)], foreground=[('selected', ACCENT_BLUE)])

        self.notebook = ttk.Notebook(self.chart_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.tabs = {}
        tab_infos = [
            ('DAMUS', 'Fibo'),
            ('L', 'L'),
            ('M', 'M'),
            ('S', 'S'),
            ('XS', '1-Day'),
            ('RSI', 'RSI 14'),
            ('MACD', '추세모멘텀')
        ]
        for key, label in tab_infos:
            frame = tk.Frame(self.notebook, bg=BG_PANEL)
            self.notebook.add(frame, text=label)
            self.tabs[key] = {
                'frame': frame,
                'canvas': None,
                'fig': None
            }

        # F. Lazy Load — 탭 전환 이벤트 바인딩
        self._last_analysis_data = None   # 최신 분석 결과 저장 (lazy render용)
        self._rendered_tabs = set()        # 이미 렌더링된 탭 key 집합
        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)

        # 최하단 상태표시줄 (Status Bar - 캔버스 전광판)
        self.status_bar = tk.Frame(self.root, bg=BG_PANEL, height=30)
        self.status_bar.grid(row=1, column=0, sticky='ew')
        self.status_bar.pack_propagate(False)
        
        self.status_canvas = tk.Canvas(self.status_bar, bg=BG_PANEL, bd=0, highlightthickness=0, height=30)
        self.status_canvas.pack(fill=tk.BOTH, expand=True)
        self.marquee_items = []
        self.marquee_paused = False
        self.status_canvas.bind('<Enter>', lambda e: self._on_status_canvas_enter(e))
        self.status_canvas.bind('<Leave>', lambda e: self._on_status_canvas_leave(e))

        # ★ 하단 상태바 우클릭 메뉴 — 표시할 종목 그룹 선택
        self._statusbar_menu = tk.Menu(self.root, tearoff=0, bg=BG_PANEL, fg=TEXT_LIGHT,
                                       activebackground=ACCENT_BLUE, activeforeground='white',
                                       bd=1, relief=tk.SOLID)
        self.status_canvas.bind('<Button-3>', self._show_statusbar_context_menu)


    def _build_indicator_cards(self):
        """핵심 지표 카드 6개를 생성합니다. 분석 완료 후 update_indicator_cards()로 값 갱신."""
        cards_frame = tk.Frame(self.workspace, bg=BG_DARK)
        cards_frame.grid(row=0, column=0, columnspan=4, sticky='ew', pady=(0, 8))
        for i in range(6):
            cards_frame.columnconfigure(i, weight=1)

        # 카드 정의: (key, label, default_val, default_color)
        card_defs = [
            ('price',     '💰 현재 가격',    '—',         '#90CAF9'),
            ('rsi',       '📉 RSI (14)',     '—',         '#B0BEC5'),
            ('score',     '⭐ 종합 점수',    '—',         '#B0BEC5'),
            ('macd',      '📊 MACD 상태',   '—',         '#B0BEC5'),
            ('buy_price', '🎯 적정 매수가',  '—',         '#B0BEC5'),
            ('outlook',   '🔮 향후 전망',    '—',         '#B0BEC5'),
        ]
        self._indicator_labels = {}
        self._indicator_val_labels = {}

        for col, (key, label, default_val, default_color) in enumerate(card_defs):
            card = tk.Frame(cards_frame, bg=BG_CARD, bd=0, relief=tk.FLAT, padx=12, pady=8)
            card.grid(row=0, column=col, sticky='ew', padx=(0 if col == 0 else 6, 0))

            lbl_title = tk.Label(card, text=label, font=('Segoe UI', 8, 'bold'),
                                 fg='#78909C', bg=BG_CARD)
            lbl_title.pack(anchor='w')

            lbl_val = tk.Label(card, text=default_val, font=('Segoe UI', 13, 'bold'),
                               fg=default_color, bg=BG_CARD)
            lbl_val.pack(anchor='w', pady=(2, 0))

            self._indicator_labels[key] = lbl_title
            self._indicator_val_labels[key] = lbl_val

    def update_indicator_cards(self, current_price, rsi, composite_score, macd_hist,
                               current_macd, current_macd_signal, rate, is_usd,
                               best_buy_str='—', rec_ko='—'):
        """분석 완료 후 핵심 지표 카드 값과 색상을 업데이트합니다."""
        # 현재 가격
        if is_usd:
            price_str = f'${current_price:,.2f}'
        else:
            price_str = f'₩{current_price:,.0f}'
        self._indicator_val_labels['price'].config(text=price_str, fg='#FFF176')

        # RSI 색상
        if rsi >= 70:
            rsi_color = '#FF5252'
            rsi_suffix = ' 🔴과매수'
        elif rsi <= 30:
            rsi_color = '#00E676'
            rsi_suffix = ' 🟢과매도'
        else:
            rsi_color = '#90CAF9'
            rsi_suffix = ''
        self._indicator_val_labels['rsi'].config(
            text=f'{rsi:.1f}{rsi_suffix}', fg=rsi_color)

        # 종합 점수 색상
        if composite_score >= 70:
            score_color = '#00E676'
        elif composite_score >= 50:
            score_color = '#FFD54F'
        else:
            score_color = '#FF5252'
        self._indicator_val_labels['score'].config(
            text=f'{composite_score:.0f} / 100', fg=score_color)

        # MACD 상태
        if macd_hist > 0 and current_macd > current_macd_signal:
            macd_str = '골든크로스 ↑'
            macd_color = '#00E676'
        elif macd_hist < 0 and current_macd < current_macd_signal:
            macd_str = '데드크로스 ↓'
            macd_color = '#FF5252'
        else:
            macd_str = '전환 구간 ～'
            macd_color = '#FFB300'
        self._indicator_val_labels['macd'].config(text=macd_str, fg=macd_color)

        # 적정 매수가
        self._indicator_val_labels['buy_price'].config(text=best_buy_str, fg='#00E676')

        # 향후 전망
        outlook_color = '#B0BEC5'
        if any(w in rec_ko for w in ['매수', 'Buy']):
            outlook_color = '#00E676'
        elif any(w in rec_ko for w in ['매도', 'Sell', '축소', 'Caution']):
            outlook_color = '#FF5252'
        elif any(w in rec_ko for w in ['보유', 'Hold', '중립', 'Neutral']):
            outlook_color = '#FFD54F'
        self._indicator_val_labels['outlook'].config(text=rec_ko, fg=outlook_color)

    # ──────────────────────────────────────────────────────────────────
    # ★ 현재 가격 자동 갱신 (30초 주기)
    # ──────────────────────────────────────────────────────────────────
    def _start_price_auto_refresh(self):
        """현재 보고 있는 종목의 가격을 30초마다 갱신합니다."""
        self._refresh_current_price()

    def _refresh_current_price(self):
        """백그라운드에서 현재 종목의 실시간 가격을 가져와 좌상단 카드에 반영합니다."""
        if not self.root.winfo_exists():
            return

        ticker = getattr(self, 'current_ticker', None)
        if not ticker:
            self.root.after(30000, self._refresh_current_price)
            return

        def worker():
            try:
                is_usd = not (ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'))
                period = '2d' if is_usd else '5d'
                df = yf.download(ticker, period=period, progress=False)
                if df.columns.nlevels > 1:
                    df.columns = df.columns.droplevel(1)
                if not df.empty:
                    close_series = df['Close'].dropna()
                    if len(close_series) >= 1:
                        curr_price = float(close_series.iloc[-1])
                        prev_price = float(close_series.iloc[-2]) if len(close_series) >= 2 else curr_price
                        pct_change = ((curr_price / prev_price) - 1) * 100 if prev_price > 0 else 0.0

                        # 환율
                        rate = 1.0
                        if is_usd:
                            try:
                                rate_df = yf.download("USDKRW=X", period="1d", progress=False)
                                if rate_df.columns.nlevels > 1:
                                    rate_df.columns = rate_df.columns.droplevel(1)
                                if not rate_df.empty:
                                    rate = float(rate_df['Close'].iloc[-1])
                            except:
                                rate = 1380.0

                        if self.root.winfo_exists():
                            self.root.after(0, lambda: self._update_price_card(
                                curr_price, pct_change, rate, is_usd))
            except Exception as e:
                print(f"[Price Auto-Refresh] {ticker} 가격 갱신 실패: {e}")

            # 다음 갱신 예약 (30초)
            if self.root.winfo_exists():
                self.root.after(0, lambda: self.root.after(30000, self._refresh_current_price))

        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    def _update_price_card(self, price, pct_change, rate, is_usd):
        """좌상단 '현재 가격' 카드의 값과 색상을 갱신합니다."""
        try:
            if is_usd:
                price_str = f'${price:,.2f}'
                krw_str = f' (₩{price * rate:,.0f})'
            else:
                price_str = f'₩{price:,.0f}'
                krw_str = ''

            # 등락률에 따른 색상
            if pct_change > 0:
                color = '#FF5252'  # 상승 빨강
                arrow = ' ▲'
            elif pct_change < 0:
                color = '#2979FF'  # 하락 파랑
                arrow = ' ▼'
            else:
                color = '#FFF176'
                arrow = ''

            display_text = f'{price_str}{krw_str}{arrow}{abs(pct_change):.1f}%'
            self._indicator_val_labels['price'].config(text=display_text, fg=color)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    # ★ 하단 상태바 우클릭 메뉴 — 표시할 종목 그룹 선택
    # ──────────────────────────────────────────────────────────────────
    def _show_statusbar_context_menu(self, event):
        """하단 상태바를 우클릭하면 표시할 종목 그룹을 선택하는 메뉴를 보여줍니다."""
        menu = self._statusbar_menu
        menu.delete(0, tk.END)

        # 체크 변수들
        def toggle_and_refresh(attr_name):
            setattr(self, attr_name, not getattr(self, attr_name))
            self.fetch_status_bar_prices_async()

        menu.add_command(
            label=f"{'✅' if self._statusbar_show_favorites else '⬜'} 즐겨찾기 종목",
            command=lambda: toggle_and_refresh('_statusbar_show_favorites')
        )
        menu.add_separator()
        menu.add_command(
            label=f"{'✅' if self._statusbar_show_yahoo_gainers else '⬜'} 야후 급등 종목",
            command=lambda: toggle_and_refresh('_statusbar_show_yahoo_gainers')
        )
        menu.add_command(
            label=f"{'✅' if self._statusbar_show_yahoo_losers else '⬜'} 야후 급락 종목",
            command=lambda: toggle_and_refresh('_statusbar_show_yahoo_losers')
        )
        menu.add_command(
            label=f"{'✅' if self._statusbar_show_nasdaq_gainers else '⬜'} 나스닥 급등 종목",
            command=lambda: toggle_and_refresh('_statusbar_show_nasdaq_gainers')
        )
        menu.add_command(
            label=f"{'✅' if self._statusbar_show_nasdaq_losers else '⬜'} 나스닥 급락 종목",
            command=lambda: toggle_and_refresh('_statusbar_show_nasdaq_losers')
        )
        menu.add_separator()
        menu.add_command(label="🔄 시세 새로고침", command=self.fetch_status_bar_prices_async)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ──────────────────────────────────────────────────────────────────
    # B. 좌측 즐겨찾기 사이드바
    # ──────────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        """160px 고정 좌측 사이드바를 생성합니다."""
        SIDEBAR_W = 160
        self._sidebar_frame = tk.Frame(
            self.workspace, bg='#131920', width=SIDEBAR_W
        )
        self._sidebar_frame.grid(row=2, column=0, sticky='ns', padx=(0, 6))
        self._sidebar_frame.grid_propagate(False)  # 너비 고정
        self._sidebar_frame.configure(width=SIDEBAR_W)

        # 사이드바 제목 + 토글 버튼
        title_bar = tk.Frame(self._sidebar_frame, bg='#1A237E')
        title_bar.pack(fill=tk.X)

        self._sidebar_title_lbl = tk.Label(
            title_bar,
            text='★ 즐겨찾기',
            font=('Segoe UI', 9, 'bold'),
            fg='#E3F2FD', bg='#1A237E'
        )
        self._sidebar_title_lbl.pack(side=tk.LEFT, padx=8, pady=6)

        toggle_btn = tk.Button(
            title_bar,
            text='◄',
            font=('Segoe UI', 8, 'bold'),
            bg='#283593', fg='#90CAF9',
            activebackground='#1A237E',
            bd=0, padx=5, pady=4, cursor='hand2',
            command=self._toggle_sidebar
        )
        toggle_btn.pack(side=tk.RIGHT)
        self._sidebar_toggle_btn = toggle_btn

        # 맨 하단 구분선 + 자산 추가 버튼
        add_frame = tk.Frame(self._sidebar_frame, bg='#131920', pady=4)
        add_frame.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(
            add_frame,
            text='+ 티커 추가',
            font=('Segoe UI', 8, 'bold'),
            bg='#1E2A3A', fg='#90CAF9',
            activebackground='#263238',
            bd=0, padx=8, pady=4, cursor='hand2',
            command=self._sidebar_add_ticker
        ).pack(fill=tk.X, padx=6)

        # AI 요약 진단 카드 패널 추가
        self.ai_summary_frame = tk.Frame(
            self._sidebar_frame,
            bg='#1A2530',
            bd=1,
            relief=tk.SOLID,
            highlightbackground='#2979FF',
            highlightthickness=1
        )
        self.ai_summary_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=(4, 6))

        # 패널 내부 요소들 배치
        lbl_title = tk.Label(
            self.ai_summary_frame,
            text='🤖 AI 실시간 진단',
            font=('Segoe UI', 9, 'bold'),
            fg='#90CAF9',
            bg='#1A2530',
            anchor='w'
        )
        lbl_title.pack(fill=tk.X, padx=8, pady=(8, 4))

        # 구분선
        sep = tk.Frame(self.ai_summary_frame, bg='#263238', height=1)
        sep.pack(fill=tk.X, padx=8, pady=2)

        self.ai_lbl_ticker_price = tk.Label(
            self.ai_summary_frame,
            text='— | —',
            font=('Segoe UI', 9, 'bold'),
            fg='#FFF176',
            bg='#1A2530',
            anchor='w'
        )
        self.ai_lbl_ticker_price.pack(fill=tk.X, padx=8, pady=2)

        self.ai_lbl_score_judgment = tk.Label(
            self.ai_summary_frame,
            text='종합 판단: —',
            font=('Segoe UI', 8, 'bold'),
            fg='#B0BEC5',
            bg='#1A2530',
            anchor='w'
        )
        self.ai_lbl_score_judgment.pack(fill=tk.X, padx=8, pady=2)

        self.ai_lbl_sentiment = tk.Label(
            self.ai_summary_frame,
            text='뉴스 감성: —',
            font=('Segoe UI', 8, 'bold'),
            fg='#B0BEC5',
            bg='#1A2530',
            anchor='w'
        )
        self.ai_lbl_sentiment.pack(fill=tk.X, padx=8, pady=2)

        self.ai_lbl_outlook = tk.Label(
            self.ai_summary_frame,
            text='단기 전망:\n분석을 대기 중입니다.',
            font=('Segoe UI', 8),
            fg='#E3F2FD',
            bg='#1A2530',
            anchor='nw',
            justify=tk.LEFT,
            wraplength=135
        )
        self.ai_lbl_outlook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        # 스크롤 가능한 자산 목록
        list_outer = tk.Frame(self._sidebar_frame, bg='#131920')
        list_outer.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self._sidebar_canvas = tk.Canvas(
            list_outer, bg='#131920', bd=0, highlightthickness=0
        )
        sidebar_sb = tk.Scrollbar(
            list_outer, orient='vertical', command=self._sidebar_canvas.yview
        )
        self._sidebar_canvas.configure(yscrollcommand=sidebar_sb.set)
        sidebar_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._sidebar_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._sidebar_list = tk.Frame(self._sidebar_canvas, bg='#131920')
        self._sidebar_canvas.create_window((0, 0), window=self._sidebar_list, anchor='nw')
        self._sidebar_list.bind(
            '<Configure>',
            lambda e: self._sidebar_canvas.configure(
                scrollregion=self._sidebar_canvas.bbox('all')
            )
        )
        self._sidebar_canvas.bind('<Enter>', lambda _: self._sidebar_canvas.bind_all(
            '<MouseWheel>', lambda e: self._sidebar_canvas.yview_scroll(int(-1*(e.delta/120)), 'units')))
        self._sidebar_canvas.bind('<Leave>', lambda _: self._sidebar_canvas.unbind_all('<MouseWheel>'))

        self._sidebar_price_data = {}   # {ticker: (price_str, pct_str, color)}
        self._sidebar_btn_frames = {}   # {ticker: frame}
        self._refresh_sidebar_list()

    def _refresh_sidebar_list(self):
        """즐겨찾기 목록을 사이드바에 다시 및닙니다."""
        for w in self._sidebar_list.winfo_children():
            w.destroy()
        self._sidebar_btn_frames.clear()

        for name, ticker in self.favorites:
            self._add_sidebar_item(name, ticker)

    def _add_sidebar_item(self, name, ticker):
        """사이드바에 자산 아이템 하나를 추가합니다."""
        is_active = (ticker == self.current_ticker)
        bg_color = '#1E3A5F' if is_active else '#1A2530'
        border_color = '#2979FF' if is_active else '#1E2A3A'

        item_frame = tk.Frame(
            self._sidebar_list,
            bg=border_color, pady=1
        )
        item_frame.pack(fill=tk.X, padx=4, pady=2)

        inner = tk.Frame(item_frame, bg=bg_color, padx=6, pady=6)
        inner.pack(fill=tk.X)

        # 자산명 버튼
        display_name = ticker.replace('-USD', '').replace('.KS', '').replace('.KQ', '')
        if len(display_name) > 7:
            display_name = display_name[:7]

        name_btn = tk.Button(
            inner,
            text=display_name,
            font=('Segoe UI', 9, 'bold'),
            fg='#E3F2FD' if is_active else '#B0BEC5',
            bg=bg_color,
            activebackground='#1E3A5F',
            bd=0, cursor='hand2', anchor='w',
            command=lambda t=ticker: self.select_tab(t)
        )
        name_btn.pack(fill=tk.X)

        # 실시간 가격 / 등락률 라벨
        price_data = self._sidebar_price_data.get(ticker, ('—', '', '#78909C'))
        price_str, pct_str, pct_color = price_data

        price_lbl = tk.Label(
            inner,
            text=price_str,
            font=('Segoe UI', 7),
            fg='#FFF176', bg=bg_color, anchor='w'
        )
        price_lbl.pack(fill=tk.X)

        pct_lbl = tk.Label(
            inner,
            text=pct_str,
            font=('Segoe UI', 7, 'bold'),
            fg=pct_color, bg=bg_color, anchor='w'
        )
        pct_lbl.pack(fill=tk.X)

        # 동적 툴팁 메시지 생성기
        def get_sidebar_tip():
            p_data = self._sidebar_price_data.get(ticker, ('—', '', '#78909C'))
            p_str, p_pct, _ = p_data
            return f"⭐ {name}\n• 티커: {ticker}\n• 가격: {p_str}\n• 등락률: {p_pct}"

        name_btn.bind("<Enter>", lambda e, func=get_sidebar_tip: self._show_widget_tooltip(e, func))
        name_btn.bind("<Leave>", self._hide_widget_tooltip)
        price_lbl.bind("<Enter>", lambda e, func=get_sidebar_tip: self._show_widget_tooltip(e, func))
        price_lbl.bind("<Leave>", self._hide_widget_tooltip)
        pct_lbl.bind("<Enter>", lambda e, func=get_sidebar_tip: self._show_widget_tooltip(e, func))
        pct_lbl.bind("<Leave>", self._hide_widget_tooltip)

        self._sidebar_btn_frames[ticker] = (item_frame, inner, name_btn, price_lbl, pct_lbl, bg_color, border_color)


    def _update_sidebar_prices(self, price_data_dict):
        """실시간 시세 데이터를 받아 사이드바 가격라벨을 갱신합니다.
        price_data_dict: {ticker_upper: (price_str, pct_str, pct_color)}
        """
        self._sidebar_price_data.update(price_data_dict)
        for ticker, data in price_data_dict.items():
            frames = self._sidebar_btn_frames.get(ticker)
            if not frames:
                continue
            _, _, _, price_lbl, pct_lbl, _, _ = frames
            price_str, pct_str, pct_color = data
            try:
                price_lbl.config(text=price_str)
                pct_lbl.config(text=pct_str, fg=pct_color)
            except Exception:
                pass

    def _toggle_sidebar(self):
        """사이드바를 접거나 펼칩니다."""
        if self._sidebar_collapsed:
            # 펼치기
            self._sidebar_frame.grid()
            self._sidebar_collapsed = False
            # 외부 토글 버튼 숨김, 내부 버튼 표시
            try:
                self._ext_toggle_btn.place_forget()
            except Exception:
                pass
        else:
            # 접기
            self._sidebar_frame.grid_remove()
            self._sidebar_collapsed = True
            # 외부 토글 버튼을 chart_frame 좌상단에 표시
            try:
                self._ext_toggle_btn.place(relx=0, rely=0, x=0, y=0, anchor='nw')
                self._ext_toggle_btn.lift()  # 최상단으로
            except Exception:
                pass

    def _build_ai_panel(self):
        """AI Q&A 비서 우측 패널을 생성합니다."""
        AI_PANEL_W = 320
        self._ai_panel_frame = tk.Frame(
            self.workspace, bg='#151B22', width=AI_PANEL_W, bd=1, relief=tk.SOLID
        )
        self._ai_panel_frame.grid_propagate(False)
        self._ai_panel_frame.configure(width=AI_PANEL_W)
        
        # Header Frame
        header = tk.Frame(self._ai_panel_frame, bg='#1A237E')
        header.pack(fill=tk.X)
        
        lbl_title = tk.Label(
            header,
            text='🤖 Gemini AI 비서',
            font=('Segoe UI', 10, 'bold'),
            fg='#E3F2FD', bg='#1A237E'
        )
        lbl_title.pack(side=tk.LEFT, padx=10, pady=8)
        
        btn_close = tk.Button(
            header,
            text='✕',
            font=('Segoe UI', 9, 'bold'),
            bg='#283593', fg='#90CAF9',
            activebackground='#1A237E',
            bd=0, padx=8, pady=4, cursor='hand2',
            command=self._toggle_ai_panel
        )
        btn_close.pack(side=tk.RIGHT)
        
        # Chat History Text Area
        chat_outer = tk.Frame(self._ai_panel_frame, bg='#151B22')
        chat_outer.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        
        self.chat_history_txt = tk.Text(
            chat_outer,
            font=('Segoe UI', 9),
            bg='#0E1117',
            fg='#D0D0D0',
            insertbackground='white',
            wrap=tk.WORD,
            bd=0,
            padx=8,
            pady=8,
            state=tk.DISABLED
        )
        chat_sb = ttk.Scrollbar(chat_outer, command=self.chat_history_txt.yview)
        self.chat_history_txt.configure(yscrollcommand=chat_sb.set)
        
        chat_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_history_txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Input Frame (Bottom)
        input_frame = tk.Frame(self._ai_panel_frame, bg='#151B22', pady=6, padx=6)
        input_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.ai_entry = tk.Entry(
            input_frame,
            font=('Segoe UI', 10),
            bg=BG_CARD,
            fg=TEXT_LIGHT,
            bd=1,
            relief=tk.FLAT,
            insertbackground='white'
        )
        self.ai_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=(0, 5))
        self.ai_entry.bind('<Return>', lambda e: self.send_ai_question())
        
        btn_send = tk.Button(
            input_frame,
            text='전송',
            font=('Segoe UI', 9, 'bold'),
            bg='#1A73E8',
            fg='white',
            activebackground='#1557B0',
            bd=0,
            padx=10,
            pady=3,
            cursor='hand2',
            command=self.send_ai_question
        )
        btn_send.pack(side=tk.RIGHT)
        
        self._ai_chat_history = []  # List of tuples: (role, text)
        self._ai_panel_collapsed = True
        
        # 초기 메시지 추가
        self._append_to_chat("Gemini", "안녕하세요! FiboAnalyzer AI 비서입니다. 🤖\n현재 차트와 기술적 분석 리포트에 대해 궁금한 점을 질문해 주세요! (예: 현재가와 피보나치 레벨의 의미는 무엇인가요?)")

    def _toggle_ai_panel(self):
        """AI 비서 패널을 접거나 펼칩니다."""
        if self._ai_panel_collapsed:
            # 펼치기
            self._ai_panel_frame.grid(row=2, column=2, sticky='ns', padx=(8, 0))
            self._ai_panel_collapsed = False
            if hasattr(self, '_right_ai_btn'):
                self._right_ai_btn.config(bg='#1A237E', fg='#90CAF9')
        else:
            # 접기
            self._ai_panel_frame.grid_remove()
            self._ai_panel_collapsed = True
            if hasattr(self, '_right_ai_btn'):
                self._right_ai_btn.config(bg='#1E2A3A', fg='#90CAF9')

    # ──────────────────────────────────────────────────────────────────
    # 🗂️ 우측 메뉴 사이드바
    # ──────────────────────────────────────────────────────────────────
    def _build_right_sidebar(self):
        """120px 고정 우측 메뉴 사이드바를 생성합니다."""
        RSB_W = 120
        self._right_sidebar_frame = tk.Frame(
            self.workspace, bg='#131920', width=RSB_W
        )
        self._right_sidebar_frame.grid(row=2, column=3, sticky='ns', padx=(6, 0))
        self._right_sidebar_frame.grid_propagate(False)
        self._right_sidebar_frame.configure(width=RSB_W)

        # ── 제목 바 ────────────────────────────────────────────────
        title_bar = tk.Frame(self._right_sidebar_frame, bg='#1A237E')
        title_bar.pack(fill=tk.X)

        tk.Label(
            title_bar,
            text='🗂️ 메뉴',
            font=('Segoe UI', 9, 'bold'),
            fg='#E3F2FD', bg='#1A237E'
        ).pack(side=tk.LEFT, padx=8, pady=6)

        rsb_toggle_btn = tk.Button(
            title_bar,
            text='►',
            font=('Segoe UI', 8, 'bold'),
            bg='#283593', fg='#90CAF9',
            activebackground='#1A237E',
            bd=0, padx=5, pady=4, cursor='hand2',
            command=self._toggle_right_sidebar
        )
        rsb_toggle_btn.pack(side=tk.RIGHT)
        self._right_sidebar_toggle_btn = rsb_toggle_btn

        # ── 메뉴 버튼 영역 ─────────────────────────────────────────
        btn_area = tk.Frame(self._right_sidebar_frame, bg='#131920')
        btn_area.pack(fill=tk.BOTH, expand=True, pady=8)

        def _btn(parent, text, command):
            b = tk.Button(
                parent, text=text,
                font=('Segoe UI', 8, 'bold'),
                bg='#1E2A3A', fg='#E3F2FD',
                activebackground='#263238',
                activeforeground='white',
                bd=0, padx=6, pady=6,
                cursor='hand2', anchor='w',
                wraplength=100,
                justify=tk.LEFT,
                command=command
            )
            b.pack(fill=tk.X, padx=5, pady=3)
            return b

        def post_analysis():
            self._right_sidebar_frame.update_idletasks()
            x = self._right_sidebar_frame.winfo_rootx()
            y = self._right_analysis_btn.winfo_rooty()
            self.analysis_menu.post(x, y)

        def post_tools():
            self._right_sidebar_frame.update_idletasks()
            x = self._right_sidebar_frame.winfo_rootx()
            y = self._right_tools_btn.winfo_rooty()
            self.tools_menu.post(x, y)

        self._right_analysis_btn = _btn(btn_area, "📊 분석 메뉴", post_analysis)
        self._right_tools_btn    = _btn(btn_area, "🛠️ 부가 기능", post_tools)
        self._right_ai_btn       = _btn(btn_area, "🤖 AI 비서",   self._toggle_ai_panel)

        # 구분선
        tk.Frame(btn_area, bg='#283593', height=1).pack(fill=tk.X, padx=5, pady=4)

        # 보고서 갱신 버튼
        _btn(btn_area, "🔄 갱신", self.refresh_current_ticker)

        # 우측 사이드바 접힌 상태에서 항상 보이는 외부 토글 버튼 (chart_frame 우상단에 place 고정)
        self._right_ext_toggle_btn = tk.Button(
            self.chart_frame,
            text='◀',
            font=('Segoe UI', 8, 'bold'),
            bg='#1A237E', fg='#90CAF9',
            activebackground='#283593',
            bd=0, padx=5, pady=6, cursor='hand2',
            command=self._toggle_right_sidebar
        )
        self._right_ext_toggle_btn.place_forget()

    def _toggle_right_sidebar(self):
        """우측 메뉴 사이드바를 접거나 펼칩니다."""
        if self._right_sidebar_collapsed:
            # 펼치기 — 원래 grid 위치를 명시적으로 지정해야 복원됨
            self._right_sidebar_frame.grid(row=2, column=3, sticky='ns', padx=(6, 0))
            self._right_sidebar_collapsed = False
            try:
                self._right_ext_toggle_btn.place_forget()
            except Exception:
                pass
        else:
            # 접기
            self._right_sidebar_frame.grid_remove()
            self._right_sidebar_collapsed = True
            try:
                # 차트 프레임 우상단에 배치
                self._right_ext_toggle_btn.place(relx=1, rely=0, x=0, y=0, anchor='ne')
                self._right_ext_toggle_btn.lift()
            except Exception:
                pass


    def _append_to_chat(self, role, text):
        """채팅창에 메시지를 추가합니다."""
        self.chat_history_txt.config(state=tk.NORMAL)
        if role == "User":
            self.chat_history_txt.insert(tk.END, f"\n[나] \n{text}\n", "user")
        elif role == "Gemini":
            self.chat_history_txt.insert(tk.END, f"\n[Gemini] 🤖\n{text}\n", "gemini")
        elif role == "System":
            self.chat_history_txt.insert(tk.END, f"\n{text}\n", "system")
        
        self.chat_history_txt.tag_configure("user", foreground="#90CAF9", font=("Segoe UI", 9, "bold"))
        self.chat_history_txt.tag_configure("gemini", foreground="#A5D6A7", font=("Segoe UI", 9, "bold"))
        self.chat_history_txt.tag_configure("system", foreground="#888888", font=("Segoe UI", 9, "italic"))
        
        self.chat_history_txt.config(state=tk.DISABLED)
        self.chat_history_txt.see(tk.END)

    def send_ai_question(self):
        """사용자 질문을 전송하고 Gemini 답변을 비동기로 요청합니다."""
        question = self.ai_entry.get().strip()
        if not question:
            return
            
        self.ai_entry.delete(0, tk.END)
        self._append_to_chat("User", question)
        self._ai_chat_history.append(("User", question))
        
        # 로딩 메시지 표시
        self.chat_history_txt.config(state=tk.NORMAL)
        self.chat_history_txt.insert(tk.END, "\n답변을 생각하는 중입니다... 🤖\n", "loading")
        self.chat_history_txt.tag_configure("loading", foreground="#A0A0A0", font=("Segoe UI", 9, "italic"))
        self.chat_history_txt.config(state=tk.DISABLED)
        self.chat_history_txt.see(tk.END)
        
        ticker = self.current_ticker
        
        # 분석 리포트 내용 가져오기
        report_text = ""
        if hasattr(self, 'last_report_text') and self.last_report_text and self.last_report_text != "분석이 완료되지 않았습니다.":
            report_text = self.last_report_text
        else:
            try:
                import os as _os
                _base = _os.path.dirname(_os.path.abspath(__file__))
                from search import search_ticker_by_name
                actual_ticker = search_ticker_by_name(ticker) or ticker
                md_path = _os.path.join(_base, f"{actual_ticker}_technical_report.md")
                if not _os.path.exists(md_path):
                    md_path = _os.path.join(_base, f"{ticker}_technical_report.md")
                if _os.path.exists(md_path):
                    with open(md_path, 'r', encoding='utf-8') as f:
                        report_text = f.read()
            except Exception as e:
                print(f"[AI Q&A] 파일 읽기 실패: {e}")
                
        if not report_text:
            report_text = f"현재 {ticker}에 대한 상세 기술 분석 보고서가 생성되지 않았습니다."
            
        def worker():
            try:
                response = ask_gemini_qna(ticker, report_text, question, self._ai_chat_history)
                self.root.after(0, lambda: self.handle_ai_response(response))
            except Exception as ex:
                self.root.after(0, lambda: self.handle_ai_response(f"오류가 발생했습니다: {str(ex)}"))
                
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
        
    def handle_ai_response(self, response):
        """Gemini 답변 완료 시 로딩 문구를 지우고 답변을 출력합니다."""
        self.chat_history_txt.config(state=tk.NORMAL)
        ranges = self.chat_history_txt.tag_ranges("loading")
        if ranges:
            try:
                self.chat_history_txt.delete(ranges[0], ranges[1])
            except Exception:
                pass
        self.chat_history_txt.config(state=tk.DISABLED)
        
        self._append_to_chat("Gemini", response)
        self._ai_chat_history.append(("Gemini", response))

    def _on_status_canvas_enter(self, event):
        """마우스가 상태표시줄 시세창에 들어오면 스크롤을 멈춥니다."""
        self.marquee_paused = True

    def _on_status_canvas_leave(self, event):
        """마우스가 상태표시줄 시세창을 벗어나면 스크롤을 재개하고 툴팁을 숨깁니다."""
        self.marquee_paused = False
        self._hide_canvas_tooltip()

    def _show_canvas_tooltip(self, event, text):
        """상태표시줄의 종목 위에 마우스를 올렸을 때 상세 정보 툴팁을 표시합니다."""
        self._hide_canvas_tooltip()
            
        self._canvas_tip_window = tw = tk.Toplevel(self.root)
        tw.wm_overrideredirect(True)
        # 마우스 위치 근처에 툴팁 배치
        tw.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 15}")
        
        label = tk.Label(
            tw, text=text, justify=tk.LEFT,
            background="#2D2D2D", foreground="#FFFFFF",
            relief=tk.SOLID, borderwidth=1,
            font=("Segoe UI", 9, "bold"), padx=8, pady=6
        )
        label.pack()

    def _hide_canvas_tooltip(self, event=None):
        """툴팁 창을 닫습니다."""
        if hasattr(self, '_canvas_tip_window') and self._canvas_tip_window:
            try:
                self._canvas_tip_window.destroy()
            except Exception:
                pass
            self._canvas_tip_window = None

    def _show_widget_tooltip(self, event, text_func):
        """사이드바 자산 항목 위에 마우스를 올렸을 때 상세 정보 툴팁을 표시합니다."""
        self._hide_widget_tooltip()
        text = text_func()
        if not text:
            return
            
        self._widget_tip_window = tw = tk.Toplevel(self.root)
        tw.wm_overrideredirect(True)
        # 마우스 위치 근처에 툴팁 배치
        tw.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 15}")
        
        label = tk.Label(
            tw, text=text, justify=tk.LEFT,
            background="#2D2D2D", foreground="#FFFFFF",
            relief=tk.SOLID, borderwidth=1,
            font=("Segoe UI", 9, "bold"), padx=8, pady=6
        )
        label.pack()

    def _hide_widget_tooltip(self, event=None):
        """사이드바 툴팁 창을 닫습니다."""
        if hasattr(self, '_widget_tip_window') and self._widget_tip_window:
            try:
                self._widget_tip_window.destroy()
            except Exception:
                pass
            self._widget_tip_window = None

    def _sidebar_add_ticker(self):
        """사이드바에서 새 티커를 입력하고 즐겨찾기에 추가합니다."""
        from tkinter import simpledialog
        val = simpledialog.askstring(
            '티커 추가', '등록할 티커 또는 자산명을 입력하세요:',
            parent=self.root
        )
        if val:
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, val.strip())
            self.perform_search()

    def load_favorites_ui(self):
        fav_names = [format_asset_name(ticker) for _, ticker in self.favorites]
        self.fav_combo['values'] = fav_names

        current_name = format_asset_name(self.current_ticker)
        if current_name in fav_names:
            self.fav_combo.set(current_name)
        else:
            self.fav_combo.set("")

        # B. 사이드바도 동기화
        try:
            self._refresh_sidebar_list()
        except Exception:
            pass

    def show_realtime_price_popup(self):
        self.fetch_status_bar_prices_async()

    def fetch_status_bar_prices_async(self):
        if not getattr(self, 'show_status_bar_prices', False):
            return
            
        def worker():
            import time
            rate = 1380.0
            try:
                rate_df = yf.download("USDKRW=X", period="1d", progress=False)
                if rate_df.columns.nlevels > 1:
                    rate_df.columns = rate_df.columns.droplevel(1)
                if not rate_df.empty:
                    rate = float(rate_df['Close'].iloc[-1])
            except Exception as e:
                print(f"[Status Bar Price] 환율 로드 실패: {e}")

            # 1. 즐겨찾기 자산들의 시세 가져오기
            prices_data = []
            fav_copy = self.favorites.copy()
            for name, ticker in fav_copy:
                try:
                    is_usd = not (ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'))
                    # 국내주식은 야후 데이터 지연이 있어 5d로 넉넉히 가져옴
                    period = '2d' if is_usd else '5d'
                    df = yf.download(ticker, period=period, progress=False)
                    if df.columns.nlevels > 1:
                        df.columns = df.columns.droplevel(1)

                    if not df.empty:
                        # NaN이 아닌 마지막 유효 Close 값 사용
                        close_series = df['Close'].dropna()
                        if len(close_series) >= 1:
                            curr_price = float(close_series.iloc[-1])
                            prev_price = float(close_series.iloc[-2]) if len(close_series) >= 2 else curr_price
                            pct_change = ((curr_price / prev_price) - 1) * 100 if prev_price > 0 else 0.0
                            prices_data.append((ticker, curr_price, pct_change, is_usd))
                        else:
                            prices_data.append((ticker, None, None, is_usd))
                    else:
                        prices_data.append((ticker, None, None, is_usd))
                except Exception as e:
                    print(f"[Status Bar Price] {ticker} 시세 로드 실패: {e}")
                    prices_data.append((ticker, None, None, not (ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'))))
                time.sleep(0.05) # 대기를 살짝 단축하여 전체 속도를 보장합니다.

            # 2. 야후 파이낸스 급등/급락 스크래핑
            yahoo_gainers = []
            yahoo_losers = []
            try:
                yahoo_gainers = parse_yahoo_movers('https://finance.yahoo.com/markets/stocks/gainers/')
                yahoo_losers = parse_yahoo_movers('https://finance.yahoo.com/markets/stocks/losers/')
            except Exception as e:
                print(f"[Status Bar Price] 야후 급등/급락 스크래핑 실패: {e}")

            # 3. 야후 전체 5종목 & 나스닥 5종목 분류
            # 나스닥 Heuristic: 티커가 4글자 또는 5글자 영어 알파벳으로만 구성된 것
            def is_nasdaq_heuristic(symbol):
                return len(symbol) in (4, 5) and symbol.isalpha()

            g_overall = yahoo_gainers[:5]
            l_overall = yahoo_losers[:5]

            g_nasdaq = [item for item in yahoo_gainers if is_nasdaq_heuristic(item[0])][:5]
            l_nasdaq = [item for item in yahoo_losers if is_nasdaq_heuristic(item[0])][:5]

            movers_data = {
                'g_overall': g_overall,
                'l_overall': l_overall,
                'g_nasdaq': g_nasdaq,
                'l_nasdaq': l_nasdaq
            }

            if self.root.winfo_exists() and getattr(self, 'show_status_bar_prices', False):
                self.root.after(0, lambda: self.update_status_bar_prices_ui(prices_data, rate, movers_data))
                
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    def update_status_bar_prices_ui(self, prices_data, rate, movers_data=None):
        if not getattr(self, 'show_status_bar_prices', False) or not self.root.winfo_exists():
            return

        # 작업표시줄 스크롤용 평문 텍스트 빌드
        taskbar_items = []
        sidebar_update = {}   # {ticker: (price_str, pct_str, color)}

        for ticker, price, pct, is_usd in prices_data:
            formatted_name = format_asset_name(ticker)
            if price is not None:
                if is_usd:
                    p_usd_str = f"${price:,.2f}" if price < 10 else f"${price:,.1f}" if price < 100 else f"${price:,.0f}"
                    krw_price = price * rate
                    p_krw_str = f"₩{krw_price:,.0f}"
                    p_str = f"{p_usd_str}({p_krw_str})"
                    sidebar_price_str = p_usd_str
                else:
                    p_str = f"₩{price:,.0f}"
                    sidebar_price_str = p_str

                emoji = "🔴" if pct > 0 else "🔵" if pct < 0 else "⚪"
                sign = "+" if pct > 0 else "-" if pct < 0 else ""
                pct_str = f"{emoji}{sign}{abs(pct):.1f}%"
                taskbar_items.append(f"{formatted_name}: {p_str} ({pct_str})")

                # B. 사이드바용 데이터 축적
                pct_color = '#FF5252' if pct > 0 else '#2979FF' if pct < 0 else '#78909C'
                sidebar_update[ticker] = (sidebar_price_str, pct_str, pct_color)
            else:
                taskbar_items.append(f"{formatted_name}: 시세오류")

        # B. 사이드바 가격 업데이트
        try:
            if sidebar_update:
                self._update_sidebar_prices(sidebar_update)
        except Exception:
            pass


        
        if taskbar_items:
            self.taskbar_text = " ★ " + " | ".join(taskbar_items) + "   "

        # 기존 스크롤 위치를 유지하기 위해 첫 번째 아이템의 현재 x 좌표를 정밀하게 역산합니다.
        current_x = None
        if self.marquee_items:
            try:
                valid_coords = []
                for idx, (item, w) in enumerate(self.marquee_items):
                    c = self.status_canvas.coords(item)
                    if c:
                        valid_coords.append((idx, c[0], w))
                
                if valid_coords:
                    # 현재 가장 왼쪽에 위치한 아이템을 기준으로 잡습니다.
                    min_idx, min_x, min_w = min(valid_coords, key=lambda x: x[1])
                    
                    # 0번째 아이템의 시작 x 좌표를 역산합니다.
                    accumulated_w = 0
                    for i in range(min_idx):
                        item_obj, w_val = self.marquee_items[i]
                        txt = self.status_canvas.itemcget(item_obj, "text")
                        # 텍스트 콘텐츠 기반으로 가격 또는 변동 정보인지 확인하여 60 패딩 더하기
                        if any(char in txt for char in ["▲", "▼", "%", "시세오류"]):
                            accumulated_w += w_val + 60
                        else:
                            accumulated_w += w_val
                    current_x = min_x - accumulated_w
            except Exception as e:
                print(f"[Status Bar] 스크롤 위치 역산 실패: {e}")
                
        if current_x is None:
            canvas_w = self.status_canvas.winfo_width() or 1400
            current_x = canvas_w
            
        self.status_canvas.delete("all")
        self.marquee_items = []
        
        if not prices_data and not (movers_data and any(movers_data.values())):
            item = self.status_canvas.create_text(
                current_x, 15, text="📊 실시간 시세 로드 중...",
                font=("Segoe UI", 9, "bold"), fill="#A0A0A0", anchor="w"
            )
            self.marquee_items.append((item, 180))
            return
            
        # 1. 즐겨찾기 자산들 렌더링 (사용자 선택에 따라)
        if getattr(self, '_statusbar_show_favorites', True):
            for ticker, price, pct, is_usd in prices_data:
                formatted_name = format_asset_name(ticker)
                ticker_name = f"📊  {formatted_name}  "
                
                item_name = self.status_canvas.create_text(
                    current_x, 15, text=ticker_name,
                    font=("Segoe UI", 9, "bold"), fill="#FFFFFF", anchor="w"
                )
                bbox = self.status_canvas.bbox(item_name)
                w_name = bbox[2] - bbox[0] if bbox else len(ticker_name)*7
                self.marquee_items.append((item_name, w_name))
                current_x += w_name
                
                if price is not None:
                    if is_usd:
                        p_usd_str = f"${price:,.2f}" if price < 10 else f"${price:,.1f}" if price < 100 else f"${price:,.0f}"
                        krw_price = price * rate
                        p_krw_str = f"₩{krw_price:,.0f}"
                        p_str = f"{p_usd_str} ({p_krw_str})"
                    else:
                        p_str = f"₩{price:,.0f}"
                        
                    sign = "▲" if pct > 0 else "▼" if pct < 0 else ""
                    pct_str = f"{sign}{abs(pct):.1f}%"
                    price_text = f"{p_str}  {pct_str}"
                    color = "#FF5252" if pct > 0 else "#2979FF" if pct < 0 else "#FFFFFF"
                else:
                    p_str = "시세오류"
                    pct_str = ""
                    price_text = "시세오류"
                    color = "#888888"
                    
                item_price = self.status_canvas.create_text(
                    current_x, 15, text=price_text,
                    font=("Segoe UI", 9, "bold"), fill=color, anchor="w"
                )
                bbox = self.status_canvas.bbox(item_price)
                w_price = bbox[2] - bbox[0] if bbox else len(price_text)*7
                self.marquee_items.append((item_price, w_price))
                
                # 마우스 오버 툴팁 생성
                tip_msg = f"📊 [{formatted_name}]\n• 현재가: {p_str}\n• 전일대비: {pct_str}"
                self.status_canvas.tag_bind(item_name, "<Enter>", lambda e, msg=tip_msg: self._show_canvas_tooltip(e, msg))
                self.status_canvas.tag_bind(item_name, "<Leave>", self._hide_canvas_tooltip)
                self.status_canvas.tag_bind(item_price, "<Enter>", lambda e, msg=tip_msg: self._show_canvas_tooltip(e, msg))
                self.status_canvas.tag_bind(item_price, "<Leave>", self._hide_canvas_tooltip)
                
                current_x += w_price + 60

        # 2. 야후 및 나스닥 Movers 데이터 렌더링
        if movers_data:
            def render_mover_group(title, list_data, title_color="#FFD54F"):
                nonlocal current_x
                if not list_data:
                    return
                # 그룹 타이틀 출력
                title_text = f"  {title}  "
                item_title = self.status_canvas.create_text(
                    current_x, 15, text=title_text,
                    font=("Segoe UI", 9, "bold"), fill=title_color, anchor="w"
                )
                bbox = self.status_canvas.bbox(item_title)
                w_title = bbox[2] - bbox[0] if bbox else len(title_text)*7
                self.marquee_items.append((item_title, w_title))
                current_x += w_title

                # 그룹 내 개별 종목 출력
                for symbol, price, pct in list_data:
                    symbol_text = f" {symbol} "
                    item_sym = self.status_canvas.create_text(
                        current_x, 15, text=symbol_text,
                        font=("Segoe UI", 9, "bold"), fill="#FFFFFF", anchor="w"
                    )
                    bbox = self.status_canvas.bbox(item_sym)
                    w_sym = bbox[2] - bbox[0] if bbox else len(symbol_text)*7
                    self.marquee_items.append((item_sym, w_sym))
                    current_x += w_sym

                    sign = "▲" if pct > 0 else "▼" if pct < 0 else ""
                    pct_val = f"{sign}{abs(pct):.1f}%"
                    color = "#FF5252" if pct > 0 else "#2979FF" if pct < 0 else "#FFFFFF"
                    
                    # KRW 변환 가격 포함
                    krw_price = price * rate
                    p_usd_str = f"${price:,.2f}"
                    p_krw_str = f"₩{krw_price:,.0f}"
                    price_val_text = f"{p_usd_str}({pct_val})"
                    
                    item_pct = self.status_canvas.create_text(
                        current_x, 15, text=price_val_text,
                        font=("Segoe UI", 9, "bold"), fill=color, anchor="w"
                    )
                    bbox = self.status_canvas.bbox(item_pct)
                    w_pct = bbox[2] - bbox[0] if bbox else len(price_val_text)*7
                    self.marquee_items.append((item_pct, w_pct))
                    
                    # 마우스 오버 툴팁 생성
                    mover_tip_msg = f"{title} [{symbol}]\n• 현재가: {p_usd_str} ({p_krw_str})\n• 등락률: {pct_val}"
                    self.status_canvas.tag_bind(item_sym, "<Enter>", lambda e, msg=mover_tip_msg: self._show_canvas_tooltip(e, msg))
                    self.status_canvas.tag_bind(item_sym, "<Leave>", self._hide_canvas_tooltip)
                    self.status_canvas.tag_bind(item_pct, "<Enter>", lambda e, msg=mover_tip_msg: self._show_canvas_tooltip(e, msg))
                    self.status_canvas.tag_bind(item_pct, "<Leave>", self._hide_canvas_tooltip)
                    
                    # 60px 공백 패딩 부여
                    current_x += w_pct + 60


            # ★ 사용자 선택에 따라 각 그룹을 표시/숨김
            if getattr(self, '_statusbar_show_yahoo_gainers', True):
                render_mover_group("[야후급등]", movers_data.get('g_overall', []), "#FFCA28")
            if getattr(self, '_statusbar_show_yahoo_losers', True):
                render_mover_group("[야후급락]", movers_data.get('l_overall', []), "#64B5F6")
            if getattr(self, '_statusbar_show_nasdaq_gainers', True):
                render_mover_group("[나스닥급등]", movers_data.get('g_nasdaq', []), "#FF8F00")
            if getattr(self, '_statusbar_show_nasdaq_losers', True):
                render_mover_group("[나스닥급락]", movers_data.get('l_nasdaq', []), "#1E88E5")

        if getattr(self, 'show_status_bar_prices', False):
            if hasattr(self, '_status_after_id'):
                try:
                    self.root.after_cancel(self._status_after_id)
                except:
                    pass
            self._status_after_id = self.root.after(60_000, self.fetch_status_bar_prices_async)

    def marquee_step(self):
        if not getattr(self, 'show_status_bar_prices', False) or not self.root.winfo_exists():
            return
            
        if not getattr(self, 'marquee_paused', False):
            dx = -1
            for item, w in self.marquee_items:
                self.status_canvas.move(item, dx, 0)
                
            all_coords = []
            for item, w in self.marquee_items:
                c = self.status_canvas.coords(item)
                if c:
                    all_coords.append((item, c[0], w))
                    
            if all_coords:
                max_right = max(x + w for _, x, w in all_coords)
                
                for item, x, w in all_coords:
                    if x + w < -10:
                        txt = self.status_canvas.itemcget(item, "text")
                        offset = 60 if any(char in txt for char in ["▲", "▼", "%", "시세오류"]) else 0
                        self.status_canvas.coords(item, max_right + offset, 15)
                        max_right += w + offset
                    
        self.root.after(40, self.marquee_step)


    def on_minimize(self, event):
        # Unmap 이벤트는 창이 최소화(화면에서 사라짐)될 때 발생합니다.
        # 자식 위젯들의 Unmap 이벤트와 혼동되지 않도록 event.widget == self.root 인지 확인합니다.
        if event.widget == self.root and not self.is_minimized:
            self.is_minimized = True
            self.scroll_taskbar_title()

    def on_restore(self, event):
        # Map 이벤트는 창이 복원(화면으로 복귀)될 때 발생합니다.
        if event.widget == self.root and self.is_minimized:
            self.is_minimized = False
            if self.taskbar_scroll_job:
                self.root.after_cancel(self.taskbar_scroll_job)
                self.taskbar_scroll_job = None
            self.root.title("🎯 FiboAnalyzer분석")

    def scroll_taskbar_title(self):
        if not self.is_minimized:
            return
            
        if self.taskbar_text:
            txt_len = len(self.taskbar_text)
            idx = self.taskbar_scroll_index % txt_len
            display_text = self.taskbar_text[idx:] + self.taskbar_text[:idx]
            self.root.title(display_text)
            self.taskbar_scroll_index = (self.taskbar_scroll_index + 1) % txt_len
            
        self.taskbar_scroll_job = self.root.after(300, self.scroll_taskbar_title)

    def add_favorite_button(self, name, ticker):
        row_frame = tk.Frame(self.fav_container.scrollable_frame, bg=BG_PANEL)
        row_frame.pack(fill=tk.X, padx=5, pady=1)

        btn = tk.Button(
            row_frame,
            text=f"  {format_asset_name(ticker)}",
            font=("Segoe UI", 10),
            fg=TEXT_LIGHT,
            bg=BG_PANEL,
            activeforeground='#FFFFFF',
            activebackground=BG_CARD,
            bd=0,
            anchor='w',
            pady=8,
            cursor='hand2',
            command=lambda t=ticker: self.select_tab(t)
        )
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        del_btn = tk.Button(
            row_frame,
            text="✕",
            font=("Segoe UI", 10),
            fg='#EF5350',
            bg=BG_PANEL,
            activeforeground='#EF5350',
            activebackground=BG_CARD,
            bd=0,
            padx=10,
            cursor='hand2',
            command=lambda t=ticker, rf=row_frame: self.remove_from_favorites(t, rf)
        )
        del_btn.pack(side=tk.RIGHT)

        self.ticker_buttons[ticker] = (btn, del_btn)

        if ticker == self.current_ticker:
            btn.config(bg=BG_CARD, fg=ACCENT_BLUE)
            del_btn.config(bg=BG_CARD)

    def remove_from_favorites(self, ticker, row_frame):
        self.favorites = [item for item in self.favorites if item[1] != ticker]
        save_favorites(self.favorites)
        
        row_frame.destroy()
        if ticker in self.ticker_buttons:
            del self.ticker_buttons[ticker]
            
        if ticker == self.current_ticker:
            self.update_favorite_button_state()
            
        self.fav_container.canvas.configure(scrollregion=self.fav_container.canvas.bbox("all"))
        self.fetch_status_bar_prices_async()

    def select_tab(self, ticker):
        self.current_ticker = ticker

        self.title_label.config(text=f"📊 {format_asset_name(ticker)}")
        self.status_label.config(text="●", fg="#FF9800")

        self.update_favorite_button_state()

        # B. 사이드바 활성 자산 갱신
        try:
            self._refresh_sidebar_list()
        except Exception:
            pass

        # 선택된 자산이 암호화폐(-USD 접미사)인 경우에만 온체인 버튼 활성화
        is_coin = ticker.endswith("-USD")
        if is_coin:
            self.analysis_menu.entryconfig(3, state=tk.NORMAL)
        else:
            self.analysis_menu.entryconfig(3, state=tk.DISABLED)

        # AI 실시간 진단 상태 로딩으로 변경
        try:
            self.ai_lbl_ticker_price.config(text=f"{format_asset_name(ticker)} | 분석 중...")
            self.ai_lbl_score_judgment.config(text="종합 판단: 로딩 중...", fg='#B0BEC5')
            self.ai_lbl_sentiment.config(text="뉴스 감성: 로딩 중...", fg='#B0BEC5')
            self.ai_lbl_outlook.config(text="단기 전망:\n실시간 AI 정밀 진단이 진행 중입니다. 잠시만 기다려 주세요.", fg='#E3F2FD')
        except Exception:
            pass

        self.analysis_session_id += 1
        current_session = self.analysis_session_id

        market_opt = getattr(self, 'current_market_option', 'all')
        self.current_market_option = 'all' 
        interval_val = self.interval_var.get() if hasattr(self, 'interval_var') else "1d"
        start_analysis_thread(ticker, market_opt, interval_val, session_id=current_session)


        # 🤖 AI 비서 대화 기록 및 화면 초기화
        if hasattr(self, '_ai_chat_history'):
            self._ai_chat_history.clear()
            self.chat_history_txt.config(state=tk.NORMAL)
            self.chat_history_txt.delete("1.0", tk.END)
            self.chat_history_txt.config(state=tk.DISABLED)
            self._append_to_chat("System", f"🔄 자산이 {format_asset_name(ticker)}(으)로 변경되어 대화 기록이 초기화되었습니다.")
            self._append_to_chat("Gemini", f"안녕하세요! {format_asset_name(ticker)} 분석 화면입니다. 이 자산의 가격 흐름이나 피보나치 레벨에 대해 궁금한 점을 질문해 주세요! 🤖")


    def perform_search(self):
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("입력 오류", "검색할 주식명 또는 티커명을 입력해 주세요.")
            return
        
        self.current_market_option = self.market_var.get()
        self.select_tab(query)

    def refresh_current_ticker(self):
        if self.current_ticker:
            self.select_tab(self.current_ticker)

    def toggle_favorite(self):
        ticker = self.current_ticker
        if not ticker:
            return
            
        is_already_fav = any(t == ticker for _, t in self.favorites)
        if is_already_fav:
            self.favorites = [item for item in self.favorites if item[1] != ticker]
            save_favorites(self.favorites)
            alert_manager.set_damus_alert_ticker(ticker, False)
            alert_manager.stop_damus_monitor()
        else:
            name = format_asset_name(ticker)
            self.favorites.append((name, ticker))
            save_favorites(self.favorites)
            
        self.load_favorites_ui()
        self.update_favorite_button_state()
        self.fetch_status_bar_prices_async()

    def update_favorite_button_state(self):
        ticker = self.current_ticker
        if not ticker:
            return
        is_already_fav = any(t == ticker for _, t in self.favorites)
        if is_already_fav:
            self.add_fav_btn.config(text="★", fg='#FBC02D', state=tk.NORMAL)
        else:
            self.add_fav_btn.config(text="☆", fg='#A0A0A0', state=tk.NORMAL)

    def show_fundamental_analysis_popup(self):
        ticker = self.current_ticker
        if not ticker:
            return
            
        popup = tk.Toplevel(self.root)
        popup.title(f"🔍 {ticker} 기업/자산 기본 분석 및 장기 전망")
        popup.geometry("750x650")
        popup.configure(bg=BG_DARK)
        popup.transient(self.root) 
        popup.grab_set() 
        
        title_lbl = tk.Label(popup, text=f"🔍 {ticker} 기본적 가치 및 전망 분석", font=("Segoe UI", 14, "bold"), fg='#FFFFFF', bg=BG_DARK, pady=15)
        title_lbl.pack(fill=tk.X)
        
        txt_frame = tk.Frame(popup, bg=BG_PANEL, bd=1, relief=tk.SOLID)
        txt_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        scrollbar = ttk.Scrollbar(txt_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_box = tk.Text(
            txt_frame, 
            font=("Consolas", 10), 
            bg='#151515', 
            fg='#D0D0D0', 
            insertbackground='white',
            yscrollcommand=scrollbar.set,
            wrap=tk.WORD,
            bd=0,
            padx=12,
            pady=12
        )
        text_box.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_box.yview)
        
        text_box.insert(tk.END, f"{ticker}의 재무 상태, 시가총액, 유통량, 애널리스트 투자의견 및 비즈니스 요약본을 yfinance 서버에서 백그라운드로 가져오는 중입니다.\n\n잠시만 기다려 주세요...\n(자산에 따라 1~3초 가량 소요됩니다.)")
        text_box.config(state=tk.DISABLED)
        
        close_btn = tk.Button(
            popup,
            text="닫기",
            font=("Segoe UI", 10, "bold"),
            bg=BG_CARD,
            fg=TEXT_LIGHT,
            activebackground='#3A3A3A',
            bd=0,
            padx=25,
            pady=8,
            cursor='hand2',
            command=popup.destroy
        )
        close_btn.pack(pady=(0, 15))
        
        def fetch_fundamental():
            try:
                rate = 1.0
                is_usd = not (ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'))
                if is_usd:
                    try:
                        rate_df = yf.download("USDKRW=X", period="1d")
                        if rate_df.columns.nlevels > 1:
                            rate_df.columns = rate_df.columns.droplevel(1)
                        rate = float(rate_df['Close'].iloc[-1])
                    except:
                        rate = 1380.0
                
                t_obj = yf.Ticker(ticker)
                info = t_obj.info
                
                report_content = format_fundamental_report(ticker, info, rate)
                popup.after(0, lambda: display_report(report_content))
                
            except Exception as ex:
                import traceback
                traceback.print_exc()
                popup.after(0, lambda: display_report(f"❌ 데이터 조회 실패\n\n상세 오류: {str(ex)}\n\n티커명이 규격에 맞는지 확인해 주세요. (예: 주식 OTLK, 암호화폐 BTC-USD)"))
                
        def display_report(report_content):
            text_box.config(state=tk.NORMAL)
            text_box.delete("1.0", tk.END)
            text_box.insert(tk.END, report_content)
            text_box.config(state=tk.DISABLED)
            
        f_thread = threading.Thread(target=fetch_fundamental)
        f_thread.daemon = True
        f_thread.start()

    def show_onchain_analysis_popup(self):
        ticker = self.current_ticker
        if not ticker:
            return
            
        popup = tk.Toplevel(self.root)
        popup.title(f"⛓️ {ticker} 실시간 온체인 분석")
        popup.geometry("750x650")
        popup.configure(bg=BG_DARK)
        popup.transient(self.root) 
        popup.grab_set() 
        
        title_lbl = tk.Label(popup, text=f"⛓️ {ticker} 온체인 지표 분석", font=("Segoe UI", 14, "bold"), fg='#FFFFFF', bg=BG_DARK, pady=15)
        title_lbl.pack(fill=tk.X)
        
        txt_frame = tk.Frame(popup, bg=BG_PANEL, bd=1, relief=tk.SOLID)
        txt_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        scrollbar = ttk.Scrollbar(txt_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_box = tk.Text(
            txt_frame, 
            font=("Consolas", 10), 
            bg='#151515', 
            fg='#D0D0D0', 
            insertbackground='white',
            yscrollcommand=scrollbar.set,
            wrap=tk.WORD,
            bd=0,
            padx=12,
            pady=12
        )
        text_box.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_box.yview)
        
        text_box.insert(tk.END, f"{ticker}의 온체인 지표(활성 주소, 고래 트랜잭션, 해시레이트 등)를 CryptoCompare API 서버에서 조회 중입니다...\n\n잠시만 기다려 주세요...")
        text_box.config(state=tk.DISABLED)
        
        close_btn = tk.Button(
            popup,
            text="닫기",
            font=("Segoe UI", 10, "bold"),
            bg=BG_CARD,
            fg=TEXT_LIGHT,
            activebackground='#3A3A3A',
            bd=0,
            padx=25,
            pady=8,
            cursor='hand2',
            command=popup.destroy
        )
        close_btn.pack(pady=(0, 15))
        
        def fetch_onchain():
            try:
                from onchain import generate_onchain_report_md
                report_content = generate_onchain_report_md(ticker)
                popup.after(0, lambda: display_report(report_content))
            except Exception as ex:
                popup.after(0, lambda: display_report(f"❌ 데이터 조회 실패\n\n상세 오류: {str(ex)}"))
                
        def display_report(report_content):
            text_box.config(state=tk.NORMAL)
            text_box.delete("1.0", tk.END)
            text_box.insert(tk.END, report_content)
            text_box.config(state=tk.DISABLED)
            
        o_thread = threading.Thread(target=fetch_onchain)
        o_thread.daemon = True
        o_thread.start()

    def show_backtest_popup(self):
        ticker = self.current_ticker
        if not ticker:
            return
            
        popup = tk.Toplevel(self.root)
        popup.title(f"📈 {ticker} 피보나치 매수 신호 성과 백테스트")
        popup.geometry("1000x780")
        popup.configure(bg=BG_DARK)
        popup.transient(self.root) 
        popup.grab_set() 
        
        title_lbl = tk.Label(popup, text=f"📈 {ticker} 피보나치 백테스트 성과 분석", font=("Segoe UI", 14, "bold"), fg='#FFFFFF', bg=BG_DARK, pady=15)
        title_lbl.pack(fill=tk.X)
        
        # 상단 텍스트 및 하단 그래프 영역을 담을 프레임
        main_container = tk.Frame(popup, bg=BG_DARK)
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # 요약 성과 출력용 텍스트 프레임 (상단)
        txt_frame = tk.Frame(main_container, bg=BG_PANEL, bd=1, relief=tk.SOLID, height=180)
        txt_frame.pack(fill=tk.X, side=tk.TOP, pady=(0, 10))
        txt_frame.pack_propagate(False)
        
        scrollbar = ttk.Scrollbar(txt_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_box = tk.Text(
            txt_frame, 
            font=("Consolas", 10), 
            bg='#151515', 
            fg='#D0D0D0', 
            insertbackground='white',
            yscrollcommand=scrollbar.set,
            wrap=tk.WORD,
            bd=0,
            padx=12,
            pady=12
        )
        text_box.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_box.yview)
        
        text_box.insert(tk.END, f"{ticker}의 최근 5년 일봉 데이터를 다운로드하여 백테스트를 실행하는 중입니다...\n피보나치 매수 시그널의 성과 분석 및 차트 생성을 수행하고 있으니 잠시만 기다려 주세요.\n(약 2~4초 소요됩니다.)")
        text_box.config(state=tk.DISABLED)
        
        # 차트 출력용 프레임 (하단)
        chart_container = tk.Frame(main_container, bg=BG_PANEL, bd=1, relief=tk.SOLID)
        chart_container.pack(fill=tk.BOTH, expand=True, side=tk.BOTTOM)
        
        close_btn = tk.Button(
            popup,
            text="닫기",
            font=("Segoe UI", 10, "bold"),
            bg=BG_CARD,
            fg=TEXT_LIGHT,
            activebackground='#3A3A3A',
            bd=0,
            padx=25,
            pady=8,
            cursor='hand2',
            command=popup.destroy
        )
        close_btn.pack(pady=(0, 15))
        
        def run_backtest_thread():
            try:
                # 1) yfinance에서 백테스트용 과거 데이터 다운로드
                df = yf.download(ticker, period='5y', interval='1d')
                if df.empty:
                    raise Exception("yfinance에서 과거 일봉 데이터를 다운로드하지 못했습니다.")
                
                # 멀티레벨 컬럼 해제
                if df.columns.nlevels > 1:
                    df.columns = df.columns.droplevel(1)
                
                # 2) 백테스트 구동
                from backtest import run_backtest, generate_backtest_chart
                nest_mode = self.nest_mode_var.get()
                res = run_backtest(df, ticker, limit_years=5, nest_mode=nest_mode)
                
                if not res["success"]:
                    popup.after(0, lambda: display_error(res["message"]))
                    return
                
                # 3) 성과 보고서 포맷팅
                report_lines = []
                report_lines.append(f"============================================================")
                report_lines.append(f" 📈 {ticker} 피보나치 매수 시그널 역사적 백테스트 보고서 (최근 5년)")
                report_lines.append(f"============================================================")
                report_lines.append(f"● 총 분석 거래일: {len(df):,.0f}일")
                report_lines.append(f"● 총 매수 신호 발생 횟수: {res['total_signals']}회 (진입조건: 종합점수 65점 이상)")
                report_lines.append(f"\n[기간별 매수 신호 성과 분석]")
                
                for hold_days in [5, 10, 20, 30]:
                    m = res["metrics"][hold_days]
                    report_lines.append(
                        f" - {hold_days:2d}일 보유 후 매도: "
                        f"승률 {m['win_rate']:5.1f}% | "
                        f"평균수익률 {m['avg_ret']:+6.2f}% | "
                        f"최대수익 {m['max_ret']:+6.2f}% | "
                        f"최대손실 {m['min_ret']:+6.2f}%"
                    )
                report_lines.append(f"\n*본 백테스트 결과는 과거 기록을 바탕으로 연산된 시뮬레이션이며, 미래의 수익률을 보증하지 않습니다.")
                report_text = "\n".join(report_lines)
                
                # 4) 백테스트 차트 생성
                fig = generate_backtest_chart(res)
                
                popup.after(0, lambda: display_success(report_text, fig))
                
            except Exception as ex:
                import traceback
                traceback.print_exc()
                popup.after(0, lambda: display_error(f"❌ 백테스트 실행 실패\n\n상세 오류: {str(ex)}"))
                
        def display_error(err_msg):
            text_box.config(state=tk.NORMAL)
            text_box.delete("1.0", tk.END)
            text_box.insert(tk.END, err_msg)
            text_box.config(state=tk.DISABLED)
            
        def display_success(report_text, fig):
            text_box.config(state=tk.NORMAL)
            text_box.delete("1.0", tk.END)
            text_box.insert(tk.END, report_text)
            text_box.config(state=tk.DISABLED)
            
            # 차트 그리기
            canvas = FigureCanvasTkAgg(fig, master=chart_container)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            popup.update() # 레이아웃 업데이트 강제
            
        b_thread = threading.Thread(target=run_backtest_thread)
        b_thread.daemon = True
        b_thread.start()

    def show_technical_analysis_popup(self):
        ticker = self.current_ticker
        if not ticker:
            return

        import os
        import re
        from search import search_ticker_by_name

        popup = tk.Toplevel(self.root)
        popup.title(f"📋 {ticker} 기술적 분석 보고서")
        popup.geometry("1100x820")
        popup.configure(bg=BG_DARK)
        popup.transient(self.root)
        popup.grab_set()

        # ── 색상 태그 정의 ─────────────────────────────────────────
        # tag_name → (foreground, font)
        TAG_STYLES = {
            'h1':      ('#64B5F6', ('Consolas', 12, 'bold')),   # 섹션 번호/헤더 (파란색)
            'h2':      ('#90CAF9', ('Consolas', 11, 'bold')),   # 소헤더
            'divider': ('#3A4A6A', ('Consolas', 10, 'normal')), # 구분선
            'label':   ('#B0BEC5', ('Consolas', 11, 'normal')), # 항목명 (*)
            'up':      ('#FF5252', ('Consolas', 11, 'bold')),   # 상승/양수 (빨강)
            'down':    ('#2979FF', ('Consolas', 11, 'bold')),   # 하락/음수 (파랑)
            'price':   ('#FFF176', ('Consolas', 11, 'bold')),   # 가격/수치 (노랑)
            'buy':     ('#00E676', ('Consolas', 11, 'bold')),   # 매수 신호 (초록)
            'sell':    ('#FF5252', ('Consolas', 11, 'bold')),   # 매도 신호 (빨강)
            'watch':   ('#FFB300', ('Consolas', 11, 'bold')),   # 관망/주의 (주황)
            'normal':  ('#D0D0D0', ('Consolas', 11, 'normal')), # 일반 텍스트
            'score':   ('#FFD54F', ('Consolas', 14, 'bold')),   # 점수 (황금)
            'emoji':   ('#FFFFFF', ('Segoe UI Emoji', 11, 'normal')), # 이모지
        }

        # ── 텍스트박스 공통 생성 + 태그 등록 함수 ──────────────────
        def make_text_widget(parent):
            txt = tk.Text(
                parent,
                font=('Consolas', 11),
                bg='#0E1117',
                fg='#D0D0D0',
                insertbackground='white',
                wrap=tk.WORD,
                bd=0,
                padx=14,
                pady=10,
                spacing1=1,
                spacing3=3,
                relief=tk.FLAT
            )
            sb = ttk.Scrollbar(parent, command=txt.yview)
            txt.configure(yscrollcommand=sb.set)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            # 태그 등록
            for tag, (fg, font) in TAG_STYLES.items():
                txt.tag_configure(tag, foreground=fg, font=font)
            return txt

        # ── 자동 색상 태그 적용 함수 ────────────────────────────────
        def insert_colored_text(txt_widget, text):
            """텍스트를 줄별로 파싱하여 색상 태그 자동 적용."""
            txt_widget.config(state=tk.NORMAL)
            txt_widget.delete('1.0', tk.END)
            lines = text.split('\n')
            for line in lines:
                line_stripped = line.strip()

                # 구분선
                if re.match(r'^[-─]{5,}', line_stripped):
                    txt_widget.insert(tk.END, line + '\n', 'divider')

                # 섹션 번호 헤더 (1. 2. 3. 등)
                elif re.match(r'^\d+\.\s+.+', line_stripped):
                    txt_widget.insert(tk.END, line + '\n', 'h1')

                # ## 마크다운 헤더
                elif line_stripped.startswith('## '):
                    txt_widget.insert(tk.END, line + '\n', 'h1')

                # ### 마크다운 소헤더
                elif line_stripped.startswith('### ') or line_stripped.startswith('#### '):
                    txt_widget.insert(tk.END, line + '\n', 'h2')

                # ● 시작 헤더
                elif line_stripped.startswith('●'):
                    txt_widget.insert(tk.END, line + '\n', 'h1')

                # 점수 표시
                elif '종합 점수:' in line or '최종 판단:' in line or 'Technical Score' in line:
                    txt_widget.insert(tk.END, line + '\n', 'score')

                # 매수 신호
                elif any(kw in line for kw in ['매수 고려', '적극 매수', '강력 매수', '매수 적극', '▶ 매수']):
                    txt_widget.insert(tk.END, line + '\n', 'buy')

                # 매도/과매수 신호
                elif any(kw in line for kw in ['매도 주의', '과매수', '하락 경계', '조정 경계']):
                    txt_widget.insert(tk.END, line + '\n', 'sell')

                # 관망/주의
                elif any(kw in line for kw in ['관망', '주의', '중립', '관찰']):
                    txt_widget.insert(tk.END, line + '\n', 'watch')

                # 상승 화살표 라인
                elif '▲' in line:
                    # 줄 단위로 up 색상 적용
                    txt_widget.insert(tk.END, line + '\n', 'up')

                # 하락 화살표 라인
                elif '▼' in line:
                    txt_widget.insert(tk.END, line + '\n', 'down')

                # * 항목 라인 — 값 부분만 노란색으로 강조
                elif line_stripped.startswith('*'):
                    # 레이블 부분
                    colon_idx = line.find(':')
                    if colon_idx != -1:
                        label_part = line[:colon_idx + 1]
                        value_part = line[colon_idx + 1:]
                        txt_widget.insert(tk.END, label_part, 'label')
                        # 가격/% 숫자가 포함되면 price, 아니면 normal
                        if re.search(r'[\$₩\d%\.]+', value_part):
                            txt_widget.insert(tk.END, value_part + '\n', 'price')
                        else:
                            txt_widget.insert(tk.END, value_part + '\n', 'normal')
                    else:
                        txt_widget.insert(tk.END, line + '\n', 'label')

                # 일반 텍스트
                else:
                    txt_widget.insert(tk.END, line + '\n', 'normal')

            txt_widget.config(state=tk.DISABLED)

        # ── 보고서 텍스트를 섹션별로 파싱 ──────────────────────────
        def parse_sections(report_text):
            """요약 보고서를 4개 섹션으로 분리."""
            sections = {
                'summary': [],   # 1. 현재 가격 정보
                'fib': [],       # 2. 타임프레임별 진입 신호
                'indicators': [], # 3. 신규 보조지표
                'score': [],     # 종합 점수 및 전략
            }
            current = 'summary'
            for line in report_text.split('\n'):
                stripped = line.strip()
                if re.match(r'.*2\.\s*타임프레임', stripped) or '진입 신호' in stripped:
                    current = 'fib'
                elif re.match(r'.*3\.\s*신규 보조지표', stripped) or 'MACD' in stripped or '볼린저' in stripped:
                    current = 'indicators'
                elif '종합' in stripped and '점수' in stripped or '★' in stripped or '판단' in stripped:
                    current = 'score'
                sections[current].append(line)
            return {k: '\n'.join(v) for k, v in sections.items()}

        # ── 상단 헤더 바 ─────────────────────────────────────────
        header_bar = tk.Frame(popup, bg='#1A237E', pady=12, padx=18)
        header_bar.pack(fill=tk.X)

        header_title = tk.Label(
            header_bar,
            text=f"📋  {ticker}  기술적 분석 보고서",
            font=('Segoe UI', 14, 'bold'),
            fg='#E3F2FD',
            bg='#1A237E'
        )
        header_title.pack(side=tk.LEFT)

        # 보고서 파일 로드 버튼 (마크다운 열기)
        def open_report_file():
            import os as _os
            _base = _os.path.dirname(_os.path.abspath(__file__))
            actual_ticker = search_ticker_by_name(ticker) or ticker
            path = _os.path.join(_base, f"{actual_ticker}_technical_report.md")
            if not _os.path.exists(path):
                path = _os.path.join(_base, f"{ticker}_technical_report.md")
            if _os.path.exists(path):
                import subprocess
                subprocess.Popen(['notepad.exe', path])
            else:
                messagebox.showwarning("파일 없음", "상세 보고서 파일이 아직 생성되지 않았습니다.\n메인화면에서 '🔄 보고서 갱신'을 먼저 실행해 주세요.")

        open_btn = tk.Button(
            header_bar,
            text="📄 .md 파일 열기",
            font=('Segoe UI', 9, 'bold'),
            bg='#283593',
            fg='#90CAF9',
            activebackground='#1A237E',
            bd=0, padx=10, pady=4, cursor='hand2',
            command=open_report_file
        )
        open_btn.pack(side=tk.RIGHT, padx=5)

        # ── 탭 Notebook ─────────────────────────────────────────
        nb_style = ttk.Style()
        nb_style.configure('Report.TNotebook', background=BG_DARK, borderwidth=0)
        nb_style.configure('Report.TNotebook.Tab',
                           background='#1E2A3A', foreground='#90CAF9',
                           borderwidth=0, padding=[16, 7],
                           font=('Segoe UI', 10, 'bold'))
        nb_style.map('Report.TNotebook.Tab',
                     background=[('selected', '#0D1B2A')],
                     foreground=[('selected', '#64B5F6')])

        notebook = ttk.Notebook(popup, style='Report.TNotebook')
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 0))

        tab_defs = [
            ('📈 시장 요약', 'summary'),
            ('🎯 피보나치 신호', 'fib'),
            ('📊 보조지표', 'indicators'),
            ('⭐ 종합 판단', 'score'),
            ('📄 전체 보고서', 'full'),
        ]

        tab_frames = {}
        tab_texts = {}
        for tab_label, tab_key in tab_defs:
            fr = tk.Frame(notebook, bg='#0E1117')
            notebook.add(fr, text=tab_label)
            tab_frames[tab_key] = fr
            tab_texts[tab_key] = make_text_widget(fr)

        # ── 섹션 데이터 채우기 ────────────────────────────────────
        def load_report():
            """요약 보고서 및 전체 보고서를 탭에 로드."""
            report = getattr(self, 'last_report_text', '분석 결과가 없습니다.')

            # 섹션 파싱 및 삽입
            sections = parse_sections(report)
            for key in ('summary', 'fib', 'indicators', 'score'):
                content = sections.get(key, '').strip() or '해당 섹션 데이터가 없습니다.'
                insert_colored_text(tab_texts[key], content)

            # 전체 보고서 탭
            insert_colored_text(tab_texts['full'], report)

            # 상세 마크다운 파일도 전체 탭에 보강 (파일이 있을 경우)
            import os as _os
            _base = _os.path.dirname(_os.path.abspath(__file__))
            actual_ticker = search_ticker_by_name(ticker) or ticker
            md_path = _os.path.join(_base, f"{actual_ticker}_technical_report.md")
            if not _os.path.exists(md_path):
                md_path = _os.path.join(_base, f"{ticker}_technical_report.md")
            if _os.path.exists(md_path):
                try:
                    with open(md_path, 'r', encoding='utf-8') as f:
                        md_content = f.read()
                    insert_colored_text(tab_texts['full'], md_content)
                except Exception:
                    pass  # 파일 읽기 실패 시 기존 요약 유지

        load_report()

        # ── 하단 버튼 바 ─────────────────────────────────────────
        btn_bar = tk.Frame(popup, bg=BG_DARK, pady=10)
        btn_bar.pack(fill=tk.X, padx=15)

        refresh_btn = tk.Button(
            btn_bar,
            text="🔄 보고서 새로고침",
            font=('Segoe UI', 9, 'bold'),
            bg='#1A73E8',
            fg='white',
            activebackground='#1557B0',
            bd=0, padx=14, pady=6, cursor='hand2',
            command=load_report
        )
        refresh_btn.pack(side=tk.LEFT, padx=5)

        # ── E. HTML 보고서 내보내기 버튼 ─────────────────────────
        def export_html():
            import os as _os
            import webbrowser
            from tkinter import filedialog as _fd

            report = getattr(self, 'last_report_text', '')
            if not report or report == '분석이 완료되지 않았습니다.':
                messagebox.showwarning("보고서 없음", "먼저 분석을 실행해 주세요.", parent=popup)
                return

            save_path = _fd.asksaveasfilename(
                title="HTML 보고서 저장",
                defaultextension=".html",
                filetypes=[("HTML 파일", "*.html"), ("모든 파일", "*.*")],
                initialfile=f"{ticker}_report.html",
                initialdir=_os.path.dirname(_os.path.abspath(__file__))
            )
            if not save_path:
                return

            # 마크다운 텍스트 → HTML 변환 (간단 규칙 기반)
            import html as _html
            lines = report.split('\n')
            html_body = []
            for ln in lines:
                s = ln.strip()
                esc = _html.escape(ln)
                if s.startswith('## '):
                    html_body.append(f'<h2>{_html.escape(s[3:])}</h2>')
                elif s.startswith('### '):
                    html_body.append(f'<h3>{_html.escape(s[4:])}</h3>')
                elif s.startswith('#### '):
                    html_body.append(f'<h4>{_html.escape(s[5:])}</h4>')
                elif s.startswith('# '):
                    html_body.append(f'<h1>{_html.escape(s[2:])}</h1>')
                elif s.startswith('---'):
                    html_body.append('<hr>')
                elif s.startswith('* ') or s.startswith('- '):
                    html_body.append(f'<li>{_html.escape(s[2:])}</li>')
                elif s == '':
                    html_body.append('<br>')
                else:
                    # 상승/하락 색상
                    if '▲' in s:
                        html_body.append(f'<p class="up">{esc}</p>')
                    elif '▼' in s:
                        html_body.append(f'<p class="down">{esc}</p>')
                    elif any(kw in s for kw in ['매수 고려', '적극 매수', '강력 매수']):
                        html_body.append(f'<p class="buy">{esc}</p>')
                    elif any(kw in s for kw in ['매도 주의', '과매수', '하락 경계']):
                        html_body.append(f'<p class="sell">{esc}</p>')
                    elif '종합 점수:' in s or '최종 판단:' in s:
                        html_body.append(f'<p class="score">{esc}</p>')
                    else:
                        html_body.append(f'<p>{esc}</p>')

            html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{ticker} 기술적 분석 보고서 — FiboAnalyzer</title>
<style>
  body {{font-family:'Consolas','Malgun Gothic',monospace;background:#0E1117;color:#D0D0D0;max-width:960px;margin:40px auto;padding:0 20px;line-height:1.7;}}
  h1 {{color:#64B5F6;border-bottom:2px solid #1A237E;padding-bottom:8px;}}
  h2 {{color:#64B5F6;margin-top:28px;}}
  h3 {{color:#90CAF9;}}
  h4 {{color:#90CAF9;}}
  hr {{border:none;border-top:1px solid #1E2A3A;margin:16px 0;}}
  li {{color:#B0BEC5;margin:4px 0;}}
  .up {{color:#FF5252;font-weight:bold;}}
  .down {{color:#2979FF;font-weight:bold;}}
  .buy {{color:#00E676;font-weight:bold;}}
  .sell {{color:#FF5252;font-weight:bold;}}
  .score {{color:#FFD54F;font-size:1.1em;font-weight:bold;}}
  p {{margin:4px 0;}}
  .header-bar {{background:#1A237E;padding:16px 20px;border-radius:6px;margin-bottom:24px;}}
  .header-bar h1 {{border:none;margin:0;}}
  .footer {{color:#546E7A;font-size:0.85em;margin-top:32px;border-top:1px solid #1E2A3A;padding-top:12px;}}
</style>
</head>
<body>
<div class="header-bar"><h1>📋 {ticker} 기술적 분석 보고서</h1></div>
{''.join(html_body)}
<div class="footer">Generated by FiboAnalyzer — 투자 참고용으로만 사용하시기 바랍니다.</div>
</body>
</html>"""

            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                webbrowser.open(f'file:///{save_path.replace(chr(92), "/")}')
                messagebox.showinfo("저장 완료", f"HTML 보고서가 저장되었습니다.\n{save_path}", parent=popup)
            except Exception as ex:
                messagebox.showerror("저장 실패", str(ex), parent=popup)

        html_btn = tk.Button(
            btn_bar,
            text="🌐 HTML 저장",
            font=('Segoe UI', 9, 'bold'),
            bg='#2E7D32',
            fg='white',
            activebackground='#1B5E20',
            bd=0, padx=12, pady=6, cursor='hand2',
            command=export_html
        )
        html_btn.pack(side=tk.LEFT, padx=5)

        close_btn = tk.Button(
            btn_bar,
            text="닫기",
            font=('Segoe UI', 10, 'bold'),
            bg=BG_CARD,
            fg=TEXT_LIGHT,
            activebackground='#3A3A3A',
            bd=0, padx=25, pady=6,
            cursor='hand2',
            command=popup.destroy
        )
        close_btn.pack(side=tk.RIGHT, padx=5)



    def show_recommendations_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("💡 FiboAnalyzer 추천 자산 포트폴리오")
        popup.geometry("920x760")
        popup.configure(bg=BG_DARK)
        popup.transient(self.root)
        popup.grab_set()
        
        title_lbl = tk.Label(popup, text="💡 추천 자산 포트폴리오", font=("Segoe UI", 14, "bold"), fg='#FFFFFF', bg=BG_DARK, pady=15)
        title_lbl.pack(fill=tk.X)
        
        subtitle_lbl = tk.Label(popup, text="※ 티커 버튼을 클릭하면 메인 화면에서 즉시 피보나치 분석을 실행합니다.", font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_DARK)
        subtitle_lbl.pack(fill=tk.X, pady=(0, 5))
        
        scroll_container = ScrollableFrame(popup, bg=BG_DARK)
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))
        
        ko_assets = [
            ("005930.KS", "삼성전자 - 반도체 대장주"),
            ("000660.KS", "SK하이닉스 - AI HBM 선두"),
            ("005490.KS", "POSCO홀딩스 - 2차전지 소재"),
            ("207940.KS", "삼성바이오 - CMO 바이오"),
            ("035420.KS", "NAVER - 검색 및 AI 포털"),
            ("005380.KS", "현대차 - 자동차 및 친환경차"),
            ("051910.KS", "LG화학 - 이차전지 화학소재"),
            ("035720.KS", "카카오 - 대표 플랫폼"),
            ("068270.KS", "셀트리온 - 바이오시밀러 강자"),
            ("009830.KS", "한화솔루션 - 신재생 태양광")
        ]
        
        crypto_assets = [
            ("BTC-USD", "비트코인 - 암호화폐 대장주"),
            ("ETH-USD", "이더리움 - 스마트계약 대장"),
            ("XRP-USD", "리플 - 해외 저비용 송금"),
            ("SOL-USD", "솔라나 - 초고속 레이어1"),
            ("ADA-USD", "에이다 - 학술 검증 블록체인"),
            ("DOGE-USD", "도지코인 - 대표 밈 코인"),
            ("BNB-USD", "바이낸스 코인 - 거래소 코인"),
            ("LINK-USD", "체인링크 - 탈중앙 오라클"),
            ("AVAX-USD", "아발란체 - 고확장성 메인넷"),
            ("DOT-USD", "폴카닷 - 인터체인 솔루션")
        ]
        
        us_sectors = {
            "AI / 플랫폼 (AI & Platform)": [
                ("MSFT", "Microsoft - 글로벌 AI 리더"),
                ("GOOGL", "Alphabet - 구글/유튜브 AI"),
                ("META", "Meta - 메타버스 & SNS"),
                ("PLTR", "Palantir - 군사/기업 AI 분석"),
                ("AMZN", "Amazon - 클라우드 & 이커머스")
            ],
            "반도체 (Semiconductors)": [
                ("NVDA", "Nvidia - GPU AI 반도체 독점"),
                ("AVGO", "Broadcom - 유무선 통신 반도체"),
                ("AMD", "AMD - 엔비디아 핵심 대항마 CPU/GPU"),
                ("TSM", "TSMC - 글로벌 1위 파운드리"),
                ("ASML", "ASML - EUV 노광장비 독점 제조")
            ],
            "우주항공 (Space & Aerospace)": [
                ("LMT", "Lockheed Martin - 최대 방위산업체"),
                ("RTX", "Raytheon - 첨단 미사일 및 항공 엔진"),
                ("SPCE", "Virgin Galactic - 민간 우주 관광 선두"),
                ("PL", "Planet Labs - 위성 지구관측 데이터"),
                ("RKLB", "Rocket Lab - 소형 위성 발사 서비스")
            ],
            "바이오테크 (Bio Tech)": [
                ("MRNA", "Moderna - mRNA 차세대 백신/치료제"),
                ("VRTX", "Vertex - 낭포성 섬유증 독점 혁신 신약"),
                ("LLY", "Eli Lilly - 비만 치료제 글로벌 1위"),
                ("NVO", "Novo Nordisk - 당뇨 및 비만 치료제"),
                ("REGN", "Regeneron - 안과/항암 바이오 의약품")
            ],
            "빅테크 / 친환경 (Tech & Green)": [
                ("AAPL", "Apple - 시총 최정상 IT 하드웨어"),
                ("TSLA", "Tesla - 글로벌 전기차 및 자율주행"),
                ("ENPH", "Enphase Energy - 친환경 태양광 인버터"),
                ("NEE", "NextEra Energy - 친환경 풍력/태양광 발전"),
                ("O", "Realty Income - 고배당 대표 리츠")
            ],
            "🤖 제미나이 AI 특별 추천 30선": [
                ("MSFT", "Microsoft - 클라우드 및 AI 선도"),
                ("AAPL", "Apple - 강력한 생태계 및 현금창출"),
                ("NVDA", "NVIDIA - AI 반도체 독점적 지위"),
                ("GOOGL", "Alphabet - 검색 및 AI 생태계"),
                ("AMZN", "Amazon - e커머스 및 AWS 클라우드"),
                ("META", "Meta - 글로벌 SNS 및 오픈소스 AI"),
                ("TSM", "TSMC - 글로벌 파운드리 압도적 1위"),
                ("AVGO", "Broadcom - AI 네트워킹 핵심 칩"),
                ("ASML", "ASML - EUV 노광장비 글로벌 독점"),
                ("AMD", "AMD - 데이터센터 및 PC 프로세서"),
                ("LLY", "Eli Lilly - 비만/당뇨 치료제 시장 주도"),
                ("NVO", "Novo Nordisk - 글로벌 비만 치료제 선두"),
                ("UNH", "UnitedHealth - 최대 헬스케어 네트워크"),
                ("JNJ", "Johnson & Johnson - 헬스케어/제약 우량주"),
                ("V", "Visa - 글로벌 결제 네트워크 압도적 1위"),
                ("MA", "Mastercard - 강력한 결제 인프라 과점"),
                ("JPM", "JPMorgan Chase - 세계 최대 금융사"),
                ("WMT", "Walmart - 유통 공룡 및 경기 방어주"),
                ("COST", "Costco - 멤버십 기반 안정적 성장"),
                ("PG", "Procter & Gamble - 필수소비재 1위 대장주"),
                ("CRM", "Salesforce - 기업용 클라우드 CRM 1위"),
                ("ADBE", "Adobe - 크리에이티브 소프트웨어 표준"),
                ("NOW", "ServiceNow - IT 워크플로우 자동화 선도"),
                ("INTU", "Intuit - 핀테크 및 세무 소프트웨어 강자"),
                ("PLTR", "Palantir - AI 기반 빅데이터 분석 솔루션"),
                ("UBER", "Uber - 글로벌 모빌리티 및 배달 플랫폼"),
                ("ABNB", "Airbnb - 여행 및 숙박 플랫폼 선두주자"),
                ("NFLX", "Netflix - 스트리밍 콘텐츠 1위 강자"),
                ("TSLA", "Tesla - 전기차, 에너지 및 자율주행(FSD)"),
                ("CRWD", "CrowdStrike - 차세대 클라우드 사이버 보안")
            ],
            "⚡ 제미나이 AI 추천 하이리스크 30선": [
                ("MSTR", "MicroStrategy - 비트코인 연동 최고 변동성"),
                ("COIN", "Coinbase - 대표 가상자산 거래소 주식"),
                ("MARA", "Marathon Digital - 대표 비트코인 채굴주"),
                ("RIOT", "Riot Platforms - 비트코인 채굴"),
                ("CLSK", "CleanSpark - 비트코인 채굴"),
                ("CVNA", "Carvana - 온라인 중고차 판매 플랫폼"),
                ("UPST", "Upstart - AI 기반 대출 플랫폼"),
                ("AFRM", "Affirm - 선구매 후결제(BNPL) 대장주"),
                ("ROKU", "Roku - 스트리밍 플랫폼 강자"),
                ("SQ", "Block - 디지털 결제 및 핀테크"),
                ("HOOD", "Robinhood - 개인투자자 주식/코인 거래앱"),
                ("SOFI", "SoFi - 차세대 핀테크/디지털 뱅킹"),
                ("PLUG", "Plug Power - 수소 연료전지 기업"),
                ("FCEL", "FuelCell Energy - 수소 에너지 솔루션"),
                ("QS", "QuantumScape - 전고체 배터리 스타트업"),
                ("LCID", "Lucid Group - 프리미엄 전기차 스타트업"),
                ("RIVN", "Rivian - 전기 픽업트럭 및 SUV"),
                ("NIO", "NIO - 중국 프리미엄 전기차"),
                ("XPEV", "XPeng - 중국 스마트 전기차"),
                ("BYND", "Beyond Meat - 식물성 대체육"),
                ("DKNG", "DraftKings - 온라인 스포츠 베팅"),
                ("PTON", "Peloton - 홈 피트니스 구독 서비스"),
                ("GME", "GameStop - 대표 밈 주식(Meme Stock)"),
                ("AMC", "AMC Entertainment - 글로벌 영화관 체인"),
                ("SPCE", "Virgin Galactic - 민간 우주 관광"),
                ("ASTS", "AST SpaceMobile - 저궤도 위성 통신망"),
                ("JOBY", "Joby Aviation - UAM(도심항공교통) 선두주자"),
                ("IONQ", "IonQ - 양자 컴퓨터 하드웨어"),
                ("DNA", "Ginkgo Bioworks - 합성 생물학"),
                ("CRSP", "CRISPR Therapeutics - 유전자 가위 편집 기술")
            ]
        }
        
        ko_frame = tk.LabelFrame(scroll_container.scrollable_frame, text=" 🇰🇷 한국 주식 (KOSPI/KOSDAQ) ", font=("Segoe UI", 10, "bold"), bg=BG_PANEL, fg='#42A5F5', bd=1, relief=tk.SOLID, padx=12, pady=12)
        ko_frame.pack(fill=tk.X, padx=10, pady=8)
        ko_frame.columnconfigure(0, weight=1)
        ko_frame.columnconfigure(1, weight=1)
        
        for i, (ticker, desc) in enumerate(ko_assets):
            r = i // 2
            c = i % 2
            btn_frame = tk.Frame(ko_frame, bg=BG_PANEL)
            btn_frame.grid(row=r, column=c, sticky='ew', padx=5, pady=4)
            
            ticker_btn = tk.Button(
                btn_frame, 
                text=ticker, 
                font=("Segoe UI", 9, "bold"), 
                bg='#1976D2', 
                fg='white', 
                activebackground='#1565C0',
                bd=0, 
                width=10, 
                pady=3,
                cursor='hand2',
                command=lambda t=ticker: [self.select_tab(t), popup.destroy()]
            )
            ticker_btn.pack(side=tk.LEFT)
            desc_lbl = tk.Label(btn_frame, text=f"  {desc}", font=("Segoe UI", 9), fg=TEXT_LIGHT, bg=BG_PANEL, anchor='w')
            desc_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
        crypto_frame = tk.LabelFrame(scroll_container.scrollable_frame, text=" 🪙 가상자산 (Crypto) ", font=("Segoe UI", 10, "bold"), bg=BG_PANEL, fg='#FF6D00', bd=1, relief=tk.SOLID, padx=12, pady=12)
        crypto_frame.pack(fill=tk.X, padx=10, pady=8)
        crypto_frame.columnconfigure(0, weight=1)
        crypto_frame.columnconfigure(1, weight=1)
        
        for i, (ticker, desc) in enumerate(crypto_assets):
            r = i // 2
            c = i % 2
            btn_frame = tk.Frame(crypto_frame, bg=BG_PANEL)
            btn_frame.grid(row=r, column=c, sticky='ew', padx=5, pady=4)
            
            ticker_btn = tk.Button(
                btn_frame, 
                text=ticker, 
                font=("Segoe UI", 9, "bold"), 
                bg='#E65100', 
                fg='white', 
                activebackground='#EF6C00',
                bd=0, 
                width=10, 
                pady=3,
                cursor='hand2',
                command=lambda t=ticker: [self.select_tab(t), popup.destroy()]
            )
            ticker_btn.pack(side=tk.LEFT)
            desc_lbl = tk.Label(btn_frame, text=f"  {desc}", font=("Segoe UI", 9), fg=TEXT_LIGHT, bg=BG_PANEL, anchor='w')
            desc_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        us_super_frame = tk.LabelFrame(scroll_container.scrollable_frame, text=" 🇺🇸 미국 주식 섹터별 추천 (US Market) ", font=("Segoe UI", 11, "bold"), bg='#151515', fg=ACCENT_GREEN, bd=1, relief=tk.SOLID, padx=10, pady=10)
        us_super_frame.pack(fill=tk.X, padx=10, pady=8)
        
        for sector_name, assets in us_sectors.items():
            is_high_risk = "하이리스크" in sector_name
            frame_fg = '#EF5350' if is_high_risk else ACCENT_GREEN
            frame_bg = BG_PANEL
            btn_bg = '#D32F2F' if is_high_risk else '#388E3C'
            btn_active_bg = '#C62828' if is_high_risk else '#2E7D32'
            
            sub_frame = tk.LabelFrame(us_super_frame, text=f" {sector_name} ", font=("Segoe UI", 9, "bold"), bg=frame_bg, fg=frame_fg, bd=1, relief=tk.SOLID, padx=10, pady=8)
            sub_frame.pack(fill=tk.X, padx=5, pady=6)
            sub_frame.columnconfigure(0, weight=1)
            sub_frame.columnconfigure(1, weight=1)
            
            for j, (ticker, desc) in enumerate(assets):
                row = j // 2
                col = j % 2
                btn_frame = tk.Frame(sub_frame, bg=frame_bg)
                btn_frame.grid(row=row, column=col, sticky='ew', padx=5, pady=4)
                
                ticker_btn = tk.Button(
                    btn_frame, 
                    text=ticker, 
                    font=("Segoe UI", 9, "bold"), 
                    bg=btn_bg, 
                    fg='white', 
                    activebackground=btn_active_bg,
                    bd=0, 
                    width=10, 
                    pady=3,
                    cursor='hand2',
                    command=lambda t=ticker: [self.select_tab(t), popup.destroy()]
                )
                ticker_btn.pack(side=tk.LEFT)
                desc_lbl = tk.Label(btn_frame, text=f"  {desc}", font=("Segoe UI", 9), fg=TEXT_LIGHT, bg=frame_bg, anchor='w')
                desc_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
                
        popup.update_idletasks()
        scroll_container.canvas.configure(scrollregion=scroll_container.canvas.bbox("all"))
            
        close_btn = tk.Button(
            popup,
            text="닫기",
            font=("Segoe UI", 10, "bold"),
            bg=BG_CARD,
            fg=TEXT_LIGHT,
            activebackground='#3A3A3A',
            bd=0,
            padx=25,
            pady=8,
            cursor='hand2',
            command=popup.destroy
        )
        close_btn.pack(pady=15)

    def _bind_chart_resize(self, frame, canvas, fig):
        """창 크기 변경 시 matplotlib Figure를 프레임 크기에 맞게 자동 조정합니다."""
        def _on_resize(event):
            # 중복 호출 방지: 80ms 디바운스
            if hasattr(frame, '_resize_job') and frame._resize_job:
                try:
                    frame.after_cancel(frame._resize_job)
                except Exception:
                    pass
            frame._resize_job = frame.after(80, lambda: _do_resize(event.width, event.height))

        def _do_resize(w, h):
            try:
                if w < 20 or h < 20:
                    return
                dpi = fig.get_dpi()
                new_w = max(w / dpi, 1.0)
                new_h = max(h / dpi, 1.0)
                fig.set_size_inches(new_w, new_h, forward=False)
                canvas.draw_idle()
            except Exception:
                pass

        # 기존 Configure 바인딩 제거 후 재등록
        try:
            frame.unbind('<Configure>')
        except Exception:
            pass
        frame.bind('<Configure>', _on_resize)

        # 탭 전환 시 현재 프레임 크기로 즉시 재렌더링
        def _on_tab_changed(event):
            try:
                selected = self.notebook.select()
                if str(frame) == selected:
                    w = frame.winfo_width()
                    h = frame.winfo_height()
                    _do_resize(w, h)
            except Exception:
                pass

        # 노트북 탭 변경 이벤트 바인딩 (중복 방지: unbind_all 대신 태그 활용)
        try:
            self.notebook.bind('<<NotebookTabChanged>>', _on_tab_changed, add=True)
        except Exception:
            pass

    def bind_hover_tooltip(self, canvas, fig, key, is_usd, rate):
        # 피보나치: 당일 1시간봉 데이터 기반 전용 처리
        if key == 'DAMUS':
            if not fig.axes or not hasattr(self, 'current_damus_df') or self.current_damus_df is None:
                return
            ax = fig.axes[0]
            df_plot = self.current_damus_df
            import matplotlib.dates as mdates
            import numpy as np
            plot_dates_num = mdates.date2num(df_plot.index.to_pydatetime())

            annot = ax.annotate(
                "",
                xy=(0, 0),
                xytext=(10, 10),
                textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.5", fc="#1E1E1E", ec="#00E676", alpha=0.9, lw=1),
                fontproperties=ax.title.get_fontproperties(),
                color="#E0E0E0",
                fontsize=8,
                zorder=100
            )
            annot.set_visible(False)

            def hover_damus(event):
                vis = annot.get_visible()
                if event.inaxes == ax:
                    x, y = event.xdata, event.ydata
                    if x is None or y is None:
                        return
                    idx = np.abs(plot_dates_num - x).argmin()
                    actual_time = df_plot.index[idx]
                    time_str = actual_time.strftime('%m/%d %H:%M')
                    val = float(df_plot['Close'].iloc[idx])
                    if is_usd:
                        val_krw = val * rate
                        y_val_str = f"${val:,.2f} (\\{val_krw:,.0f})"
                    else:
                        y_val_str = fmt_chart_val(val, is_usd)
                    target_x = plot_dates_num[idx]
                    target_y = val
                    annot.xy = (target_x, target_y)
                    annot.set_text(f"시간: {time_str}\n가격: {y_val_str}")
                    annot.set_visible(True)
                    canvas.draw_idle()
                else:
                    if vis:
                        annot.set_visible(False)
                        canvas.draw_idle()

            canvas.mpl_connect("motion_notify_event", hover_damus)
            return

        if not fig.axes or not hasattr(self, 'current_df') or self.current_df is None:
            return
        ax = fig.axes[0]
        
        # 툴팁용 annotation 생성
        annot = ax.annotate(
            "", 
            xy=(0,0), 
            xytext=(15, 15), 
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc="#1E1E1E", ec="#2979FF", alpha=0.92, lw=1),
            fontproperties=ax.title.get_fontproperties(),
            color="#E0E0E0",
            fontsize=8,
            zorder=100
        )
        annot.set_visible(False)

        # 각 탭에 대응하는 데이터 윈도우 필터링
        # ★ 차트 draw_candlestick_with_volume의 tail() 값과 반드시 일치해야 함
        if key == 'L':
            df_plot = self.current_df.copy()
        elif key in ['M', 'RSI', 'MACD']:
            df_plot = self.current_df.tail(180).copy()
        elif key == 'S':
            df_plot = self.current_df.tail(30).copy()
        elif key == 'XS':
            df_plot = self.current_df.tail(14).copy()   # 차트는 tail(14)를 사용
        else:
            df_plot = self.current_df.copy()

        # MultiIndex 컬럼 평탄화 (yfinance가 MultiIndex를 반환하는 경우 대비)
        if df_plot.columns.nlevels > 1:
            df_plot.columns = df_plot.columns.droplevel(1)

        import numpy as np
        n = len(df_plot)

        def hover(event):
            vis = annot.get_visible()
            if event.inaxes == ax:
                x, y = event.xdata, event.ydata
                if x is None or y is None:
                    return
                
                # ★ 차트가 정수 x축(0,1,2,...)을 사용하므로 round()로 인덱스 매칭
                idx = int(round(x))
                if idx < 0:
                    idx = 0
                if idx >= n:
                    idx = n - 1
                
                actual_date = df_plot.index[idx]
                x_date_str = actual_date.strftime('%Y-%m-%d')
                target_x = idx  # 정수 x좌표
                
                if key in ['L', 'M', 'S', 'XS']:
                    try:
                        close_val = float(df_plot['Close'].iloc[idx])
                        high_val = float(df_plot['High'].iloc[idx])
                        low_val = float(df_plot['Low'].iloc[idx])

                        if is_usd:
                            close_str = f"${close_val:,.2f} (₩{close_val*rate:,.0f})"
                            high_str  = f"${high_val:,.2f} (₩{high_val*rate:,.0f})"
                            low_str   = f"${low_val:,.2f} (₩{low_val*rate:,.0f})"
                        else:
                            close_str = f"₩{close_val:,.0f}"
                            high_str  = f"₩{high_val:,.0f}"
                            low_str   = f"₩{low_val:,.0f}"

                        y_val_str = f"종가: {close_str}\n고가(상한): {high_str}\n저가(하한): {low_str}"
                        target_y = close_val
                    except Exception as e:
                        print(f"[Hover Tooltip Error] {key} 패널 파싱 실패: {e}")
                        return
                elif key == 'RSI':
                    if 'RSI_14' in df_plot.columns:
                        val = float(df_plot['RSI_14'].iloc[idx])
                        y_val_str = f"{val:.2f} (RSI)"
                        target_y = val
                    else:
                        return
                elif key == 'MACD':
                    if 'MACD' in df_plot.columns:
                        val = float(df_plot['MACD'].iloc[idx])
                        y_val_str = f"{val:.4f} (MACD)"
                        target_y = val
                    else:
                        return
                else:
                    target_y = y
                    y_val_str = f"{y:.4f}"

                # 툴팁 업데이트 및 위치 조정
                annot.xy = (target_x, target_y)
                text = f"날짜: {x_date_str}\n{y_val_str}" if key in ['L', 'M', 'S', 'XS'] else f"날짜: {x_date_str}\n수치: {y_val_str}"
                annot.set_text(text)

                # ★ 오른쪽 끝 근처이면 툴팁을 왼쪽에 표시
                xlim = ax.get_xlim()
                x_range = xlim[1] - xlim[0]
                if x_range > 0 and (x - xlim[0]) / x_range > 0.70:
                    annot.set_position((-180, 15))
                else:
                    annot.set_position((15, 15))

                annot.set_visible(True)
                canvas.draw_idle()
            else:
                if vis:
                    annot.set_visible(False)
                    canvas.draw_idle()

        canvas.mpl_connect("motion_notify_event", hover)

    def update_ui_success(self, results):
        ticker = results['ticker']
        # 세션 검증
        if results.get('session_id') is not None and results.get('session_id') != self.analysis_session_id:
            print(f"[UI Sync] Discarding analysis results for {ticker} (Session {results.get('session_id')} != Current {self.analysis_session_id})")
            return

        report_text = results['report_text']
        figs = results['figs']
        price = results['current_price']
        rsi = results['current_rsi']
        report_path = results['report_path']
        rate = results['rate']
        is_usd = results['is_usd']
        self.current_df = results.get('df_all')
        self.current_damus_df = results.get('damus_today_1h')  # 피보나치 당일 1시간봉

        self.last_report_text = report_text

        # 실제 검색 및 분석 완료된 정식 티커명으로 current_ticker 갱신
        self.current_ticker = ticker

        self.title_label.config(text=f"📊 {ticker}")
        self.status_label.config(text="●", fg=ACCENT_GREEN)

        # ── A. 핵심 지표 대시보드 카드 업데이트 ─────────────────────
        try:
            self.update_indicator_cards(
                current_price=price,
                rsi=rsi,
                composite_score=results.get('composite_score', 50),
                macd_hist=results.get('current_macd_hist', 0),
                current_macd=results.get('current_macd', 0),
                current_macd_signal=results.get('current_macd_signal', 0),
                rate=rate,
                is_usd=is_usd,
                best_buy_str=results.get('best_buy_str', '—'),
                rec_ko=results.get('rec_ko', '—'),
            )
        except Exception:
            pass

        # F. Lazy Load — 분석 데이터 저장 (탭 전환 시 on-demand 렌더링)
        self._last_analysis_data = results
        self._rendered_tabs = set()   # 새 분석 시작 → 캐시 초기화

        for key, fig in figs.items():
            if key in self.tabs:
                tab_data = self.tabs[key]
                if tab_data['canvas']:
                    tab_data['canvas'].get_tk_widget().destroy()

                canvas = FigureCanvasTkAgg(fig, master=tab_data['frame'])
                canvas.draw()
                widget = canvas.get_tk_widget()
                widget.pack(fill=tk.BOTH, expand=True)
                tab_data['canvas'] = canvas
                tab_data['fig'] = fig
                self.bind_hover_tooltip(canvas, fig, key, is_usd, rate)
                self._bind_chart_resize(tab_data['frame'], canvas, fig)
                self._rendered_tabs.add(key)
                plt.close(fig)

        self.update_favorite_button_state()
        self.load_favorites_ui()

        # 피보나치 레벨 알림 모니터 — 즐겨찾기에서 해당 티커가 체크되어 있을 때만 시작
        token, chat_id = alert_manager.get_token_and_chat_id()
        if token and chat_id and ticker in alert_manager.get_damus_alert_tickers():
            alert_manager.start_damus_monitor(ticker, is_usd, check_interval_sec=60)

        # AI 실시간 진단 요약 패널 갱신
        try:
            formatted_ticker = format_asset_name(ticker)
            if is_usd:
                krw_price = price * rate
                price_text = f"{formatted_ticker} | ${price:,.2f} (₩{krw_price:,.0f})" if price < 10 else f"{formatted_ticker} | ${price:,.1f} (₩{krw_price:,.0f})" if price < 100 else f"{formatted_ticker} | ${price:,.0f} (₩{krw_price:,.0f})"
            else:
                price_text = f"{formatted_ticker} | ₩{price:,.0f}"
            self.ai_lbl_ticker_price.config(text=price_text)

            score_color = '#EF5350'
            if results.get('composite_score', 50) >= 60:
                score_color = '#00E676'
            elif results.get('composite_score', 50) >= 40:
                score_color = '#FFA726'
            self.ai_lbl_score_judgment.config(text=f"종합 판단: {results.get('score_label', '—')} ({results.get('composite_score', 50)}점)", fg=score_color)

            ai_result = results.get('ai_result')
            if ai_result:
                sentiment = ai_result.get('sentiment', '중립')
                score = ai_result.get('sentiment_score', 0)
                sent_emoji = "🟢" if "긍정" in sentiment or score > 20 else "🔴" if "부정" in sentiment or score < -20 else "🟡"
                self.ai_lbl_sentiment.config(text=f"뉴스 감성: {sent_emoji} {sentiment} ({score:+.0f})", fg='#FFF176')
                
                short_term_text = ai_result.get('short_term', '단기 전망 정보 없음')
                self.ai_lbl_outlook.config(text=f"단기 전망:\n{short_term_text}", fg='#E3F2FD')
            else:
                self.ai_lbl_sentiment.config(text="뉴스 감성: 🟡 분석 실패", fg='#B0BEC5')
                self.ai_lbl_outlook.config(text="단기 전망:\nGemini AI 실시간 뉴스 분석 결과를 가져오지 못했습니다.", fg='#EF5350')
        except Exception as ex:
            print(f"[AI Summary UI Warning] 요약 패널 갱신 실패: {ex}")

    def _on_tab_changed(self, event):
        """F. Lazy Load — 탭 전환 시 아직 렌더링되지 않은 탭의 차트를 on-demand로 생성합니다."""
        try:
            selected_tab_id = self.notebook.select()
            # 현재 선택된 탭의 key 찾기
            current_key = None
            for key, tab_data in self.tabs.items():
                if str(tab_data['frame']) == selected_tab_id:
                    current_key = key
                    break

            if current_key is None:
                return

            # 이미 렌더링된 탭이면 스킵
            if current_key in self._rendered_tabs:
                return

            # 분석 데이터가 없으면 스킵
            if self._last_analysis_data is None:
                return

            figs = self._last_analysis_data.get('figs', {})
            rate = self._last_analysis_data.get('rate', 1.0)
            is_usd = self._last_analysis_data.get('is_usd', True)

            fig = figs.get(current_key)
            if fig is None:
                return

            tab_data = self.tabs[current_key]
            if tab_data['canvas']:
                tab_data['canvas'].get_tk_widget().destroy()

            canvas = FigureCanvasTkAgg(fig, master=tab_data['frame'])
            canvas.draw()
            widget = canvas.get_tk_widget()
            widget.pack(fill=tk.BOTH, expand=True)
            tab_data['canvas'] = canvas
            tab_data['fig'] = fig
            self.bind_hover_tooltip(canvas, fig, current_key, is_usd, rate)
            self._bind_chart_resize(tab_data['frame'], canvas, fig)
            self._rendered_tabs.add(current_key)
            plt.close(fig)
        except Exception:
            pass

    def update_ui_error(self, results):
        ticker = results['ticker']
        # 세션 검증
        if results.get('session_id') is not None and results.get('session_id') != self.analysis_session_id:
            return

        error_msg = results['error_msg']
        
        self.title_label.config(text=f"❌ {ticker}")
        self.status_label.config(text="●", fg='#EF5350')

        # 하단 AI 패널도 에러 표시
        try:
            self.ai_lbl_ticker_price.config(text=f"{format_asset_name(ticker)} | 분석 실패")
            self.ai_lbl_score_judgment.config(text="종합 판단: 오류 발생", fg='#EF5350')
            self.ai_lbl_sentiment.config(text="뉴스 감성: 에러", fg='#EF5350')
            self.ai_lbl_outlook.config(text=f"오류 원인:\n{error_msg}", fg='#EF5350')
        except Exception:
            pass
        messagebox.showerror("데이터 조회 실패", f"'{ticker}' 데이터를 가져오는 데 실패했습니다.\n\n원인: {error_msg}")

    def show_group_backtest_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("📊 피보나치 매수 모델 5개년 일괄 백테스트 랭킹")
        popup.geometry("850x650")
        popup.configure(bg=BG_DARK)
        popup.transient(self.root)
        popup.grab_set()
        
        title_lbl = tk.Label(popup, text="📊 14개 주요 자산 피보나치 일괄 백테스트 랭킹", font=("Segoe UI", 14, "bold"), fg='#FFFFFF', bg=BG_DARK, pady=15)
        title_lbl.pack(fill=tk.X)
        
        txt_frame = tk.Frame(popup, bg=BG_PANEL, bd=1, relief=tk.SOLID)
        txt_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        scrollbar = ttk.Scrollbar(txt_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_box = tk.Text(
            txt_frame, 
            font=("Consolas", 10), 
            bg='#151515', 
            fg='#D0D0D0', 
            insertbackground='white',
            yscrollcommand=scrollbar.set,
            wrap=tk.WORD,
            bd=0,
            padx=12,
            pady=12
        )
        text_box.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_box.yview)
        
        close_btn = tk.Button(
            popup,
            text="닫기",
            font=("Segoe UI", 10, "bold"),
            bg=BG_CARD,
            fg=TEXT_LIGHT,
            activebackground='#3A3A3A',
            bd=0,
            padx=25,
            pady=8,
            cursor='hand2',
            command=popup.destroy
        )
        close_btn.pack(pady=(0, 15))
        
        def run_analysis():
            import yfinance as _yf
            from backtest import run_backtest as _run_bt
            import os as _os
            
            tickers = [
                'BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'DOGE-USD',
                'TSLA', 'NVDA', 'AAPL', 'MSFT', 'AMZN',
                '005930.KS', '000660.KS',
                'OTLK', 'SMR'
            ]
            
            def log(msg):
                def _write():
                    text_box.config(state=tk.NORMAL)
                    text_box.insert(tk.END, msg + "\n")
                    text_box.see(tk.END)
                    text_box.config(state=tk.DISABLED)
                popup.after(0, _write)
                
            log("==================================================")
            log("Fibo Backtest Group Analysis Start (5-Year Daily)")
            log("==================================================")
            
            results_list = []
            
            for ticker in tickers:
                log(f"[{ticker}] 과거 데이터 다운로드 중...")
                try:
                    df = _yf.download(ticker, period='5y', interval='1d', progress=False)
                    if df.empty:
                        log(f"❌ [{ticker}] 데이터를 가져오지 못했습니다.")
                        continue
                    if df.columns.nlevels > 1:
                        df.columns = df.columns.droplevel(1)
                        
                    log(f"[{ticker}] 백테스트 연산 시작...")
                    nest_mode = self.nest_mode_var.get()
                    res = _run_bt(df, ticker, limit_years=5, nest_mode=nest_mode)
                    if not res.get("success", False):
                        log(f"❌ [{ticker}] 백테스트 실패: {res.get('message')}")
                        continue
                        
                    total_signals = res["total_signals"]
                    metrics = res["metrics"]
                    
                    row = {
                        'Ticker': ticker,
                        'Total Signals': total_signals,
                        'Hold_5d_WinRate': metrics[5]['win_rate'],
                        'Hold_5d_AvgReturn': metrics[5]['avg_ret'],
                        'Hold_10d_WinRate': metrics[10]['win_rate'],
                        'Hold_10d_AvgReturn': metrics[10]['avg_ret'],
                        'Hold_20d_WinRate': metrics[20]['win_rate'],
                        'Hold_20d_AvgReturn': metrics[20]['avg_ret'],
                        'Hold_30d_WinRate': metrics[30]['win_rate'],
                        'Hold_30d_AvgReturn': metrics[30]['avg_ret']
                    }
                    results_list.append(row)
                    log(f"✅ [{ticker}] 백테스트 성공. 신호 수: {total_signals}회")
                except Exception as ex:
                    log(f"❌ [{ticker}] 처리 중 오류: {ex}")
                    
            if not results_list:
                log("\n❌ 수집된 백테스트 결과가 없습니다.")
                return
                
            df_res = pd.DataFrame(results_list)
            
            # 로컬 저장
            import os
            base_dir = os.path.dirname(os.path.abspath(__file__))
            csv_path = os.path.join(base_dir, "Fibo_Backtest_Report.csv")
            md_path = os.path.join(base_dir, "Fibo_Backtest_Summary.md")
            
            df_res.to_csv(csv_path, index=False, encoding='utf-8-sig')
            
            df_res_sorted = df_res.sort_values(by='Hold_30d_WinRate', ascending=False)
            
            # 마크다운 요약본 생성
            md_lines = []
            md_lines.append("# Fibo Retracement Group Backtest 5-Year Report\n")
            md_lines.append(f"- **Generation Time**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
            md_lines.append("- **Assets**: Crypto, US Stocks, KO Stocks (Total 14 assets)")
            md_lines.append("- **Period**: Past 5 Years (Daily candle)")
            md_lines.append("- **Signal Rule**: Composite Technical Score >= 65\n")
            
            md_lines.append("## 🏆 Total Win Rate Ranking (30-Day Hold)\n")
            md_lines.append("| Rank | Ticker | Signals | 30d WinRate | 30d AvgReturn | 20d WinRate | 10d WinRate | 5d WinRate |")
            md_lines.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
            
            for rank, (_, r) in enumerate(df_res_sorted.iterrows(), 1):
                md_lines.append(
                    f"| {rank} | **{r['Ticker']}** | {r['Total Signals']} | "
                    f"{r['Hold_30d_WinRate']:.1f}% | {r['Hold_30d_AvgReturn']:+.2f}% | "
                    f"{r['Hold_20d_WinRate']:.1f}% | {r['Hold_10d_WinRate']:.1f}% | {r['Hold_5d_WinRate']:.1f}% |"
                )
                
            md_lines.append("\n---\n")
            md_lines.append("## 📊 Statistical Summary by Asset Classes\n")
            
            crypto_list = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'DOGE-USD']
            df_crypto = df_res[df_res['Ticker'].isin(crypto_list)]
            df_stocks = df_res[~df_res['Ticker'].isin(crypto_list)]
            
            md_lines.append(f"### 🪙 1. Cryptocurrencies Average Performance")
            md_lines.append(f"- **Avg Signals**: {df_crypto['Total Signals'].mean():.1f} times")
            md_lines.append(f"- **Avg Win Rate (30d)**: **{df_crypto['Hold_30d_WinRate'].mean():.1f}%**")
            md_lines.append(f"- **Avg Return (30d)**: **{df_crypto['Hold_30d_AvgReturn'].mean():+.2f}%**")
            md_lines.append(f"- *Crypto assets show high returns with significant volatility, proving that momentum works well.*\n")
            
            md_lines.append(f"### 📈 2. Stocks Average Performance")
            md_lines.append(f"- **Avg Signals**: {df_stocks['Total Signals'].mean():.1f} times")
            md_lines.append(f"- **Avg Win Rate (30d)**: **{df_stocks['Hold_30d_WinRate'].mean():.1f}%**")
            md_lines.append(f"- **Avg Return (30d)**: **{df_stocks['Hold_30d_AvgReturn'].mean():+.2f}%**")
            md_lines.append(f"- *Stocks provide reliable win rates with lower volatility compared to crypto, indicating solid bounce patterns.*\n")
            
            md_lines.append("\n---\n")
            md_lines.append("## 💡 Investment Guidelines\n")
            
            best_picks = df_res[df_res['Hold_30d_WinRate'] >= 70.0]
            md_lines.append("### 🎯 1. Top Picks (30d Win Rate >= 70%)")
            if best_picks.empty:
                md_lines.append("- No assets exceeded 70% win rate in this simulation.\n")
            else:
                for _, p in best_picks.iterrows():
                    md_lines.append(f"- **{p['Ticker']}**: 30d Win Rate **{p['Hold_30d_WinRate']:.1f}%** (Avg Return {p['Hold_30d_AvgReturn']:+.2f}%)")
                md_lines.append("")
                
            md_lines.append("### 📅 2. Optimal Holding Period Analysis")
            avg_5 = df_res['Hold_5d_WinRate'].mean()
            avg_10 = df_res['Hold_10d_WinRate'].mean()
            avg_20 = df_res['Hold_20d_WinRate'].mean()
            avg_30 = df_res['Hold_30d_WinRate'].mean()
            
            md_lines.append(f"- **5d Avg Win Rate**: {avg_5:.1f}%")
            md_lines.append(f"- **10d Avg Win Rate**: {avg_10:.1f}%")
            md_lines.append(f"- **20d Avg Win Rate**: {avg_20:.1f}%")
            md_lines.append(f"- **30d Avg Win Rate**: **{avg_30:.1f}%**")
            md_lines.append("- *Statistically, extending the holding period to 30 days yields the highest win rates and yields across most assets. This implies that composite fibonacci nested zones serve as medium-term pivot anchors rather than mere noise.*")
            
            report_text = "\n".join(md_lines)
            
            # 파일 쓰기
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report_text)
                
            def _show_final():
                text_box.config(state=tk.NORMAL)
                text_box.delete("1.0", tk.END)
                text_box.insert(tk.END, report_text)
                text_box.config(state=tk.DISABLED)
                log(f"\n📂 CSV Report Saved: {csv_path}")
                log(f"📂 Summary Report Saved: {md_path}")
                
            popup.after(0, _show_final)
            
        t = threading.Thread(target=run_analysis)
        t.daemon = True
        t.start()

    def show_damus_analysis_popup(self):
        ticker = self.current_ticker
        if not ticker:
            return
            
        popup = tk.Toplevel(self.root)
        popup.title(f"💎 {ticker} 피보나치 알고리즘 시황 분석 및 숙제")
        popup.geometry("900x780")
        popup.configure(bg=BG_DARK)
        popup.transient(self.root) 
        popup.grab_set() 
        
        title_lbl = tk.Label(popup, text=f"💎 {ticker} 피보나치 알고리즘 시황 및 숙제 분석", font=("Segoe UI", 14, "bold"), fg='#FFFFFF', bg=BG_DARK, pady=15)
        title_lbl.pack(fill=tk.X)
        
        main_container = tk.Frame(popup, bg=BG_DARK)
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # 차트 출력용 프레임 (상단)
        chart_container = tk.Frame(main_container, bg=BG_PANEL, bd=1, relief=tk.SOLID, height=350)
        chart_container.pack(fill=tk.BOTH, expand=False, side=tk.TOP, pady=(0, 10))
        chart_container.pack_propagate(False)
        
        # 요약 성과 출력용 텍스트 프레임 (하단)
        txt_frame = tk.Frame(main_container, bg=BG_PANEL, bd=1, relief=tk.SOLID)
        txt_frame.pack(fill=tk.BOTH, expand=True, side=tk.BOTTOM)
        
        scrollbar = ttk.Scrollbar(txt_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_box = tk.Text(
            txt_frame, 
            font=("Consolas", 10), 
            bg='#151515', 
            fg='#D0D0D0', 
            insertbackground='white',
            yscrollcommand=scrollbar.set,
            wrap=tk.WORD,
            bd=0,
            padx=12,
            pady=12
        )
        text_box.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_box.yview)
        
        text_box.insert(tk.END, f"{ticker}의 피보나치 당일 1시간봉 시가(SOP), 실시간 피벗(R2/R7) 및 미결제 리테스트 숙제 가격대를 산출 중입니다...\n\n잠시만 기다려 주세요...\n(약 1~2초 소요됩니다.)")
        text_box.config(state=tk.DISABLED)
        
        close_btn = tk.Button(
            popup,
            text="닫기",
            font=("Segoe UI", 10, "bold"),
            bg=BG_CARD,
            fg=TEXT_LIGHT,
            activebackground='#3A3A3A',
            bd=0,
            padx=25,
            pady=8,
            cursor='hand2',
            command=popup.destroy
        )
        close_btn.pack(pady=(0, 15))
        
        def run_damus_fetch_thread():
            try:
                rate = 1.0
                is_usd = not (ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'))
                if is_usd:
                    try:
                        rate_df = yf.download("USDKRW=X", period="1d", progress=False)
                        if rate_df.columns.nlevels > 1:
                            rate_df.columns = rate_df.columns.droplevel(1)
                        rate = float(rate_df['Close'].iloc[-1])
                    except:
                        rate = 1380.0
                
                from damus import get_damus_data, generate_damus_chart, generate_damus_report_md
                data = get_damus_data(ticker, is_usd)
                if not data:
                    raise Exception("피보나치 데이터를 수집하지 못했습니다.")
                    
                report_content = generate_damus_report_md(data, rate)
                fig = generate_damus_chart(data)
                
                popup.after(0, lambda: display_success(report_content, fig, data))
                
            except Exception as ex:
                import traceback
                traceback.print_exc()
                popup.after(0, lambda: display_error(f"❌ 피보나치 데이터 분석 실패\n\n상세 오류: {str(ex)}"))
                
        def display_error(err_msg):
            text_box.config(state=tk.NORMAL)
            text_box.delete("1.0", tk.END)
            text_box.insert(tk.END, err_msg)
            text_box.config(state=tk.DISABLED)
            
        def display_success(report_text, fig, data):
            text_box.config(state=tk.NORMAL)
            text_box.delete("1.0", tk.END)
            text_box.insert(tk.END, report_text)
            text_box.config(state=tk.DISABLED)
            
            # 차트 그리기
            canvas = FigureCanvasTkAgg(fig, master=chart_container)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
            # 호버 툴팁 바인딩
            df_today_1h = data.get('df_today_1h')
            df_1h = data.get('df_1h')
            df_plot = df_today_1h if (df_today_1h is not None and len(df_today_1h) >= 2) else df_1h.tail(24)
            self.current_damus_df = df_plot
            self.bind_hover_tooltip(canvas, fig, 'DAMUS', is_usd, rate)
            
            popup.update() # 레이아웃 업데이트 강제
            
        d_thread = threading.Thread(target=run_damus_fetch_thread)
        d_thread.daemon = True
        d_thread.start()

    def show_alert_settings_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("🔔 목표가 알림 설정 (텔레그램)")
        popup.geometry("600x750")
        popup.configure(bg=BG_DARK)
        popup.transient(self.root)
        popup.grab_set()

        title_lbl = tk.Label(popup, text="🔔 텔레그램 실시간 목표가 알림", font=("Segoe UI", 14, "bold"), fg='#FFFFFF', bg=BG_DARK, pady=15)
        title_lbl.pack(fill=tk.X)

        # 1. 텔레그램 API 설정 영역
        api_frame = tk.LabelFrame(popup, text=" 1. 텔레그램 봇 API 설정 ", font=("Segoe UI", 10, "bold"), bg=BG_PANEL, fg=ACCENT_BLUE, bd=1, relief=tk.SOLID, padx=15, pady=10)
        api_frame.pack(fill=tk.X, padx=15, pady=5)

        tk.Label(api_frame, text="Bot Token:", font=("Segoe UI", 9), bg=BG_PANEL, fg=TEXT_LIGHT).grid(row=0, column=0, sticky="e", pady=5)
        token_entry = tk.Entry(api_frame, width=45, bg=BG_CARD, fg=TEXT_LIGHT, insertbackground='white', bd=1, relief=tk.FLAT)
        token_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(api_frame, text="Chat ID:", font=("Segoe UI", 9), bg=BG_PANEL, fg=TEXT_LIGHT).grid(row=1, column=0, sticky="e", pady=5)
        chat_id_entry = tk.Entry(api_frame, width=45, bg=BG_CARD, fg=TEXT_LIGHT, insertbackground='white', bd=1, relief=tk.FLAT)
        chat_id_entry.grid(row=1, column=1, padx=10, pady=5)

        curr_token, curr_chat_id = alert_manager.get_token_and_chat_id()
        token_entry.insert(0, curr_token)
        chat_id_entry.insert(0, curr_chat_id)

        def save_api():
            alert_manager.set_telegram_config(token_entry.get().strip(), chat_id_entry.get().strip())
            messagebox.showinfo("저장 완료", "텔레그램 API 설정이 저장되었습니다.", parent=popup)

        tk.Button(api_frame, text="설정 저장", font=("Segoe UI", 9, "bold"), bg=ACCENT_BLUE, fg='white', bd=0, padx=10, pady=3, cursor='hand2', command=save_api).grid(row=2, column=1, sticky="w", padx=10, pady=5)

        # 2. 알림 추가 영역
        add_frame = tk.LabelFrame(popup, text=" 2. 신규 알림 등록 ", font=("Segoe UI", 10, "bold"), bg=BG_PANEL, fg='#00E676', bd=1, relief=tk.SOLID, padx=15, pady=10)
        add_frame.pack(fill=tk.X, padx=15, pady=10)

        tk.Label(add_frame, text="티커:", font=("Segoe UI", 9), bg=BG_PANEL, fg=TEXT_LIGHT).grid(row=0, column=0, sticky="e", pady=5)
        ticker_entry = tk.Entry(add_frame, width=15, bg=BG_CARD, fg=TEXT_LIGHT, insertbackground='white', bd=1, relief=tk.FLAT)
        ticker_entry.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        if self.current_ticker:
            ticker_entry.insert(0, self.current_ticker)

        tk.Label(add_frame, text="목표 가격:", font=("Segoe UI", 9), bg=BG_PANEL, fg=TEXT_LIGHT).grid(row=1, column=0, sticky="e", pady=5)
        price_entry = tk.Entry(add_frame, width=15, bg=BG_CARD, fg=TEXT_LIGHT, insertbackground='white', bd=1, relief=tk.FLAT)
        price_entry.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        tk.Label(add_frame, text="조건:", font=("Segoe UI", 9), bg=BG_PANEL, fg=TEXT_LIGHT).grid(row=2, column=0, sticky="e", pady=5)
        cond_var = tk.StringVar(value="above")
        rb_above = tk.Radiobutton(add_frame, text="상향 돌파 (지정가 이상)", variable=cond_var, value="above", bg=BG_PANEL, fg=TEXT_LIGHT, selectcolor=BG_PANEL, activebackground=BG_PANEL, activeforeground=TEXT_LIGHT, cursor='hand2')
        rb_below = tk.Radiobutton(add_frame, text="하향 돌파 (지정가 이하)", variable=cond_var, value="below", bg=BG_PANEL, fg=TEXT_LIGHT, selectcolor=BG_PANEL, activebackground=BG_PANEL, activeforeground=TEXT_LIGHT, cursor='hand2')
        rb_above.grid(row=2, column=1, sticky="w", padx=10)
        rb_below.grid(row=3, column=1, sticky="w", padx=10, pady=(0,5))

        def add_alert_cmd():
            t = ticker_entry.get().strip().upper()
            p = price_entry.get().strip()
            c = cond_var.get()
            if not t or not p:
                messagebox.showerror("오류", "티커와 목표 가격을 모두 입력해 주세요.", parent=popup)
                return
            try:
                p_float = float(p.replace(',', ''))
                alert_manager.add_alert(t, p_float, c)
                refresh_list()
                price_entry.delete(0, tk.END)
                messagebox.showinfo("등록 완료", f"{t} 목표가 알림이 등록되었습니다.", parent=popup)
            except ValueError:
                messagebox.showerror("오류", "가격은 숫자만 입력해 주세요.", parent=popup)

        tk.Button(add_frame, text="알림 추가", font=("Segoe UI", 9, "bold"), bg='#00E676', fg='#121212', bd=0, padx=15, pady=4, cursor='hand2', command=add_alert_cmd).grid(row=4, column=1, sticky="w", padx=10, pady=5)

        # 2-b.피보나치 레벨 알림 ON/OFF 섹션
        damus_frame = tk.LabelFrame(popup, text=" 2-b. 피보나치 레벨 알림 (SOP·R2/R7·Y2/Y7 근접 시 경고) ",
                                    font=("Segoe UI", 10, "bold"), bg=BG_PANEL, fg='#00E676',
                                    bd=1, relief=tk.SOLID, padx=15, pady=10)
        damus_frame.pack(fill=tk.X, padx=15, pady=(0, 5))

        info_lbl = tk.Label(damus_frame,
                            text="즐겨찾기 종목 중 하나를 드롭다운에서 선택하여 알림 전송 여부를 지정하거나 즐겨찾기에서 완전히 삭제합니다.",
                            font=("Segoe UI", 8), bg=BG_PANEL, fg=TEXT_MUTED, wraplength=520, justify='left')
        info_lbl.pack(anchor='w', pady=(0, 6))

        # 컨트롤들을 담을 프레임 생성
        ctrl_frame = tk.Frame(damus_frame, bg=BG_PANEL)
        ctrl_frame.pack(fill=tk.X, pady=5)

        # 드롭다운 변수 및 생성
        combo_var = tk.StringVar()
        damus_combo = ttk.Combobox(
            ctrl_frame, 
            textvariable=combo_var,
            state="readonly", 
            style='Dark.TCombobox',
            font=("Segoe UI", 10, "bold"), 
            width=25
        )
        damus_combo.pack(side=tk.LEFT, padx=(0, 10))

        # 알림 ON/OFF 체크박스
        cb_var = tk.BooleanVar(value=False)
        
        def get_selected_ticker():
            selected_str = combo_var.get()
            if not selected_str:
                return None
            fmt_name = selected_str.split()[0]
            for _, fav_ticker in self.favorites:
                if format_asset_name(fav_ticker) == fmt_name:
                    return fav_ticker
            return fmt_name

        def on_toggle_cb():
            ticker = get_selected_ticker()
            if not ticker:
                return
            is_enabled = cb_var.get()
            
            # 피보나치 알림 설정 즉시 저장
            alert_manager.set_damus_alert_ticker(ticker, is_enabled)
            
            # 드롭다운의 체크 표시 갱신
            current_selected = combo_var.get()
            update_combo_list()
            
            # 방금 갱신된 리스트에서 선택 상태 유지
            values = damus_combo['values']
            fmt_name = format_asset_name(ticker)
            for idx, val in enumerate(values):
                if val.startswith(fmt_name + " "):
                    damus_combo.current(idx)
                    break
            
            # 현재 분석 중인 티커와 동일하다면, 모니터링 스레드 제어
            if ticker == self.current_ticker:
                is_usd = not (ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'))
                tok, cid = alert_manager.get_token_and_chat_id()
                if is_enabled and tok and cid:
                    alert_manager.start_damus_monitor(ticker, is_usd, check_interval_sec=60)
                elif not is_enabled and getattr(alert_manager, '_damus_ticker', None) == ticker:
                    alert_manager.stop_damus_monitor()

        cb = tk.Checkbutton(
            ctrl_frame, text="전송유무",
            variable=cb_var,
            font=("Segoe UI", 10, "bold"),
            fg='#00E676', bg=BG_PANEL,
            selectcolor=BG_CARD,
            activebackground=BG_PANEL, activeforeground='#00E676',
            bd=0, cursor='hand2',
            command=on_toggle_cb
        )
        cb.pack(side=tk.LEFT, padx=(0, 15))

        def update_combo_list():
            values = []
            cur_tickers = alert_manager.get_damus_alert_tickers()
            for name, ticker in self.favorites:
                fmt_name = format_asset_name(ticker)
                status = "[✓]" if ticker in cur_tickers else "[ ]"
                values.append(f"{fmt_name} {status}")
            
            damus_combo['values'] = values
            
            if values:
                # 현재 분석 중인 티커가 즐겨찾기에 있다면 기본 선택
                default_idx = 0
                current_formatted = format_asset_name(self.current_ticker)
                for idx, val in enumerate(values):
                    if val.startswith(current_formatted + " "):
                        default_idx = idx
                        break
                damus_combo.current(default_idx)
                on_combo_change(None)
            else:
                combo_var.set("")
                cb_var.set(False)
                cb.config(state=tk.DISABLED)

        def on_combo_change(event):
            ticker = get_selected_ticker()
            if not ticker:
                return
            cur_tickers = alert_manager.get_damus_alert_tickers()
            cb_var.set(ticker in cur_tickers)
            cb.config(state=tk.NORMAL)

        damus_combo.bind("<<ComboboxSelected>>", on_combo_change)
        
        # 드롭다운 초기화
        update_combo_list()

        def on_close():
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_close)

        # 3. 현재 등록된 알림 목록 (드롭다운 메뉴로 개편)
        list_frame = tk.LabelFrame(popup, text=" 3. 등록된 알림 목록 ", font=("Segoe UI", 10, "bold"), bg=BG_PANEL, fg='#FF6D00', bd=1, relief=tk.SOLID, padx=15, pady=15)
        list_frame.pack(fill=tk.X, padx=15, pady=5)

        list_ctrl_frame = tk.Frame(list_frame, bg=BG_PANEL)
        list_ctrl_frame.pack(fill=tk.X, pady=5)

        alert_combo_var = tk.StringVar()
        alert_list_combo = ttk.Combobox(
            list_ctrl_frame,
            textvariable=alert_combo_var,
            state="readonly",
            style='Dark.TCombobox',
            font=("Segoe UI", 10, "bold"),
            width=38
        )
        alert_list_combo.pack(side=tk.LEFT, padx=(0, 10))

        current_alerts_data = []

        def refresh_list():
            nonlocal current_alerts_data
            alerts = alert_manager.get_all_alerts()
            values = []
            current_alerts_data = []
            
            if not alerts:
                alert_combo_var.set("등록된 알림이 없습니다.")
                alert_list_combo['values'] = ["등록된 알림이 없습니다."]
                del_alert_btn.config(state=tk.DISABLED)
                return
                
            for a in alerts:
                status_txt = "활성" if a["is_active"] else "종료"
                cond_txt = "이상 📈" if a["condition"] == "above" else "이하 📉"
                display_str = f"[{status_txt}] {a['ticker']} | 목표가: {a['target_price']} {cond_txt}"
                values.append(display_str)
                current_alerts_data.append((display_str, a['id']))
                
            alert_list_combo['values'] = values
            alert_combo_var.set(values[0])
            del_alert_btn.config(state=tk.NORMAL)

        def del_alert_cmd():
            selected_str = alert_combo_var.get()
            target_id = None
            for display_str, aid in current_alerts_data:
                if display_str == selected_str:
                    target_id = aid
                    break
            
            if target_id is not None:
                alert_manager.remove_alert(target_id)
                refresh_list()
                messagebox.showinfo("삭제 완료", "선택한 목표가 알림이 삭제되었습니다.", parent=popup)

        del_alert_btn = tk.Button(
            list_ctrl_frame, text="삭제",
            font=("Segoe UI", 9, "bold"), fg='white', bg='#EF5350',
            activeforeground='white', activebackground='#C62828',
            bd=0, padx=15, pady=4, cursor='hand2',
            command=del_alert_cmd
        )
        del_alert_btn.pack(side=tk.RIGHT)

        refresh_list()

        tk.Button(popup, text="닫기", font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=TEXT_LIGHT, activebackground='#3A3A3A', bd=0, padx=25, pady=8, cursor='hand2', command=on_close).pack(pady=15)


    def show_save_all_reports_popup(self):
        """즐겨찾기에 등록된 모든 자산의 분석 보고서를 일괄 생성 및 저장합니다."""
        import os
        import shutil
        from tkinter import filedialog
        import yfinance as yf
        import pandas as pd

        if not self.favorites:
            messagebox.showwarning(
                "즐겨찾기 없음",
                "즐겨찾기에 등록된 자산이 없습니다.\n"
                "메인 화면에서 ★ 버튼으로 자산을 즐겨찾기에 추가해 주세요."
            )
            return

        # ── 저장 폴더 선택 ────────────────────────────────────────
        save_dir = filedialog.askdirectory(
            title="보고서 저장 폴더를 선택하세요",
            initialdir=os.path.dirname(os.path.abspath(__file__))
        )
        if not save_dir:
            return

        # ── 진행 상황 팝업 ────────────────────────────────────────
        popup = tk.Toplevel(self.root)
        popup.title("💾 모든 보고서 일괄 저장 중...")
        popup.geometry("680x500")
        popup.configure(bg=BG_DARK)
        popup.transient(self.root)
        popup.grab_set()
        popup.resizable(False, False)

        # 헤더
        header = tk.Frame(popup, bg='#1B5E20', pady=12, padx=18)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="💾  즐겨찾기 자산 보고서 일괄 저장",
            font=("Segoe UI", 13, "bold"),
            fg='#E8F5E9', bg='#1B5E20'
        ).pack(side=tk.LEFT)

        # 저장 경로 표시
        path_frame = tk.Frame(popup, bg=BG_DARK, pady=8)
        path_frame.pack(fill=tk.X, padx=15)
        tk.Label(
            path_frame,
            text="📁 저장 위치:",
            font=("Segoe UI", 9, "bold"),
            fg='#90A4AE', bg=BG_DARK
        ).pack(side=tk.LEFT)
        tk.Label(
            path_frame,
            text=save_dir,
            font=("Segoe UI", 9),
            fg='#64B5F6', bg=BG_DARK,
            anchor='w'
        ).pack(side=tk.LEFT, padx=(5, 0))

        # 전체 진행 바
        total = len(self.favorites)
        prog_outer = tk.Frame(popup, bg=BG_DARK, padx=15, pady=4)
        prog_outer.pack(fill=tk.X)
        tk.Label(
            prog_outer, text="전체 진행도",
            font=("Segoe UI", 9, "bold"),
            fg='#B0BEC5', bg=BG_DARK
        ).pack(anchor='w')
        prog_bar_bg = tk.Frame(prog_outer, bg='#263238', height=18)
        prog_bar_bg.pack(fill=tk.X, pady=(2, 0))
        prog_bar_fill = tk.Frame(prog_bar_bg, bg='#00E676', height=18, width=0)
        prog_bar_fill.place(x=0, y=0, relheight=1.0, width=0)
        prog_pct_lbl = tk.Label(
            prog_outer, text="0 / 0 (0%)",
            font=("Segoe UI", 9),
            fg='#80CBC4', bg=BG_DARK
        )
        prog_pct_lbl.pack(anchor='e')

        # 현재 처리 중인 자산명
        current_lbl = tk.Label(
            popup,
            text="분석 준비 중...",
            font=("Segoe UI", 10, "bold"),
            fg='#FFD54F', bg=BG_DARK
        )
        current_lbl.pack(pady=(6, 0))

        # 로그 텍스트 박스
        log_frame = tk.Frame(popup, bg=BG_PANEL, bd=1, relief=tk.SOLID)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        log_sb = ttk.Scrollbar(log_frame)
        log_sb.pack(side=tk.RIGHT, fill=tk.Y)
        log_box = tk.Text(
            log_frame,
            font=("Consolas", 9),
            bg='#0A0F14',
            fg='#B0BEC5',
            insertbackground='white',
            yscrollcommand=log_sb.set,
            wrap=tk.WORD,
            bd=0, padx=10, pady=8,
            state=tk.DISABLED
        )
        log_box.pack(fill=tk.BOTH, expand=True)
        log_sb.config(command=log_box.yview)

        # 로그 색상 태그
        log_box.tag_configure('ok',    foreground='#00E676', font=("Consolas", 9, "bold"))
        log_box.tag_configure('err',   foreground='#FF5252', font=("Consolas", 9, "bold"))
        log_box.tag_configure('info',  foreground='#90CAF9', font=("Consolas", 9))
        log_box.tag_configure('head',  foreground='#FFD54F', font=("Consolas", 9, "bold"))
        log_box.tag_configure('dim',   foreground='#546E7A', font=("Consolas", 9))

        # 하단 버튼
        btn_bar = tk.Frame(popup, bg=BG_DARK, pady=8)
        btn_bar.pack(fill=tk.X, padx=15)
        open_folder_btn = tk.Button(
            btn_bar,
            text="📂 저장 폴더 열기",
            font=("Segoe UI", 9, "bold"),
            bg='#37474F', fg='#90CAF9',
            activebackground='#455A64',
            bd=0, padx=12, pady=5, cursor='hand2',
            state=tk.DISABLED,
            command=lambda: os.startfile(save_dir)
        )
        open_folder_btn.pack(side=tk.LEFT)
        close_btn = tk.Button(
            btn_bar,
            text="닫기",
            font=("Segoe UI", 10, "bold"),
            bg=BG_CARD, fg=TEXT_LIGHT,
            activebackground='#3A3A3A',
            bd=0, padx=25, pady=5,
            cursor='hand2',
            command=popup.destroy
        )
        close_btn.pack(side=tk.RIGHT)

        # ── 유틸 함수 ────────────────────────────────────────────
        def log(msg, tag='info'):
            def _write():
                log_box.config(state=tk.NORMAL)
                log_box.insert(tk.END, msg + "\n", tag)
                log_box.see(tk.END)
                log_box.config(state=tk.DISABLED)
            if popup.winfo_exists():
                popup.after(0, _write)

        def set_current(text):
            if popup.winfo_exists():
                popup.after(0, lambda: current_lbl.config(text=text))

        def update_progress(done, total_n):
            def _update():
                if not popup.winfo_exists():
                    return
                bar_w = prog_bar_bg.winfo_width()
                fill_w = int(bar_w * done / total_n) if total_n > 0 else 0
                prog_bar_fill.place(x=0, y=0, relheight=1.0, width=fill_w)
                pct = int(done / total_n * 100) if total_n > 0 else 0
                prog_pct_lbl.config(text=f"{done} / {total_n} ({pct}%)")
            popup.after(0, _update)

        def finish(success_count, fail_count):
            def _finish():
                if not popup.winfo_exists():
                    return
                current_lbl.config(
                    text=f"✅ 완료!  성공 {success_count}개 / 실패 {fail_count}개",
                    fg='#00E676' if fail_count == 0 else '#FFB300'
                )
                popup.title("💾 보고서 저장 완료")
                open_folder_btn.config(state=tk.NORMAL)
            popup.after(0, _finish)

        # ── 백그라운드 일괄 분석 및 저장 스레드 ─────────────────
        def batch_worker():
            import time
            from analysis import (
                fmt_price, fmt_range, fmt_large_value, fmt_chart_val,
                get_fib_levels, get_entry_signal, get_t_signal, get_adjacent_l_levels,
                calculate_composite_score, score_to_label, make_fib_markdown_table,
                generate_figures, format_fundamental_report, generate_future_outlook,
                generate_fibonacci_scenario_md, generate_news_impact_md,
                generate_strategy_and_buy_price_md
            )
            from search import search_ticker_by_name as _search

            success_n = 0
            fail_n = 0
            fav_copy = list(self.favorites)

            log(f"▶ 총 {len(fav_copy)}개 자산 보고서 저장 시작", 'head')
            log(f"  저장 경로: {save_dir}", 'dim')
            log("-" * 60, 'dim')

            for idx, (name, raw_ticker) in enumerate(fav_copy):
                if not popup.winfo_exists():
                    break

                display_name = raw_ticker.upper()
                set_current(f"⏳  [{idx+1}/{len(fav_copy)}] {display_name} 분석 중...")
                log(f"[{idx+1}/{len(fav_copy)}] {display_name} 분석 시작...", 'info')

                try:
                    # 티커 검색
                    ticker = _search(raw_ticker) or raw_ticker

                    # yfinance 데이터 다운로드
                    df_all = yf.download(ticker, period='max', interval='1d', progress=False)
                    if df_all.empty:
                        raise Exception("데이터 없음")
                    if df_all.columns.nlevels > 1:
                        df_all.columns = df_all.columns.droplevel(1)

                    is_usd = not (ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'))
                    rate = 1.0
                    if is_usd:
                        try:
                            rate_df = yf.download("USDKRW=X", period="1d", progress=False)
                            if rate_df.columns.nlevels > 1:
                                rate_df.columns = rate_df.columns.droplevel(1)
                            rate = float(rate_df['Close'].iloc[-1])
                        except:
                            rate = 1380.0

                    # 보조 지표 계산
                    delta = df_all['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
                    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
                    rs = gain / loss
                    df_all['RSI_14'] = 100 - (100 / (1 + rs))
                    df_all['SMA_5']  = df_all['Close'].rolling(5).mean()
                    df_all['SMA_20'] = df_all['Close'].rolling(20).mean()
                    ema12 = df_all['Close'].ewm(span=12, adjust=False).mean()
                    ema26 = df_all['Close'].ewm(span=26, adjust=False).mean()
                    df_all['MACD']        = ema12 - ema26
                    df_all['MACD_Signal'] = df_all['MACD'].ewm(span=9, adjust=False).mean()
                    df_all['MACD_Hist']   = df_all['MACD'] - df_all['MACD_Signal']
                    df_all['BB_Mid']   = df_all['Close'].rolling(20).mean()
                    df_all['BB_Std']   = df_all['Close'].rolling(20).std()
                    df_all['BB_Upper'] = df_all['BB_Mid'] + 2 * df_all['BB_Std']
                    df_all['BB_Lower'] = df_all['BB_Mid'] - 2 * df_all['BB_Std']
                    vol_ma20 = df_all['Volume'].rolling(20).mean()

                    current_price = float(df_all['Close'].iloc[-1])
                    current_rsi   = float(df_all['RSI_14'].iloc[-1])
                    current_sma5  = float(df_all['SMA_5'].iloc[-1])
                    current_sma20 = float(df_all['SMA_20'].iloc[-1])
                    current_macd  = float(df_all['MACD'].iloc[-1])
                    current_macd_signal = float(df_all['MACD_Signal'].iloc[-1])
                    current_macd_hist   = float(df_all['MACD_Hist'].iloc[-1])
                    current_bb_upper = float(df_all['BB_Upper'].iloc[-1])
                    current_bb_lower = float(df_all['BB_Lower'].iloc[-1])
                    current_bb_mid   = float(df_all['BB_Mid'].iloc[-1])
                    current_vol = float(df_all['Volume'].iloc[-1]) if 'Volume' in df_all.columns else 0
                    vol_ma20_val = float(vol_ma20.iloc[-1]) if vol_ma20.iloc[-1] > 0 else 1
                    vol_ratio = current_vol / vol_ma20_val if vol_ma20_val > 0 else 1.0

                    bb_band_width = current_bb_upper - current_bb_lower
                    bb_pct = (current_price - current_bb_lower) / bb_band_width if bb_band_width > 0 else 0.5

                    df_52w = df_all.tail(252)
                    week52_high = float(df_52w['High'].max())
                    week52_low  = float(df_52w['Low'].min())
                    week52_pos  = (current_price - week52_low) / (week52_high - week52_low) * 100 if (week52_high - week52_low) > 0 else 50

                    nest_mode = self.nest_mode_var.get()

                    l_high   = float(df_all['High'].max())
                    l_low    = float(df_all['Low'].min())
                    l_levels = get_fib_levels(l_high, l_low)
                    l_signal = get_entry_signal(current_price, l_levels, current_rsi)

                    df_m     = df_all.tail(180).copy()
                    df_s     = df_all.tail(30).copy()
                    df_xs    = df_all.tail(7).copy()

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
                        m_low    = float(df_m['Low'].min())
                        m_high   = float(df_m.loc[m_low_idx:]['High'].max())
                        m_levels = get_fib_levels(m_high, m_low)
                        m_signal = get_entry_signal(current_price, m_levels, current_rsi)

                        s_low_idx = df_s['Low'].idxmin()
                        s_low    = float(df_s['Low'].min())
                        s_high   = float(df_s.loc[s_low_idx:]['High'].max())
                        s_levels = get_fib_levels(s_high, s_low)
                        s_signal = get_entry_signal(current_price, s_levels, current_rsi)

                        xs_low_idx = df_xs['Low'].idxmin()
                        xs_low   = float(df_xs['Low'].min())
                        xs_high  = float(df_xs.loc[xs_low_idx:]['High'].max())
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

                    signals = [l_signal, m_signal, s_signal, xs_signal]
                    composite_score = calculate_composite_score(signals, current_rsi, current_macd_hist, bb_pct, vol_ratio)
                    score_label = score_to_label(composite_score)

                    # Ticker info
                    info = {}
                    news_list = []
                    try:
                        t_obj = yf.Ticker(ticker)
                        info = t_obj.info
                        try:
                            news_list = t_obj.news
                        except:
                            pass
                    except:
                        pass

                    # MACD, BB, 거래량 의견 (간략)
                    if current_macd > current_macd_signal and current_macd_hist > 0:
                        macd_opinion = f"MACD 골든크로스 (MACD: {current_macd:.4f} > Signal: {current_macd_signal:.4f}) — 상승 모멘텀 확인"
                    elif current_macd < current_macd_signal and current_macd_hist < 0:
                        macd_opinion = f"MACD 데드크로스 (MACD: {current_macd:.4f} < Signal: {current_macd_signal:.4f}) — 하락 모멘텀 주의"
                    else:
                        macd_opinion = f"MACD 전환 구간 (Hist: {current_macd_hist:+.4f}) — 추세 전환 관찰 필요"

                    if bb_pct >= 1.0:
                        bb_opinion = f"볼린저 상단 돌파({bb_pct*100:.0f}%) — 단기 과매수 경계"
                    elif bb_pct <= 0.0:
                        bb_opinion = f"볼린저 하단 하회({bb_pct*100:.0f}%) — 단기 과매도 반등 가능"
                    else:
                        bb_opinion = f"볼린저밴드 중립({bb_pct*100:.0f}%)"

                    vol_opinion = f"거래량 {'급증' if vol_ratio>=2 else '증가' if vol_ratio>=1.5 else '보통'} (평균 대비 {vol_ratio:.1f}배)"

                    # 전략 섹션 생성
                    strategy_md = generate_strategy_and_buy_price_md(
                        ticker, current_price, l_levels, m_levels, s_levels, xs_levels,
                        current_rsi, rate, is_usd, composite_score, vol_ratio, current_macd_hist,
                        week52_pos, bb_pct, current_sma5, current_sma20
                    )
                    fib_scenario_md  = generate_fibonacci_scenario_md(ticker, current_price, l_levels, m_levels, s_levels, xs_levels, current_rsi, rate, is_usd, vol_ratio, macd_opinion)
                    future_outlook_md = '\n' + generate_future_outlook(ticker, info, rate)
                    news_impact_md, _ = generate_news_impact_md(ticker, news_list)

                    from damus import get_damus_data, generate_damus_report_md
                    damus_data      = get_damus_data(ticker, is_usd)
                    damus_report_md = generate_damus_report_md(damus_data, rate)

                    now_str = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')

                    full_content = f"""# 📊 {ticker} 멀티 타임프레임 피보나치 중첩 분석 리포트

- **생성 일시**: {now_str}
- **분석 기준**: All-time(역사적), M(L레벨 중첩), S(M레벨 중첩), XS(S레벨 중첩)
- **적용 통화**: {'USD / KRW (환율: 1달러 = ' + f'{rate:,.2f}원)' if is_usd else 'KRW'}

---

## 1. 현재 시장 및 지표 요약
- **현재 가격**: {fmt_price(current_price, rate, is_usd)}
- **RSI (14)**: {current_rsi:.2f} ({'과매수' if current_rsi>=70 else '과매도' if current_rsi<=30 else '중립'})
- **5일 이평선**: {fmt_price(current_sma5, rate, is_usd)} / **20일 이평선**: {fmt_price(current_sma20, rate, is_usd)}

---

## 2. 타임프레임별 피보나치 진입점

| 스케일 | 고점 | 저점 | 진입 신호 |
|---|---|---|---|
| L (All-Time) | {fmt_price(l_high, rate, is_usd)} | {fmt_price(l_low, rate, is_usd)} | **{l_signal}** |
| M (Nested L) | {fmt_price(m_high, rate, is_usd)} | {fmt_price(m_low, rate, is_usd)} | **{m_signal}** |
| S (Nested M) | {fmt_price(s_high, rate, is_usd)} | {fmt_price(s_low, rate, is_usd)} | **{s_signal}** |
| XS (Nested S) | {fmt_price(xs_high, rate, is_usd)} | {fmt_price(xs_low, rate, is_usd)} | **{xs_signal}** |
| T (Yesterday) | {fmt_price(t_high, rate, is_usd)} | {fmt_price(t_low, rate, is_usd)} | **{t_signal}** |

### 📊 T Size (Yesterday's Range) 상세 레벨
| 피보나치 비율 | 레벨 구분 | 타겟 가격 | 현재가와의 이격 |
| :--- | :--- | :--- | :--- |
{make_fib_markdown_table(t_levels, current_price, rate, is_usd)}

---

## 3. 보조 지표
- **MACD**: {macd_opinion}
- **볼린저밴드**: {bb_opinion}
- **거래량**: {vol_opinion}
- **52주 위치**: {week52_pos:.1f}%

---

## 4. 종합 기술 점수
> **종합 점수: {composite_score} / 100점**  
> **최종 판단: {score_label}**

{strategy_md}
{fib_scenario_md}
{damus_report_md}
{future_outlook_md}
{news_impact_md}

---
*본 보고서는 기술적 분석 보조지표를 바탕으로 자동 생성된 정보이며, 투자 참고용으로만 사용하시기 바랍니다.*
"""
                    # 파일 저장
                    safe_name = ticker.replace('/', '_').replace('\\', '_')
                    file_path = os.path.join(save_dir, f"{safe_name}_technical_report.md")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(full_content)

                    success_n += 1
                    log(f"  ✅ {display_name} — 저장 완료  →  {os.path.basename(file_path)}", 'ok')

                except Exception as ex:
                    fail_n += 1
                    log(f"  ❌ {display_name} — 저장 실패: {ex}", 'err')

                update_progress(idx + 1, len(fav_copy))
                time.sleep(0.2)  # API 과부하 방지

            log("-" * 60, 'dim')
            log(f"▶ 완료:  성공 {success_n}개 / 실패 {fail_n}개", 'head')
            finish(success_n, fail_n)

        t = threading.Thread(target=batch_worker)
        t.daemon = True
        t.start()
