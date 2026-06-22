@echo off
:: =============================================================================
:: run_sync.bat — Ejecuta la sincronización diaria SabioGo → App360
::
:: Uso normal (Task Scheduler, sin argumentos = sincroniza ayer):
::   run_sync.bat
::
:: Con argumentos:
::   run_sync.bat --fecha 2026-06-01
::   run_sync.bat --desde 2026-05-01 --hasta 2026-05-31
:: =============================================================================

setlocal
set SCRIPT_DIR=%~dp0

:: Activar entorno virtual
if not exist "%SCRIPT_DIR%venv\Scripts\activate.bat" (
    echo ERROR: Entorno virtual no encontrado. Ejecutar setup.bat primero.
    exit /b 1
)
call "%SCRIPT_DIR%venv\Scripts\activate.bat"

:: Ejecutar sync con todos los argumentos pasados a este .bat
python "%SCRIPT_DIR%sync.py" %*

set EXIT_CODE=%errorlevel%
if %EXIT_CODE% neq 0 (
    echo.
    echo ERROR: La sincronizacion fallo con codigo %EXIT_CODE%.
    echo Ver detalles en: %SCRIPT_DIR%sync.log
)

exit /b %EXIT_CODE%
