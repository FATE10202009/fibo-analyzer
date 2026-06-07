# -*- coding: utf-8 -*-
import json
import traceback
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL

def analyze_news_with_gemini(news_list, ticker, is_usd, api_key=None):
    """
    yfinance 뉴스 데이터를 기반으로 Gemini AI를 통해 시장 영향도를 분석합니다.
    API 키가 없거나 실패하는 경우 None을 반환하여 폴백을 수행하도록 합니다.
    """
    use_key = api_key or GEMINI_API_KEY
    if not use_key:
        print("[AI Analyzer] GEMINI_API_KEY가 설정되지 않아 AI 뉴스 분석을 건너뜁니다.")
        return None

    try:
        # Gemini API 설정
        genai.configure(api_key=use_key)
        
        # 뉴스 내용 정합
        news_contents = []
        for i, item in enumerate(news_list[:5]): # 최대 5개 뉴스 요약
            content = item.get('content', {})
            title = content.get('title', '제목 없음')
            summary = content.get('summary', '요약 정보 없음')
            provider = content.get('provider', {}).get('displayName', '알 수 없음')
            news_contents.append(f"뉴스 {i+1}:\n- 제목: {title}\n- 요약: {summary}\n- 제공처: {provider}")

        all_news_text = "\n\n".join(news_contents)
        if not all_news_text:
            print("[AI Analyzer] 분석할 뉴스 내용이 없습니다.")
            return None

        # 시스템 지침 및 프롬프트 작성
        prompt = f"""
당신은 금융 시장 분석가이자 인공지능 트레이더입니다.
아래 제공된 자산 '{ticker}'에 관한 최근 뉴스들을 바탕으로 종합적인 시장 영향을 분석해 주세요.

[분석 대상 자산]
- 티커: {ticker}
- 통화 유형: {'미국 달러(USD)' if is_usd else '원화(KRW)'}

[최근 뉴스 정보]
{all_news_text}

[요구사항]
위 뉴스를 면밀히 분석하여 다음 형식의 JSON 객체로만 응답해 주세요. 다른 인사말이나 설명 텍스트 없이 순수한 JSON만 반환해야 합니다.

JSON 형식:
{{
  "sentiment": "긍정" | "중립" | "부정",
  "sentiment_score": -100에서 100 사이의 정수 (예: 호재가 많으면 +80, 악재가 많으면 -60),
  "short_term": "1~4주 이내의 단기 영향에 대한 분석 및 가격 전망 (1~2문장의 한글)",
  "mid_term": "3~6개월 이내의 중장기 영향에 대한 분석 및 전망 (1~2문장의 한글)",
  "risks": [
    "뉴스 분석을 통해 파악된 핵심 리스크 요인 1 (한글)",
    "뉴스 분석을 통해 파악된 핵심 리스크 요인 2 (한글)"
  ],
  "catalysts": [
    "뉴스 분석을 통해 파악된 핵심 호재/촉매 요인 1 (한글)",
    "뉴스 분석을 통해 파악된 핵심 호재/촉매 요인 2 (한글)"
  ]
}}
"""

        # Gemini 모델 호출
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # JSON 출력을 명시적으로 요청하기 위한 구성
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        result_text = response.text.strip()
        parsed_json = json.loads(result_text)
        
        # 필수 키 존재성 검증 및 기본값 보완
        required_keys = ['sentiment', 'sentiment_score', 'short_term', 'mid_term', 'risks', 'catalysts']
        for key in required_keys:
            if key not in parsed_json:
                raise ValueError(f"Gemini 응답 JSON에 필수 키 '{key}'가 누락되었습니다.")
                
        return parsed_json

    except Exception as e:
        print(f"[AI Analyzer] Gemini API 분석 실패: {e}")
        traceback.print_exc()
        return None

def ask_gemini_qna(ticker, report_text, question, chat_history=None, api_key=None):
    """
    사용자가 화면의 리포트와 차트를 보며 입력한 질문에 대해,
    이전 대화 맥락과 현재 리포트 내용을 Context로 제공하여 Gemini API의 응답을 받아옵니다.
    """
    use_key = api_key or GEMINI_API_KEY
    if not use_key:
        return "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 API 키를 등록하거나 웹 화면에서 입력해 주세요."

    try:
        # Gemini API 설정
        genai.configure(api_key=use_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # 이전 대화 내용 빌드 (최근 10개 메시지)
        history_text = ""
        if chat_history:
            history_text = "\n[이전 대화 기록]\n"
            for role, text in chat_history[-10:]:
                history_text += f"- {role}: {text}\n"

        # 프롬프트 작성
        prompt = f"""
당신은 FiboAnalyzer 프로그램에 탑재된 스마트 AI 금융 비서입니다.
사용자는 현재 화면의 피보나치 차트와 보조지표 분석 리포트를 보면서 질문하고 있습니다.

[분석 대상 자산]
- 티커: {ticker}

[현재 분석 보고서 내용]
{report_text}
{history_text}
[사용자 질문]
{question}

위 분석 정보를 적극 활용하여 사용자의 질문에 금융 전문가의 관점에서 구체적이고 신뢰성 높은 답변을 한글로 제공해 주세요.
- 보고서에 나오는 가격 수치(피보나치 지지선, RSI, MACD 등)를 직접 인용하여 답변해 주면 신뢰도가 높습니다.
- 답변은 친절한 어조로 하되, 줄바꿈과 글머리 기호(마크다운 스타일) 등을 사용하여 가독성 있게 표현해 주세요.
- 투자 책임에 대한 고지(본 답변은 참고용이며 최종 투자 결정은 본인의 판단하에 행해져야 한다는 안내)를 답변 끝에 자연스럽게 1줄 추가해 주세요.
"""
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        print(f"[AI Analyzer] Gemini Q&A 호출 실패: {e}")
        traceback.print_exc()
        return f"Gemini API 호출 중 오류가 발생했습니다: {str(e)}"

