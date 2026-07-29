@echo off
setlocal EnableExtensions

:: =============================================================================
:: rebaseline_2026.bat — Recarga segura de SabioGo para todo 2026
::
:: Ejecuta cada mes por separado. Cada fecha es procesada por sync.py con:
::   - ventas y compras en una sola transaccion API;
::   - replace=true (valor por defecto; NO usar --no-replace);
::   - finalize de facts y objetivos;
::   - reporte de estado operativo.
::
:: Requisitos:
::   - ejecutar en C:\SabioGoSync;
::   - config.ini valido y credenciales ya configuradas;
::   - tarea diaria de Windows pausada durante la recarga;
::   - la fecha final 2026-07-28 corresponde al ultimo dia cerrado.
::
:: Si un mes falla, el script se detiene. Es seguro volver a ejecutar ese mes:
:: replace=true reemplaza cada fecha y origen de forma atomica.
:: =============================================================================

set "SCRIPT_DIR=%~dp0"
set "RUNNER=%SCRIPT_DIR%run_sync.bat"
set "CONFIG=%SCRIPT_DIR%config.ini"
set "PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"
set "LOG_DIR=%SCRIPT_DIR%rebaseline_logs"
set "MASTER_LOG=%LOG_DIR%\rebaseline_2026.log"

if not exist "%RUNNER%" (
    echo ERROR: No existe "%RUNNER%".
    exit /b 1
)

if not exist "%CONFIG%" (
    echo ERROR: No existe "%CONFIG%". Completar config.ini antes de continuar.
    exit /b 1
)

if not exist "%PYTHON%" (
    echo ERROR: No existe el entorno virtual "%PYTHON%".
    echo Ejecutar setup.bat primero.
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if errorlevel 1 (
    echo ERROR: No se pudo crear "%LOG_DIR%".
    exit /b 1
)

echo.
echo ============================================================
echo  REBASELINE SABIOGO - TODO 2026
echo ============================================================
echo.
echo Se procesaran estos rangos, fecha por fecha:
echo   2026-01-01 a 2026-01-31
echo   2026-02-01 a 2026-02-28
echo   2026-03-01 a 2026-03-31
echo   2026-04-01 a 2026-04-30
echo   2026-05-01 a 2026-05-31
echo   2026-06-01 a 2026-06-30
echo   2026-07-01 a 2026-07-28
echo.
echo IMPORTANTE:
echo   1. Pausar temporalmente la tarea "App360 SabioGo Sync".
echo   2. Verificar que config.ini use origenes=CARNES,LACTEOS.
echo   3. No agregar --no-replace.
echo   4. No cerrar esta ventana hasta finalizar o informar un error.
echo.

choice /C YN /N /M "Iniciar la recarga productiva con replace=true? [Y/N] "
if errorlevel 2 (
    echo Recarga cancelada por el usuario.
    exit /b 2
)

>>"%MASTER_LOG%" echo.
>>"%MASTER_LOG%" echo ============================================================
>>"%MASTER_LOG%" echo Inicio rebaseline 2026
>>"%MASTER_LOG%" echo ============================================================

call :run_month "2026-01-01" "2026-01-31" "ENERO"
if errorlevel 1 exit /b %errorlevel%

call :run_month "2026-02-01" "2026-02-28" "FEBRERO"
if errorlevel 1 exit /b %errorlevel%

call :run_month "2026-03-01" "2026-03-31" "MARZO"
if errorlevel 1 exit /b %errorlevel%

call :run_month "2026-04-01" "2026-04-30" "ABRIL"
if errorlevel 1 exit /b %errorlevel%

call :run_month "2026-05-01" "2026-05-31" "MAYO"
if errorlevel 1 exit /b %errorlevel%

call :run_month "2026-06-01" "2026-06-30" "JUNIO"
if errorlevel 1 exit /b %errorlevel%

call :run_month "2026-07-01" "2026-07-28" "JULIO"
if errorlevel 1 exit /b %errorlevel%

>>"%MASTER_LOG%" echo Rebaseline 2026 finalizado correctamente.
echo.
echo ============================================================
echo  REBASELINE 2026 FINALIZADO CORRECTAMENTE
echo ============================================================
echo Log: "%MASTER_LOG%"
echo.
echo Siguiente paso: ejecutar validate_rebaseline_2026.sql contra PostgreSQL.
exit /b 0

:run_month
set "FROM_DATE=%~1"
set "TO_DATE=%~2"
set "MONTH_NAME=%~3"

echo.
echo ------------------------------------------------------------
echo Procesando %MONTH_NAME%: %FROM_DATE% a %TO_DATE%
echo ------------------------------------------------------------
>>"%MASTER_LOG%" echo.
>>"%MASTER_LOG%" echo Inicio %MONTH_NAME%: %FROM_DATE% a %TO_DATE%

:: El runner no recibe --no-replace: el valor efectivo es replace=true.
call "%RUNNER%" --desde "%FROM_DATE%" --hasta "%TO_DATE%" >>"%MASTER_LOG%" 2>&1
set "MONTH_EXIT_CODE=%ERRORLEVEL%"

if not "%MONTH_EXIT_CODE%"=="0" (
    >>"%MASTER_LOG%" echo ERROR %MONTH_NAME% codigo=%MONTH_EXIT_CODE%
    echo.
    echo ERROR: Fallo %MONTH_NAME% con codigo %MONTH_EXIT_CODE%.
    echo La recarga se detuvo. Revisar:
    echo   "%MASTER_LOG%"
    echo.
    echo Es seguro volver a ejecutar este mismo mes con replace=true.
    exit /b %MONTH_EXIT_CODE%
)

>>"%MASTER_LOG%" echo Fin %MONTH_NAME%: OK
echo %MONTH_NAME% finalizado correctamente.
exit /b 0
