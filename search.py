# -*- coding: utf-8 -*-
import urllib.request
import urllib.parse
import json
import yfinance as yf

def filter_quote_by_market(quotes, market_option):
    """
    야후 파이낸스 검색 결과(quotes)를 사용자가 선택한 마켓 옵션(all, nasdaq, binance)에 맞춰 필터링합니다.
    """
    if not quotes:
        return None
        
    if market_option == 'all':
        return quotes[0]
        
    for q in quotes:
        symbol = q.get('symbol', '').upper()
        exchange = q.get('exchange', '').upper()
        quote_type = q.get('quoteType', '').upper()
        
        if market_option == 'nasdaq':
            # 나스닥 거래소 식별자들: NMS (Global Select), NGM (Global Market), NCM (Capital Market), NAS (Nasdaq)
            if exchange in ['NMS', 'NGM', 'NCM', 'NAS'] and quote_type == 'EQUITY':
                return q
        elif market_option == 'binance':
            # 가상자산 타입이거나 symbol이 -USD, -BTC 등으로 끝나는 경우
            if quote_type == 'CRYPTOCURRENCY' or symbol.endswith('-USD') or exchange == 'CCC':
                return q
                
    # 매칭되는 것이 없을 경우 차선책으로 1순위 리턴
    return quotes[0]

def translate_and_romanize(text):
    """구글 번역 무료 API를 사용하여 한글을 영어로 변환하고, 로마자 음역(발음) 표기도 가져옵니다."""
    try:
        encoded = urllib.parse.quote(text)
        # dt=t(번역) 및 dt=rm(로마자 표기) 파라미터를 추가하여 호출합니다.
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=en&dt=t&dt=rm&q={encoded}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            translated = None
            romanized = None
            
            if data and data[0]:
                for item in data[0]:
                    if isinstance(item, list) and len(item) >= 4:
                        if item[0] is not None and item[1] is not None:
                            translated = item[0]
                        elif item[3] is not None:
                            romanized = item[3]
            if not translated and data and data[0] and data[0][0]:
                translated = data[0][0][0]
                
            return (translated.strip() if translated else None), (romanized.strip() if romanized else None)
    except Exception as e:
        print(f"번역 및 로마자 변환 실패: {e}")
        return None, None

def _try_yfinance_search(search_term, market_opt, original_query):
    """주어진 검색어로 yfinance Search를 수행하고 티커를 반환합니다. 실패 시 None."""
    try:
        s = yf.Search(search_term, max_results=10)
        quotes = s.quotes if hasattr(s, 'quotes') else []
        if not quotes:
            return None
        best = filter_quote_by_market(quotes, market_opt)
        if best:
            symbol = best.get('symbol')
            name = best.get('shortname') or best.get('longname', '')
            exch = best.get('exchDisp') or best.get('exchange', '')
            print(f"[검색 성공] '{original_query}' → {symbol} ({name}) @ {exch}  (검색어: '{search_term}')")
            return symbol
    except Exception as e:
        print(f"[yfinance 검색 오류] '{search_term}': {e}")
    return None

def search_ticker_by_name(query, market_opt="all"):
    """
    한글 또는 영문 자산 이름을 입력받아 티커를 찾습니다.
    
    검색 전략 (순서대로 시도):
    1. 순수 티커 판별 → 즉시 반환
    2. 영문 검색어면 yfinance 직접 검색
    3. 한글인 경우:
       (a) 구글 번역 결과 및 로마자 발음 표기 조합으로 검색
       (b) 핵심 단어 조합 및 단어 변형으로 재시도
    실패 시 None 반환
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return None

    # 1. 영문/숫자/기호로만 구성되어 있고 공백 없으면 티커로 간주 (즉시 반환)
    is_pure_ticker = (
        all(c.isalnum() or c in ['-', '.', '=', ':'] for c in cleaned_query) 
        and cleaned_query.isascii()
    )
    if is_pure_ticker:
        return cleaned_query.upper()

    # 2. 영문 검색어이면 yfinance로 바로 검색
    has_korean = any('\uAC00' <= c <= '\uD7A3' or '\u3131' <= c <= '\u314E' for c in cleaned_query)
    if not has_korean:
        result = _try_yfinance_search(cleaned_query, market_opt, cleaned_query)
        if result:
            return result
        # 공백이 있는 영문이면 첫 단어만으로도 재시도
        words = cleaned_query.split()
        if len(words) > 1:
            result = _try_yfinance_search(words[0], market_opt, cleaned_query)
            if result:
                return result
        print(f"[검색 실패] '{cleaned_query}'에 해당하는 자산을 찾지 못했습니다.")
        return None

    # 3. 한글인 경우: 구글 번역 및 로마자 발음 표기 조합으로 시도
    translated, romanized = translate_and_romanize(cleaned_query)
    if not translated:
        print(f"[번역 실패] '{cleaned_query}' 번역에 실패하여 검색을 중단합니다.")
        return None

    print(f"[번역] '{cleaned_query}' → 번역: '{translated}', 음역: '{romanized}'")

    stop_words = {'inc', 'inc.', 'corp', 'corp.', 'ltd', 'ltd.', 'co', 'co.', 'llc', 'group', 'the'}
    
    candidates = []
    
    # 후보 1: 번역본 (예: "cacao" 또는 "Samsung Electronics")
    if translated:
        candidates.append(translated)
        
    # 후보 2: 로마자 발음 표기 (예: "kakao" 또는 "samseongjeonja")
    if romanized and romanized.lower() != translated.lower():
        candidates.append(romanized)

    # 후보 3: 핵심 단어 조합
    for cand in [translated, romanized]:
        if cand:
            words = cand.split()
            core_words = [w for w in words if w.lower() not in stop_words]
            core_query = ' '.join(core_words)
            if core_query and core_query != cand and core_query not in candidates:
                candidates.append(core_query)
            if len(words) >= 2:
                w1 = words[0]
                w2 = ' '.join(words[:2])
                if w1 not in candidates:
                    candidates.append(w1)
                if w2 not in candidates:
                    candidates.append(w2)

    for candidate in candidates:
        result = _try_yfinance_search(candidate, market_opt, cleaned_query)
        if result:
            return result

    print(f"[검색 실패] '{cleaned_query}' (번역: '{translated}', 음역: '{romanized}')에 해당하는 자산을 찾지 못했습니다.")
    return None
