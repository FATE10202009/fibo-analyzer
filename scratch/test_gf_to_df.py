import requests
import re
import sys
import pandas as pd
import yfinance as yf

sys.stdout.reconfigure(encoding='utf-8')

def resolve_exchange(ticker):
    """yfinance Search를 활용해 티커의 거래소 매핑"""
    if ticker.endswith('.KS'):
        return ticker.split('.')[0] + ":KRX"
    if ticker.endswith('.KQ'):
        return ticker.split('.')[0] + ":KOSDAQ"
    if ticker.endswith('-USD'):
        return ticker # 코인은 거래소 접미사 없이 바로 BTC-USD 형태
        
    # 그 외 미국 주식 등
    try:
        s = yf.Search(ticker, max_results=3)
        quotes = s.quotes if hasattr(s, 'quotes') else []
        if quotes:
            for q in quotes:
                if q.get('symbol', '').upper() == ticker.upper():
                    exch = q.get('exchange', '').upper()
                    if exch in ['NMS', 'NGM', 'NCM', 'NAS']:
                        return f"{ticker}:NASDAQ"
                    elif exch in ['NYQ', 'ASE', 'NYS']:
                        return f"{ticker}:NYSE"
                    else:
                        return f"{ticker}:{exch}"
    except Exception as e:
        print(f"Exchange resolution failed: {e}")
        
    # 기본값은 NASDAQ으로 가정
    return f"{ticker}:NASDAQ"

def download_from_google_finance(ticker):
    target = resolve_exchange(ticker)
    url = f"https://www.google.com/finance/quote/{target}"
    print(f"Requesting URL: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"HTTP Error: {response.status_code}")
        return None
        
    html = response.text
    callbacks = re.findall(r"AF_initDataCallback\s*\(\s*({.*?})\s*\)\s*;", html, re.DOTALL)
    
    ds11_data = None
    for cb in callbacks:
        if 'ds:11' in cb:
            cb_py = cb.replace("key:", "'key':").replace("hash:", "'hash':").replace("data:", "'data':").replace("sideChannel:", "'sideChannel':")
            try:
                null = None; true = True; false = False; undefined = None
                data_dict = eval(cb_py)
                ds11_data = data_dict.get('data')
                break
            except Exception as e:
                print("Eval failed:", e)
                
    if not ds11_data:
        print("Failed to find ds:11 data")
        return None
        
    try:
        d1 = ds11_data[0]
        d2 = d1[0]
        
        is_coin = ticker.endswith('-USD')
        
        rows = []
        if is_coin:
            # 코인 데이터 파싱 (ds:11에서 d2[3][0][1] 에 들어있음)
            raw_list = d2[3][0][1]
            for item in raw_list:
                # item: [[year, month, day, hour, min, ...], [close, diff, diff_pct, ...], 0]
                date_parts = item[0]
                # 날짜 파싱 [2026, 5, 8, 23, 58, ...]
                year, month, day = date_parts[0], date_parts[1], date_parts[2]
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                
                close_val = item[1][0]
                # 코인은 시/고/저가 없으므로 Close와 동일하게 매핑
                rows.append({
                    "Date": date_str,
                    "Open": close_val,
                    "High": close_val,
                    "Low": close_val,
                    "Close": close_val,
                    "Volume": 0
                })
        else:
            # 주식 데이터 파싱 (ds:11에서 d2[3][0][2] 에 들어있음)
            raw_list = d2[3][0][2]
            for item in raw_list:
                # item: [open, close, high, low, date_str, volume]
                # 예: [137900, 144100, 144400, 137700, '2026-05-08T15:30:00+09:00', 581512]
                o, c, h, l = item[0], item[1], item[2], item[3]
                dt_str = item[4][:10] # YYYY-MM-DD
                vol = item[5] if len(item) > 5 else 0
                rows.append({
                    "Date": dt_str,
                    "Open": float(o),
                    "High": float(h),
                    "Low": float(l),
                    "Close": float(c),
                    "Volume": float(vol)
                })
                
        df = pd.DataFrame(rows)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        print("Parsing to DataFrame failed:", e)
        return None

if __name__ == "__main__":
    df_stock = download_from_google_finance("103590.KS")
    if df_stock is not None:
        print("\n--- Stock DataFrame (103590.KS) ---")
        print(df_stock.tail())
        
    df_coin = download_from_google_finance("BTC-USD")
    if df_coin is not None:
        print("\n--- Coin DataFrame (BTC-USD) ---")
        print(df_coin.tail())
