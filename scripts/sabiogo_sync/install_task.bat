@echo off
setlocal EnableExtensions

set "TASK_NAME=App360 SabioGo Sync"
set "APP_DIR=C:\SabioGoSync"
set "RUNNER=%APP_DIR%\run_sync.bat"
set "RUN_AS=%COMPUTERNAME%\Administrador"
set "SECURE_SCRIPT=%APP_DIR%\secure_folder.ps1"

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Abrir Simbolo del sistema como administrador.
    exit /b 1
)

if not exist "%RUNNER%" (
    echo ERROR: No existe %RUNNER%
    echo Copiar primero los archivos aprobados a %APP_DIR%.
    exit /b 1
)

if not exist "%SECURE_SCRIPT%" (
    echo ERROR: No existe %SECURE_SCRIPT%
    exit /b 1
)

net user "Administrador" >nul 2>&1
if errorlevel 1 (
    echo ERROR: No existe la cuenta local Administrador.
    exit /b 1
)

for /f "delims=" %%Z in ('tzutil /g') do set "CURRENT_TZ=%%Z"
if /I not "%CURRENT_TZ%"=="Argentina Standard Time" (
    echo ERROR: Zona horaria actual: %CURRENT_TZ%
    echo La tarea requiere Argentina Standard Time para calcular ayer correctamente.
    echo Ejecutar: tzutil /s "Argentina Standard Time"
    echo Luego volver a ejecutar install_task.bat.
    exit /b 1
)

powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%SECURE_SCRIPT%" -Path "%APP_DIR%"
if errorlevel 1 (
    echo ERROR: No se pudo proteger o verificar %APP_DIR%.
    exit /b 1
)

echo Se creara o actualizara la tarea "%TASK_NAME%".
echo Horario: todos los dias a las 02:00.
echo Cuenta: %RUN_AS%.
echo Zona horaria: %CURRENT_TZ%.
echo Acceso a carpeta: Administrador y SYSTEM.
echo SchTasks solicitara la contrasena de la cuenta. No se mostrara en pantalla.
echo.

schtasks /Create /TN "%TASK_NAME%" /TR "%RUNNER%" /SC DAILY /ST 02:00 /RU "%RUN_AS%" /RP * /RL HIGHEST /F
if errorlevel 1 (
    echo.
    echo ERROR: No se pudo crear la tarea programada.
    exit /b 1
)

powershell.exe -NoProfile -NonInteractive -Command "$task = Get-ScheduledTask -TaskName '%TASK_NAME%' -ErrorAction Stop; if ($task.Principal.LogonType -ne 'Password') { throw ('Modo de inicio invalido: ' + $task.Principal.LogonType) }"
if errorlevel 1 (
    echo ERROR: La tarea no quedo configurada para ejecutarse sin sesion.
    exit /b 1
)

echo.
echo [OK] Tarea programada creada. No se ejecuto manualmente.
echo.
schtasks /Query /TN "%TASK_NAME%" /V /FO LIST

exit /b 0