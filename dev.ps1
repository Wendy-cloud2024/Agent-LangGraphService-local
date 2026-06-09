# thesis-agent 开发启动脚本
# 用法: .\dev.ps1          (同时启动前后端)
#       .\dev.ps1 server    (仅后端)
#       .\dev.ps1 frontend  (仅前端)

param([string]$target = "all")

$BackendPort = 8000
$FrontendPort = 5173

function Start-Backend {
    Write-Host "`n🚀 启动 FastAPI 后端 (http://localhost:$BackendPort)" -ForegroundColor Green
    Write-Host "   API文档: http://localhost:$BackendPort/docs`n" -ForegroundColor Gray
    py -m src.server.run_server
}

function Start-Frontend {
    Write-Host "`n🚀 启动 Vue 前端 (http://localhost:$FrontendPort)`n" -ForegroundColor Green
    Set-Location frontend
    npm run dev
    Set-Location ..
}

switch ($target) {
    "server"   { Start-Backend }
    "frontend" { Start-Frontend }
    default {
        Write-Host "`n🛍️  电商智能客服 Agent - 开发环境" -ForegroundColor Cyan
        Write-Host "   后端: http://localhost:$BackendPort (API: http://localhost:$BackendPort/docs)" -ForegroundColor Gray
        Write-Host "   前端: http://localhost:$FrontendPort`n" -ForegroundColor Gray

        # 后台启动后端
        $job = Start-Job -ScriptBlock {
            Set-Location $using:PWD
            py -m src.server.run_server 2>&1
        }

        # 等待后端启动
        Start-Sleep -Seconds 3

        # 前台启动前端 (Ctrl+C 同时终止后端)
        try {
            Set-Location frontend
            npm run dev
        } finally {
            Set-Location ..
            Stop-Job $job -ErrorAction SilentlyContinue
            Remove-Job $job -ErrorAction SilentlyContinue
            Write-Host "`n✅ 开发环境已停止" -ForegroundColor Yellow
        }
    }
}
