# -*- coding: utf-8 -*-
import requests
import traceback
from config import CRYPTOCOMPARE_API_KEY

def get_clean_symbol(ticker):
    """티커에서 순수 코인 심볼만 추출합니다. (예: BTC-USD -> BTC)"""
    if "-" in ticker:
        return ticker.split("-")[0].upper()
    return ticker.upper()

def fetch_onchain_data(ticker):
    """
    CryptoCompare API를 통해 온체인 데이터를 수집합니다.
    성공 시 데이터 딕셔너리를 반환하고, 실패하거나 키가 없을 경우 에러 메시지가 포함된 딕셔너리를 반환합니다.
    """
    symbol = get_clean_symbol(ticker)
    
    # 1) API 키 체크
    if not CRYPTOCOMPARE_API_KEY:
        return {
            "success": False,
            "error_type": "no_key",
            "message": "🗝️ CryptoCompare API 키가 등록되지 않았습니다.\n\n"
                       "온체인 분석을 이용하려면 [CryptoCompare API](https://min-api.cryptocompare.com)에서 무료 API 키를 발급받아\n"
                       "`config.py` 파일의 `CRYPTOCOMPARE_API_KEY`에 설정해 주세요."
        }

    try:
        # CryptoCompare Blockchain Latest 데이터 요청
        url = "https://min-api.cryptocompare.com/data/blockchain/latest"
        params = {
            "fsym": symbol,
            "api_key": CRYPTOCOMPARE_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=8)
        if response.status_code != 200:
            return {
                "success": False,
                "error_type": "http_error",
                "message": f"❌ API 호출 실패 (HTTP {response.status_code})\n네트워크 연결 상태나 API 제한을 확인해 주세요."
            }

        res_json = response.json()
        if res_json.get("Response") == "Error":
            err_msg = res_json.get("Message", "알 수 없는 API 에러")
            # 코인 심볼 미지원 등의 사유
            return {
                "success": False,
                "error_type": "api_error",
                "message": f"⚠️ CryptoCompare API 응답 오류: {err_msg}\n\n"
                           f"자산 '{symbol}'은 CryptoCompare 온체인 분석이 제공되지 않을 수 있습니다."
            }

        data = res_json.get("Data")
        if not data:
            return {
                "success": False,
                "error_type": "no_data",
                "message": f"⚠️ '{symbol}'에 대한 온체인 데이터가 존재하지 않습니다."
            }

        return {
            "success": True,
            "symbol": symbol,
            "active_addresses": data.get("active_addresses"),
            "large_transaction_count": data.get("large_transaction_count"),
            "transaction_count": data.get("transaction_count"),
            "hashrate": data.get("hashrate"),
            "difficulty": data.get("difficulty"),
            "current_supply": data.get("current_supply"),
            "new_addresses": data.get("new_addresses"),
            "raw_time": data.get("time")
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error_type": "timeout",
            "message": "⏳ CryptoCompare API 요청 시간이 초과되었습니다. 네트워크 연결을 확인하고 다시 시도해 주세요."
        }
    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "error_type": "exception",
            "message": f"❌ 온체인 데이터를 수집하는 도중 예기치 않은 오류가 발생했습니다.\n\n상세 내용: {str(e)}"
        }

