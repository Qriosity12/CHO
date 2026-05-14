# CHO细胞培养优化系统 - 启动脚本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CHO细胞培养优化系统" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendCommand = "Set-Location '$scriptPath'; if (Test-Path 'venv\Scripts\Activate.ps1') { & '.\venv\Scripts\Activate.ps1' }; python app.py"
$frontendPath = ($scriptPath + '\frontend').Replace("'", "''")
$frontendCommand = "Set-Location '$frontendPath'; npm run dev"

# 启动后端
Write-Host "`n[1/2] 启动后端服务器..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $backendCommand)
Start-Sleep -Seconds 3

# 启动前端
Write-Host "[2/2] 启动前端服务器..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $frontendCommand)
Start-Sleep -Seconds 3

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "系统启动完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "`n前端地址: http://localhost:5173" -ForegroundColor Cyan
Write-Host "后端API: http://localhost:8000" -ForegroundColor Cyan
Write-Host "API文档: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "`n按任意键打开浏览器..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
Start-Process "http://localhost:5173"
