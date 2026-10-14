@echo off
chcp 65001 > nul
echo =======================================================
echo          KHỞI ĐỘNG VIDEO SUBBER STUDIO (ALL-IN-ONE)
echo =======================================================
echo.

cd /d "%~dp0"

echo [1/2] Đang kích hoạt máy chủ Studio...
start http://localhost:5000

echo [2/2] Đang chạy backend Python...
python app.py

pause
