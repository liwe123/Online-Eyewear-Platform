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

:: ---------------------------------------------------------------------------
:: 选择 Python 解释器
:: 问题：MediaPipe 等原生库在 Windows 上无法读取「含中文路径」下的模型文件
::       (Python 能看到文件，但 C++ 层按 ANSI 解析失败 -> FileNotFoundError)。
:: 解决：若项目路径含非 ASCII 字符，则在系统盘建一个 ASCII 路径的「目录联接」(junction)
::       指向项目 .venv，用该联接里的 python 启动。模型文件仍在项目 .venv 内，
::       不复制、不污染系统环境，仅作为路径别名。
:: ---------------------------------------------------------------------------
set "VENV_LINK=%SystemDrive%\dzhy_venv"

for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command ^
  "$pd='%PROJECT_DIR%'; $link='%VENV_LINK%'; ^
   $venvDir=Join-Path $pd '.venv'; ^
   $venvPy=Join-Path (Join-Path $pd '.venv') 'Scripts\python.exe'; ^
   if(Test-Path $venvPy){ ^
     if($pd -match '[^\x00-\x7F]'){ ^
       if(Test-Path $link){ Remove-Item $link -Force -ErrorAction SilentlyContinue }; ^
       New-Item -ItemType Junction -Path $link -Target $venvDir -Force | Out-Null; ^
       Join-Path $link 'Scripts\python.exe' ^
     } else { $venvPy } ^
   } else { 'python' }"`) do set "PYTHON=%%i"

if "%PYTHON%"=="" set "PYTHON=python"
echo [√] 使用 Python: %PYTHON%
echo.

:: ---- 启动模型API (端口 8000) ----
echo [1/3] 启动模型API服务 (端口 8000)...
start "丹智慧眼-模型API" cmd /c "cd /d %PROJECT_DIR% && "%PYTHON%" model_api.py"
timeout /t 6 /nobreak >nul

:: ---- 启动后端 (端口 5000) ----
echo [2/3] 启动后端服务 (端口 5000)...
start "丹智慧眼-后端" cmd /c "cd /d %PROJECT_DIR% && "%PYTHON%" backend/backend_main.py"
timeout /t 3 /nobreak >nul

:: ---- 启动前端 (端口 5500) ----
echo [3/3] 启动前端页面 (端口 5500)...
start "丹智慧眼-前端" cmd /c "cd /d %PROJECT_DIR%\frontend && "%PYTHON%" -m http.server 5500"

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
