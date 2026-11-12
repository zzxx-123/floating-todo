@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title 悬浮待办 - 调试启动
echo Starting Floating Todo with a console so startup errors are visible...
echo.
python app.pyw
set "code=%errorlevel%"
echo.
echo Floating Todo exited with code %code%.
echo If it did not start, check %%APPDATA%%\FloatingTodoCard\app.log for details.
pause
