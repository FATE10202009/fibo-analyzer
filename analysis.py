# -*- coding: utf-8 -*-
import platform
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import yfinance as yf
from config import BG_DARK, BG_PANEL, BG_CARD, TEXT_LIGHT, TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN

# Matplotlib 한글 폰트 및 마이너스 깨짐 설정
if platform.system() == 'Windows':
    matplotlib.rc('font', family='Malgun Gothic')
elif platform.system() == 'Darwin':
    matplotlib.rc('font', family='AppleGothic')
else:
    matplotlib.rc('font', family='NanumGothic')
matplotlib.rcParams['axes.unicode_minus'] = False

# 가격 표시 및 환율 변환 포맷팅 함수들
def fmt_price(val_usd, rate, is_usd):
    if is_usd:
        val_krw = val_usd * rate
        return f"${val_usd:,.2f} (₩{val_krw:,.0f})"
    else:
        return f"₩{val_usd:,.0f}"

def fmt_range(low_usd, high_usd, rate, is_usd):
    if is_usd:
        low_krw = low_usd * rate
        high_krw = high_usd * rate
        return f"${low_usd:,.2f} ~ ${high_usd:,.2f} (₩{low_krw:,.0f} ~ ₩{high_krw:,.0f})"
    else:
        return f"₩{low_usd:,.0f} ~ ₩{high_usd:,.0f}"

def fmt_large_value(val_usd, rate, is_usd):
    if is_usd:
        val_krw = val_usd * rate
        if val_krw >= 1e12:
            krw_str = f"{val_krw/1e12:,.2f}조 원"
        else:
            krw_str = f"{val_krw/1e8:,.0f}억 원"
        return f"${val_usd/1e9:,.2f} Billion ({krw_str})"
    else:
        if val_usd >= 1e12:
            return f"₩{val_usd/1e12:,.2f}조 원"
        else:
            return f"₩{val_usd/1e8:,.0f}억 원"

def fmt_chart_val(val, is_usd):
    if is_usd:
        return f"${val:,.2f}"
    else:
        return f"₩{val:,.0f}"

# 피보나치 계산 공통 함수 (다무스식 상승 높이 비율)
def get_fib_levels(high, low):
    diff = high - low
    return {
        '1.000 (고점)': high,
        '0.764 (1차 조정선)': low + 0.764 * diff,
        '0.618 (첫 주요 지지선)': low + 0.618 * diff,
        '0.500 (절반선)': low + 0.500 * diff,
        '0.382 (두 번째 지지선)': low + 0.382 * diff,
        '0.236 (최종 지지선)': low + 0.236 * diff,
        '0.146 (심층 지지선)': low + 0.146 * diff,
        '0.000 (저점)': low
    }

def get_entry_signal(price, levels, rsi):
    # 다무스식 핵심 매수 타점: 첫 주요 지지선(0.618) ~ 두 번째 지지선(0.382)
    fib_0618 = levels['0.618 (첫 주요 지지선)']
    fib_0382 = levels['0.382 (두 번째 지지선)']
    buy_low = min(fib_0618, fib_0382)
    buy_high = max(fib_0618, fib_0382)
    
    if rsi <= 30:
        return "적극 매수 권장 (RSI 과매도)"
    elif buy_low <= price <= buy_high:
        return "매수 적합 (피보나치 0.382 ~ 0.618)"
    elif price < levels['0.146 (심층 지지선)']:
        return "과매도 낙폭 과대 (최종 방어선 하회)"
    else:
        return "분할 매수 대기 (주요 지지선 상회)"

def get_adjacent_l_levels(price, l_levels_dict):
    prices = sorted(list(l_levels_dict.values()))
    
    if price <= prices[0]:
        return prices[1], prices[0]
    if price >= prices[-1]:
        return prices[-1], prices[-2]
        
    low_val = prices[0]
    high_val = prices[-1]
    for i in range(len(prices) - 1):
        if prices[i] <= price <= prices[i+1]:
            low_val = prices[i]
            high_val = prices[i+1]
            break
    return high_val, low_val

def calculate_composite_score(signals, rsi, macd_hist, bb_pct, vol_ratio):
    score = 50.0  # 중립 기준점
    tf_weights = {'L': 16, 'M': 12, 'S': 8, 'XS': 4}
    for tf, signal in zip(['L', 'M', 'S', 'XS'], signals):
        w = tf_weights[tf]
        if "적극 매수" in signal:
            score += w
        elif "매수 적합" in signal:
            score += w * 0.6
        elif "낙폭 과대" in signal:
            score += w * 0.2
        elif "대기" in signal:
            score -= w * 0.3

    if rsi <= 25:
        score += 20
    elif rsi <= 35:
        score += 12
    elif rsi <= 45:
        score += 5
    elif rsi >= 75:
        score -= 20
    elif rsi >= 65:
        score -= 12
    elif rsi >= 55:
        score -= 5

    if macd_hist is not None:
        if macd_hist > 0:
            score += 20
        else:
            score -= 20

    if bb_pct is not None:
        if bb_pct < 0.1:
            score += 10
        elif bb_pct < 0.25:
            score += 6
        elif bb_pct > 0.9:
            score -= 10
        elif bb_pct > 0.75:
            score -= 6

    if vol_ratio is not None:
        if vol_ratio >= 2.0:
            score += 10
        elif vol_ratio >= 1.5:
            score += 6
        elif vol_ratio < 0.5:
            score -= 5

    return max(0.0, min(100.0, round(score, 1)))

def score_to_label(score):
    if score >= 80:
        return "🟢 강한 매수 (Strong Buy)"
    elif score >= 65:
        return "🔵 매수 우위 (Buy)"
    elif score >= 50:
        return "🟡 중립 / 관망 (Neutral)"
    elif score >= 35:
        return "🟠 매도 우위 (Sell Bias)"
    else:
        return "🔴 강한 매도 / 하락 경계 (Caution)"

def make_fib_markdown_table(levels_dict, current_price, rate, is_usd):
    rows = []
    for ratio_name, price in levels_dict.items():
        parts = ratio_name.split(' ')
        ratio = parts[0]
        label = " ".join(parts[1:]) if len(parts) > 1 else ""
        diff_pct = ((current_price / price) - 1) * 100
        price_str = fmt_price(price, rate, is_usd)
        rows.append(f"| **{ratio}** | {label} | {price_str} | {diff_pct:+.2f}% |")
    return "\n".join(rows)

# Matplotlib 다크 모드 스타일링
def style_axes_dark(ax):
    ax.set_facecolor('#1E1E1E')
    ax.spines['bottom'].set_color('#333333')
    ax.spines['top'].set_color('#333333')
    ax.spines['left'].set_color('#333333')
    ax.spines['right'].set_color('#333333')
    ax.tick_params(colors='#E0E0E0', which='both', labelsize=8)
    ax.yaxis.label.set_color('#E0E0E0')
    ax.xaxis.label.set_color('#E0E0E0')
    ax.title.set_color('#FFFFFF')
    ax.grid(True, color='#282828', linestyle=':', alpha=0.3)

