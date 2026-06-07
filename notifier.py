# -*- coding: utf-8 -*-
import json
import os
import time
import threading
import urllib.request
import urllib.parse
import yfinance as yf
import traceback
import uuid

ALERTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts.json")

def load_alerts_data():
    if os.path.exists(ALERTS_FILE):
        try:
            with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "alerts": []
    }

def save_alerts_data(data):
    try:
        with open(ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[Notifier] 설정 저장 중 오류: {e}")

def send_telegram_message(bot_token, chat_id, message):
    if not bot_token or not chat_id:
        return False, "봇 토큰 또는 Chat ID가 설정되지 않았습니다."
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=5) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            if res_data.get("ok"):
                return True, "발송 성공"
            else:
                return False, res_data.get("description", "알 수 없는 오류")
    except Exception as e:
        return False, str(e)


class AlertManager:
    def __init__(self):
        self.data = load_alerts_data()
        self.running = False
        self.thread = None
        self.check_interval = 60 * 5  # 기본 5분마다 체크
        # 다무스 레벨 알림 관련
        self._damus_thread = None
        self._damus_running = False
        self._damus_cooldown = {}  # {"TICKER_레벨명": last_sent_time} — 중복 발송 방지
        self._damus_cooldown_sec = 300  # 같은 레벨 5분 이내 재발송 금지

    def get_token_and_chat_id(self):
        return self.data.get("telegram_bot_token", ""), self.data.get("telegram_chat_id", "")
        
    def set_telegram_config(self, token, chat_id):
        self.data["telegram_bot_token"] = token
        self.data["telegram_chat_id"] = chat_id
        save_alerts_data(self.data)
        
    def add_alert(self, ticker, target_price, condition):
        new_alert = {
            "id": str(uuid.uuid4())[:8],
            "ticker": ticker.upper(),
            "target_price": float(target_price),
            "condition": condition, # 'above' or 'below'
            "is_active": True
        }
        self.data.setdefault("alerts", []).append(new_alert)
        save_alerts_data(self.data)
        return new_alert["id"]
        
    def remove_alert(self, alert_id):
        if "alerts" in self.data:
            self.data["alerts"] = [a for a in self.data["alerts"] if a["id"] != alert_id]
            save_alerts_data(self.data)
            
    def get_all_alerts(self):
        return self.data.get("alerts", [])
        
    def toggle_alert(self, alert_id, is_active):
        for a in self.data.get("alerts", []):
            if a["id"] == alert_id:
                a["is_active"] = is_active
                break
        save_alerts_data(self.data)

    def _get_current_price(self, ticker):
        try:
            # yfinance 최신 가격 가져오기 (가장 빠른 방법 시도 후 폴백)
            ticker_obj = yf.Ticker(ticker)
            if hasattr(ticker_obj, 'fast_info') and 'lastPrice' in ticker_obj.fast_info:
                return float(ticker_obj.fast_info['lastPrice'])
                
            # fallback
            hist = ticker_obj.history(period="1d", interval="1m")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception as e:
            print(f"[Notifier] 가격 조회 실패 ({ticker}): {e}")
        return None

    def start_monitor(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print("[Notifier] 목표가 알림 모니터링이 시작되었습니다.")
        
    def stop_monitor(self):
        self.running = False

    def _monitor_loop(self):
        while self.running:
            try:
                self.check_alerts()
            except Exception as e:
                print(f"[Notifier] 루프 오류: {e}")
                traceback.print_exc()
                
            # 슬립을 작게 쪼개어 중지 명령에 빠르게 반응하도록 함
            for _ in range(self.check_interval):
                if not self.running:
                    break
                time.sleep(1)

    def check_alerts(self):
        self.data = load_alerts_data() # 최신화
        alerts = self.data.get("alerts", [])
        active_alerts = [a for a in alerts if a.get("is_active")]
        
        if not active_alerts:
            return
            
        token, chat_id = self.get_token_and_chat_id()
        if not token or not chat_id:
            return
            
        # 동일 티커 중복 조회를 막기 위해 고유 티커 목록 추출
        unique_tickers = list(set([a["ticker"] for a in active_alerts]))
        prices = {}
        for ticker in unique_tickers:
            price = self._get_current_price(ticker)
            if price is not None:
                prices[ticker] = price
                
        alerts_updated = False
        
        for alert in active_alerts:
            ticker = alert["ticker"]
            current_price = prices.get(ticker)
            
            if current_price is None:
                continue
                
            target = alert["target_price"]
            cond = alert["condition"]
            triggered = False
            
            if cond == 'above' and current_price >= target:
                triggered = True
                cond_str = "상향 돌파 (>=)"
            elif cond == 'below' and current_price <= target:
                triggered = True
                cond_str = "하향 돌파 (<=)"
                
            if triggered:
                # 심볼 포맷팅
                symbol_str = ticker
                if not (ticker.endswith(".KS") or ticker.endswith(".KQ")):
                    price_str = f"${current_price:,.4f}"
                    target_str = f"${target:,.4f}"
                else:
                    price_str = f"₩{current_price:,.0f}"
                    target_str = f"₩{target:,.0f}"

                msg = (
                    f"🚨 <b>[FiboAnalyzer 목표가 도달 알림]</b>\n\n"
                    f"<b>종목명:</b> {symbol_str}\n"
                    f"<b>현재가:</b> {price_str}\n"
                    f"<b>목표가:</b> {target_str} ({cond_str})\n\n"
                    f"지정하신 목표가 조건이 달성되었습니다!"
                )
                
                success, err = send_telegram_message(token, chat_id, msg)
                if success:
                    print(f"[Notifier] {ticker} 알림 발송 성공!")
                    # 발송 후 중복 발송 방지를 위해 비활성화
                    alert["is_active"] = False
                    alerts_updated = True
                else:
                    print(f"[Notifier] {ticker} 알림 발송 실패: {err}")
                    
        if alerts_updated:
            save_alerts_data(self.data)

    # ─────────────────────────────────────────────────────────────
    # 피보나치 알림 대상 티커 관리
    # ─────────────────────────────────────────────────────────────
    def get_damus_alert_tickers(self):
        """피보나치 알림이 켜진 티커 집합을 반환합니다."""
        self.data = load_alerts_data()
        return set(self.data.get('damus_alert_tickers', []))

    def set_damus_alert_ticker(self, ticker, enabled):
        """특정 티커의 피보나치 알림 ON/OFF를 저장합니다."""
        self.data = load_alerts_data()
        tickers = set(self.data.get('damus_alert_tickers', []))
        if enabled:
            tickers.add(ticker)
        else:
            tickers.discard(ticker)
        self.data['damus_alert_tickers'] = list(tickers)
        save_alerts_data(self.data)

    # ─────────────────────────────────────────────────────────────
    # 피보나치 레벨 알림 기능
    # ─────────────────────────────────────────────────────────────
    def start_damus_monitor(self, ticker, is_usd, check_interval_sec=60):
        """
        피보나치 알고리즘 레벨(SOP, R2, R7, Y2, Y7)을 주기적으로 체크하여
        현재가가 해당 레벨에 근접(±0.15%)하면 텔레그램 경고를 발송합니다.
        """
        if self._damus_running:
            self.stop_damus_monitor()

        self._damus_running = True
        self._damus_ticker  = ticker
        self._damus_is_usd  = is_usd
        self._damus_interval = check_interval_sec
        self._damus_thread  = threading.Thread(
            target=self._damus_loop, daemon=True
        )
        self._damus_thread.start()
        print(f"[Fibo Notifier] {ticker} 피보나치 레벨 모니터링 시작 (간격: {check_interval_sec}초)")

    def stop_damus_monitor(self):
        self._damus_running = False
        print("[Fibo Notifier] 피보나치 레벨 모니터링 중지")

    def _damus_loop(self):
        while self._damus_running:
            try:
                self._check_damus_levels()
            except Exception as e:
                print(f"[Fibo Notifier] 오류: {e}")
                traceback.print_exc()
            for _ in range(self._damus_interval):
                if not self._damus_running:
                    break
                time.sleep(1)

    def _check_damus_levels(self):
        token, chat_id = self.get_token_and_chat_id()
        if not token or not chat_id:
            return

        ticker  = self._damus_ticker
        is_usd  = self._damus_is_usd

        # 피보나치 데이터 산출
        try:
            from damus import get_damus_data
            data = get_damus_data(ticker, is_usd)
        except Exception as e:
            print(f"[Fibo Notifier] 데이터 수집 실패: {e}")
            return

        if not data:
            return

        cp  = data['current_price']
        levels = [
            ("🥔 SOP (감자)",   data['sop'], "SOP"),
            ("📈 R7 실시간고점", data['r7'],  "R7"),
            ("📉 R2 실시간저점", data['r2'],  "R2"),
            ("🔶 Y7 전일고가",   data['y7'],  "Y7"),
            ("🔷 Y2 전일저가",   data['y2'],  "Y2"),
        ]
        # 숙제 레벨도 추가
        for hw_name, hw_price, _ in data.get('homework', []):
            levels.append((f"🔔 숙제 {hw_name}", hw_price, f"HW_{hw_price:.4f}"))
        for hw_name, hw_price, _ in data.get('carried_homework', []):
            levels.append((f"📌 이월숙제 {hw_name}", hw_price, f"CHW_{hw_price:.4f}"))

        now = time.time()
        proximity_pct = 0.0015   # ±0.15% 이내 접근 시 알림

        for label, level_price, key in levels:
            if level_price <= 0:
                continue
            diff_pct = abs((cp - level_price) / level_price)
            if diff_pct > proximity_pct:
                continue   # 범위 밖 → 스킵

            # 쿨다운 체크 (5분 이내 중복 발송 방지)
            cooldown_key = f"{ticker}_{key}"
            last_sent = self._damus_cooldown.get(cooldown_key, 0)
            if now - last_sent < self._damus_cooldown_sec:
                continue

            # 방향 판단
            direction = "근접" if diff_pct < 0.0005 else ("상향 접근 ↑" if cp > level_price else "하향 접근 ↓")

            # 가격 포맷
            if is_usd:
                cp_str    = f"${cp:,.4f}"
                lv_str    = f"${level_price:,.4f}"
            else:
                cp_str    = f"₩{cp:,.0f}"
                lv_str    = f"₩{level_price:,.0f}"

            msg = (
                f"⚡ <b>[피보나치 레벨 경고]</b>\n\n"
                f"<b>종목:</b> {ticker}\n"
                f"<b>레벨:</b> {label}\n"
                f"<b>레벨 가격:</b> {lv_str}\n"
                f"<b>현재 가격:</b> {cp_str} ({direction})\n"
                f"<b>차이:</b> {diff_pct*100:.3f}%\n\n"
                f"피보나치 알고리즘 핵심 구간에 현재가가 진입했습니다!"
            )

            success, err = send_telegram_message(token, chat_id, msg)
            if success:
                self._damus_cooldown[cooldown_key] = now
                print(f"[Fibo Notifier] {ticker} {label} 알림 발송 성공")
            else:
                print(f"[Fibo Notifier] 발송 실패: {err}")


# 싱글톤 인스턴스
alert_manager = AlertManager()
