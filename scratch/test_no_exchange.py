import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.google.com/finance/quote/AAPL"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
response = requests.get(url, headers=headers)
html = response.text

callbacks = re.findall(r"AF_initDataCallback\s*\(\s*({.*?})\s*\)\s*;", html, re.DOTALL)
print(f"URL: {url}")
print(f"Callbacks found: {len(callbacks)}")

has_ds11 = False
for cb in callbacks:
    if 'ds:11' in cb:
        has_ds11 = True
        break
print("Has ds:11:", has_ds11)