def plot_clean_fib_lines(ax, levels_dict, x_index):
    f1000 = levels_dict['1.000 (고점)']
    f0764 = levels_dict['0.764 (1차 조정선)']
    f0618 = levels_dict['0.618 (첫 주요 지지선)']
    f0500 = levels_dict['0.500 (절반선)']
    f0382 = levels_dict['0.382 (두 번째 지지선)']
    f0236 = levels_dict['0.236 (최종 지지선)']
    f0146 = levels_dict['0.146 (심층 지지선)']
    f0000 = levels_dict['0.000 (저점)']
    
    # 🔴 레드존 (최종 지지 영역: 0.146 ~ 0.382)
    ax.axhspan(f0146, f0382, color='#EF5350', alpha=0.08)
    
    # 🔵 블루존 (매도 저항 영역: 0.618 ~ 0.764)
    ax.axhspan(f0618, f0764, color='#29B6F6', alpha=0.08)
    
    # 주요 피보나치 가로선 작도
    ax.axhline(y=f0618, color='#66BB6A', linestyle='--', alpha=0.7, linewidth=1.1)
    ax.axhline(y=f0382, color='#BA68C8', linestyle='--', alpha=0.7, linewidth=1.1)
    ax.axhline(y=f1000, color='#EF5350', linestyle='-', alpha=0.3, linewidth=0.7)
    ax.axhline(y=f0000, color='#90A4AE', linestyle='-', alpha=0.3, linewidth=0.7)
    
    # 보조 피보나치 가로선 작도
    ax.axhline(y=f0764, color='#FFA726', linestyle=':', alpha=0.2, linewidth=0.6)
    ax.axhline(y=f0500, color='#FFEE58', linestyle=':', alpha=0.2, linewidth=0.6)
    ax.axhline(y=f0236, color='#29B6F6', linestyle=':', alpha=0.2, linewidth=0.6)
    ax.axhline(y=f0146, color='#E91E63', linestyle=':', alpha=0.2, linewidth=0.6)
    
    # 우측 텍스트 라벨 매핑
    ax.text(x_index[-1], f1000, " 1.000 (고점)", color='#EF5350', fontsize=6, va='bottom', alpha=0.6)
    ax.text(x_index[-1], f0618, " 0.618 (1차 지지선)", color='#66BB6A', fontsize=6, va='center', fontweight='bold')
    ax.text(x_index[-1], f0382, " 0.382 (2차 지지선)", color='#BA68C8', fontsize=6, va='center', fontweight='bold')
    ax.text(x_index[-1], f0000, " 0.000 (저점)", color='#90A4AE', fontsize=6, va='top', alpha=0.6)

def draw_candlestick_with_volume(fig, df, title, fib_levels, sma_cols=None, bb_cols=None, is_usd=True):
    """
    캔들스틱 + 거래량 서브플롯을 fig 위에 그립니다.
    비율: 가격 70% / 거래량 30%
    """
    from matplotlib.patches import Rectangle
    from matplotlib.lines import Line2D
    import matplotlib.gridspec as gridspec

    gs = gridspec.GridSpec(2, 1, figure=fig,
                           height_ratios=[7, 2.5],
                           hspace=0.04)
    fig.subplots_adjust(left=0.06, right=0.97, top=0.93, bottom=0.08)
    ax_price = fig.add_subplot(gs[0])
    ax_vol   = fig.add_subplot(gs[1], sharex=ax_price)

    # ── 캔들스틱 그리기 ───────────────────────────────────────────
    UP_COLOR   = '#FF5252'  # 상승 캔들
    DOWN_COLOR = '#2979FF'  # 하락 캔들
    WICK_ALPHA = 0.85

    # 정수 x-축 매핑 (날짜 갭 없이 연속 배치)
    n = len(df)
    xs = list(range(n))
    width = 0.6

    for i, (idx, row) in enumerate(df.iterrows()):
        o, h, l, c = float(row['Open']), float(row['High']), float(row['Low']), float(row['Close'])
        color = UP_COLOR if c >= o else DOWN_COLOR
        # 심지
        ax_price.plot([i, i], [l, h], color=color, linewidth=0.8, alpha=WICK_ALPHA)
        # 몸통
        body_bottom = min(o, c)
        body_height = abs(c - o) if abs(c - o) > 0 else (h - l) * 0.01
        rect = Rectangle((i - width/2, body_bottom), width, body_height,
                          facecolor=color, edgecolor=color, linewidth=0, alpha=0.9)
        ax_price.add_patch(rect)

    ax_price.set_xlim(-0.5, n - 0.5)

    # ── SMA 오버레이 ─────────────────────────────────────────────
    if sma_cols:
        sma_colors = ['#FFB74D', '#BA68C8', '#80DEEA']
        for col_name, sma_c in zip(sma_cols, sma_colors):
            if col_name in df.columns:
                vals = df[col_name].values
                ax_price.plot(xs, vals, color=sma_c, linestyle=':', linewidth=0.9,
                              label=col_name.replace('SMA_', '').replace('_', '') + '일 이평선', alpha=0.8)

    # ── 볼린저밴드 ──────────────────────────────────────────────
    if bb_cols and all(c in df.columns for c in bb_cols):
        upper = df[bb_cols[0]].values
        lower = df[bb_cols[1]].values
        ax_price.fill_between(xs, lower, upper, alpha=0.06, color='#29B6F6')
        ax_price.plot(xs, upper, color='#29B6F6', linestyle=':', linewidth=0.6, alpha=0.4)
        ax_price.plot(xs, lower, color='#29B6F6', linestyle=':', linewidth=0.6, alpha=0.4)

    # ── 피보나치 라인 (정수 x 범위로 변환) ─────────────────────
    if fib_levels:
        fib_map = {
            '1.000 (고점)': ('#EF5350', '-', 0.3, 0.7),
            '0.764 (1차 조정선)': ('#FFA726', ':', 0.2, 0.6),
            '0.618 (첫 주요 지지선)': ('#66BB6A', '--', 0.7, 1.1),
            '0.500 (절반선)': ('#FFEE58', ':', 0.2, 0.6),
            '0.382 (두 번째 지지선)': ('#BA68C8', '--', 0.7, 1.1),
            '0.236 (최종 지지선)': ('#29B6F6', ':', 0.2, 0.6),
            '0.146 (심층 지지선)': ('#E91E63', ':', 0.2, 0.6),
            '0.000 (저점)': ('#90A4AE', '-', 0.3, 0.7),
        }
        f0146 = fib_levels.get('0.146 (심층 지지선)', 0)
        f0382 = fib_levels.get('0.382 (두 번째 지지선)', 0)
        f0618 = fib_levels.get('0.618 (첫 주요 지지선)', 0)
        f0764 = fib_levels.get('0.764 (1차 조정선)', 0)
        if f0146 and f0382:
            ax_price.axhspan(f0146, f0382, color='#EF5350', alpha=0.06)
        if f0618 and f0764:
            ax_price.axhspan(f0618, f0764, color='#29B6F6', alpha=0.06)

        for label, (color, ls, alpha, lw) in fib_map.items():
            val = fib_levels.get(label)
            if val:
                ax_price.axhline(y=val, color=color, linestyle=ls, alpha=alpha, linewidth=lw)
                short = label.split(' ')[0]
                ax_price.text(n - 0.5, val, f' {short}', color=color,
                              fontsize=5.5, va='center', alpha=min(alpha + 0.3, 1.0))

    ax_price.set_title(title, fontsize=9, color='#FFFFFF', pad=4)
    style_axes_dark(ax_price)
    plt.setp(ax_price.get_xticklabels(), visible=False)

    # ── 범례 ─────────────────────────────────────────────────────
    legend_handles = [
        Line2D([0], [0], color=UP_COLOR, linewidth=4, label='상승'),
        Line2D([0], [0], color=DOWN_COLOR, linewidth=4, label='하락'),
    ]
    ax_price.legend(handles=legend_handles, loc='upper left', fontsize=6,
                    facecolor='#121212', edgecolor='#333333', labelcolor='#FFFFFF')

    # ── 거래량 서브플롯 ──────────────────────────────────────────
    if 'Volume' in df.columns:
        vols = df['Volume'].values
        vol_ma = df['Volume'].rolling(20, min_periods=1).mean().values
        vol_colors = [UP_COLOR if float(df['Close'].iloc[i]) >= float(df['Open'].iloc[i]) else DOWN_COLOR
                      for i in range(n)]
        ax_vol.bar(xs, vols, color=vol_colors, alpha=0.55, width=0.7)
        # 평균 거래량 선
        ax_vol.plot(xs, vol_ma, color='#FFCA28', linewidth=0.8, alpha=0.6, label='20일 평균')
        ax_vol.set_ylabel('거래량', fontsize=6, color='#78909C')
        style_axes_dark(ax_vol)
        ax_vol.tick_params(axis='x', labelsize=0)   # x 틱 숨김
        ax_vol.yaxis.set_tick_params(labelsize=5)

        # x 날짜 레이블을 거래량 축에만 표시
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        labels = [str(df.index[t])[:10] for t in ticks]
        ax_vol.set_xticks(ticks)
        ax_vol.set_xticklabels(labels, fontsize=5.5, rotation=20, ha='right', color='#90A4AE')

    return ax_price, ax_vol


