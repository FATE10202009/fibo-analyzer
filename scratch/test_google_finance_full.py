import requests
from bs4 import BeautifulSoup
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.google.com/finance/quote/103590:KRX"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}
response = requests.get(url, headers=headers)
html = response.text

print("HTML length:", len(html))

# 1. YMlKec 검색
matches = re.findall(r'class="[^"]*YMlKec[^"]*"[^>]*>([^<]+)', html)
print("YMlKec matches:", matches)

# 2. fxKbKc 검색
matches_fx = re.findall(r'class="[^"]*fxKbKc[^"]*"[^>]*>([^<]+)', html)
print("fxKbKc matches:", matches_fx)

# 3. data-last-price 검색
matches_dl = re.findall(r'data-last-price="([^"]+)"', html)
print("data-last-price matches:", matches_dl)

# 4. JSON-LD 또는 script 내 데이터 검색
# 종종 "103590", "KRX", 가격이 들어있는 JS array가 있음
# 예: [,72400,] 같은 형태
soup = BeautifulSoup(html, 'html.parser')
for s in soup.find_all('script'):
    content = s.string
    if content and '103590' in content and '72' in content: # 7만2천원 근처 가격
        print("Found possible script containing ticker and price!")
        # 100글자씩 잘라서 근처 확인
        idx = content.find('103590')
        print(content[max(0, idx-100):idx+200])
