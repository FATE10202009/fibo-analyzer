# -*- coding: utf-8 -*-
import os
import time
import subprocess

# 감시할 파일 확장자 목록 (소스코드 및 텍스트 설정)
WATCHED_EXTENSIONS = ('.py', '.txt', '.html', '.css')
# 확장자와 무관하게 항상 감시할 특정 파일 (사용자 계정 DB)
WATCHED_FILES = ('access_control.json',)
# 제외할 폴더나 파일 (가상 거래 내역 json 파일 등이 저장되는 virtual_data와 git 등은 감시 제외)
EXCLUDED_DIRS = ('virtual_data', '.git', '.gemini', '__pycache__', '.idea', '.vscode')

def get_last_modified_time(path):
    max_time = 0
    for root, dirs, files in os.walk(path):
        # 제외 폴더는 아예 탐색하지 않도록 함
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            is_watched_ext = file.endswith(WATCHED_EXTENSIONS) and file != 'auto_push.py'
            is_watched_file = file in WATCHED_FILES
            if is_watched_ext or is_watched_file:
                file_path = os.path.join(root, file)
                try:
                    mtime = os.path.getmtime(file_path)
                    if mtime > max_time:
                        max_time = mtime
                except:
                    pass
    return max_time

def run_cmd(cmd):
    try:
        # 윈도우 환경(CP949/UTF-8) 인코딩 문제를 피하기 위해 shell=True로 실행
        result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        if result.stdout.strip():
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 명령 실행 중 오류 발생: {e.stderr}")
        return False
    except Exception as ex:
        # 인코딩 에러 발생 시 시스템 디폴트로 재시도
        try:
            result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.stdout.strip():
                print(result.stdout)
            return True
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
            return False

def main():
    workspace = os.path.dirname(os.path.abspath(__file__))
    print("==================================================")
    print("🚀 FiboAnalyzer 자동 코드 업로드 감시기가 시작되었습니다.")
    print(f"📁 감시 대상 폴더: {workspace}")
    print("💡 파일(.py, .txt 등)을 수정하고 저장하면 자동으로 깃허브에 업로드됩니다.")
    print("⌨️ 종료하시려면 Ctrl + C 를 누르세요.")
    print("==================================================")
    
    last_mtime = get_last_modified_time(workspace)
    
    while True:
        try:
            time.sleep(2)  # 2초마다 파일 수정 시간 체크
            current_mtime = get_last_modified_time(workspace)
            
            if current_mtime > last_mtime:
                print(f"\n⚡ [{time.strftime('%H:%M:%S')}] 파일 변경 감지! 자동 업로드를 시작합니다...")
                
                # Git 명령어 실행
                print("1. 파일 추가 중 (git add .)...")
                if run_cmd("git add ."):
                    commit_msg = f"Auto-upload: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                    print(f"2. 커밋 작성 중 (git commit -m \"{commit_msg}\")...")
                    if run_cmd(f'git commit -m "{commit_msg}"'):
                        print("3. 깃허브 업로드 중 (git push origin main)...")
                        if run_cmd("git push origin main"):
                            print("🎉 [성공] 자동 업로드가 완료되었습니다!")
                        else:
                            print("❌ [실패] push에 실패했습니다. 네트워크 연결 상태를 확인해 주세요.")
                    else:
                        print("ℹ️ 커밋할 새로운 변경 사항이 없습니다.")
                
                last_mtime = current_mtime
        except KeyboardInterrupt:
            print("\n👋 자동 업로드 감시기를 종료합니다.")
            break
            
if __name__ == "__main__":
    main()
