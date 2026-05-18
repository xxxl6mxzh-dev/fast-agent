# Fast 新闻 Agent — 注册 Windows 定时任务（每天 9:00）
$taskName = "Fast News Agent"
$action = New-ScheduledTaskAction -Execute "python" -Argument "C:\Users\Lenovo\fast-agent\news-agent.py"
$trigger = New-ScheduledTaskTrigger -Daily -At 09:00
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Fast 管家每日新闻推送" -Force
Write-Host "定时任务已注册：每天 9:00 自动运行新闻推送" -ForegroundColor Green
