param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000,
    [string]$ApiBaseUrl = "",
    [switch]$Rebuild
)

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CHO细胞培养优化系统 - 生产启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "激活虚拟环境..." -ForegroundColor Green
    & .\venv\Scripts\Activate.ps1
}

if ([string]::IsNullOrWhiteSpace($ApiBaseUrl)) {
    $resolvedApiBaseUrl = "http://localhost:$Port"
} else {
    $resolvedApiBaseUrl = $ApiBaseUrl.TrimEnd('/')
}

$shouldBuild = $Rebuild -or -not (Test-Path "frontend\dist\index.html")

if ($shouldBuild) {
    if ($Rebuild) {
        Write-Host "检测到 -Rebuild，重新构建前端..." -ForegroundColor Yellow
    } else {
        Write-Host "未检测到前端构建产物，开始构建..." -ForegroundColor Yellow
    }

    Push-Location frontend
    if (-not (Test-Path "node_modules")) {
        npm install
    }

    Write-Host "前端构建使用 API 地址：$resolvedApiBaseUrl" -ForegroundColor Cyan
    $env:VITE_API_BASE_URL = $resolvedApiBaseUrl
    npm run build
    Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue
    Pop-Location
} else {
    Write-Host "检测到已有前端构建产物，跳过构建。" -ForegroundColor Green
    Write-Host "如需更新前端 API 地址或强制重新打包，请使用 -Rebuild。" -ForegroundColor DarkYellow
    Write-Host "当前生产 API 地址预期为：$resolvedApiBaseUrl" -ForegroundColor Cyan
}

Write-Host "启动生产服务：http://$HostAddress`:$Port" -ForegroundColor Green
python -m uvicorn app:app --host $HostAddress --port $Port

