@echo off
chcp 65001 >nul
title 丹智慧眼 - 停止服务

echo ============================================
echo   丹智慧眼 - 停止所有服务
echo ============================================
echo.

:: 按进程「命令行」精确匹配本项目的脚本名，而非端口：
:: 避免 netstat+taskkill 误杀同一端口上无关的进程。
:: wmic 在新版 Windows 上已弃用但仍可用；如不可用会静默跳过，下方给出提示。
set "STOPPED="

:: 停止模型API (model_api.py)
for /f "skip=1 tokens=1" %%a in ('wmic process where "commandline like '%%model_api.py%%'" get processid 2^>nul') do (
    if not "%%a"=="" (
        taskkill /PID %%a /F >nul 2>nul
        if not errorlevel 1 (
            echo [√] 已停止模型API (PID: %%a)
            set "STOPPED=1"
        )
    )
)

:: 停止后端 (backend_main.py)
for /f "skip=1 tokens=1" %%a in ('wmic process where "commandline like '%%backend_main.py%%'" get processid 2^>nul') do (
    if not "%%a"=="" (
        taskkill /PID %%a /F >nul 2>nul
        if not errorlevel 1 (
            echo [√] 已停止后端 (PID: %%a)
            set "STOPPED=1"
        )
    )
)

:: 停止前端 (http.server，端口 5500)
for /f "skip=1 tokens=1" %%a in ('wmic process where "commandline like '%%http.server 5500%%'" get processid 2^>nul') do (
    if not "%%a"=="" (
        taskkill /PID %%a /F >nul 2>nul
        if not errorlevel 1 (
            echo [√] 已停止前端 (PID: %%a)
            set "STOPPED=1"
        )
    )
)

if not defined STOPPED (
    echo [!] 未匹配到本项目的服务进程（服务可能未启动，或 wmic 不可用）。
    echo     如确认服务在运行，请手动执行：netstat -ano ^| findstr ":5000"
)

echo.
echo 所有服务已停止。
pause
