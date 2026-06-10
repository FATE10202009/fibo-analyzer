# -*- coding: utf-8 -*-
"""
damus.py — 피보나치 알고리즘 전용 모듈
핵심 개념: SOP(감자), R2/R7(실시간 파동), T2/T7(당일), Y2/Y7(전일), 숙제(미해결 리테스트)
"""
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from analysis import fmt_chart_val, fmt_price


# ─────────────────────────────────────────────────────────────────
# 내부 헬퍼: 지역 고점(피벗 하이) / 지역 저점(피벗 로우) 탐지
# ─────────────────────────────────────────────────────────────────
def _find_local_pivots(df_1h, window=3):
    """
    최근 1시간봉 배열에서 양쪽 window개 봉보다 높은/낮은 지점을
    직전 지역 고점(R7) 및 직전 지역 저점(R2)으로 반환합니다.
    """
    highs = df_1h['High'].values
    lows  = df_1h['Low'].values
    n = len(highs)

    r7 = r2 = None

    # 뒤에서부터 스캔 (최근 피벗 우선)
    for i in range(n - window - 1, window - 1, -1):
        # 지역 고점
        if r7 is None:
            left_ok  = all(highs[i] >= highs[i - j] for j in range(1, window + 1) if i - j >= 0)
            right_ok = all(highs[i] >= highs[i + j] for j in range(1, window + 1) if i + j < n)
            if left_ok and right_ok:
                r7 = float(highs[i])

        # 지역 저점
        if r2 is None:
            left_ok  = all(lows[i] <= lows[i - j] for j in range(1, window + 1) if i - j >= 0)
            right_ok = all(lows[i] <= lows[i + j] for j in range(1, window + 1) if i + j < n)
            if left_ok and right_ok:
                r2 = float(lows[i])

        if r7 is not None and r2 is not None:
            break

    # 피벗 미발견 시 폴백: 단순 최고/최저
    if r7 is None:
        r7 = float(df_1h['High'].max())
    if r2 is None:
        r2 = float(df_1h['Low'].min())

    return r7, r2