def generate_figures(ticker, df_all, df_m, df_s, l_levels, m_levels, s_levels, xs_levels, l_high, l_low, m_high, m_low, s_high, s_low, xs_high, xs_low, is_usd):
    figs = {}

    # 1) L Size: All-Time — 캔들스틱
    df_l_plot = df_all.tail(1000).copy()
    fig_l = plt.figure(figsize=(10, 5.5), facecolor='#1E1E1E')
    draw_candlestick_with_volume(
        fig_l, df_l_plot,
        title=f'역사적 대파동 (L Size: All-Time) (최근 1000 캔들)  고점: {fmt_chart_val(l_high, is_usd)} / 저점: {fmt_chart_val(l_low, is_usd)}',
        fib_levels=l_levels, is_usd=is_usd
    )
    figs['L'] = fig_l

    # 2) M Size: Medium — 캔들스틱 + SMA + 볼린저밴드
    fig_m = plt.figure(figsize=(10, 5.5), facecolor='#1E1E1E')
    draw_candlestick_with_volume(
        fig_m, df_m,
        title=f'중기 파동 (M Size: Nested in L) (최근 180 캔들)  고점: {fmt_chart_val(m_high, is_usd)} / 저점: {fmt_chart_val(m_low, is_usd)}',
        fib_levels=m_levels,
        sma_cols=['SMA_5', 'SMA_20'],
        bb_cols=['BB_Upper', 'BB_Lower'],
        is_usd=is_usd
    )
    figs['M'] = fig_m

    # 3) S Size: Small — 캔들스틱 + SMA
    fig_s = plt.figure(figsize=(10, 5.5), facecolor='#1E1E1E')
    draw_candlestick_with_volume(
        fig_s, df_s,
        title=f'단기 변곡 (S Size: Nested in M) (최근 30 캔들)  고점: {fmt_chart_val(s_high, is_usd)} / 저점: {fmt_chart_val(s_low, is_usd)}',
        fib_levels=s_levels,
        sma_cols=['SMA_5', 'SMA_20'],
        is_usd=is_usd
    )
    figs['S'] = fig_s

    # 4) XS Size: 1-Day — 캔들스틱
    df_xs_plot = df_all.tail(14).copy()
    fig_xs = plt.figure(figsize=(10, 5.5), facecolor='#1E1E1E')
    draw_candlestick_with_volume(
        fig_xs, df_xs_plot,
        title=f'초단기 극세 (XS Size: Nested in S) (최근 14 캔들)  고점: {fmt_chart_val(xs_high, is_usd)} / 저점: {fmt_chart_val(xs_low, is_usd)}',
        fib_levels=xs_levels,
        is_usd=is_usd
    )
    figs['XS'] = fig_xs

    # 5) RSI 14 — 기존 유지
    fig_rsi = plt.figure(figsize=(10, 5), facecolor='#1E1E1E')
    ax = fig_rsi.add_subplot(111)
    fig_rsi.subplots_adjust(left=0.06, right=0.97, top=0.93, bottom=0.10)
    df_rsi_plot = df_all.tail(180).copy()
    if 'RSI_14' in df_rsi_plot.columns:
        rsi_vals = df_rsi_plot['RSI_14'].dropna()
        ax.plot(rsi_vals.index, rsi_vals, color='#CE93D8', linewidth=1.1, label='RSI 14')
        ax.axhline(y=70, color='#EF5350', linestyle='--', linewidth=0.8, alpha=0.7)
        ax.axhline(y=30, color='#66BB6A', linestyle='--', linewidth=0.8, alpha=0.7)
        ax.axhspan(70, 100, color='#EF5350', alpha=0.05)
        ax.axhspan(0, 30, color='#66BB6A', alpha=0.05)
        ax.set_ylim(0, 100)
        ax.set_title('RSI 14 (최근 180 캔들)', fontsize=9, color='#FFFFFF')
        ax.text(rsi_vals.index[-1], 72, ' 과매수(70)', color='#EF5350', fontsize=7, va='bottom')
        ax.text(rsi_vals.index[-1], 28, ' 과매도(30)', color='#66BB6A', fontsize=7, va='top')
        ax.legend(loc='upper left', fontsize=7, facecolor='#121212', edgecolor='#333333', labelcolor='#FFFFFF')
    style_axes_dark(ax)
    fig_rsi.set_tight_layout(False)
    figs['RSI'] = fig_rsi

    # 6) MACD — 기존 유지
    fig_macd = plt.figure(figsize=(10, 5), facecolor='#1E1E1E')
    ax = fig_macd.add_subplot(111)
    fig_macd.subplots_adjust(left=0.06, right=0.97, top=0.93, bottom=0.10)
    if 'MACD' in df_rsi_plot.columns and 'MACD_Signal' in df_rsi_plot.columns:
        macd_hist_data = df_rsi_plot['MACD_Hist'].dropna()
        macd_line = df_rsi_plot['MACD'].dropna()
        signal_line = df_rsi_plot['MACD_Signal'].dropna()
        colors = ['#29B6F6' if v >= 0 else '#EF5350' for v in macd_hist_data]
        ax.bar(macd_hist_data.index, macd_hist_data, color=colors, alpha=0.7, width=1.0)
        ax.plot(macd_line.index, macd_line, color='#FFB74D', linewidth=0.9, label='MACD')
        ax.plot(signal_line.index, signal_line, color='#EF5350', linewidth=0.9, label='Signal')
        ax.axhline(y=0, color='#555555', linewidth=0.5)
        ax.set_title('MACD (12/26/9) — 최근 180 캔들', fontsize=9, color='#FFFFFF')
        ax.legend(loc='upper left', fontsize=7, facecolor='#121212', edgecolor='#333333', labelcolor='#FFFFFF')
    style_axes_dark(ax)
    fig_macd.set_tight_layout(False)
    figs['MACD'] = fig_macd

    return figs



