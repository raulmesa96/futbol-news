# Registra futbol-news en el Programador de tareas de Windows.
#   powershell -ExecutionPolicy Bypass -File install-task.ps1
# Para quitarla:
#   Unregister-ScheduledTask -TaskName "futbol-news" -Confirm:$false

$ErrorActionPreference = "Stop"

$TaskName = "futbol-news"
$Root     = $PSScriptRoot
$Python   = Join-Path $Root ".venv\Scripts\pythonw.exe"   # pythonw = sin consola
$Script   = Join-Path $Root "bot.py"
$Minutes  = 30

if (-not (Test-Path $Python)) {
    throw "No existe $Python. Crea el entorno: python -m venv .venv"
}

$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Root

# Arranca 2 min despues de registrarla y repite indefinidamente.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes)

# StartWhenAvailable recupera las ejecuciones perdidas mientras el PC estaba
# apagado o suspendido, en lugar de esperar al siguiente hueco.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Publica noticias de futbol en el canal Zona Mixta" `
    -Force | Out-Null

Write-Host "Tarea '$TaskName' registrada: cada $Minutes minutos." -ForegroundColor Green
Write-Host "Ver estado:  Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "Lanzar ya:   Start-ScheduledTask -TaskName $TaskName"
