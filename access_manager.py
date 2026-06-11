# -*- coding: utf-8 -*-
"""
access_manager.py — FiboAnalyzer 접근 제어 모듈
================================================
승인된 사용자만 앱을 사용할 수 있도록 합니다.

[상태 구분]
  - approved : 승인된 사용자 토큰 목록 (list of str)
  - pending  : 승인 대기 신청 목록
               [{"token": str, "name": str, "reason": str, "requested_at": str}, ...]
  - denied   : 거부된 사용자 토큰 목록 (list of str)

[관리자 비밀번호]
  - .env 파일의 ADMIN_PASSWORD 값을 우선 사용
  - 없으면 코드 내 DEFAULT_ADMIN_HASH(SHA-256) 사용
  - 앱 내 "개발자 옵션"에서 언제든지 변경 가능
    (변경 시 .env 파일의 ADMIN_PASSWORD 항목을 덮어씀)
"""

import json
import os
import hashlib
import datetime
from typing import Literal

# ──────────────────────────────────────────────────────────────────────────────
# 경로 설정
# ──────────────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCESS_DB_FILE = os.path.join(_BASE_DIR, "access_control.json")
ENV_FILE = os.path.join(_BASE_DIR, ".env")

# 기본 관리자 비밀번호 해시 (seco4265!@#)
DEFAULT_ADMIN_HASH = hashlib.sha256("seco4265!@#".encode("utf-8")).hexdigest()

# ──────────────────────────────────────────────────────────────────────────────
# 내부 상태 (Singleton)
# ──────────────────────────────────────────────────────────────────────────────
_DB_CACHE: dict | None = None


def _empty_db() -> dict:
    return {"approved": [], "pending": [], "denied": []}


def load_access_db(force_reload: bool = False) -> dict:
    """access_control.json 을 로드합니다. 없으면 빈 DB를 생성합니다."""
    global _DB_CACHE
    if _DB_CACHE is not None and not force_reload:
        return _DB_CACHE
    if os.path.exists(ACCESS_DB_FILE):
        try:
            with open(ACCESS_DB_FILE, "r", encoding="utf-8") as f:
                _DB_CACHE = json.load(f)
                # 키 누락 보완
                for key in ("approved", "pending", "denied"):
                    if key not in _DB_CACHE:
                        _DB_CACHE[key] = []
                return _DB_CACHE
        except Exception as e:
            print(f"[AccessManager] DB 로드 실패: {e}")
    _DB_CACHE = _empty_db()
    save_access_db(_DB_CACHE)
    return _DB_CACHE


