import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

tickers = [
    ("103590.KS", "103590:KRX"),
    ("AAPL", "AAPL:NASDAQ"),
    ("BTC-USD", "BTC-USD"),
    ("005930.KS", "005930:KRX")
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}

for original, target in tickers:
    url = f"https://www.google.com/finance/quote/{target}"
    response = requests.get(url, headers=headers)
    html = response.text
    
    # ds:11 (일봉 데이터) 또는 ds:9 (일일 데이터) 혹은 ds:8 (실시간)
    # AF_initDataCallback를 찾음
    callbacks = re.findall(r"AF_initDataCallback\s*\(\s*({.*?})\s*\)\s*;", html, re.DOTALL)
    
    print(f"\n===== Ticker: {original} (Google: {target}) =====")
    print(f"HTML len: {len(html)}")
    print(f"Callbacks found: {len(callbacks)}")
    
    found_keys = []
    for cb in callbacks:
        cb_py = cb.replace("key:", "'key':").replace("hash:", "'hash':").replace("data:", "'data':").replace("sideChannel:", "'sideChannel':")
        try:
            data_dict = eval(cb_py, {"null": None, "true": True, "false": False, "undefined": None})
            key = data_dict.get('key')
            found_keys.append(key)
            if key in ['ds:11', 'ds:9', 'ds:8', 'ds:2']:
                data = data_dict.get('data')
                if data:
                    print(f"  - Key: {key}, Data preview: {str(data)[:200]}")
        except:
            pass
    print(f"Keys found: {found_keys}")
