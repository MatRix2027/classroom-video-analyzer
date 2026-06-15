@echo off
chcp 65001 >nul 2>&1
title 火花课堂视频分析 - 启动脚本

echo ============================================
echo   火花课堂视频分析 - 一键启动
echo ============================================
echo.

:: 项目根目录
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

:: Python 和 pip 路径
set "PYTHON=C:\Users\bobbe\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
set "PIP=C:\Users\bobbe\.workbuddy\binaries\python\envs\default\Scripts\pip.exe"

:: Node 和 npm 路径
set "NPM_DIR=C:\Users\bobbe\.workbuddy\binaries\node\versions\22.22.2"

echo [1/4] 安装后端 Python 依赖...
"%PIP%" install fastapi "uvicorn[standard]" python-multipart pyyaml loguru --quiet 2>nul
if errorlevel 1 (
    echo [警告] 部分 Python 依赖安装失败，尝试继续...
)
echo [1/4] 后端依赖安装完成
echo.

echo [2/4] 构建前端...
cd /d "%PROJECT_DIR%web"
set "PATH=%NPM_DIR%;%PATH%"
if not exist "node_modules" (
    echo   正在安装 npm 依赖...
    call npm install --registry=https://registry.npmmirror.com
    if errorlevel 1 (
        echo [错误] npm install 失败
        pause
        exit /b 1
    )
)
echo   正在构建前端...
call npm run build
if errorlevel 1 (
    echo [错误] 前端构建失败
    pause
    exit /b 1
)
echo [2/4] 前端构建完成
echo.

cd /d "%PROJECT_DIR%"

echo [3/4] 启动后端服务...
echo   服务地址：http://localhost:8000
echo   API 文档：http://localhost:8000/docs
echo.

:: 设置 PYTHONPATH 包含 src 目录
set "PYTHONPATH=%PROJECT_DIR%src"

:: 先启动 uvicorn 后台进程
start /b "" "%PYTHON%" -m uvicorn classroom_analyzer.server.app:app --host 0.0.0.0 --port 8000

:: 等待服务启动
echo   等待服务启动...
timeout /t 3 /nobreak >nul

echo [4/4] 打开浏览器...
start http://localhost:8000

echo.
echo ============================================
echo   服务已启动！
echo   关闭此窗口可停止服务
echo ============================================
echo.

:: 保持窗口打开，等待用户按键退出
pause