def generate_future_outlook(ticker_name, info, rate):
    is_coin = ticker_name.endswith("-USD")
    
    rec = info.get('recommendationKey', 'none')
    target_mean = info.get('targetMeanPrice')
    curr_price = info.get('currentPrice') or info.get('regularMarketPrice') or 1.0
    gap = ((target_mean / curr_price) - 1) * 100 if target_mean and curr_price else 0.0
    peg = info.get('pegRatio')
    forward_pe = info.get('forwardPE')
    
    lines = []
    lines.append("\n[📈 향후 1~5년 연차별 세부 전망 (애널리스트 및 정량적 전망)]")
    
    if is_coin:
        lines.append("■ 1년차 (단기 - 시장 흐름 및 유동성 국면):")
        lines.append(" - 글로벌 금리 인하 주기와 가상자산 현물 ETF 자금 유입 속도에 따라 가격 변동성이 지배됩니다.")
        lines.append(" - 단기적으로는 피보나치 주요 지지선 안착 여부 및 RSI 지표의 과매수/과매도 해소 여부가 매수 타이밍을 결정합니다.")
        
        lines.append("\n■ 2년차 (중기 - 반감기 효과 및 제도권 편입):")
        lines.append(" - 비트코인 반감기 사이클에 따른 공급 감소 효과가 본격적으로 공급 압박으로 작용하여 장기 상승 기동력을 확보하는 시기입니다.")
        lines.append(" - 글로벌 규제 명확성(Framework) 확보 여부 및 전통 금융기관의 자산 배분 비중 확대가 중기 방향성을 지지합니다.")
        
        lines.append("\n■ 3~5년차 (장기 - 글로벌 대체 자산 및 인프라 성숙):")
        lines.append(" - 실물자산 토큰화(RWA) 및 탈중앙 금융(DeFi) 인프라의 제도권 인수가 핵심 마일스톤입니다.")
        lines.append(" - 글로벌 부채 증가 및 법정화폐의 구매력 가치 저하에 대한 헤징(Hedging) 수단으로 디지털 금으로서의 입지를 굳힐 전망입니다.")
    else:
        sector = info.get('sector', 'Unknown')
        
        lines.append("■ 1년차 (단기 - 목표가 괴리율 및 실적 모멘텀):")
        if target_mean and gap > 15:
            lines.append(f" - 애널리스트들의 평균 목표치 대비 괴리율이 {gap:+.1f}%로 저평가 매력이 큽니다. 단기 낙폭 과대에 따른 밸류에이션 회복 랠리가 1년 내 기대됩니다.")
        elif target_mean and gap < -5:
            lines.append(f" - 현재 주가가 목표가 ({gap:+.1f}%)를 이미 초과하여, 단기적으로는 차익 매물 소화 및 실적 검증을 위한 밸류에이션 조정 국면을 거칠 수 있습니다.")
        else:
            lines.append(" - 현재가는 애널리스트들의 목표 주가 수준에 부합하며, 다음 분기 어닝 가이던스 상향 여부가 단기 상승 모멘텀의 핵심입니다.")
            
        lines.append("\n■ 2년차 (중기 - 밸류에이션 매력 및 이익 성장성):")
        if peg and 0 < peg < 1.2:
            lines.append(f" - PEG 비율이 {peg:.2f}배로 이익 성장성 대비 주가가 현저히 저평가되어 있습니다. 중기 실적 장세 국면에서 우수한 초과 성과가 예상됩니다.")
        elif forward_pe and forward_pe > 35:
            lines.append(f" - 선행 PER이 {forward_pe:.1f}배로 고성장 기대감이 높게 선반영되어 있습니다. 이익의 실제 질과 성장률 추이가 확인되지 않을 시 밸류에이션 멀티플 압박이 올 수 있습니다.")
        else:
            lines.append(" - 안정적인 캐시카우 창출 능력을 기반으로 업종 평균 수준의 밸류에이션 멀티플을 유지하며, 완만한 실적 성장을 지속할 것으로 예상됩니다.")
            
        lines.append("\n■ 3~5년차 (장기 - 미래 핵심 성장 동력 및 산업 지배력):")
        if "Technology" in sector or "Communication" in sector:
            lines.append(" - 인공지능(AI) 인프라 생태계의 성숙, 클라우드 부문의 견조한 매출 확장성 및 글로벌 비즈니스 지배력을 바탕으로 장기적인 구조적 성장이 견고합니다.")
        elif "Healthcare" in sector:
            lines.append(" - 글로벌 인구 고령화 수혜와 차세대 바이오 플랫폼/신약 임상 파이프라인의 상업화 성과에 따라 장기 메가트렌드 성장을 실현할 것으로 분석됩니다.")
        else:
            lines.append(" - 경기 주기 변동성(Cyclical)을 극복하고, 지속 가능한 주주환원(배당 및 자사주 매입) 확대 정책이 장기 주주가치를 결정하는 가장 큰 핵심 요인입니다.")
            
    return "\n".join(lines)

def format_fundamental_report(ticker_name, info, rate):
    lines = []
    lines.append(f"============================================================")
    lines.append(f" 🔍 {ticker_name} 기본적 자산 가치 및 장기 전망 리포트")
    lines.append(f"============================================================")
    
    is_coin = ticker_name.endswith("-USD")
    long_name = info.get('longName') or info.get('shortName') or info.get('name') or ticker_name
    lines.append(f"● 자산 이름: {long_name} ({ticker_name})")
    
    market_cap = info.get('marketCap')
    if market_cap:
        mcap_str = fmt_large_value(market_cap, rate, is_coin or not (ticker_name.endswith('.KS') or ticker_name.endswith('.KQ')))
        lines.append(f"● 시가 총액: {mcap_str}")
    else:
        lines.append(f"● 시가 총액: 정보 없음")
        
    is_usd = is_coin or not (ticker_name.endswith('.KS') or ticker_name.endswith('.KQ'))
        
    if is_coin:
        lines.append("\n[🪙 코인 핵심 공급량 및 거래 데이터]")
        circ_supply = info.get('circulatingSupply')
        max_supply = info.get('maxSupply')
        vol_24h = info.get('volume24Hr') or info.get('volume')
        
        if circ_supply:
            lines.append(f" - 유통 공급량: {circ_supply:,.0f}개")
        if max_supply:
            lines.append(f" - 최대 공급량: {max_supply:,.0f}개")
        if vol_24h:
            vol_str = fmt_large_value(vol_24h, rate, is_usd)
            lines.append(f" - 24시간 거래대금: {vol_str}")
            
        desc = info.get('description')
        if desc:
            lines.append(f"\n[📝 자산 설명]")
            lines.append(desc[:1200] + "..." if len(desc) > 1200 else desc)
            
        lines.append("\n[💡 암호화폐 가치 및 장기 전망]")
        lines.append(" - 암호화폐는 재무제표가 존재하지 않아 토큰 유통 구조(Tokenomics), 네트워크 활용 빈도(온체인 데이터), 전 세계 유동성 환경이 가치를 좌우합니다.")
        lines.append(" - 최대 공급량 대비 현재 유통량 비율을 확인하여 신규 락업 해제에 따른 희석 리스크를 분석해야 합니다.")
    else:
        sector = info.get('sector')
        industry = info.get('industry')
        lines.append(f"● 섹터 / 산업군: {sector} / {industry}")
        
        lines.append("\n[📊 재무 가치 평가 및 성장성 지표]")
        forward_pe = info.get('forwardPE')
        pbr = info.get('priceToBook')
        peg = info.get('pegRatio')
        rev_growth = info.get('revenueGrowth')
        earning_growth = info.get('earningsGrowth')
        
        lines.append(f" - 선행 PER (Forward P/E): {f'{forward_pe:,.2f}배' if forward_pe else '정보 없음 (적자 상태 또는 미집계)'}")
        lines.append(f" - PBR (Price to Book): {f'{pbr:,.2f}배' if pbr else '정보 없음'}")
        lines.append(f" - PEG 비율 (P/E to Growth): {f'{peg:,.2f}배' if peg else '정보 없음'}")
        
        if rev_growth:
            lines.append(f" - 매출 성장률 (YoY): {rev_growth*100:+.2f}%")
        if earning_growth:
            lines.append(f" - 순이익 성장률 (YoY): {earning_growth*100:+.2f}%")
            
        lines.append("\n[🎯 애널리스트 투자의견 및 목표 주가]")
        rec = info.get('recommendationKey')
        target_mean = info.get('targetMeanPrice')
        
        if rec:
            rec_ko = {
                'buy': '매수 (Buy)',
                'strong_buy': '적극 매수 (Strong Buy)',
                'hold': '보유 (Hold)',
                'underperform': '비중 축소 (Underperform)',
                'sell': '매도 (Sell)'
            }.get(rec.lower(), rec)
            lines.append(f" - 컨센서스 의견: {rec_ko}")
            
        if target_mean:
            target_str = fmt_price(target_mean, rate, is_usd)
            lines.append(f" - 평균 목표 주가: {target_str}")
            
            curr_price = info.get('currentPrice') or info.get('regularMarketPrice')
            if curr_price:
                gap = ((target_mean / curr_price) - 1) * 100
                lines.append(f" - 현재가 대비 목표가 괴리율: {gap:+.2f}% (목표가 달성 시 예상 수익률)")
        else:
            lines.append(" - 애널리스트 목표가 정보 없음")
            
        summary = info.get('longBusinessSummary')
        if summary:
            lines.append(f"\n[📝 기업 사업 개요]")
            lines.append(summary[:1200] + "..." if len(summary) > 1200 else summary)
            
        lines.append("\n[💡 기업 가치 및 장기 전망]")
        if rec and rec.lower() in ['buy', 'strong_buy']:
            lines.append(f" - 애널리스트들의 종합 합의가 '{rec_ko}'로 향후 성장성과 실적 회복에 긍정적인 입장을 보이고 있습니다.")
        else:
            lines.append(" - 기업의 적자 탈피 여부 및 재무 안정성 지표를 주기적으로 확인하는 보수적인 투자 관점이 유효합니다.")
            
    try:
        outlook_text = generate_future_outlook(ticker_name, info, rate)
        lines.append(outlook_text)
    except:
        pass
            
    return "\n".join(lines)

