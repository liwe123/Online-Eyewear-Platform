@echo off
chcp 65001 >nul
title 丹智慧眼 - 服务启动中...

echo ============================================
echo   丹智慧眼 - 一键启动
echo   (请确保已安装 Python 依赖: pip install -r requirements.txt)
echo ============================================
echo.

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

:: 检查虚拟环境
if exist ".venv\Scripts\activate.bat" (
    echo [√] 检测到虚拟环境，正在激活...
    call .venv\Scripts\activate.bat
) else (
    echo [!] 未检测到虚拟环境，使用系统 Python
)

echo.

:: ---- 启动模型API (端口 8000) ----
echo [1/3] 启动模型API服务 (端口 8000)...
start "丹智慧眼-模型API" cmd /c "cd /d %PROJECT_DIR% && python model_api.py"
timeout /t 5 /nobreak >nul

:: ---- 启动后端 (端口 5000) ----
echo [2/3] 启动后端服务 (端口 5000)...
start "丹智慧眼-后端" cmd /c "cd /d %PROJECT_DIR% && python backend/backend_main.py"
timeout /t 3 /nobreak >nul

:: ---- 启动前端 (端口 5500) ----
echo [3/3] 启动前端页面 (端口 5500)...
start "丹智慧眼-前端" cmd /c "cd /d %PROJECT_DIR%\frontend && python -m http.server 5500"

echo.
echo ============================================
echo   全部服务已启动！
echo   前端:    http://localhost:5500
echo   后端:    http://localhost:5000
echo   模型API: http://localhost:8000/docs
echo ============================================
echo.
echo 关闭本窗口不会停止服务，请手动关闭各个服务窗口。
pause
