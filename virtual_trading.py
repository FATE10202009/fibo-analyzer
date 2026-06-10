# -*- coding: utf-8 -*-
import os
import json
import time
import datetime
import threading
import traceback
import yfinance as yf

# 사용자 데이터가 저장될 디렉토리
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "virtual_data")
os.makedirs(DATA_DIR, exist_ok=True)

class VirtualTradingManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(VirtualTradingManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.lock = threading.Lock()  # 파일 I/O 및 데이터 수정용 락
        self.running = False
        self.thread = None
        self.check_interval = 60  # 60초마다 체크
        self._initialized = True

    def get_user_file_path(self, user_id):
        # 닉네임 정제 (알파벳, 숫자, 한글, 하이픈, 언더스코어만 허용)
        safe_id = "".join([c for c in user_id if c.isalnum() or c in ("-", "_")]).strip()
        if not safe_id:
            safe_id = "guest"
        return os.path.join(DATA_DIR, f"virtual_user_{safe_id}.json")

    def load_user_data(self, user_id):
        file_path = self.get_user_file_path(user_id)
        with self.lock:
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # 스키마 호환성 보장
                        data.setdefault("usd_cash", 100000000.0)
                        data.setdefault("krw_cash", 10000000000.0)
                        data.setdefault("portfolio", {})
                        data.setdefault("history", [])
                        data.setdefault("limit_orders", [])
                        return data
                except Exception as e:
                    print(f"[VirtualTrading] 데이터 로드 오류 ({user_id}): {e}")
            
            # 파일이 없거나 오류 발생 시 기본값 반환 및 저장
            default_data = {
                "usd_cash": 100000000.0,
                "krw_cash": 10000000000.0,
                "portfolio": {},
                "history": [],
                "limit_orders": []
            }
            # 파일 쓰기
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"[VirtualTrading] 기본 데이터 저장 오류 ({user_id}): {e}")
            return default_data

    def save_user_data(self, user_id, data):
        file_path = self.get_user_file_path(user_id)
        with self.lock:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                return True
            except Exception as e:
                print(f"[VirtualTrading] 데이터 저장 오류 ({user_id}): {e}")
                return False

    def reset_user_data(self, user_id):
        default_data = {
            "usd_cash": 100000000.0,
            "krw_cash": 10000000000.0,
            "portfolio": {},
            "history": [],
            "limit_orders": []
        }
        self.save_user_data(user_id, default_data)
        return default_data

    # 시장가 매수
    def execute_market_buy(self, user_id, ticker, amount, current_price, is_usd):
        data = self.load_user_data(user_id)
        cash_key = "usd_cash" if is_usd else "krw_cash"
        
        if data[cash_key] < amount:
            return False, "잔액이 부족합니다."
        
        qty = amount / current_price if current_price > 0 else 0.0
        if qty <= 0:
            return False, "올바르지 않은 주문 수량입니다."
            
        # 현금 차감
        data[cash_key] -= amount
        
        # 포트폴리오 업데이트
        portfolio = data["portfolio"]
        holding = portfolio.get(ticker, {"qty": 0.0, "avg_price": 0.0, "is_usd": is_usd})
        new_qty = holding["qty"] + qty
        new_avg = ((holding["qty"] * holding["avg_price"]) + amount) / new_qty if new_qty > 0 else 0.0
        
        portfolio[ticker] = {
            "qty": new_qty,
            "avg_price": new_avg,
            "is_usd": is_usd
        }
        
        # 이력 추가
        currency = "$" if is_usd else "₩"
        data["history"].append({
            "time": datetime.datetime.now().strftime("%m-%d %H:%M:%S"),
            "ticker": ticker,
            "type": "시장가 매수",
            "price": current_price,
            "qty": qty,
            "amount": amount,
            "currency": currency
        })
        
        self.save_user_data(user_id, data)
        return True, f"{ticker} {qty:,.4f}개 시장가 매수 완료!"

    # 시장가 매도
    def execute_market_sell(self, user_id, ticker, qty, current_price, is_usd):
        data = self.load_user_data(user_id)
        cash_key = "usd_cash" if is_usd else "krw_cash"
        
        portfolio = data["portfolio"]
        holding = portfolio.get(ticker, {"qty": 0.0, "avg_price": 0.0, "is_usd": is_usd})
        
        if holding["qty"] < qty:
            return False, "보유 수량이 부족합니다."
            
        recv_amount = qty * current_price
        
        # 포트폴리오 업데이트
        new_qty = holding["qty"] - qty
        if new_qty <= 0.0001:
            portfolio.pop(ticker, None)
        else:
            portfolio[ticker] = {
                "qty": new_qty,
                "avg_price": holding["avg_price"],
                "is_usd": is_usd
            }
            
        # 현금 증가
        data[cash_key] += recv_amount
        
        # 이력 추가
        currency = "$" if is_usd else "₩"
        data["history"].append({
            "time": datetime.datetime.now().strftime("%m-%d %H:%M:%S"),
            "ticker": ticker,
            "type": "시장가 매도",
            "price": current_price,
            "qty": qty,
            "amount": recv_amount,
            "currency": currency
        })
        
        self.save_user_data(user_id, data)
        return True, f"{ticker} {qty:,.4f}개 시장가 매도 완료!"

    # 지정가 매수 예약
    def add_limit_buy(self, user_id, ticker, target_price, amount, is_usd):
        data = self.load_user_data(user_id)
        cash_key = "usd_cash" if is_usd else "krw_cash"
        
        if data[cash_key] < amount:
            return False, "잔액이 부족합니다."
            
        qty = amount / target_price if target_price > 0 else 0.0
        if qty <= 0:
            return False, "올바르지 않은 지정가 또는 금액입니다."
            
        # 현금 선차감 (증거금 잠금)
        data[cash_key] -= amount
        
        # 지정가 대기 목록 추가
        order = {
            "id": f"buy_{int(time.time())}_{ticker}",
            "ticker": ticker,
            "type": "지정가 매수 (LIMIT BUY)",
            "target_price": float(target_price),
            "qty": qty,
            "amount": amount,
            "is_usd": is_usd,
            "created_at": datetime.datetime.now().strftime("%m-%d %H:%M:%S")
        }
        data["limit_orders"].append(order)
        
        self.save_user_data(user_id, data)
        currency = "$" if is_usd else "₩"
        return True, f"{ticker} @ {currency}{target_price:,.2f} 지정가 매수 예약 완료!"

    # 지정가 매도 예약
    def add_limit_sell(self, user_id, ticker, target_price, qty, is_usd):
        data = self.load_user_data(user_id)
        portfolio = data["portfolio"]
        holding = portfolio.get(ticker, {"qty": 0.0, "avg_price": 0.0, "is_usd": is_usd})
        
        if holding["qty"] < qty:
            return False, "보유 수량이 부족합니다."
            
        # 수량 선차감 (주문 가능 수량 잠금)
        holding["qty"] -= qty
        if holding["qty"] <= 0.0001:
            portfolio.pop(ticker, None)
        else:
            portfolio[ticker] = holding
            
        # 지정가 대기 목록 추가
        order = {
            "id": f"sell_{int(time.time())}_{ticker}",
            "ticker": ticker,
            "type": "지정가 매도 (LIMIT SELL)",
            "target_price": float(target_price),
            "qty": qty,
            "amount": qty * target_price,
            "is_usd": is_usd,
            "created_at": datetime.datetime.now().strftime("%m-%d %H:%M:%S")
        }
        data["limit_orders"].append(order)
        
        self.save_user_data(user_id, data)
        currency = "$" if is_usd else "₩"
        return True, f"{ticker} @ {currency}{target_price:,.2f} 지정가 매도 예약 완료!"

    # 지정가 주문 취소
    def cancel_limit_order(self, user_id, order_id):
        data = self.load_user_data(user_id)
        orders = data["limit_orders"]
        
        target_order = None
        for order in orders:
            if order["id"] == order_id:
                target_order = order
                break
                
        if not target_order:
            return False, "주문을 찾을 수 없습니다."
            
        orders.remove(target_order)
        
        # 잠금 해제 (현금 또는 주식 복구)
        is_usd = target_order["is_usd"]
        ticker = target_order["ticker"]
        qty = target_order["qty"]
        amount = target_order["amount"]
        
        if "LIMIT BUY" in target_order["type"]:
            cash_key = "usd_cash" if is_usd else "krw_cash"
            data[cash_key] += amount
        else:
            portfolio = data["portfolio"]
            holding = portfolio.get(ticker, {"qty": 0.0, "avg_price": target_order["target_price"], "is_usd": is_usd})
            holding["qty"] += qty
            portfolio[ticker] = holding
            
        self.save_user_data(user_id, data)
        return True, "주문이 취소되었습니다."

    # 백그라운드 엔진 가동
    def start_matching_engine(self):
        with self._lock:
            if self.running:
                return
            self.running = True
            self.thread = threading.Thread(target=self._matching_loop, daemon=True)
            self.thread.start()
            print("[VirtualTrading] 24시간 백그라운드 매칭 엔진이 가동되었습니다.")

    def stop_matching_engine(self):
        self.running = False

    def _matching_loop(self):
        while self.running:
            try:
                self.process_all_users()
            except Exception as e:
                print(f"[VirtualTrading] 매칭 루프 에러: {e}")
                traceback.print_exc()
            
            # check_interval 동안 대기
            for _ in range(self.check_interval):
                if not self.running:
                    break
                time.sleep(1)

    def _get_current_price(self, ticker):
        try:
            ticker_obj = yf.Ticker(ticker)
            if hasattr(ticker_obj, 'fast_info') and 'lastPrice' in ticker_obj.fast_info:
                return float(ticker_obj.fast_info['lastPrice'])
            
            hist = ticker_obj.history(period="1d", interval="1m")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception as e:
            print(f"[VirtualTrading Engine] 가격 조회 실패 ({ticker}): {e}")
        return None

    def process_all_users(self):
        # virtual_data 폴더의 모든 사용자 json 파일 스캔
        if not os.path.exists(DATA_DIR):
            return
            
        files = [f for f in os.listdir(DATA_DIR) if f.startswith("virtual_user_") and f.endswith(".json")]
        if not files:
            return
            
        # 모든 파일들의 대기 지정가 주문 모으기
        user_orders_map = {} # {user_id: [orders]}
        all_tickers = set()
        
        for file in files:
            user_id = file.replace("virtual_user_", "").replace(".json", "")
            data = self.load_user_data(user_id)
            orders = data.get("limit_orders", [])
            if orders:
                user_orders_map[user_id] = (data, orders)
                for o in orders:
                    all_tickers.add(o["ticker"])
                    
        if not all_tickers:
            return
            
        # 티커 가격 수집
        prices = {}
        for ticker in all_tickers:
            p = self._get_current_price(ticker)
            if p is not None:
                prices[ticker] = p
                
        # 각 유저별 지정가 충족여부 체크 및 체결
        for user_id, (data, orders) in user_orders_map.items():
            executed_any = False
            remaining_orders = []
            
            for order in orders:
                ticker = order["ticker"]
                target_p = order["target_price"]
                qty = order["qty"]
                amount = order["amount"]
                is_usd = order["is_usd"]
                order_type = order["type"]
                
                price = prices.get(ticker)
                if price is None:
                    remaining_orders.append(order)
                    continue
                    
                triggered = False
                
                # 지정가 매수 체결 조건: 현재가 <= 목표가
                if "LIMIT BUY" in order_type and price <= target_p:
                    triggered = True
                    # 실 체결가에 근거하여 수량 재조정 (선결제된 금액 기준)
                    actual_qty = amount / price
                    
                    portfolio = data["portfolio"]
                    holding = portfolio.get(ticker, {"qty": 0.0, "avg_price": 0.0, "is_usd": is_usd})
                    new_qty = holding["qty"] + actual_qty
                    new_avg = ((holding["qty"] * holding["avg_price"]) + amount) / new_qty if new_qty > 0 else 0.0
                    
                    portfolio[ticker] = {
                        "qty": new_qty,
                        "avg_price": new_avg,
                        "is_usd": is_usd
                    }
                    
                    currency = "$" if is_usd else "₩"
                    data["history"].append({
                        "time": datetime.datetime.now().strftime("%m-%d %H:%M:%S"),
                        "ticker": ticker,
                        "type": "지정가 매수 체결",
                        "price": price,
                        "qty": actual_qty,
                        "amount": amount,
                        "currency": currency
                    })
                    executed_any = True
                    print(f"[VirtualTrading Engine] {user_id} - {ticker} 매수 체결 완료 @ {price}")
                    
                # 지정가 매도 체결 조건: 현재가 >= 목표가
                elif "LIMIT SELL" in order_type and price >= target_p:
                    triggered = True
                    # 실제 체결 금액 계산 (체결 금액 복구)
                    actual_recv = qty * price
                    cash_key = "usd_cash" if is_usd else "krw_cash"
                    data[cash_key] += actual_recv
                    
                    currency = "$" if is_usd else "₩"
                    data["history"].append({
                        "time": datetime.datetime.now().strftime("%m-%d %H:%M:%S"),
                        "ticker": ticker,
                        "type": "지정가 매도 체결",
                        "price": price,
                        "qty": qty,
                        "amount": actual_recv,
                        "currency": currency
                    })
                    executed_any = True
                    print(f"[VirtualTrading Engine] {user_id} - {ticker} 매도 체결 완료 @ {price}")
                    
                if not triggered:
                    remaining_orders.append(order)
                    
            if executed_any:
                data["limit_orders"] = remaining_orders
                self.save_user_data(user_id, data)

# 싱글톤 인스턴스 생성
virtual_trading_manager = VirtualTradingManager()