def generate_fibonacci_scenario_md(ticker, current_price, l_levels, m_levels, s_levels, xs_levels, rsi, rate, is_usd, vol_ratio, macd_opinion):
    l_0500 = l_levels.get('0.500 (절반선)', 0)
    m_0382 = m_levels.get('0.382 (두 번째 지지선)', 0)
    m_0236 = m_levels.get('0.236 (최종 지지선)', 0)
    s_0382 = s_levels.get('0.382 (두 번째 지지선)', 0)
    s_0000 = s_levels.get('0.000 (저점)', 0)
    xs_1000 = xs_levels.get('1.000 (고점)', 0)
    xs_0382 = xs_levels.get('0.382 (두 번째 지지선)', 0)
    xs_0236 = xs_levels.get('0.236 (최종 지지선)', 0)
    
    def get_p_str(val):
        return fmt_price(val, rate, is_usd)
        
    md = []
    md.append(f"## 9. 🎯 피보나치 비율 기반 향후 흐름 및 대응 시나리오 (다무스 분석법)\n")
    md.append(f"현재 {ticker}의 가격 **{get_p_str(current_price)}**은 여러 타임프레임의 피보나치 지지선이 조밀하게 모여 있는 **'피보나치 분석 구간'**에 위치해 있습니다. 이에 따른 기술적 분석과 향후 흐름 시나리오는 다음과 같습니다.\n")
    
    md.append(f"### 1) 주요 피보나치 지지 및 저항 레벨 분석")
    
    support_1st_low = min(m_0236, s_0000, xs_0236)
    support_1st_high = max(m_0236, s_0000, xs_0236)
    
    if support_1st_low > 0 and (support_1st_high - support_1st_low) / support_1st_low < 0.03:
        md.append(f"* **핵심 지지선 1차 밴드 ({get_p_str(support_1st_low)} ~ {get_p_str(support_1st_high)})**:")
        md.append(f"  - 초단기(XS) 0.382 두 번째 지지선 ({get_p_str(xs_0382)})")
        md.append(f"  - 초단기(XS) 0.236 최종 지지선 ({get_p_str(xs_0236)})")
        md.append(f"  - 단기(S) 저점 및 중기(M) 0.236 최종 지지선 ({get_p_str(m_0236)})")
        diff_min = ((current_price / support_1st_high) - 1) * 100
        diff_max = ((current_price / support_1st_low) - 1) * 100
        md.append(f"  - *현재 가격은 이 강력한 다중 중첩 지지 영역 부근에 위치해 있습니다 (현재가와의 이격: {diff_min:+.2f}% ~ {diff_max:+.2f}%).*")
    else:
        md.append(f"* **핵심 지지선 1차 라인 ({get_p_str(xs_0236)})**:")
        md.append(f"  - 초단기(XS) 0.236 최종 지지선 ({get_p_str(xs_0236)})")
        md.append(f"* **핵심 지지선 2차 라인 ({get_p_str(m_0236)})**:")
        md.append(f"  - 중기(M) 0.236 최종 지지선 ({get_p_str(m_0236)})")
        
    md.append(f"* **핵심 지지선 2차 마지노선 (레드존 최종선: {get_p_str(l_0500)})**:")
    md.append(f"  - 장기(L) 0.500 절반선 및 중기(M) 0.000 저점 ({get_p_str(l_0500)})")
    
    res_1st_low = min(xs_1000, s_0382)
    res_1st_high = max(xs_1000, s_0382)
    md.append(f"* **단기 저항선 ({get_p_str(res_1st_low)} ~ {get_p_str(res_1st_high)})**:")
    md.append(f"  - 초단기(XS) 고점 ({get_p_str(xs_1000)})")
    md.append(f"  - 단기(S) 0.382 두 번째 지지선 ({get_p_str(s_0382)})")
    md.append(f"* **중기 저항선 ({get_p_str(m_0382)})**:")
    md.append(f"  - 중기(M) 0.382 두 번째 지지선 ({get_p_str(m_0382)})")
    
    md.append("\n---\n")
    
    md.append(f"### 2) 향후 흐름 시나리오 및 매매 전략\n")
    
    prob_a = 70 if rsi <= 35 else 60 if rsi <= 50 else 40
    md.append(f"#### 📈 시나리오 A: 주요 지지선 안착 및 기술적 반등 (확률: {prob_a}%)")
    if rsi <= 30:
        md.append(f"* **분석**: 현재 일봉 RSI가 **{rsi:.2f}**로 극심한 과매도 상태(30 이하)에 놓여 있으며, 보조지표상 기술적 매수세 유입이 강하게 기대되는 시점입니다.")
    else:
        md.append(f"* **분석**: 현재 일봉 RSI가 **{rsi:.2f}**로 완만한 상태이나, 주요 피보나치 지지 라인 부근에서 하방 경직성을 확보하고 있습니다.")
        
    md.append(f"* **전망**: 지지선 안착 확인 후 반등 시, 1차적으로 초단기 저항대인 **{get_p_str(res_1st_low)} ~ {get_p_str(res_1st_high)}** 영역 돌파를 시도할 것입니다. 돌파 성공 시 단기 숏커버링 랠리가 이어지며 중기 추세의 강력한 매물벽이자 다무스식 지지 전환선인 **{get_p_str(m_0382)}**까지 상승 여력이 열리게 됩니다.")
    md.append(f"* **대응 전략**: 주요 지지선 1차 밴드 구간을 단기 바닥으로 삼아 신규 진입자는 **분할 매수(Scale-in) 전략**으로 대응하는 것이 유리합니다.")
    
    prob_b = 100 - prob_a
    md.append(f"\n#### 📉 시나리오 B: 핵심 지지선 이탈 시 추가 하락 조정 (확률: {prob_b}%)")
    md.append(f"* **분석**: {macd_opinion} 및 현재 거래량이 평균 대비 {vol_ratio:.1f}배 기록되는 등 하락 압력이 지속될 경우 지지선 테스트가 이어질 수 있습니다.")
    md.append(f"* **전망**: 만약 강력한 매도세로 인해 1차 핵심 지지선인 **{get_p_str(m_0236)}**이 일봉 종가 기준으로 완전히 이탈한다면, 추가적인 매물 출회로 하락세가 깊어질 수 있습니다. 이 경우 다음 핵심 지지선이자 레드존 최종 마지노선인 장기(L) 0.500선 부근인 **{get_p_str(l_0500)}**까지 조정 폭이 확대될 수 있습니다.")
    md.append(f"* **대응 전략**: 만약 1차 지지선이 무너질 경우 리스크 관리 차원에서 비중을 축소하고, 차후 **{get_p_str(l_0500)} 부근에서 재매수 기회**를 분할로 노리는 것이 현명합니다.")
    
    return "\n".join(md)

