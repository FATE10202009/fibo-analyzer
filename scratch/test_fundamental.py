import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

tickers = ["103590:KRX", "005930:KRX", "AAPL:NASDAQ"]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

for target in tickers:
    url = f"https://www.google.com/finance/quote/{target}"
    response = requests.get(url, headers=headers)
    html = response.text
    
    callbacks = re.findall(r"AF_initDataCallback\s*\(\s*({.*?})\s*\)\s*;", html, re.DOTALL)
    
    ds7_data = None
    for cb in callbacks:
        if 'ds:7' in cb:
            cb_py = cb.replace("key:", "'key':").replace("hash:", "'hash':").replace("data:", "'data':").replace("sideChannel:", "'sideChannel':")
            try:
                null = None; true = True; false = False; undefined = None
                data_dict = eval(cb_py)
                ds7_data = data_dict.get('data')
                break
            except:
                pass
                
    if ds7_data:
        d1 = ds7_data[0]
        d2 = d1[0]
        print(f"\n===== Ticker: {target} =====")
        # d2 내부에서 큰 숫자(시가총액 범위)를 가진 인덱스를 찾음
        for i, val in enumerate(d2):
            if isinstance(val, (int, float)) and val > 1e9:
                print(f"d2[{i}] = {val} (Possible Market Cap)")
            elif isinstance(val, list):
                # 리스트 내부도 검사
                for j, sub_val in enumerate(val):
                    if isinstance(sub_val, (int, float)) and sub_val > 1e9:
                        print(f"d2[{i}][{j}] = {sub_val} (Possible Market Cap)")
