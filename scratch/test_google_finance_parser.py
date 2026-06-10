import requests
from bs4 import BeautifulSoup
import re
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.google.com/finance/quote/103590:KRX"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}
response = requests.get(url, headers=headers)
html = response.text

# AF_initDataCallback 함수 호출을 찾는 정규식
# AF_initDataCallback({key: 'ds:X', hash: 'Y', data: [...]}); 형태를 추출
callbacks = re.findall(r"AF_initDataCallback\s*\(\s*({.*?})\s*\)\s*;", html, re.DOTALL)

print(f"Found {len(callbacks)} callbacks.")

for i, cb in enumerate(callbacks):
    # JSON 형태로 변환하기 위해 js 객체를 가공
    # key: 'ds:8' -> "key": "ds:8"
    # data: [...] -> "data": [...]
    # 단, 따옴표가 없거나 이스케이프가 있는 경우를 처리해야 하므로 안전하게 파이썬의 dict로 리터럴 평가를 하거나 정규식 가공을 함.
    # 안전하게 가공하기 위해 node.js나 python의 demjson 등을 쓰면 좋지만, 여기서는 간단하게 regex로 속성명을 따옴표로 감싸서 json.loads를 유도해봄.
    
    # 1. 속성명에 따옴표 붙이기
    cb_json = cb
    cb_json = re.sub(r'(\b\w+\b)\s*:', r'"\1":', cb_json)
    # 2. 작은따옴표를 큰따옴표로
    cb_json = cb_json.replace("'", '"')
    # 3. 널(null) 문자 처리 등 자바스크립트 리터럴을 JSON으로 맞춤
    # (하지만 원본 데이터에 자바스크립트 특유의 빈 쉼표 ,, 나 undef 등이 있으면 json.loads가 실패할 수 있음)
    # 예: [1,,3] -> [1, null, 3]
    # 파이썬 literal_eval을 사용하면 null, true, false 만 적절히 정의해주면 바로 파싱 가능하므로 이것이 더 견고함.
    
    try:
        # 안전한 파이썬 literal_eval 사용을 위해 null, true, false 변수 정의
        null = None
        true = True
        false = False
        # literal_eval을 위해 cb의 딕셔너리 부분만 가져옴
        # js object literal을 python dict literal로 평가
        # key: 'ds:8' -> 'key': 'ds:8'
        # data: [...]
        # literal_eval은 식별자 key, hash, data를 사전 정의해줄 수 없음. 
        # 대신 cb 문자열에서 'key:', 'hash:', 'data:' 부분을 파이썬 dict 문법에 맞게 문자열 키로 교체해줌.
        cb_py = cb.replace("key:", "'key':")
        cb_py = cb_py.replace("hash:", "'hash':")
        cb_py = cb_py.replace("data:", "'data':")
        cb_py = cb_py.replace("sideChannel:", "'sideChannel':")
        
        # null, true, false 값을 파이썬용으로 매핑할 수 있게 로컬 컨텍스트 제공
        data_dict = eval(cb_py, {"null": None, "true": True, "false": False, "undefined": None})
        
        key = data_dict.get('key')
        data = data_dict.get('data')
        
        print(f"\n[{i}] Key: {key}")
        # 데이터의 depth를 따라가며 구조 파악
        if data:
            data_str = str(data)
            print("Data preview:", data_str[:300])
            
            # 과거 데이터가 들어있는 key (예: ds:9, ds:11 등) 분석
            # 데이터 내에 날짜 포맷 ('2026-06-08' 등)이나 가격 배열이 있는지 검사
            # 'KRW' 혹은 'USD'를 찾아서 통화 단위도 확인
    except Exception as e:
        print(f"Failed to parse callback {i}: {e}")