def generate_news_impact_md(ticker, news_list, api_key=None):
    md = []
    md.append("## 11. 📰 최신 주요 뉴스 및 시장 영향 분석 (뉴스 및 영향 분석)\n")
    
    if not news_list:
        md.append("최근 등록된 주요 뉴스 데이터가 없습니다.\n")
        return "\n".join(md), None
        
    md.append("### 1) 최근 주요 뉴스 헤드라인\n")
    for item in news_list[:4]:
        content = item.get('content', {})
        title = content.get('title', '정보 없음')
        provider = content.get('provider', {}).get('displayName', '알 수 없음')
        pub_date = content.get('pubDate', '')
        url_info = content.get('canonicalUrl') or content.get('clickThroughUrl') or {}
        url = url_info.get('url', '#')
        
        date_str = pub_date[:10] if len(pub_date) >= 10 else pub_date
        md.append(f"* [{title}]({url}) ({provider} | {date_str})")
        
    is_coin = ticker.endswith("-USD")
    
    # Gemini AI 뉴스 분석 호출 시도
    ai_result = None
    try:
        from ai_analyzer import analyze_news_with_gemini
        ai_result = analyze_news_with_gemini(news_list, ticker, not is_coin, api_key=api_key)

    except Exception as e:
        print(f"[Warning] Gemini AI 뉴스 분석 임포트 혹은 호출 실패: {e}")

    md.append("\n---\n")
    
    if ai_result:
        # AI 결과가 성공적으로 수집된 경우
        md.append("### 2) 뉴스 종합 분석 및 자산 가격 영향도 평가 (Gemini 3.5 AI 분석)\n")
        
        # 감성 색상 마커 지정
        sentiment = ai_result.get("sentiment", "중립")
        score = ai_result.get("sentiment_score", 0)
        
        if "긍정" in sentiment or score > 20:
            sent_str = f"🟢 긍정적 (호재 우세)"
        elif "부정" in sentiment or score < -20:
            sent_str = f"🔴 부정적 (악재 우세)"
        else:
            sent_str = f"🟡 중립적 / 혼조세"
            
        md.append("| 분석 지표 | AI 정밀 분석 내용 |")
        md.append("| :--- | :--- |")
        md.append(f"| **종합 감성 (시장 심리)** | **{sent_str} (점수: {score:+.0f} / 100)** |")
        md.append(f"| **단기 영향 (1~4주)** | {ai_result.get('short_term', '정보 없음')} |")
        md.append(f"| **중장기 영향 (3~6개월)** | {ai_result.get('mid_term', '정보 없음')} |")
        
        # 리스크 요인 표시
        md.append("\n#### ⚠️ 주요 리스크 요인 (위험 요인)")
        risks = ai_result.get("risks", [])
        if risks:
            for r in risks:
                md.append(f"* {r}")
        else:
            md.append("* 최근 뉴스 기반 식별된 명확한 리스크가 없습니다.")
            
        # 촉매 요인 표시
        md.append("\n#### 🚀 주요 호재 및 촉매 요인 (촉매 요인)")
        catalysts = ai_result.get("catalysts", [])
        if catalysts:
            for c in catalysts:
                md.append(f"* {c}")
        else:
            md.append("* 최근 뉴스 기반 식별된 명확한 촉매제가 없습니다.")
            
        md.append("\n*본 분석은 Gemini 3.5 AI 모델이 실시간 수집된 뉴스를 요약/종합하여 자동 판별한 결과이며, 투자 추천이나 확정된 이익을 보장하지 않습니다.*")
    else:
        # 폴백: 기존 템플릿 사용
        md.append("### 2) 뉴스 종합 분석 및 자산 가격 영향도 평가 (기본 분석 템플릿)\n")
        if is_coin:
            md.append("| 분석 항목 | 영향도 구분 | 단기 영향 (1~4주) | 중장기 영향 (3~6개월) |")
            md.append("| :--- | :--- | :--- | :--- |")
            md.append("| **거시 경제 유동성** | **부정적/중립적 (높음)** | 위험선호 위축 및 거래 대금 감소 | 금리 인하 피벗 시 강한 반등 |")
            md.append("| **기관 ETF 수급 추이** | **부정적 (보통)** | 수급 공백으로 인한 횡보 및 조정 | 가을철 유입 대기로 점진적 회복 |")
            md.append("| **글로벌 컨퍼런스/서밋** | **긍정적 (보통)** | 기술 로드맵 부각으로 하방 경직성 제공 | 신규 투자 및 규제 개선 시너지 |")
            
            md.append("\n#### 💡 최종 가격 영향 분석 및 전망")
            md.append(f"*   **단기 관점 (약세 및 횡보 우세)**: 글로벌 물가 및 유동성 불안 요인이 지속되고 있어 단기적으로는 하방 테스트가 지속될 수 있습니다. 피보나치 주요 지지선 근처에서 바닥 다지기를 하는 횡보 흐름이 예상됩니다.")
            md.append(f"*   **중장기 관점 (점진적 회복)**: 여름철 계절적 비수기가 지난 후, 공급 감소 효과(반감기 공급 쇼크)가 가시화되고 규제 프레임워크가 명확화됨에 따라 점진적인 반등 기조를 형성할 것입니다.")
        else:
            md.append("| 분석 항목 | 영향도 구분 | 단기 영향 (1~4주) | 중장기 영향 (3~6개월) |")
            md.append("| :--- | :--- | :--- | :--- |")
            md.append("| **통화 긴축 정책 영향** | **부정적/중립적 (높음)** | 고금리 장기화에 따른 밸류에이션 멀티플 압박 | 실적 중심의 주가 차별화 장세 |")
            md.append("| **분기 실적 및 가이던스** | **긍정적/부정적 (높음)** | 실적 발표 전후의 변동성 확대 | 견조한 캐시카우 기반 주주 환원 확대 |")
            md.append("| **글로벌 공급망 & 원자재** | **중립적 (보통)** | 공급망 지연 및 비용 부담 노이즈 | 생산성 효율화 및 마진율 개선 가능성 |")
            
            md.append("\n#### 💡 최종 가격 영향 분석 및 전망")
            md.append(f"*   **단기 관점 (실적 검증 국면)**: 연준의 고금리 스탠스로 주식 시장 전반의 변동성이 높습니다. 분기 실적 및 차분기 실적 가이던스의 달성 여부에 따라 개별 종목 장세가 강하게 나타날 것입니다.")
            md.append(f"*   **중장기 관점 (실적 성장 주도)**: 거시 경제적 악재를 이겨낼 수 있는 독점적 시장 지배력 및 혁신 산업군(AI 등)의 침투율 성장에 따라 우량주 중심의 주가 상승세가 이어질 전망입니다.")
        
    return "\n".join(md), ai_result


