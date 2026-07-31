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

:: ---- 校验 Python 版本（需 3.x）----
"%PYTHON%" --version >nul 2>nul
if errorlevel 1 (
    echo [X] 无法运行 Python 解释器: %PYTHON%
    echo     请先安装 Python 3 并确保其可用，或创建 .venv 虚拟环境。
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PYTHON% --version 2^>^&1') do set "PYVER=%%v"
echo %PYVER% | findstr /r /c:"Python 3\." >nul
if errorlevel 1 (
    echo [X] 需要 Python 3.x，当前为: %PYVER%
    pause
    exit /b 1
)
echo [√] 使用 Python: %PYVER%
echo.

:: ---- 启动模型API (端口 8000) ----
echo [1/3] 启动模型API服务 (端口 8000)...
start "丹智慧眼-模型API" cmd /c "cd /d %PROJECT_DIR% && "%PYTHON%" model_api.py"

:: 等待模型API就绪（轮询 /health，最长 60 秒）
set /a MODEL_TRIES=0
:wait_model
curl -sf http://localhost:8000/health >nul 2>nul
if not errorlevel 1 goto model_ready
set /a MODEL_TRIES+=1
if %MODEL_TRIES% geq 60 (
    echo [X] 模型API 60 秒内未就绪，请检查 http://localhost:8000/health
    goto model_ready
)
timeout /t 1 /nobreak >nul
goto wait_model
:model_ready
echo [√] 模型API已就绪

:: ---- 启动后端 (端口 5000) ----
echo [2/3] 启动后端服务 (端口 5000)...
start "丹智慧眼-后端" cmd /c "cd /d %PROJECT_DIR% && "%PYTHON%" backend/backend_main.py"

:: 等待后端就绪（后端无 /health，轮询 /api/glasses/list，最长 60 秒）
set /a BACKEND_TRIES=0
:wait_backend
curl -sf http://localhost:5000/api/glasses/list >nul 2>nul
if not errorlevel 1 goto backend_ready
set /a BACKEND_TRIES+=1
if %BACKEND_TRIES% geq 60 (
    echo [X] 后端 60 秒内未就绪，请检查 http://localhost:5000
    goto backend_ready
)
timeout /t 1 /nobreak >nul
goto wait_backend
:backend_ready
echo [√] 后端已就绪

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