# ─────────────────────────────────────────────────────────────────
# 메인: 피보나치 데이터 산출
# ─────────────────────────────────────────────────────────────────
def get_damus_data(ticker, is_usd, interval='1h'):
    """
    피보나치 알고리즘에 필요한 데이터를 산출하여 딕셔너리로 반환합니다.
    - SOP   : 당일 최초 1시간봉 시가 (하루 내내 고정)
    - R7/R2 : 최근 24시간봉 중 직전 지역 고점/저점 (피벗)
    - T7/T2 : 당일 장 전체의 고가/저가
    - Y7/Y2 : 전일 장 전체의 고가/저가
    - homework      : 오늘 발생했으나 미터치 숙제 (Y8/Y1)
    - carried_homework : 전일에서 이월된 숙제
    """
    try:
        # ── 데이터 수집 ───────────────────────────────────────────
        period_h = '7d'
        if interval == '1d':
            period_h = '60d'
        elif interval == '1h':
            period_h = '7d'
        elif interval in ('15m', '5m'):
            period_h = '7d'

        df_1h = yf.download(ticker, period=period_h, interval=interval, progress=False)
        if df_1h.empty:
            return None
        if df_1h.columns.nlevels > 1:
            df_1h.columns = df_1h.columns.droplevel(1)

        df_1d = yf.download(ticker, period='5d', interval='1d', progress=False)
        if df_1d.columns.nlevels > 1:
            df_1d.columns = df_1d.columns.droplevel(1)

        if len(df_1d) < 2 or len(df_1h) < 4:
            return None

        # timezone 통일
        def _align_tz(df_1h_idx, ref_ts):
            if hasattr(ref_ts, 'tzinfo') and ref_ts.tzinfo is not None:
                tz = ref_ts.tzinfo
                if df_1h_idx.tz is None:
                    return df_1h_idx.tz_localize('UTC').tz_convert(tz)
                else:
                    return df_1h_idx.tz_convert(tz)
            else:
                if df_1h_idx.tz is not None:
                    return df_1h_idx.tz_localize(None)
                return df_1h_idx

        today_session_start = df_1d.index[-1]       # 당일 세션 시작
        prev_session_start  = df_1d.index[-2]       # 전일 세션 시작
        next_session_start = today_session_start + pd.Timedelta(days=2)

        aligned_idx = _align_tz(df_1h.index, today_session_start)

        today_mask  = (aligned_idx >= today_session_start) & (aligned_idx < next_session_start)
        prev_mask   = (aligned_idx >= prev_session_start) & (aligned_idx < today_session_start)

        df_today_1h = df_1h[today_mask]
        df_prev_1h  = df_1h[prev_mask]

        # SOP (감자): 매시간마다 시가 기준선 생성. 미체크(가격 미돌파/미터치)된 건만 유지되며 여러 개가 존재할 수 있음.
        active_sops = []
        df_source = df_today_1h if len(df_today_1h) > 0 else df_1h.tail(24)
        
        import numpy as np
        for idx_src, row_src in df_source.iterrows():
            sop_val = float(row_src['Open'])
            indices = np.where(df_1h.index == idx_src)[0]
            if len(indices) > 0:
                pos = int(indices[0])
                checked = False
                # 해당 시점 이후(pos+1부터 끝까지)의 봉들 중에서 이 시가(sop_val)를 터치/돌파했는지 판단
                for j in range(pos + 1, len(df_1h)):
                    low_j = float(df_1h['Low'].iloc[j])
                    high_j = float(df_1h['High'].iloc[j])
                    if low_j <= sop_val <= high_j:
                        checked = True
                        break
                if not checked:
                    active_sops.append((idx_src, sop_val))
                    
        # 호환성 유지를 위한 단일 sop 값 (가장 최신 미체크 SOP 또는 폴백)
        if active_sops:
            sop = active_sops[-1][1]
        elif len(df_today_1h) > 0:
            sop = float(df_today_1h.iloc[0]['Open'])
        else:
            sop = float(df_1h.iloc[-1]['Open'])

        current_price = float(df_1h.iloc[-1]['Close'])

        # R7/R2
        r7, r2 = _find_local_pivots(df_1h.tail(24), window=3)

        # T7/T2 (당일)
        if len(df_today_1h) > 0:
            t7 = float(df_today_1h['High'].max())
            t2 = float(df_today_1h['Low'].min())
        else:
            t7 = float(df_1d.iloc[-1]['High'])
            t2 = float(df_1d.iloc[-1]['Low'])

        # Y7/Y2 (전일)
        if len(df_prev_1h) > 0:
            y7 = float(df_prev_1h['High'].max())
            y2 = float(df_prev_1h['Low'].min())
        else:
            y7 = float(df_1d.iloc[-2]['High'])
            y2 = float(df_1d.iloc[-2]['Low'])

        # 숙제 계산 (Y8/Y1)
        homework = []
        retest_info = []

        if t7 > y7 and len(df_today_1h) > 1:
            breakout_confirmed = False
            retested = False
            for _, row in df_today_1h.iterrows():
                if float(row['High']) >= y7:
                    breakout_confirmed = True
                if breakout_confirmed and float(row['Low']) <= y7:
                    retested = True
                    break

            retest_info.append({
                'name': 'Y8',
                'price': y7,
                'direction': 'up',
                'retested': retested,
                'breakout_high': t7
            })
            if not retested:
                homework.append(("Y8 — 전일고점 돌파 후 리테스트 미완", y7, "up"))

        if t2 < y2 and len(df_today_1h) > 1:
            breakout_confirmed = False
            retested = False
            for _, row in df_today_1h.iterrows():
                if float(row['Low']) <= y2:
                    breakout_confirmed = True
                if breakout_confirmed and float(row['High']) >= y2:
                    retested = True
                    break

            retest_info.append({
                'name': 'Y1',
                'price': y2,
                'direction': 'down',
                'retested': retested,
                'breakout_low': t2
            })
            if not retested:
                homework.append(("Y1 — 전일저점 이탈 후 리테스트 미완", y2, "down"))

        # 이월 숙제
        carried_homework = []
        if len(df_1d) >= 3:
            dby_high = float(df_1d.iloc[-3]['High'])
            dby_low  = float(df_1d.iloc[-3]['Low'])

            if len(df_prev_1h) > 1:
                prev_t7 = float(df_prev_1h['High'].max())
                prev_t2 = float(df_prev_1h['Low'].min())

                if prev_t7 > dby_high:
                    bc, rt = False, False
                    for _, row in df_prev_1h.iterrows():
                        if float(row['High']) >= dby_high:
                            bc = True
                        if bc and float(row['Low']) <= dby_high:
                            rt = True
                            break
                    if not rt:
                        carried_homework.append(("이월숙제 Y8 — 전전일 고점 미해결", dby_high, "up"))

                if prev_t2 < dby_low:
                    bc, rt = False, False
                    for _, row in df_prev_1h.iterrows():
                        if float(row['Low']) <= dby_low:
                            bc = True
                        if bc and float(row['High']) >= dby_low:
                            rt = True
                            break
                    if not rt:
                        carried_homework.append(("이월숙제 Y1 — 전전일 저점 미해결", dby_low, "down"))
            else:
                prev_high = float(df_1d.iloc[-2]['High'])
                prev_low  = float(df_1d.iloc[-2]['Low'])
                if prev_high > dby_high and prev_low > dby_high:
                    carried_homework.append(("이월숙제 Y8 — 전전일 고점 미해결", dby_high, "up"))
                if prev_low < dby_low and prev_high < dby_low:
                    carried_homework.append(("이월숙제 Y1 — 전전일 저점 미해결", dby_low, "down"))

        return {
            'df_1h':           df_1h,
            'df_today_1h':     df_today_1h,
            'df_prev_1h':      df_prev_1h,
            'sop':             sop,
            'active_sops':     active_sops,
            'r7':              r7,
            'r2':              r2,
            't7':              t7,
            't2':              t2,
            'y7':              y7,
            'y2':              y2,
            'homework':        homework,
            'carried_homework': carried_homework,
            'retest_info':     retest_info,
            'current_price':   current_price,
            'is_usd':          is_usd,
            'interval':        interval
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[FiboAnalyzer] 데이터 산출 오류: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# 차트 생성
# ─────────────────────────────────────────────────────────────────
def generate_damus_chart(data):
    """
    피보나치 데이터 기반 간격별 차트를 Plotly 인터랙티브 차트로 생성.
    """
    if not data:
        fig = go.Figure()
        fig.add_annotation(
            text="피보나치 데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#EF5350")
        )
        fig.update_layout(
            template="plotly_dark",
            plot_bgcolor='#13131A',
            paper_bgcolor='#0F0F12'
        )
        return fig

    df_today_1h    = data['df_today_1h']
    df_1h          = data['df_1h']
    sop            = data['sop']
    t7, t2         = data['t7'], data['t2']
    y7, y2         = data['y7'], data['y2']
    r7, r2         = data['r7'], data['r2']
    homework       = data['homework']
    carried_hw     = data['carried_homework']
    cp             = data['current_price']
    is_usd         = data['is_usd']
    interval       = data.get('interval', '1h')

    df_plot = df_today_1h if (len(df_today_1h) >= 2 and interval != '1d') else df_1h.tail(24)
    if len(df_plot) == 0:
        df_plot = df_1h.tail(24)

    start_time = df_plot.index[0]
    session_end = start_time + pd.Timedelta(days=1) if interval != '1d' else df_plot.index[-1] + pd.Timedelta(days=1)

    if interval == '1d':
        last_candle_time = df_plot.index[-1] + pd.Timedelta(days=2)
    else:
        last_candle_time = df_plot.index[-1] + pd.Timedelta(hours=2)
    end_time = min(last_candle_time, session_end)

    fig = go.Figure()

    # 1. 주 가격 선 추가
    intv_label = {
        '1d': '1D',
        '1h': '1H',
        '15m': '15M',
        '5m': '5M'
    }.get(interval, interval.upper())

    fig.add_trace(
        go.Scatter(
            x=df_plot.index,
            y=df_plot['Close'],
            mode='lines+markers',
            line=dict(color='#E2E8F0', width=1.5),
            marker=dict(size=4, color='#60A5FA'),
            name=f"가격 ({intv_label})"
        )
    )

    # 2. SOP (감자) 수평선 추가
    active_sops = data.get('active_sops', [])
    if active_sops:
        for idx, (t, s_val) in enumerate(active_sops):
            lbl = f"SOP ({t.strftime('%H:%M')})"
            fig.add_hline(
                y=s_val,
                line_dash="dash",
                line_color="#00E676",
                line_width=1.2,
                opacity=0.8,
                annotation_text=f" {lbl} ({fmt_chart_val(s_val, is_usd)})",
                annotation_position="left",
                annotation_font_color="#00E676",
                annotation_font_size=9
            )
    else:
        fig.add_hline(
            y=sop,
            line_dash="dash",
            line_color="#00E676",
            line_width=1.2,
            opacity=0.5,
            annotation_text=f" SOP (기본) ({fmt_chart_val(sop, is_usd)})",
            annotation_position="left",
            annotation_font_color="#00E676",
            annotation_font_size=9
        )

    # 3. Y7/Y2 (전일 고/저)
    fig.add_hline(
        y=y7,
        line_dash="dot",
        line_color="#FFA726",
        line_width=1.0,
        opacity=0.8,
        annotation_text=f" Y7 전일고 ({fmt_chart_val(y7, is_usd)})",
        annotation_position="right",
        annotation_font_color="#FFA726",
        annotation_font_size=8
    )
    fig.add_hline(
        y=y2,
        line_dash="dot",
        line_color="#2979FF",
        line_width=1.0,
        opacity=0.8,
        annotation_text=f" Y2 전일저 ({fmt_chart_val(y2, is_usd)})",
        annotation_position="right",
        annotation_font_color="#2979FF",
        annotation_font_size=8
    )

    # 4. R7/R2 (지역 피벗 고/저)
    fig.add_hline(
        y=r7,
        line_dash="dashdot",
        line_color="#CE93D8",
        line_width=0.9,
        opacity=0.75,
        annotation_text=f" R7 실시간고점 ({fmt_chart_val(r7, is_usd)})",
        annotation_position="right",
        annotation_font_color="#CE93D8",
        annotation_font_size=8
    )
    fig.add_hline(
        y=r2,
        line_dash="dashdot",
        line_color="#80DEEA",
        line_width=0.9,
        opacity=0.75,
        annotation_text=f" R2 실시간저점 ({fmt_chart_val(r2, is_usd)})",
        annotation_position="right",
        annotation_font_color="#80DEEA",
        annotation_font_size=8
    )

    # 5. 피보나치 (오늘 6번/3번 지지선)
    if t7 is not None and t2 is not None and t7 > t2:
        t_diff = t7 - t2
        fib_618 = t2 + t_diff * 0.618
        fib_382 = t2 + t_diff * 0.382
        
        fig.add_hline(
            y=fib_618,
            line_color="#FFD700",
            line_width=1.2,
            opacity=0.85,
            annotation_text=f" 6번 (오늘 61.8%) ({fmt_chart_val(fib_618, is_usd)})",
            annotation_position="left",
            annotation_font_color="#FFD700",
            annotation_font_size=9
        )
        fig.add_hline(
            y=fib_382,
            line_color="#BA55D3",
            line_width=1.2,
            opacity=0.85,
            annotation_text=f" 3번 (오늘 38.2%) ({fmt_chart_val(fib_382, is_usd)})",
            annotation_position="left",
            annotation_font_color="#BA55D3",
            annotation_font_size=9
        )

    # 6. 레드존/블루존 (어제 y1~y2, y7~y8) 채우기
    if y7 is not None and y2 is not None and y7 > y2:
        y_diff = y7 - y2
        red_low = y2 + y_diff * 0.146
        red_high = y2 + y_diff * 0.236
        blue_low = y2 + y_diff * 0.764
        blue_high = y2 + y_diff * 0.854
        
        fig.add_hrect(
            y0=red_low, y1=red_high,
            fillcolor="#FF5252", opacity=0.15,
            line_width=0,
            annotation_text="🟥 레드존 최후지지 (어제 y1-y2)",
            annotation_position="bottom left",
            annotation_font_color="#FF5252",
            annotation_font_size=8
        )
        fig.add_hrect(
            y0=blue_low, y1=blue_high,
            fillcolor="#2979FF", opacity=0.15,
            line_width=0,
            annotation_text="🟦 블루존 핵심저항 (어제 y7-y8)",
            annotation_position="top left",
            annotation_font_color="#2979FF",
            annotation_font_size=8
        )

    # 7. 오늘 숙제 라인
    for hw_name, hw_price, hw_dir in homework:
        color = '#EF5350' if hw_dir == 'up' else '#2979FF'
        fig.add_hline(
            y=hw_price,
            line_color=color,
            line_width=1.8,
            opacity=0.95,
            annotation_text=f" 🔔 숙제: {hw_name.split(' ')[0]} ({fmt_chart_val(hw_price, is_usd)})",
            annotation_position="left",
            annotation_font_color=color,
            annotation_font_size=9
        )

    # 8. 이월 숙제 라인
    for hw_name, hw_price, hw_dir in carried_hw:
        color = '#FF8A65' if hw_dir == 'up' else '#80CBC4'
        fig.add_hline(
            y=hw_price,
            line_dash="dash",
            line_color=color,
            line_width=1.3,
            opacity=0.8,
            annotation_text=f" 📌 {hw_name.split(' ')[0]} ({fmt_chart_val(hw_price, is_usd)})",
            annotation_position="left",
            annotation_font_color=color,
            annotation_font_size=8
        )

    # 9. 현재가 라인
    fig.add_hline(
        y=cp,
        line_color="#FFEE58",
        line_width=0.8,
        opacity=0.7,
        annotation_text=f" ▶ 현재 ({fmt_chart_val(cp, is_usd)})",
        annotation_position="right",
        annotation_font_color="#FFEE58",
        annotation_font_size=8
    )

    title_label = {
        '1d': '일봉',
        '1h': '1시간봉',
        '15m': '15분봉',
        '5m': '5분봉'
    }.get(interval, '1시간봉')

    fig.update_layout(
        title=dict(
            text=f"📊 피보나치 알고리즘 — 당일 시황 (SOP · R2/R7 · 숙제) [{title_label}]",
            font=dict(size=13, color='#FFFFFF')
        ),
        template="plotly_dark",
        plot_bgcolor='#13131A',
        paper_bgcolor='#0F0F12',
        margin=dict(l=20, r=40, t=40, b=20),
        hovermode="x unified",
        xaxis=dict(
            gridcolor='#22222A',
            range=[start_time, end_time]
        ),
        yaxis=dict(
            gridcolor='#22222A',
            title_text="가격"
        )
    )