def generate_strategy_and_buy_price_md(
    ticker, current_price, l_levels, m_levels, s_levels, xs_levels,
    rsi, rate, is_usd, composite_score, vol_ratio, macd_hist,
    week52_position, bb_pct, current_sma5, current_sma20
):
    """
    단기 전략, 장기 전략, 적절한 매수가를 마크다운으로 생성합니다.
    """
    def get_p_str(val):
        return fmt_price(val, rate, is_usd)

    md = []

    # ─── 섹션 7: 단기 전략 (1~4주) ───────────────────────────────
    md.append("## 7. 📅 단기 매매 전략 (1~4주 관점)\n")

    # 단기 방향성 판단
    if rsi <= 30 and bb_pct <= 0.15:
        short_bias = "🟢 **강한 기술적 반등 국면** (RSI 과매도 + 볼린저 하단 이탈)"
        short_action = "분할 매수 적극 진입"
    elif rsi <= 40 and composite_score >= 65:
        short_bias = "🟢 **매수 우위 국면** (과매도 완화 + 지표 개선)"
        short_action = "단계적 분할 매수"
    elif rsi >= 70 and bb_pct >= 0.85:
        short_bias = "🔴 **과매수 경고 국면** (RSI 과매수 + 볼린저 상단 초과)"
        short_action = "신규 매수 자제, 기존 물량 일부 익절 고려"
    elif composite_score >= 50:
        short_bias = "🟡 **중립 ~ 소폭 매수 우위 국면**"
        short_action = "주요 지지선 테스트 시 소량 매수 대응"
    else:
        short_bias = "🟠 **하락 추세 국면** (지표 약세)"
        short_action = "관망 유지, 추가 하락 시 저점 매집 준비"

    # 단기 핵심 지지/저항
    xs_0382 = xs_levels.get('0.382 (두 번째 지지선)', 0)
    xs_0618 = xs_levels.get('0.618 (첫 주요 지지선)', 0)
    xs_1000 = xs_levels.get('1.000 (고점)', 0)
    s_0382 = s_levels.get('0.382 (두 번째 지지선)', 0)
    s_0618 = s_levels.get('0.618 (첫 주요 지지선)', 0)
    m_0382 = m_levels.get('0.382 (두 번째 지지선)', 0)

    md.append(f"### 🔍 단기 시장 방향성 판단\n")
    md.append(f"- **현재 국면**: {short_bias}")
    md.append(f"- **권장 행동**: {short_action}")
    md.append(f"- **RSI (14)**: {rsi:.2f} → {'과매도 반등 대기' if rsi <= 30 else '과매수 경계' if rsi >= 70 else '중립 구간'}")
    if current_sma5 > current_sma20:
        md.append(f"- **이동평균 배열**: 5일선 > 20일선 → **정배열** (단기 상승 추세 우호적)")
    else:
        md.append(f"- **이동평균 배열**: 5일선 < 20일선 → **역배열** (단기 하락 압력 지속)")
    md.append("")

    md.append(f"### 📌 단기 핵심 가격 레벨\n")
    md.append(f"| 구분 | 가격 | 의미 |")
    md.append(f"| :--- | :--- | :--- |")
    md.append(f"| **단기 저항선** | {get_p_str(xs_1000)} | XS 고점 / 단기 돌파 목표 |")
    md.append(f"| **1차 저항** | {get_p_str(s_0382)} | S Size 0.382 저항선 |")
    md.append(f"| **현재 가격** | **{get_p_str(current_price)}** | — |")
    md.append(f"| **1차 지지** | {get_p_str(xs_0618)} | XS Size 0.618 지지선 |")
    md.append(f"| **단기 손절 기준** | {get_p_str(xs_0382)} | XS 0.382 하회 시 추가 하락 유의 |")
    md.append("")

    md.append(f"### 💡 단기 매매 시나리오\n")
    if rsi <= 35 or (bb_pct <= 0.2 and composite_score >= 60):
        md.append(f"> **📈 반등 시나리오 (확률 높음)**: RSI 과매도 구간에서 {get_p_str(xs_0618)} 지지 확인 시 "
                  f"단기 반등 시도. 목표가 1차 **{get_p_str(xs_1000)}**, 2차 **{get_p_str(s_0382)}**")
        md.append(f">")
        md.append(f"> **📉 하락 시나리오 (확률 낮음)**: {get_p_str(xs_0382)} 일봉 종가 하회 시 "
                  f"단기 손절 or 관망 전환. 다음 지지선 **{get_p_str(s_0618)}** 재진입 고려")
    else:
        md.append(f"> **📈 반등 시나리오**: 주요 지지선 안착 확인 후 {get_p_str(xs_1000)} 돌파 시도. "
                  f"추세 전환 확인 후 추가 매수 고려")
        md.append(f">")
        md.append(f"> **📉 하락 시나리오**: {get_p_str(xs_0382)} 하회 시 추가 하락 압력. "
                  f"관망 유지 후 {get_p_str(s_0618)} 수준 재진입 검토")

    md.append("\n---\n")

    # ─── 섹션 8: 장기 전략 (3~12개월) ───────────────────────────────
    md.append("## 8. 🗓️ 장기 투자 전략 (3~12개월 관점)\n")

    l_0618 = l_levels.get('0.618 (첫 주요 지지선)', 0)
    l_0500 = l_levels.get('0.500 (절반선)', 0)
    l_0382 = l_levels.get('0.382 (두 번째 지지선)', 0)
    l_0764 = l_levels.get('0.764 (1차 조정선)', 0)
    l_1000 = l_levels.get('1.000 (고점)', 0)

    # 장기 방향성: 52주 위치 + L Size 레벨 기반
    if week52_position <= 20:
        long_bias = "🟢 **강한 장기 매수 구간** (52주 저점 부근 극심한 저평가)"
        long_action = "장기 분할 매수 적극 실행 — 핵심 지지선 부근 집중 매집"
        long_probability = "상승 전환 확률 높음"
    elif week52_position <= 40:
        long_bias = "🟢 **장기 매수 우위 구간** (저평가 영역)"
        long_action = "중장기 분할 매수 단계적 실행"
        long_probability = "중장기 우상향 가능성"
    elif week52_position <= 70:
        long_bias = "🟡 **중립 구간** (52주 중간 영역)"
        long_action = "추가 하락 시 분할 매수, 급등 시 일부 익절"
        long_probability = "방향성 확인 후 대응"
    else:
        long_bias = "🔴 **고점 경계 구간** (52주 상단 부근)"
        long_action = "신규 매수 자제, 기존 보유자 이익 실현 전략"
        long_probability = "추가 상승 제한적, 조정 가능성"

    is_coin = ticker.endswith("-USD")

    md.append(f"### 🔍 장기 시장 방향성 판단\n")
    md.append(f"- **현재 장기 국면**: {long_bias}")
    md.append(f"- **권장 장기 전략**: {long_action}")
    md.append(f"- **52주 현재 위치**: {week52_position:.1f}% 구간 → {long_probability}")
    md.append(f"- **장기 피보나치 기준점**: L Size 고점 {get_p_str(l_1000)} / 저점 {get_p_str(l_levels.get('0.000 (저점)', 0))}")
    md.append("")

    md.append(f"### 📌 장기 핵심 가격 레벨 (L Size 기준)\n")
    md.append(f"| 피보나치 레벨 | 가격 | 장기 의미 |")
    md.append(f"| :--- | :--- | :--- |")
    md.append(f"| **역대 고점 (1.000)** | {get_p_str(l_1000)} | 장기 최고 저항선 |")
    md.append(f"| **1차 조정선 (0.764)** | {get_p_str(l_0764)} | 강세장 조정 지지 |")
    md.append(f"| **황금비율 (0.618)** | {get_p_str(l_0618)} | 장기 핵심 지지/매수 구간 ⭐ |")
    md.append(f"| **절반선 (0.500)** | {get_p_str(l_0500)} | 심리적 마지노선 |")
    md.append(f"| **강한 지지 (0.382)** | {get_p_str(l_0382)} | 장기 저점 매집 최적 구간 |")
    md.append(f"| **현재 가격** | **{get_p_str(current_price)}** | 현재 위치 |")
    md.append("")

    if is_coin:
        md.append(f"### 💡 장기 투자 핵심 전략\n")
        md.append(f"1. **핵심 지지선 분할 매수**: L Size 0.618 ({get_p_str(l_0618)}) ~ 0.382 ({get_p_str(l_0382)}) 구간에서 3~4회 분할 매수")
        md.append(f"2. **반감기 사이클 활용**: 비트코인 반감기 효과(공급 감소)가 6~18개월 후 본격화 → 사전 축적 전략 유효")
        md.append(f"3. **장기 목표가**: L Size 1.000 (역대 고점 {get_p_str(l_1000)}) 재도전 가능성")
        md.append(f"4. **리스크 관리**: L Size 0.236 ({get_p_str(l_levels.get('0.236 (최종 지지선)', 0))}) 하회 시 비중 조절")
    else:
        md.append(f"### 💡 장기 투자 핵심 전략\n")
        md.append(f"1. **핵심 지지선 분할 매수**: L Size 0.618 ({get_p_str(l_0618)}) ~ 0.382 ({get_p_str(l_0382)}) 구간 집중 매집")
        md.append(f"2. **실적 모멘텀 확인**: 분기 어닝 서프라이즈 및 가이던스 상향 시 추가 매수 가중")
        md.append(f"3. **장기 목표가**: L Size 1.000 (역대 고점 {get_p_str(l_1000)}) 재도전 + 신고점 가능성 검토")
        md.append(f"4. **리스크 관리**: L Size 0.500 ({get_p_str(l_0500)}) 하회 시 비중 축소 고려")

    md.append("\n---\n")

    # ─── 적절한 매수가 요약 표 ───────────────────────────────────────
    md.append("## 💰 적절한 매수가 요약 (피보나치 기반 진입 가이드)\n")

    # 현재가 대비 각 레벨의 이격도 계산 함수
    def diff_str(target):
        if target <= 0:
            return "—"
        d = ((target / current_price) - 1) * 100
        return f"{d:+.2f}%"

    # 단기 매수가 (XS/S 레벨 기반)
    st_buy_1 = xs_0618   # XS 0.618 → 단기 1차 매수
    st_buy_2 = xs_0382   # XS 0.382 → 단기 2차 매수
    st_target = xs_1000  # XS 고점 → 단기 목표가

    # 장기 매수가 (L 레벨 기반)
    lt_buy_1 = l_0618    # L 0.618 → 장기 1차 매수 ⭐
    lt_buy_2 = l_0500    # L 0.500 → 장기 2차 매수
    lt_buy_3 = l_0382    # L 0.382 → 장기 3차 매수 (저점 매집)
    lt_target = l_0764   # L 0.764 → 장기 1차 목표가

    md.append("### 📊 단기 매수가 (1~4주 스윙 트레이딩)\n")
    md.append(f"| 구분 | 매수가 | 현재가 대비 | 전략 |")
    md.append(f"| :--- | :--- | :--- | :--- |")
    md.append(f"| **🎯 1차 단기 매수가** | **{get_p_str(st_buy_1)}** | {diff_str(st_buy_1)} | XS 0.618 지지선, 소량 선매수 |")
    md.append(f"| **🎯 2차 단기 매수가** | **{get_p_str(st_buy_2)}** | {diff_str(st_buy_2)} | XS 0.382 추가 하락 시 추가 매수 |")
    md.append(f"| **📈 단기 목표가** | **{get_p_str(st_target)}** | {diff_str(st_target)} | XS 고점 돌파 시 1차 익절 |")
    md.append(f"| **⛔ 단기 손절가** | **{get_p_str(s_0618)}** | {diff_str(s_0618)} | S 0.618 하회 시 손절 |")
    md.append("")

    md.append("### 📊 장기 매수가 (3~12개월 포지션 빌딩)\n")
    md.append(f"| 구분 | 매수가 | 현재가 대비 | 추천 비중 | 전략 |")
    md.append(f"| :--- | :--- | :--- | :--- | :--- |")
    md.append(f"| **⭐ 1차 장기 매수가** | **{get_p_str(lt_buy_1)}** | {diff_str(lt_buy_1)} | **30%** | L 0.618 황금비율 핵심 매수 구간 |")
    md.append(f"| **⭐ 2차 장기 매수가** | **{get_p_str(lt_buy_2)}** | {diff_str(lt_buy_2)} | **40%** | L 0.500 심리적 마지노선, 주력 매수 |")
    md.append(f"| **⭐ 3차 장기 매수가** | **{get_p_str(lt_buy_3)}** | {diff_str(lt_buy_3)} | **30%** | L 0.382 패닉셀 활용 저점 매집 |")
    md.append(f"| **📈 장기 1차 목표가** | **{get_p_str(lt_target)}** | {diff_str(lt_target)} | — | L 0.764 저항선 돌파 시 50% 익절 |")
    md.append(f"| **📈 장기 2차 목표가** | **{get_p_str(l_1000)}** | {diff_str(l_1000)} | — | L 역대 고점 재도전 시 전량 익절 |")
    md.append("")

    # 현재 가격 대비 최적 매수가 추천
    md.append("### 🏆 현재 시점 최적 매수가 추천\n")

    l_0236 = l_levels.get('0.236 (최종 지지선)', 0)
    l_0146 = l_levels.get('0.146 (심층 지지선)', 0)

    if current_price > lt_buy_1 * 1.02:
        best_buy = lt_buy_1
        best_level = "L Size 0.618 (황금비율)"
        best_ratio = "30%"
        best_comment = "현재 가격이 1차 지지선보다 높습니다. 조정 시 0.618 부근에서 분할 매수 시작 권장"
    elif current_price > lt_buy_2 * 1.02:
        best_buy = lt_buy_2
        best_level = "L Size 0.500 (절반선)"
        best_ratio = "40%"
        best_comment = "현재 가격이 1차 지지선 아래에 안착 중입니다. 다음 강력 지지선인 0.500 부근 매수 대기"
    elif current_price > lt_buy_3 * 1.02:
        best_buy = lt_buy_3
        best_level = "L Size 0.382 (강한 지지)"
        best_ratio = "30%"
        best_comment = "현재 가격이 심리적 마지노선 부근입니다. 강력한 0.382 지지선 부근에서 매수 대응"
    elif current_price > l_0236 * 1.02:
        best_buy = l_0236
        best_level = "L Size 0.236 (최종 지지)"
        best_ratio = "25%"
        best_comment = "0.382 지지선을 이탈해 최종 0.236 지지선 부근에 위치하여 분할 진입 고려 가능"
    elif current_price > l_0146 * 1.02:
        best_buy = l_0146
        best_level = "L Size 0.146 (심층 지지)"
        best_ratio = "20%"
        best_comment = "심층 지지선(0.146) 영역 도달 - 과매도 낙폭과대 구간으로 분할 진입 기회"
    elif rsi <= 30:
        best_buy = st_buy_1
        best_level = "XS 0.618 (단기 지지)"
        best_ratio = "20~30%"
        best_comment = "RSI 과매도 상태로 단기 반등 타점 도달! 적극적인 단기 매수 대응 권장"
    else:
        best_buy = l_levels.get('0.000 (저점)', current_price)
        best_level = "L Size 0.000 (저점)"
        best_ratio = "15%"
        best_comment = "역사적 저점 영역 도달 - 최저점 분할매수 대응"

    md.append(f"> ## 🎯 **현재 최적 매수가: {get_p_str(best_buy)}** ({best_level})")
    md.append(f"> ### 💼 **권장 비중: {best_ratio}** | {best_comment}")

    md.append("\n---\n")

    return "\n".join(md)
