import requests
from bs4 import BeautifulSoup

def get_google_finance_price(ticker, exchange="KRX"):
    url = f"https://www.google.com/finance/quote/{ticker}:{exchange}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch data, status code: {response.status_code}")
        return None
        
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 구글 파이낸스 현재가 클래스 또는 속성 찾기
    # 보통 현재 가격은 data-last-price 속성이 있는 div나 특정 class에 들어있음.
    # class name이 자주 바뀌기 때문에 data-last-price 또는 특정 구조로 찾는 것이 안전함.
    
    # 1. data-last-price 속성을 가진 엘리먼트 검색
    price_el = soup.find(attrs={"data-last-price": True})
    if price_el:
        price = price_el["data-last-price"]
        currency = price_el.get("data-currency-code", "")
        return price, currency
        
    # 2. 다른 방식: class="YMl7ec" 등 (구글 파이낸스의 현재 가격 div 클래스, 단 바뀔 수 있음)
    # yMl7ec는 현재 가격을 가지고 있는 클래스 중 하나로 널리 알려져 있음
    price_div = soup.find(class_="YMl7ec")
    if price_div:
        return price_div.text, ""
        
    return None

if __name__ == "__main__":
    # 일진전기 테스트 (103590)
    result = get_google_finance_price("103590", "KRX")
    print("일진전기 결과:", result)
    
    # Apple 테스트 (AAPL, exchange=NASDAQ)
    result_aapl = get_google_finance_price("AAPL", "NASDAQ")
    print("Apple 결과:", result_aapl)
