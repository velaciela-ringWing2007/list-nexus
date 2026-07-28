@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python仮想環境がありません。
    echo setup.batを先に実行してください。
    pause
    exit /b 1
)

start "" http://127.0.0.1:8501

".venv\Scripts\python.exe" -m streamlit run app.py ^
    --server.address 127.0.0.1 ^
    --server.port 8501 ^
    --server.headless true ^
    --browser.gatherUsageStats false
