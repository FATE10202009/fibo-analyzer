import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.google.com/finance/quote/AAPL:NASDAQ"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}
response = requests.get(url, headers=headers)
html = response.text

callbacks = re.findall(r"AF_initDataCallback\s*\(\s*({.*?})\s*\)\s*;", html, re.DOTALL)

for cb in callbacks:
    cb_py = cb.replace("key:", "'key':").replace("hash:", "'hash':").replace("data:", "'data':").replace("sideChannel:", "'sideChannel':")
    try:
        null = None; true = True; false = False; undefined = None
        data_dict = eval(cb_py)
        key = data_dict.get('key')
        if key == 'ds:11':
            data = data_dict.get('data')
            print("--- AAPL ds:11 Detailed Structure ---")
            d1 = data[0]
            d2 = d1[0]
            for i, val in enumerate(d2):
                print(f"d2[{i}] type: {type(val)}")
                if isinstance(val, list):
                    print(f"d2[{i}] len: {len(val)}")
                    print(f"d2[{i}] preview: {str(val)[:300]}")
    except Exception as e:
        print("Error parsing ds:11:", e)
