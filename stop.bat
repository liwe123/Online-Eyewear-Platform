@echo off
chcp 65001 >nul
title 丹智慧眼 - 停止服务

echo ============================================
echo   丹智慧眼 - 停止所有服务
echo ============================================
echo.

:: 停止模型API (端口 8000)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do (
    taskkill /PID %%a /F 2>nul && echo [√] 已停止模型API (PID: %%a)
)

:: 停止后端 (端口 5000)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000"') do (
    taskkill /PID %%a /F 2>nul && echo [√] 已停止后端 (PID: %%a)
)

:: 停止前端 (端口 5500)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5500"') do (
    taskkill /PID %%a /F 2>nul && echo [√] 已停止前端 (PID: %%a)
)

echo.
echo 所有服务已停止。
pause
