# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from analysis import (
    get_fib_levels, get_entry_signal, get_adjacent_l_levels,
    calculate_composite_score, style_axes_dark
)

def run_backtest(df, ticker, limit_years=5, nest_mode="time"):
    """
    과거 데이터에 대해 피보나치 기반 종합 점수를 산출하고, 
    매수 신호 발생 이후 +5, +10, +20, +30일 시점의 수익률을 시뮬레이션합니다.
    """
    if df is None or len(df) < 250:
        return {"success": False, "message": "데이터가 너무 적어 백테스트를 실행할 수 없습니다. (최소 250일 이상 필요)"}

    # 최근 N년 데이터로 제한 (성능 및 최신성 고려)
    df_full = df.copy()
    
    # 1) 전체 데이터 기준 보조지표 사전 계산 (루프 성능 최적화)
    # RSI 14
    delta = df_full['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df_full['RSI_14'] = 100 - (100 / (1 + rs))

    # SMA
    df_full['SMA_5'] = df_full['Close'].rolling(window=5).mean()
    df_full['SMA_20'] = df_full['Close'].rolling(window=20).mean()

    # MACD
    ema12 = df_full['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df_full['Close'].ewm(span=26, adjust=False).mean()
    df_full['MACD'] = ema12 - ema26
    df_full['MACD_Signal'] = df_full['MACD'].ewm(span=9, adjust=False).mean()
    df_full['MACD_Hist'] = df_full['MACD'] - df_full['MACD_Signal']

    # BB
    df_full['BB_Mid'] = df_full['Close'].rolling(20).mean()
    df_full['BB_Std'] = df_full['Close'].rolling(20).std()
    df_full['BB_Upper'] = df_full['BB_Mid'] + 2 * df_full['BB_Std']
    df_full['BB_Lower'] = df_full['BB_Mid'] - 2 * df_full['BB_Std']

    # Volume Ratio
    vol_ma20 = df_full['Volume'].rolling(20).mean()
    df_full['Vol_Ratio'] = df_full['Volume'] / vol_ma20

    # 결측치 제거
    df_full = df_full.dropna(subset=['RSI_14', 'SMA_20', 'MACD_Hist', 'BB_Lower', 'Vol_Ratio'])

    # 백테스트 시작 시점 결정 (최근 limit_years 년 혹은 사용가능한 시작점)
    total_len = len(df_full)
    start_idx = max(250, total_len - int(limit_years * 252))
    
    signals = []
    
    for i in range(start_idx, total_len):
        # 당일 시점까지의 데이터 (미래 데이터 참조 방지)
        df_sub = df_full.iloc[:i+1]
        
        current_price = float(df_sub['Close'].iloc[-1])
        current_rsi = float(df_sub['RSI_14'].iloc[-1])
        current_macd_hist = float(df_sub['MACD_Hist'].iloc[-1])
        current_bb_lower = float(df_sub['BB_Lower'].iloc[-1])
        current_bb_upper = float(df_sub['BB_Upper'].iloc[-1])
        vol_ratio = float(df_sub['Vol_Ratio'].iloc[-1])
        
        bb_band_width = current_bb_upper - current_bb_lower
        bb_pct = (current_price - current_bb_lower) / bb_band_width if bb_band_width > 0 else 0.5

        # L Size (All-Time) - 단, 해당 시점까지의 High/Low 기준
        l_high = float(df_sub['High'].max())
        l_low = float(df_sub['Low'].min())
        l_levels = get_fib_levels(l_high, l_low)
        l_signal = get_entry_signal(current_price, l_levels, current_rsi)

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
            # M Size (당일 시점 기준 최근 180일 프랙탈 변곡점)
            df_sub_m = df_sub.tail(180)
            m_low_idx = df_sub_m['Low'].idxmin()
            m_low = float(df_sub_m['Low'].min())
            m_high = float(df_sub_m.loc[m_low_idx:]['High'].max())
            m_levels = get_fib_levels(m_high, m_low)
            m_signal = get_entry_signal(current_price, m_levels, current_rsi)

            # S Size (당일 시점 기준 최근 30일 프랙탈 변곡점)
            df_sub_s = df_sub.tail(30)
            s_low_idx = df_sub_s['Low'].idxmin()
            s_low = float(df_sub_s['Low'].min())
            s_high = float(df_sub_s.loc[s_low_idx:]['High'].max())
            s_levels = get_fib_levels(s_high, s_low)
            s_signal = get_entry_signal(current_price, s_levels, current_rsi)

            # XS Size (당일 시점 기준 최근 7일 프랙탈 변곡점)
            df_sub_xs = df_sub.tail(7)
            xs_low_idx = df_sub_xs['Low'].idxmin()
            xs_low = float(df_sub_xs['Low'].min())
            xs_high = float(df_sub_xs.loc[xs_low_idx:]['High'].max())
            xs_levels = get_fib_levels(xs_high, xs_low)
            xs_signal = get_entry_signal(current_price, xs_levels, current_rsi)

        # 종합 기술 점수 산출
        signals_list = [l_signal, m_signal, s_signal, xs_signal]
        score = calculate_composite_score(signals_list, current_rsi, current_macd_hist, bb_pct, vol_ratio)
        
        # 매수 시그널 판단 기준: 종합 점수 65점 이상 (매수 우위 또는 강한 매수)
        if score >= 65:
            # 미래 수익률 추적 (i+5, i+10, i+20, i+30 일이 전체 데이터 범위 내에 있는지 확인)
            sig_date = df_full.index[i]
            perf = {"date": sig_date, "price": current_price, "score": score}
            
            for hold_days in [5, 10, 20, 30]:
                future_idx = i + hold_days
                if future_idx < total_len:
                    future_price = float(df_full['Close'].iloc[future_idx])
                    return_pct = ((future_price / current_price) - 1) * 100
                    perf[f"ret_{hold_days}d"] = return_pct
                else:
                    perf[f"ret_{hold_days}d"] = None
            
            signals.append(perf)

    if not signals:
        return {
            "success": False, 
            "message": "지난 5년간 발생한 피보나치 매수 신호(종합점수 65점 이상)가 없습니다.\n수치가 너무 높거나 침체기 자산일 수 있습니다."
        }

    df_signals = pd.DataFrame(signals)
    
    # 성과 분석 계산
    metrics = {}
    for hold_days in [5, 10, 20, 30]:
        col = f"ret_{hold_days}d"
        valid_rets = df_signals[col].dropna()
        if len(valid_rets) > 0:
            win_rate = (valid_rets > 0).mean() * 100
            avg_ret = valid_rets.mean()
            max_ret = valid_rets.max()
            min_ret = valid_rets.min()
        else:
            win_rate, avg_ret, max_ret, min_ret = 0.0, 0.0, 0.0, 0.0
            
        metrics[hold_days] = {
            "count": len(valid_rets),
            "win_rate": win_rate,
            "avg_ret": avg_ret,
            "max_ret": max_ret,
            "min_ret": min_ret
        }

    return {
        "success": True,
        "ticker": ticker,
        "total_signals": len(df_signals),
        "metrics": metrics,
        "raw_signals": df_signals
    }

def generate_backtest_chart(backtest_res):
    """백테스트 결과를 바탕으로 matplotlib 차트를 다크모드로 생성합니다."""
    metrics = backtest_res["metrics"]
    df_signals = backtest_res["raw_signals"]
    ticker = backtest_res["ticker"]

    # 1) 피겨 생성
    fig = plt.figure(figsize=(9, 5), facecolor='#1E1E1E')
    
    # 차트 1: 기간별 승률 및 평균 수익률 (왼쪽)
    ax1 = fig.add_subplot(121)
    days = [5, 10, 20, 30]
    win_rates = [metrics[d]["win_rate"] for d in days]
    avg_rets = [metrics[d]["avg_ret"] for d in days]

    x = np.arange(len(days))
    width = 0.35

    # 승률 바 (좌측 Y축)
    rects1 = ax1.bar(x - width/2, win_rates, width, label='승률 (%)', color='#00E676', alpha=0.8)
    ax1.set_ylabel('승률 (%)', color='#00E676')
    ax1.tick_params(axis='y', labelcolor='#00E676')
    ax1.set_ylim(0, 100)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f'+{d}일' for d in days])

    # 평균 수익률 바 (우측 Y축)
    ax1_twin = ax1.twinx()
    rects2 = ax1_twin.bar(x + width/2, avg_rets, width, label='평균수익률 (%)', color='#2979FF', alpha=0.8)
    ax1_twin.set_ylabel('평균 수익률 (%)', color='#2979FF')
    ax1_twin.tick_params(axis='y', labelcolor='#2979FF')
    
    # 0선 표시
    ax1_twin.axhline(y=0, color='#555555', linestyle='-', linewidth=0.8)

    # 범례 합치기
    lines = [rects1, rects2]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', fontsize=7, facecolor='#121212', edgecolor='#333333', labelcolor='#FFFFFF')
    
    ax1.set_title("보유 기간별 승률 및 평균 수익률", fontsize=9, color='#FFFFFF')
    style_axes_dark(ax1)
    # twinx 에도 다크 스타일 적용 (그리드 숨김)
    ax1_twin.spines['bottom'].set_color('#333333')
    ax1_twin.spines['top'].set_color('#333333')
    ax1_twin.spines['left'].set_color('#333333')
    ax1_twin.spines['right'].set_color('#333333')
    ax1_twin.tick_params(colors='#E0E0E0', labelsize=8)

    # 차트 2: 20일 보유 시의 수익률 분포 히스토그램 (오른쪽)
    ax2 = fig.add_subplot(122)
    ret_20d = df_signals['ret_20d'].dropna()
    
    if len(ret_20d) > 0:
        # 히스토그램
        n, bins, patches = ax2.hist(ret_20d, bins=15, color='#AB47BC', alpha=0.7, edgecolor='#2D2D2D')
        ax2.axvline(x=0, color='#EF5350', linestyle='--', linewidth=1, label='손익 분기선')
        ax2.axvline(x=ret_20d.mean(), color='#2979FF', linestyle='-', linewidth=1.2, label=f'평균: {ret_20d.mean():.1f}%')
        ax2.set_xlabel('수익률 (%)')
        ax2.set_ylabel('신호 빈도 (건수)')
        ax2.legend(loc='upper right', fontsize=7, facecolor='#121212', edgecolor='#333333', labelcolor='#FFFFFF')
    else:
        ax2.text(0.5, 0.5, "데이터 없음", color=TEXT_MUTED, ha='center', va='center')
        
    ax2.set_title("+20일 시점의 수익률 분포 히스토그램", fontsize=9, color='#FFFFFF')
    style_axes_dark(ax2)

    fig.suptitle(f"📈 {ticker} 피보나치 매수 신호 성과 백테스트 (최근 5개년)", fontsize=11, color='#FFFFFF', fontweight='bold', y=0.98)
    fig.tight_layout()
    
    return fig
