@echo off
chcp 65001 >nul
echo ========================================
echo CHO细胞培养优化系统 - 快速启动
echo ========================================
echo.

echo [1/2] 启动后端服务器...
start "后端服务器" cmd /k "cd /d %~dp0 && python app.py"
timeout /t 3 /nobreak >nul

echo [2/2] 启动前端服务器...
start "前端服务器" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo 系统启动完成！
echo ========================================
echo.
echo 前端地址: http://localhost:5173
echo 后端API: http://localhost:8000
echo API文档: http://localhost:8000/docs
echo.
echo 按任意键打开浏览器...
pause >nul

start http://localhost:5173

