# -*- coding: utf-8 -*-
import json
import os

# Styling constants for GUI
BG_DARK = '#121212'
BG_PANEL = '#1E1E1E'
BG_CARD = '#2D2D2D'
TEXT_LIGHT = '#E0E0E0'
TEXT_MUTED = '#A0A0A0'
ACCENT_BLUE = '#2979FF'
ACCENT_GREEN = '#00E676'

FAVORITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favorites.json")

# 기본 즐겨찾기 항목
DEFAULT_FAVORITES = [
    ("BTC", "BTC-USD"),
    ("XRP", "XRP-USD"),
    ("OTLK", "OTLK"),
    ("SMR", "SMR")
]

def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_FAVORITES.copy()

def save_favorites(favs):
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, ensure_ascii=False, indent=4)
    except:
        pass

# API Keys — .env 파일에서 로드 (보안 처리)
# .env 파일이 없을 경우 기존 하드코딩 값을 폴백으로 사용합니다.
try:
    from dotenv import load_dotenv
    import os as _os
    _env_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".env")
    load_dotenv(_env_path)
    GEMINI_API_KEY = _os.getenv("GEMINI_API_KEY", "")
    CRYPTOCOMPARE_API_KEY = _os.getenv("CRYPTOCOMPARE_API_KEY", "")
except ImportError:
    # python-dotenv가 설치되지 않은 경우 기존 값 사용
    GEMINI_API_KEY = ""
    CRYPTOCOMPARE_API_KEY = ""

GEMINI_MODEL = "gemini-2.5-flash"