def save_access_db(db: dict) -> None:
    """access_control.json 에 DB를 저장합니다."""
    global _DB_CACHE
    _DB_CACHE = db
    try:
        with open(ACCESS_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[AccessManager] DB 저장 실패: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# 접근 상태 확인
# ──────────────────────────────────────────────────────────────────────────────
AccessStatus = Literal["approved", "pending", "denied", "unknown"]


def check_access(token: str) -> AccessStatus:
    """
    토큰의 접근 상태를 반환합니다.
      - "approved" : 승인됨
      - "pending"  : 승인 대기 중
      - "denied"   : 거부됨
      - "unknown"  : 처음 접속 (신청 안 함)
    """
    if not token:
        return "unknown"
    db = load_access_db(force_reload=True)
    if token in db.get("approved", []):
        return "approved"
    if token in db.get("denied", []):
        return "denied"
    for entry in db.get("pending", []):
        if isinstance(entry, dict) and entry.get("token") == token:
            return "pending"
    return "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# 신청 등록
# ──────────────────────────────────────────────────────────────────────────────
def add_pending(token: str, name: str, reason: str) -> bool:
    """신규 접속 신청을 대기 목록에 추가합니다. 이미 등록된 토큰이면 False 반환."""
    db = load_access_db(force_reload=True)
    # 이미 존재하는 토큰인지 확인
    if token in db.get("approved", []):
        return False
    if token in db.get("denied", []):
        return False
    for entry in db.get("pending", []):
        if isinstance(entry, dict) and entry.get("token") == token:
            return False  # 이미 신청됨

    entry = {
        "token": token,
        "name": name.strip(),
        "reason": reason.strip(),
        "requested_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    db["pending"].append(entry)
    save_access_db(db)
    return True


# ──────────────────────────────────────────────────────────────────────────────
# 관리자 승인 / 거부
# ──────────────────────────────────────────────────────────────────────────────
def approve_user(token: str) -> bool:
    """pending 목록의 토큰을 approved 로 이동합니다."""
    db = load_access_db(force_reload=True)
    new_pending = []
    found = False
    for entry in db.get("pending", []):
        if isinstance(entry, dict) and entry.get("token") == token:
            found = True
        else:
            new_pending.append(entry)
    if not found:
        return False
    db["pending"] = new_pending
    if token not in db["approved"]:
        db["approved"].append(token)
    save_access_db(db)
    return True


def deny_user(token: str) -> bool:
    """pending 목록의 토큰을 denied 로 이동합니다."""
    db = load_access_db(force_reload=True)
    new_pending = []
    found = False
    for entry in db.get("pending", []):
        if isinstance(entry, dict) and entry.get("token") == token:
            found = True
        else:
            new_pending.append(entry)
    if not found:
        return False
    db["pending"] = new_pending
    if token not in db["denied"]:
        db["denied"].append(token)
    save_access_db(db)
    return True


def revoke_user(token: str) -> bool:
    """승인된 사용자를 approved 목록에서 제거합니다 (접근 박탈)."""
    db = load_access_db(force_reload=True)
    if token not in db.get("approved", []):
        return False
    db["approved"] = [t for t in db["approved"] if t != token]
    save_access_db(db)
    return True


def get_pending_list() -> list:
    """승인 대기 신청 목록을 반환합니다."""
    db = load_access_db(force_reload=True)
    return db.get("pending", [])


def get_approved_list() -> list:
    """승인된 토큰 목록을 반환합니다."""
    db = load_access_db(force_reload=True)
    return db.get("approved", [])


# ──────────────────────────────────────────────────────────────────────────────
# 관리자 비밀번호 관리
# ──────────────────────────────────────────────────────────────────────────────
def _read_env() -> dict:
    """현재 .env 파일을 파싱하여 dict로 반환합니다."""
    env_dict = {}
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env_dict[k.strip()] = v.strip()
        except Exception:
            pass
    return env_dict


def _write_env(env_dict: dict) -> None:
    """dict를 .env 파일로 저장합니다. 기존 파일이 있으면 병합합니다."""
    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            for k, v in env_dict.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        print(f"[AccessManager] .env 저장 실패: {e}")


def get_admin_hash() -> str:
    """
    현재 유효한 관리자 비밀번호의 SHA-256 해시를 반환합니다.
    .env 파일의 ADMIN_PASSWORD_HASH를 우선 사용합니다.
    """
    env = _read_env()
    stored_hash = env.get("ADMIN_PASSWORD_HASH", "").strip()
    if stored_hash:
        return stored_hash
    return DEFAULT_ADMIN_HASH


def verify_admin_password(password: str) -> bool:
    """입력된 비밀번호가 관리자 비밀번호와 일치하는지 확인합니다."""
    input_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return input_hash == get_admin_hash()


def change_admin_password(old_password: str, new_password: str) -> tuple[bool, str]:
    """
    관리자 비밀번호를 변경합니다.
    Returns: (성공 여부, 메시지)
    """
    if not verify_admin_password(old_password):
        return False, "현재 비밀번호가 올바르지 않습니다."
    if len(new_password) < 6:
        return False, "새 비밀번호는 최소 6자 이상이어야 합니다."
    new_hash = hashlib.sha256(new_password.encode("utf-8")).hexdigest()
    env = _read_env()
    env["ADMIN_PASSWORD_HASH"] = new_hash
    _write_env(env)
    return True, "✅ 관리자 비밀번호가 성공적으로 변경되었습니다."
