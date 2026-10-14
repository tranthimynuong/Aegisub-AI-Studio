@echo off
chcp 65001 > nul
echo =======================================================
echo          TOOL DỊCH PHỤ ĐỀ VIDEO VỚI HY-MT2 & WHISPER
echo =======================================================
echo.

cd /d "%~dp0"

if "%~1"=="" (
    python auto_sub.py
) else (
    python auto_sub.py "%~1"
)

echo.
echo Hoan tat. Nhan phim bat ky de thoat...
pause > nul
