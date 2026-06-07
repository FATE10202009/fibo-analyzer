# -*- coding: utf-8 -*-
import os
import sys
import tkinter as tk
from tkinter import messagebox

# ────────────────────────────────────────────────────────────
# 1) 작업 디렉토리를 스크립트 파일이 있는 폴더로 고정
#    → 어느 경로에서 실행하더라도 보고서, favorites.json 경로가
#      항상 프로젝트 폴더 기준으로 올바르게 설정됩니다.
# ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# ────────────────────────────────────────────────────────────
# 2) Windows 고해상도(DPI) 모니터 대응
#    → 4K 등 고해상도 모니터에서 글씨가 흐릿하게 나오는 현상을
#      DPI-awareness 설정으로 방지합니다.
# ────────────────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

from ui import FiboAnalyzerApp

if __name__ == "__main__":
    root = tk.Tk()
    
    # ────────────────────────────────────────────────────────
    # 3) 창 최소 크기 설정
    #    → 사이드바와 차트가 겹치거나 사라지는 현상 방지
    # ────────────────────────────────────────────────────────
    root.minsize(900, 600)
    
    # ────────────────────────────────────────────────────────
    # 4) 예기치 않은 예외를 최상위에서 잡아 메시지박스로 표시
    #    → 빈 검은 창이 사라지는 현상 없이 오류 내용을 확인 가능
    # ────────────────────────────────────────────────────────
    def handle_exception(exc_type, exc_value, exc_tb):
        import traceback
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        messagebox.showerror(
            "예기치 않은 오류 발생",
            f"프로그램에서 처리되지 않은 오류가 발생했습니다.\n\n{error_msg}"
        )

    sys.excepthook = handle_exception
    
    app = FiboAnalyzerApp(root)
    root.mainloop()