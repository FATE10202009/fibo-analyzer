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

# 기본 관리자 비밀번호 해시 (admin1234)

DEFAULT_ADMIN_HASH = hashlib.sha256("admin1234".encode("utf-8")).hexdigest()

# ──────────────────────────────────────────────────────────────────────────────

# 내부 상태 (Singleton)

# ──────────────────────────────────────────────────────────────────────────────

_DB_CACHE: dict | None = None

def _empty_db() -> dict:

    return {"approved": [], "pending": [], "denied": []}

import re

def _is_sha256(s: str) -> bool:
    return len(s) == 64 and bool(re.match(r"^[0-9a-fA-F]{64}$", s))

def _merge_secrets_users(db: dict) -> None:
    """Streamlit secrets에 등록된 유저 정보를 DB 캐시에 병합합니다."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "users" in st.secrets:
            secrets_users = st.secrets["users"]
            if "users" not in db:
                db["users"] = {}
            for uid, info in secrets_users.items():
                uid = uid.strip()
                if not uid:
                    continue
                # 이미 로컬 DB에 등록되어 있으면 덮어쓰지 않음
                if uid in db["users"]:
                    continue
                
                pw_hash = ""
                name = uid
                token = ""
                
                if isinstance(info, str):
                    info_str = info.strip()
                    if _is_sha256(info_str):
                        pw_hash = info_str
                    else:
                        pw_hash = hashlib.sha256(info_str.encode("utf-8")).hexdigest()
                elif isinstance(info, dict):
                    pw_str = str(info.get("password", "")).strip()
                    hash_val = str(info.get("password_hash", "")).strip()
                    if hash_val and _is_sha256(hash_val):
                        pw_hash = hash_val
                    elif pw_str:
                        if _is_sha256(pw_str):
                            pw_hash = pw_str
                        else:
                            pw_hash = hashlib.sha256(pw_str.encode("utf-8")).hexdigest()
                    name = info.get("name", uid)
                    token = info.get("token", "")
                
                db["users"][uid] = {
                    "password_hash": pw_hash,
                    "token": token,
                    "name": name,
                    "created_at": "Streamlit Secrets"
                }
    except Exception as e:
        pass

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
                _merge_secrets_users(_DB_CACHE)
                return _DB_CACHE
        except Exception as e:
            print(f"[AccessManager] DB 로드 실패: {e}")

    _DB_CACHE = _empty_db()
    _merge_secrets_users(_DB_CACHE)
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

def add_pending(token: str, name: str, reason: str,

                user_id: str = "", password: str = "") -> bool:

    """

    신규 접속 신청을 대기 목록에 추가합니다.

    - user_id  : 사용할 아이디 (입력 시 비밀번호와 함께 저장)

    - password : 비밀번호 (평문; 내부에서 해시 후 저장)

    이미 등록된 토큰 또는 아이디면 False 반환.

    """

    db = load_access_db(force_reload=True)

    # 이미 존재하는 토큰인지 확인

    if token in db.get("approved", []):

        return False

    if token in db.get("denied", []):

        return False

    for entry in db.get("pending", []):

        if isinstance(entry, dict) and entry.get("token") == token:

            return False  # 이미 신청됨

    # 아이디 중복 확인 (accounts + pending 모두)

    uid = user_id.strip()

    if uid:

        if uid in db.get("users", {}):

            return False  # 아이디 이미 사용 중

        for e in db.get("pending", []):

            if isinstance(e, dict) and e.get("user_id") == uid:

                return False  # 아이디 신청 중

    entry = {

        "token": token,

        "name": name.strip(),

        "reason": reason.strip(),

        "requested_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    }

    if uid and password:

        entry["user_id"] = uid

        entry["password_hash"] = _hash_password(password)

    db["pending"].append(entry)

    save_access_db(db)

    return True

# ──────────────────────────────────────────────────────────────────────────────

# 관리자 승인 / 거부

# ──────────────────────────────────────────────────────────────────────────────

def approve_user(token: str) -> bool:
    """
    pending 목록의 토큰을 approved 로 이동하고,
    pending 항목에 user_id가 있으면 계정도 자동 생성합니다.
    """
    db = load_access_db(force_reload=True)
    new_pending = []
    approved_entry = None
    for entry in db.get("pending", []):
        if isinstance(entry, dict) and entry.get("token") == token:
            approved_entry = entry
        else:
            new_pending.append(entry)
    if approved_entry is None:
        return False
    db["pending"] = new_pending
    if token not in db["approved"]:
        db["approved"].append(token)

    # 아이디가 신청 데이터에 있으면 계정 자동 생성 (비밀번호 해시가 비어있어도 허용)
    uid = approved_entry.get("user_id", "").strip()
    pw_hash = approved_entry.get("password_hash", "")
    if uid:
        if "users" not in db:
            db["users"] = {}
        if uid not in db["users"]:
            db["users"][uid] = {
                "password_hash": pw_hash,
                "token": token,
                "name": approved_entry.get("name", ""),
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            }

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

    input_hash = hashlib.sha256(password.strip().encode("utf-8")).hexdigest()

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

# ──────────────────────────────────────────────────────────────────────────────

# 🔑 아이디 / 비밀번호 계정 시스템

# ──────────────────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:

    """비밀번호를 SHA-256으로 해시합니다."""

    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def get_user_accounts() -> dict:

    """

    access_control.json 내 'users' 섹션을 반환합니다.

    형식: { "아이디": {"password_hash": str, "token": str, "created_at": str}, ... }

    """

    db = load_access_db(force_reload=True)

    return db.get("users", {})

def create_user_account(user_id: str, password: str, token: str, name: str = "") -> tuple[bool, str]:
    """
    새 사용자 계정을 생성합니다.
    - user_id  : 아이디 (영문/숫자, 2~20자)
    - password : 비밀번호 (선택사항, 없을 시 "" 전달하여 최초 로그인 때 설정)
    - token    : 이 계정에 연결할 접근 토큰
    - name     : 이름 (닉네임)
    Returns: (성공 여부, 메시지)
    """
    user_id = user_id.strip()
    if len(user_id) < 2 or len(user_id) > 20:
        return False, "아이디는 2~20자로 입력해 주세요."
    if password and len(password) < 4:
        return False, "비밀번호는 4자 이상으로 입력해 주세요."

    db = load_access_db(force_reload=True)
    if "users" not in db:
        db["users"] = {}

    if user_id in db["users"]:
        return False, f"'{user_id}' 아이디가 이미 존재합니다."

    db["users"][user_id] = {
        "password_hash": _hash_password(password) if password else "",
        "token": token,
        "name": name,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    # 토큰이 approved에 없으면 추가
    if token not in db.get("approved", []):
        db.setdefault("approved", []).append(token)
        db["pending"] = [e for e in db.get("pending", []) if e.get("token") != token]
        db["denied"] = [t for t in db.get("denied", []) if t != token]

    save_access_db(db)
    return True, f"✅ '{user_id}' 계정이 생성되었습니다."

def login_with_id_password(user_id: str, password: str, current_token: str = "") -> tuple[bool, str, str]:
    """
    아이디 + 비밀번호로 로그인을 시도합니다.
    current_token이 제공되면 계정의 토큰을 현재 브라우저의 토큰으로 동기화합니다.
    Returns: (성공 여부, 메시지, 해당 계정의 token)
    """
    user_id = user_id.strip()
    db = load_access_db(force_reload=True)
    users = db.get("users", {})

    # 1. 이미 승인되어 등록된 계정인 경우
    if user_id in users:
        stored_hash = users[user_id].get("password_hash", "")
        
        # 최초 로그인으로 비밀번호가 미설정된 상태인 경우
        if not stored_hash:
            if not password or len(password) < 4:
                return False, "🔑 최초 접속입니다. 사용할 비밀번호를 4자 이상 입력해 주세요.", ""
            
            # 사용자가 최초 입력한 비밀번호 등록
            users[user_id]["password_hash"] = _hash_password(password)
            stored_hash = users[user_id]["password_hash"]
            is_first_activation = True
        else:
            is_first_activation = False
            if _hash_password(password) != stored_hash:
                return False, "아이디 또는 비밀번호가 올바르지 않습니다.", ""

        # 현재 로그인한 브라우저의 토큰이 있으면 계정의 토큰을 업데이트
        if current_token:
            users[user_id]["token"] = current_token

        token = current_token if current_token else users[user_id].get("token", "")

        # 토큰이 approved에 없으면 자동 추가
        if token and token not in db.get("approved", []):
            db.setdefault("approved", []).append(token)
            db["pending"] = [e for e in db.get("pending", []) if e.get("token") != token]
            db["denied"] = [t for t in db.get("denied", []) if t != token]

        save_access_db(db)
        
        if is_first_activation:
            return True, f"🔑 최초 접속 완료! 비밀번호가 성공적으로 설정되었습니다. 환영합니다!", token
        return True, f"✅ '{user_id}' 님, 환영합니다!", token

    # 2. pending 목록에 가입 요청이 존재하는 경우 (아직 승인 대기 중)
    pending_list = db.get("pending", [])
    is_pending = any(
        isinstance(e, dict) and e.get("user_id") == user_id
        for e in pending_list
    )
    if is_pending:
        return False, "⏳ 아직 승인 대기 중인 아이디입니다. 관리자의 승인을 기다려 주세요.", ""

    # 3. 그 외 아예 존재하지 않는 아이디
    return False, "❌ 존재하지 않는 아이디이거나 승인되지 않았습니다. 신규 신청을 해 주세요.", ""

def change_user_password(user_id: str, old_password: str, new_password: str) -> tuple[bool, str]:

    """사용자 비밀번호를 변경합니다."""

    user_id = user_id.strip()

    db = load_access_db(force_reload=True)

    users = db.get("users", {})

    if user_id not in users:

        return False, "존재하지 않는 아이디입니다."

    if _hash_password(old_password) != users[user_id].get("password_hash", ""):

        return False, "현재 비밀번호가 올바르지 않습니다."

    if len(new_password) < 4:

        return False, "새 비밀번호는 4자 이상이어야 합니다."

    users[user_id]["password_hash"] = _hash_password(new_password)

    db["users"] = users

    save_access_db(db)

    return True, "✅ 비밀번호가 변경되었습니다."

def delete_user_account(user_id: str) -> bool:

    """사용자 계정을 삭제합니다 (연결된 토큰은 유지)."""

    db = load_access_db(force_reload=True)

    users = db.get("users", {})

    if user_id not in users:

        return False

    del users[user_id]

    db["users"] = users

    save_access_db(db)

    return True

def get_user_id_by_token(token: str) -> str:

    """토큰으로 아이디를 역조회합니다. 없으면 빈 문자열 반환."""

    db = load_access_db(force_reload=True)

    for uid, info in db.get("users", {}).items():

        if info.get("token") == token:

            return uid

    return ""

def save_user_settings(user_id: str, settings: dict) -> bool:

    """사용자의 맞춤 설정을 access_control.json에 저장합니다."""

    user_id = user_id.strip()

    db = load_access_db(force_reload=True)

    if "users" not in db or user_id not in db["users"]:

        return False

    

    if "settings" not in db["users"][user_id]:

        db["users"][user_id]["settings"] = {}

        

    db["users"][user_id]["settings"].update(settings)

    save_access_db(db)

    return True

def get_user_settings(user_id: str) -> dict:

    """사용자의 맞춤 설정을 access_control.json에서 불러옵니다."""

    user_id = user_id.strip()

    db = load_access_db(force_reload=True)

    if "users" not in db or user_id not in db["users"]:

        return {}

    return db["users"][user_id].get("settings", {})

