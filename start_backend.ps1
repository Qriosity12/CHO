# 启动后端服务器
param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CHO细胞培养优化系统 - 后端服务器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# 检查虚拟环境
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "激活虚拟环境..." -ForegroundColor Green
    & .\venv\Scripts\Activate.ps1
} else {
    Write-Host "警告: 虚拟环境不存在" -ForegroundColor Yellow
}

# 检查依赖
Write-Host "检查依赖..." -ForegroundColor Green
$packages = @("fastapi", "uvicorn", "python-multipart")
foreach ($pkg in $packages) {
    $installed = pip show $pkg 2>$null
    if (-not $installed) {
        Write-Host "安装 $pkg..." -ForegroundColor Yellow
        pip install $pkg
    }
}

# 启动服务器
Write-Host ""
Write-Host "启动后端服务器..." -ForegroundColor Green
Write-Host "服务地址: http://$HostAddress`:$Port" -ForegroundColor Cyan
Write-Host "API文档: http://localhost:$Port/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "按 Ctrl+C 停止服务器" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

python -m uvicorn app:app --host $HostAddress --port $Port

