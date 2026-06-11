@echo off
title Streamlit App - Coin Analyzer
cd /d "%~dp0"
echo Starting Streamlit app...

:: Run Streamlit in headless mode on port 8501 (does not auto-open default browser)
start /b "" "C:\Users\fate1\AppData\Local\Programs\Python\Python312\python.exe" -m streamlit run streamlit_app.py --server.headless true --server.port 8501

:: Wait 3 seconds for Streamlit server to start up
timeout /t 3 >nul

:: Launch default browser to the app's local URL
start "" "http://localhost:8501"

echo.
echo Streamlit server is running on http://localhost:8501.
echo Close this window to stop the server.
echo.

pause