# ─────────────────────────────────────────────────────────────────
# 리포트 생성
# ─────────────────────────────────────────────────────────────────
def generate_damus_report_md(data, rate):
    """
    피보나치 데이터를 기반으로 시황 요약 + 파동 목표값 + 숙제 현황 리포트 생성
    """
    if not data:
        return "\n## 💎 피보나치 알고리즘 분석\n* 데이터 로드 실패\n"

    sop  = data['sop']
    cp   = data['current_price']
    r7   = data['r7']
    r2   = data['r2']
    t7   = data['t7']
    t2   = data['t2']
    y7   = data['y7']
    y2   = data['y2']
    hw   = data['homework']
    chw  = data['carried_homework']
    is_usd = data['is_usd']

    def p(v):
        return fmt_price(v, rate, is_usd)

    active_sops = data.get('active_sops', [])
    diff_sop = ((cp / sop) - 1) * 100
    sop_status = "**🟢 SOP 상회 (강세)**" if cp > sop else "**🔴 SOP 하회 (약세)**"

    md = []
    md.append("\n---\n")
    md.append("## 💎 피보나치 알고리즘 단기 파동 분석 (SOP & 리테스트 숙제)\n")
    md.append("> 피보나치 시스템: 차트는 ① SOP(감자) ② R/T/Y 2번·7번 자리 ③ 리테스트 자리를 순환하며 터치하려는 성질을 가집니다.\n")

    # ── 오늘 시황 요약 ────────────────────────────────────────────
    md.append("### 🗞️ 현재 시점 시황 요약\n")

    # SOP 상태
    md.append(f"| 항목 | 값 | 판단 |")
    md.append(f"| :--- | :--- | :--- |")
    md.append(f"| **현재 가격** | {p(cp)} | — |")
    if active_sops:
        for t, s_val in active_sops:
            diff_s = ((cp / s_val) - 1) * 100
            s_status = "**🟢 SOP 상회 (강세)**" if cp > s_val else "**🔴 SOP 하회 (약세)**"
            time_str = t.strftime('%m-%d %H:%M')
            md.append(f"| **SOP ({time_str})** | {p(s_val)} | 현재가 대비 {s_status} ({diff_s:+.2f}%) |")
    else:
        md.append(f"| **SOP (감자, 기본)** | {p(sop)} | 현재가 대비 {sop_status} ({diff_sop:+.2f}%) |")

    # 당일 고/저 vs 전일 비교
    if t7 > y7:
        t7_status = f"🔴 전일 고가 **{p(y7)}** 상향 돌파 → Y8 발생"
    else:
        t7_status = f"전일 고가 미돌파 (Y7={p(y7)} 유지)"

    if t2 < y2:
        t2_status = f"🔵 전일 저가 **{p(y2)}** 하향 이탈 → Y1 발생"
    else:
        t2_status = f"전일 저가 미이탈 (Y2={p(y2)} 유지)"

    md.append(f"| **당일 고가 (T7)** | {p(t7)} | {t7_status} |")
    md.append(f"| **당일 저가 (T2)** | {p(t2)} | {t2_status} |")
    md.append("")

    # ── SOP 기준 상세 ─────────────────────────────────────────────
    md.append("### 1) 핵심 기준선 — SOP (감자)\n")
    if active_sops:
        md.append(f"* 현재 **{len(active_sops)}개**의 미체크 SOP가 활성화되어 있습니다 (매 정각 시가 형성 후 미돌파 상태):\n")
        for t, s_val in active_sops:
            diff_s = ((cp / s_val) - 1) * 100
            s_status = "상회 (강세)" if cp > s_val else "하회 (약세)"
            time_str = t.strftime('%m-%d %H:%M')
            md.append(f"  - **SOP ({time_str})**: **{p(s_val)}** — 현재가 대비 {s_status} ({diff_s:+.2f}%)")
        md.append("  - *SOP 상회 → 매수 우위, SOP 하회 → 매도 우위로 판단합니다. 가격이 이 레벨을 터치(돌파)하면 해당 SOP는 목록에서 즉시 제거됩니다.*\n")
    else:
        md.append(f"* **SOP (기본)**: **{p(sop)}** — 현재 활성 미체크 SOP가 없어 최근 시가를 기준으로 표시합니다. 현재가 대비 {sop_status} ({diff_sop:+.2f}%)")

    # ── 파동 목표값 ───────────────────────────────────────────────
    md.append("### 2) 파동별 목표값 (R → T → Y)\n")
    md.append("| 파동 | 의미 | 7번 자리 (고점 목표) | 2번 자리 (저점 목표) |")
    md.append("| :--- | :--- | :--- | :--- |")
    md.append(f"| **R (실시간)** | 최근 24봉 지역 피벗 | {p(r7)} | {p(r2)} |")
    md.append(f"| **T (당일)** | 오늘 장 전체 고/저 | {p(t7)} | {p(t2)} |")
    md.append(f"| **Y (전일)** | 어제 장 전체 고/저 | {p(y7)} | {p(y2)} |")
    md.append("")

    # ── 숙제 현황 ─────────────────────────────────────────────────
    md.append("### 3) 리테스트 숙제 현황\n")
    all_hw = hw + chw

    if not all_hw:
        md.append("* ✅ **현재 미해결 숙제 없음** — 돌파 후 리테스트가 모두 완료되었거나 전일 고/저 돌파가 없었습니다.")
        md.append("  - 이 경우 SOP 기준 횡보 트레이딩이 유효하며, 새 고점/저점 갱신 시 새로운 숙제가 발생합니다.\n")
    else:
        for hw_name, hw_price, hw_dir in all_hw:
            diff_hw = ((hw_price / cp) - 1) * 100
            icon = "🔴" if hw_dir == "up" else "🔵"
            carried = "이월" in hw_name
            badge = "📌 이월숙제" if carried else "🔔 오늘숙제"
            md.append(f"* {icon} **{badge}: {hw_name}**")
            md.append(f"  - 목표 리테스트 가격: **{p(hw_price)}** (현재가 대비 **{diff_hw:+.2f}%**)")
            if hw_dir == "up":
                md.append(f"  - 의미: 해당 가격({p(hw_price)})을 돌파 후 아직 되돌아 확인하지 않음 → 차트가 하락하며 이 레벨을 터치하러 올 가능성이 높습니다.")
            else:
                md.append(f"  - 의미: 해당 가격({p(hw_price)})을 하향 이탈 후 아직 되돌아 확인하지 않음 → 차트가 반등하며 이 레벨을 터치하러 올 가능성이 높습니다.")
            md.append("")

    # ── 4) 예측 방향 및 상태 분석 ─────────────────────────────────────
    md.append("### 4) 피보나치 핵심 이론 기반 예측 방향 및 시장 상태 분석\n")
    t_has_data = (t7 is not None and t2 is not None and t7 > t2)
    y_has_data = (y7 is not None and y2 is not None and y7 > y2)
    
    if t_has_data and y_has_data:
        t_diff = t7 - t2
        fib_618 = t2 + t_diff * 0.618  # 오늘 기준 6번 자리
        fib_382 = t2 + t_diff * 0.382  # 오늘 기준 3번 자리
        
        y_diff = y7 - y2
        red_low = y2 + y_diff * 0.146   # y1
        red_high = y2 + y_diff * 0.236  # y2
        blue_low = y2 + y_diff * 0.764  # y7
        blue_high = y2 + y_diff * 0.854 # y8
        
        state_desc = []
        direction_opinion = []
        
        # 레드존 판단 (어제 y1~y2 기준)
        if cp <= red_high and cp >= red_low:
            state_desc.append(f"⚠️ **레드존 최후 지지 시험 중 (어제 y1~y2)**: 상승 추세 생사의 분수령 가격인 어제자 레드존 구간 **{p(red_low)} ~ {p(red_high)}** 범위에 머물러 있습니다.")
            direction_opinion.append(f"- **레드존 지지 성공 시**: 강한 상승 반등이 예측되며, 오늘 기준 3번({p(fib_382)}) 및 6번({p(fib_618)}) 자리를 향한 상승 파동이 전개될 수 있습니다.\n- **레드존 하단({p(red_low)}) 붕괴 시**: 상승 추세 임계선이 무너지면서 큰 폭의 패닉셀(하락 전환)이 예측됩니다.")
        elif cp < red_low:
            state_desc.append(f"🚨 **레드존 붕괴 (상승 추세 이탈)**: 최후 지지 마지노선인 어제자 y1({p(red_low)}) 레벨을 하향 돌파하여 상승 추세가 깨진 국면입니다.")
            direction_opinion.append(f"- **하방 추가 조정 우세**: 알고리즘상 당분간 추가 하락 압력이 지속될 가능성이 매우 크며 보수적인 관점이 요구됩니다.")
        # 블루존 판단 (어제 y7~y8 기준)
        elif cp >= blue_low and cp <= blue_high:
            state_desc.append(f"🚫 **블루존 핵심 저항 진입 (어제 y7~y8)**: 하락 파동의 최후 저항대인 어제자 블루존 구간 **{p(blue_low)} ~ {p(blue_high)}**에 직면해 있습니다.")
            direction_opinion.append(f"- **블루존 저항 작용**: 해당 저항 구간 돌파에 실패할 경우 다시 아래로 꺾이며 재차 하락 파동이 재개될 확률이 높습니다.\n- **블루존 상단({p(blue_high)}) 돌파 시**: 강력한 상방 숏스퀴즈/슈팅으로 이어져 오늘의 피보나치 확장 목표가인 **114.6%({p(t2 + t_diff * 1.146)})** 및 **161.8%({p(t2 + t_diff * 1.618)})**까지 강세 랠리가 예측됩니다.")
        elif cp > blue_high:
            state_desc.append(f"🚀 **블루존 상방 돌파 (강세 랠리)**: 어제자 블루존 저항대({p(blue_high)})를 완전히 뚫고 안착하여 봇이 위로 슈팅을 쏘는 상방 추세 강화 상태입니다.")
            direction_opinion.append(f"- **목표가 지향**: 오늘의 피보나치 확장 목표가인 **114.6%({p(t2 + t_diff * 1.146)})** 돌파 및 최종 **161.8%({p(t2 + t_diff * 1.618)})** 가격대 도달이 예측됩니다.")
        else:
            state_desc.append("🔄 **채널 중간 횡보 및 수렴 상태**: 어제자 레드존과 블루존 사이의 안정적인 중립적 채널 내부입니다.")
            
        # SOP 회귀성 분석
        if abs(diff_sop) >= 2.0:
            state_desc.append(f"⚡ **SOP 이격 확대 ({diff_sop:+.2f}%)**: 오늘 기준점인 SOP(시가: {p(sop)})와의 가격 편차가 다소 확대되었습니다.")
            direction_opinion.append(f"- **SOP 회귀 작용**: 주가가 크게 튀었거나 내렸더라도 결국 60분봉 시가 기준선인 **{p(sop)}** 가격을 터치하러 되돌아오려는 단기 자석 효과 조정 방향이 예측됩니다.")
            
        # 오늘자 6번 / 3번 자리 분석
        if cp >= fib_382 and cp <= fib_618:
            state_desc.append(f"⚖️ **오늘 6번({p(fib_618)}) 및 3번({p(fib_382)}) 지지·저항 사이 등락**")
            direction_opinion.append(f"- **오늘 피보나치 수렴**: 6번 자리(오늘 고/저의 61.8% 첫 지지선)와 3번 자리(오늘의 38.2%) 사이에서 봇이 가격 흔들기를 진행 중일 가능성이 큽니다. 돌파 방향성을 주시해야 합니다.")
            
        # 숙제 타겟팅 예측
        all_hw = hw + chw
        if all_hw:
            direction_opinion.append("- **알고리즘 미해결 숙제 회귀 목표점**:")
            for hw_name, hw_price, hw_dir in all_hw:
                dir_txt = "하락 조정하여 Y7 선을 밟으러 내려갈" if hw_dir == "up" else "반등 상승하여 Y2 선을 밟으러 올라올"
                direction_opinion.append(f"  • {hw_name}에 근거하여, 차트는 결국 **{p(hw_price)}** 가격대까지 {dir_txt} 회귀 법칙이 작동할 것으로 분석됩니다.")

        # 조립
        md.append("#### 📊 현재 시장 진단\n")
        for sd in state_desc:
            md.append(f"* {sd}\n")
        if not state_desc:
            md.append("* 특별한 추세 변곡이 관찰되지 않는 중립 상태입니다.\n")
            
        md.append("\n#### 🔮 알고리즘 기반 단기 예측 방향성\n")
        for do in direction_opinion:
            md.append(f"{do}\n")
        if not direction_opinion:
            md.append(f"- 단기적으로는 오늘 6번 자리({p(fib_618)})와 3번 자리({p(fib_382)}) 사이에서의 지지 확인 및 박스권 트레이딩 관점을 유지합니다.\n")

    # ── 피보나치 알고리즘 교육용 해설 ─────────────────────────────────
    md.append("\n---\n")
    md.append("## 📚 피보나치(FiboAnalyzer) 알고리즘 핵심 용어 해설\n")
    md.append("### 1. 🕒 SOP (Start Open Price)\n")
    md.append("  - **개념**: **60분 봉의 시가(Open Price)**를 의미하며, 매 정각에 새로 시작될 때 형성되는 가격입니다.\n")
    md.append("  - **원리**: 특정 정각에 SOP를 만들어 두고 주가가 크게 움직이더라도, 결국 시간이 지나면 다시 그 SOP 가격으로 돌아와 **체크(터치)하고 가는 회귀 알고리즘 현상**이 매우 높은 확률로 발생합니다.\n\n")
    md.append("### 2. 🎯 리테스트 (Retest)\n")
    md.append("  - **개념**: 주가가 주요 지지/저항선을 돌파/이탈한 후, **해당 구간을 다시 밟아보며 지지/저항 여부를 확인하는 과정**을 의미합니다.\n")
    md.append("  - **상승장 (Y8)**: 전일 고가(저항)를 돌파하게 되면, 기존 저항이 지지선으로 바뀝니다. 상승을 이어가기 전에 이곳으로 잠시 내려와 지지를 확인하는 리테스트를 거칩니다.\n")
    md.append("  - **하락장 (Y1)**: 전일 저가(지지)를 깨고 내려갈 경우, 지지가 저항선으로 바뀝니다. 추가 하락 전에 다시 올라와 저항 여부를 확인하는 리테스트를 거칩니다.\n\n")
    md.append("### 3. 📚 숙제 (Homework)\n")
    md.append("  - **개념**: 시장의 추세가 너무 강해 **당일에 리테스트를 완료하지 못하고 다음 날 아침 9시(일봉 마감/시가 갱신)를 넘겨버린 가격대**를 말합니다.\n")
    md.append("  - **원리**: 명칭은 숙제로 변경되지만 알고리즘의 강력한 타겟팅 특성상 언젠가는 가격이 다시 돌아와 **반드시 체크(해결)하고 가는 자리**로 판단하여 매매의 중요 타점으로 삼습니다.\n")

    return "\n".join(md)
