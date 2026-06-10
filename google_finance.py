# -*- coding: utf-8 -*-
import requests
import re
import pandas as pd
import yfinance as yf
import datetime

def resolve_exchange(ticker):
    """
    yfinance 티커 포맷을 구글 파이낸스 쿼리 포맷(TICKER:EXCHANGE)으로 변환합니다.
    """
    ticker_upper = ticker.upper()
    if ":" in ticker_upper:
        return ticker_upper
    if ticker_upper == "USDKRW=X":
        return "USD-KRW"
    if ticker_upper.endswith('.KS'):
        return ticker_upper.split('.')[0] + ":KRX"
    if ticker_upper.endswith('.KQ'):
        return ticker_upper.split('.')[0] + ":KOSDAQ"
    if ticker_upper.endswith('.SG'):
        return ticker_upper.split('.')[0] + ":SGX"
    if ticker_upper.endswith('-USD'):
        return ticker_upper # 코인은 접미사 없이 BTC-USD 형태로 구글 파이낸스 조회 가능
        
    # 그 외 접미사가 없는 미국 주식 등은 yfinance Search를 사용하여 거래소를 파악
    try:
        s = yf.Search(ticker, max_results=3)
        quotes = s.quotes if hasattr(s, 'quotes') else []
        if quotes:
            for q in quotes:
                if q.get('symbol', '').upper() == ticker_upper:
                    exch = q.get('exchange', '').upper()
                    if exch in ['NMS', 'NGM', 'NCM', 'NAS']:
                        return f"{ticker_upper}:NASDAQ"
                    elif exch in ['NYQ', 'ASE', 'NYS']:
                        return f"{ticker_upper}:NYSE"
                    else:
                        return f"{ticker_upper}:{exch}"
    except Exception as e:
        print(f"[GoogleFinance] 거래소 조회 실패 (yfinance Search): {e}")
        
    # 최종 Fallback: 미국 나스닥으로 가정
    return f"{ticker_upper}:NASDAQ"

def _get_google_finance_html(target_ticker):
    url = f"https://www.google.com/finance/quote/{target_ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        print(f"[GoogleFinance] HTML 다운로드 에러: {e}")
    return None

def _parse_callbacks(html):
    if not html:
        return {}
    
    callbacks = re.findall(r"AF_initDataCallback\s*\(\s*({.*?})\s*\)\s*;", html, re.DOTALL)
    parsed_data = {}
    
    # eval을 안전하게 처리하기 위한 로컬 정의
    null = None
    true = True
    false = False
    undefined = None
    
    for cb in callbacks:
        # 자바스크립트 객체 리터럴을 파이썬 딕셔너리로 가공
        cb_py = cb.replace("key:", "'key':").replace("hash:", "'hash':").replace("data:", "'data':").replace("sideChannel:", "'sideChannel':")
        try:
            data_dict = eval(cb_py, {"null": None, "true": True, "false": False, "undefined": None})
            key = data_dict.get('key')
            data = data_dict.get('data')
            if key:
                parsed_data[key] = data
        except Exception:
            pass
    return parsed_data

def download_google_finance(ticker):
    """
    구글 파이낸스에서 과거 일봉 가격 데이터를 수집하여 pd.DataFrame으로 반환합니다.
    yfinance.download와 동일한 인터페이스를 지향합니다.
    """
    target = resolve_exchange(ticker)
    html = _get_google_finance_html(target)
    if not html:
        return pd.DataFrame()
        
    callbacks = _parse_callbacks(html)
    ds11_data = callbacks.get('ds:11')
    
    if not ds11_data:
        print(f"[GoogleFinance Warning] '{ticker}'의 ds:11 데이터를 찾지 못했습니다.")
        return pd.DataFrame()
        
    try:
        d1 = ds11_data[0]
        d2 = d1[0]
        
        is_coin = ticker.upper().endswith('-USD')
        rows = []
        
        if is_coin:
            # 코인 데이터 파싱 (d2[3][0][1] 에 리스트 존재)
            raw_list = d2[3][0][1]
            for item in raw_list:
                date_parts = item[0]
                year, month, day = date_parts[0], date_parts[1], date_parts[2]
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                close_val = item[1][0]
                
                rows.append({
                    "Date": date_str,
                    "Open": float(close_val),
                    "High": float(close_val),
                    "Low": float(close_val),
                    "Close": float(close_val),
                    "Volume": 0.0
                })
        else:
            # 주식 데이터 파싱 (d2[3][0][2] 에 리스트 존재)
            raw_list = d2[3][0][2]
            for item in raw_list:
                o, c, h, l = item[0], item[1], item[2], item[3]
                dt_str = item[4][:10] # YYYY-MM-DD
                vol = item[5] if len(item) > 5 else 0.0
                
                rows.append({
                    "Date": dt_str,
                    "Open": float(o),
                    "High": float(h),
                    "Low": float(l),
                    "Close": float(c),
                    "Volume": float(vol)
                })
                
        if not rows:
            return pd.DataFrame()
            
        df = pd.DataFrame(rows)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        print(f"[GoogleFinance Error] {ticker} DataFrame 파싱 실패: {e}")
        return pd.DataFrame()

