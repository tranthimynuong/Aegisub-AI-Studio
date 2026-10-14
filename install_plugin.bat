@echo off
chcp 65001 > nul
echo =======================================================
echo     CÀI ĐẶT / CẬP NHẬT AEGISUB AI STUDIO PLUGIN
echo             Tác giả: My Nuong
echo =======================================================
echo.

set "DEST_DIR=%APPDATA%\Aegisub\automation\autoload"

if not exist "%DEST_DIR%" (
    echo Đang tạo thư mục autoload Aegisub: %DEST_DIR%
    mkdir "%DEST_DIR%"
)

echo Đang copy ai_studio.lua vào thư mục autoload...
copy /Y "%~dp0ai_studio.lua" "%DEST_DIR%\ai_studio.lua" > nul

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [THÀNH CÔNG] Plugin đã được cài đặt vào Aegisub!
    echo Bây giờ bạn có thể mở Aegisub và truy cập menu 'Automation -> Aegisub AI Studio'.
) else (
    echo.
    echo [LỖI] Không thể copy plugin. Vui lòng kiểm tra quyền truy cập.
)

echo.
pause
