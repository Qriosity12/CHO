# 启动前端开发服务器
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CHO细胞培养优化系统 - 前端服务器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$scriptPath\frontend"

# 检查 node_modules
if (-not (Test-Path "node_modules")) {
    Write-Host "首次运行，安装依赖..." -ForegroundColor Yellow
    npm install
} else {
    Write-Host "依赖已安装" -ForegroundColor Green
}

# 启动开发服务器
Write-Host ""
Write-Host "启动前端服务器..." -ForegroundColor Green
Write-Host "前端地址: http://localhost:5173" -ForegroundColor Cyan
Write-Host "开发代理默认转发到: http://localhost:8000" -ForegroundColor DarkCyan
Write-Host "如需修改，可先设置环境变量 VITE_DEV_API_PROXY_TARGET" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "按 Ctrl+C 停止服务器" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

npm run dev