def generate_onchain_report_md(ticker):
    """온체인 데이터를 기반으로 해석 리포트 마크다운 텍스트를 작성합니다."""
    res = fetch_onchain_data(ticker)
    
    md = []
    md.append(f"## ⛓️ {ticker} 실시간 온체인 수급 및 네트워크 지표 분석")
    md.append(f"이 분석은 블록체인 원장의 최신 트랜잭션 데이터를 기반으로 수급 강도를 평가합니다.\n")
    
    if not res["success"]:
        md.append(res["message"])
        return "\n".join(md)

    symbol = res["symbol"]
    active_addr = res["active_addresses"]
    large_tx = res["large_transaction_count"]
    total_tx = res["transaction_count"]
    hashrate = res["hashrate"]
    supply = res["current_supply"]
    new_addr = res["new_addresses"]

    md.append(f"### 1) 온체인 핵심 활성 지표 요약 ({symbol})")
    md.append(f"| 지표 항목 | 최근 24시간 수치 | 분석적 의미 |")
    md.append(f"| :--- | :--- | :--- |")
    
    if active_addr is not None:
        md.append(f"| **활성 주소 수 (Active Addresses)** | {active_addr:,.0f} 개 | 네트워크 내 실제 트랜잭션을 전송한 고유 지갑의 총합. 네트워크 활성도 및 시장 참여도를 의미합니다. |")
    if new_addr is not None:
        md.append(f"| **신규 주소 수 (New Addresses)** | {new_addr:,.0f} 개 | 신규 자금 유입 및 시장 관심도 유입 강도. 지표 상승 시 매수 세력 확장 신호입니다. |")
    if large_tx is not None:
        md.append(f"| **대형 거래 건수 (Large Tx Count)** | {large_tx:,.0f} 건 | $100K(약 1.3억 원) 이상 거래 횟수. 기관 및 고래(Whale) 투자자들의 활동량 척도입니다. |")
    if total_tx is not None:
        md.append(f"| **총 트랜잭션 수 (Tx Count)** | {total_tx:,.0f} 건 | 네트워크 내에서 처리된 전체 송금/계약 실행 수입니다. |")
    if hashrate is not None:
        # hashrate 가 보통 EH/s, TH/s 단위일 텐데, 보기 쉽게 포맷팅
        hash_str = f"{hashrate:,.2f}"
        if hashrate > 1e12:
            hash_str = f"{hashrate / 1e12:,.2f} EH/s"
        elif hashrate > 1e9:
            hash_str = f"{hashrate / 1e9:,.2f} PH/s"
        elif hashrate > 1e6:
            hash_str = f"{hashrate / 1e6:,.2f} TH/s"
        md.append(f"| **해시레이트 (Hash Rate)** | {hash_str} | 네트워크 보안성 및 채굴자 참여 강도. 보안 강도 증가로 자산의 근본 가치를 높입니다. |")
    if supply is not None:
        md.append(f"| **현재 유통 공급량** | {supply:,.2f} {symbol} | 현재까지 블록체인상에 발행되어 유통 중인 총 토큰 수량입니다. |")

    md.append("\n---\n")
    md.append("### 2) 온체인 데이터 종합 해석 및 투자 전략 제언\n")
    
    # 간단한 정성적 룰 베이스 해석 추가
    interpretations = []
    
    # 고래 활동성 평가
    if large_tx is not None:
        if large_tx > 15000:
            interpretations.append(f"* **고래 활동성 (매우 높음)**: 최근 24시간 동안 대규모 자금 이체({large_tx:,.0f}건)가 매우 강하게 일어나고 있습니다. 이는 메이저 기관 및 거대 고래의 포지션 진입/청산 과정에서 대형 변동성이 발생하기 전조일 수 있습니다.")
        elif large_tx > 5000:
            interpretations.append(f"* **고래 활동성 (보통/안정)**: 대규모 트랜잭션이 {large_tx:,.0f}건으로 평균 수준을 지키고 있습니다. 급격한 고래의 매도 압박이나 매집 움직임보다는 평이한 분산 거래가 이어지고 있습니다.")
        else:
            interpretations.append(f"* **고래 활동성 (낮음)**: 대형 트랜잭션 건수가 {large_tx:,.0f}건으로 비활성화되어 있습니다. 기관 수급이 공백 상태이며, 당분간 개인 투자자 위주의 저유동성 횡보 장세가 유력합니다.")

    # 네트워크 유저 성장률 평가
    if active_addr is not None and new_addr is not None:
        new_ratio = (new_addr / active_addr) * 100 if active_addr > 0 else 0
        interpretations.append(f"* **신규 유저 참여 강도**: 전체 활성 지갑 대비 신규 지갑 생성 비율이 약 **{new_ratio:.1f}%**입니다. 이 비율이 높을수록 신규 투자 수요(Fomo)가 강하게 유입되어 가격 상승 탄력을 지지하는 긍정적 지표로 간주됩니다.")

    if not interpretations:
        interpretations.append("* 수집된 온체인 지표들이 한정적이어서 상세한 룰 베이스 해석이 제한됩니다. 위의 요약 표를 직접 참고해 주세요.")
        
    md.extend(interpretations)
    md.append("\n*본 온체인 분석은 블록체인 장부 데이터를 직관적으로 연산한 보조 참고서이며, 거래소 내부 수급 상황(Off-chain)에 따라 실제 가격 움직임과 괴리가 생길 수 있습니다.*")
    
    return "\n".join(md)
