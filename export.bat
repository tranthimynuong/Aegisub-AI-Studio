@echo off
chcp 65001 > nul
echo =======================================================
echo          TOOL XUẤT VIDEO GHÉP PHỤ ĐỀ TỰ ĐỘNG
echo =======================================================
echo.

cd /d "%~dp0"

if "%~1"=="" (
    python export_video.py
) else (
    python export_video.py "%~1"
)

echo.
echo Hoàn tất. Nhấn phím bất kỳ để thoát...
pause > nul