def get_ticker_info(ticker):
    """
    구글 파이낸스에서 자산 정보를 긁어와 yfinance Ticker.info 형태의 딕셔너리로 반환합니다.
    """
    info = {
        "longBusinessSummary": "정보 없음",
        "marketCap": None,
        "sector": "정보 없음",
        "industry": "정보 없음",
        "longName": ticker,
        "currentPrice": None,
        "regularMarketPrice": None,
        "currency": "USD"
    }
    
    target = resolve_exchange(ticker)
    html = _get_google_finance_html(target)
    if not html:
        return info
        
    callbacks = _parse_callbacks(html)
    
    # 1. ds:3 - 기업 개요
    ds3_data = callbacks.get('ds:3')
    if ds3_data:
        try:
            d2 = ds3_data[0][0]
            if len(d2) > 2 and d2[2]:
                info["longBusinessSummary"] = d2[2]
        except Exception:
            pass
            
    # 2. ds:7 - 시가총액, 섹터, 산업
    ds7_data = callbacks.get('ds:7')
    if ds7_data:
        try:
            d2 = ds7_data[0][0]
            if len(d2) > 16 and d2[16]:
                info["marketCap"] = int(d2[16])
            if len(d2) > 18 and d2[18]:
                info["sector"] = d2[18]
        except Exception:
            pass
            
    # 3. ds:2 - 현재가, 자산 한글 이름, 통화
    ds2_data = callbacks.get('ds:2')
    if ds2_data:
        try:
            d2 = ds2_data[0][0]
            # 한글명
            if len(d2) > 2 and d2[2]:
                info["longName"] = d2[2]
            # 통화 코드
            if len(d2) > 4 and d2[4]:
                info["currency"] = d2[4]
            # 실시간 가격 리스트 [price, diff, pct]
            if len(d2) > 5 and isinstance(d2[5], list) and len(d2[5]) > 0:
                price = float(d2[5][0])
                info["currentPrice"] = price
                info["regularMarketPrice"] = price
        except Exception:
            pass
            
    # 백업: 현재가가 여전히 None이면 ds:11의 마지막 데이터에서 Close를 가져옴
    if info["currentPrice"] is None:
        df = download_google_finance(ticker)
        if not df.empty:
            last_close = float(df['Close'].iloc[-1])
            info["currentPrice"] = last_close
            info["regularMarketPrice"] = last_close
            
    return info

def get_ticker_news(ticker):
    """
    구글 파이낸스에서 관련 뉴스 목록을 긁어와 yfinance Ticker.news 포맷의 리스트로 반환합니다.
    """
    news_list = []
    target = resolve_exchange(ticker)
    html = _get_google_finance_html(target)
    if not html:
        return news_list
        
    callbacks = _parse_callbacks(html)
    ds15_data = callbacks.get('ds:15')
    
    if not ds15_data:
        return news_list
        
    try:
        # ds:15 의 리스트
        raw_news = ds15_data[0]
        for item in raw_news[:10]: # 최근 10개만 수집
            if len(item) < 3:
                continue
            url = item[0]
            title = item[1]
            provider = item[2]
            
            # 타임스탬프 파싱
            pub_date = ""
            if len(item) > 4 and isinstance(item[4], (int, float)):
                try:
                    dt = datetime.datetime.fromtimestamp(item[4], tz=datetime.timezone.utc)
                    pub_date = dt.isoformat()
                except Exception:
                    pass
            
            news_list.append({
                'content': {
                    'title': title,
                    'provider': {'displayName': provider},
                    'pubDate': pub_date,
                    'canonicalUrl': {'url': url}
                }
            })
    except Exception as e:
        print(f"[GoogleFinance] 뉴스 파싱 실패: {e}")
        
    return news_list
