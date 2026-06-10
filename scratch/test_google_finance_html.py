import requests
from bs4 import BeautifulSoup

url = "https://www.google.com/finance/quote/103590:KRX"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}
response = requests.get(url, headers=headers)
print("Status Code:", response.status_code)

soup = BeautifulSoup(response.text, 'html.parser')

# data-last-price 검색
elements = soup.find_all(attrs={"data-last-price": True})
print(f"Found {len(elements)} elements with data-last-price")
for el in elements[:5]:
    print(el.name, el.get('class'), el.get('data-last-price'))

# YMl7ec 검색
y_elements = soup.find_all(class_="YMl7ec")
print(f"Found {len(y_elements)} elements with class YMl7ec")
for el in y_elements[:5]:
    print(el.name, el.text)

# HTML 일부 저장하여 나중에 확인할 수 있게 함
with open("google_finance_dump.html", "w", encoding="utf-8") as f:
    f.write(response.text[:100000]) # 처음 100kb만 저장
