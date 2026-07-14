@echo off
:: =============================================================================
:: setup.bat — Configuración inicial del sincronizador SabioGo → App360
:: Ejecutar UNA SOLA VEZ como Administrador en el servidor SabioGo
:: =============================================================================

echo.
echo ============================================================
echo  SabioGo Sync - Configuracion inicial
echo ============================================================
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no encontrado.
    echo Descargar e instalar Python 3.11+ desde: https://www.python.org/downloads/
    echo Asegurarse de marcar "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)
echo [OK] Python encontrado:
python --version

:: Crear entorno virtual
echo.
echo Creando entorno virtual...
if not exist "venv" (
    python -m venv venv
    echo [OK] Entorno virtual creado.
) else (
    echo [OK] Entorno virtual ya existe.
)

:: Activar e instalar dependencias
echo.
echo Instalando dependencias...
call venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Fallo la instalacion de dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.

:: Crear config.ini si no existe
echo.
if not exist "config.ini" (
    > config.ini echo [firebird]
    >> config.ini echo host = localhost
    >> config.ini echo port = 3050
    >> config.ini echo database = VYP
    >> config.ini echo user = CAMBIAR_USUARIO_FIREBIRD
    >> config.ini echo password = CAMBIAR_PASSWORD_FIREBIRD
    >> config.ini echo client_library =
    >> config.ini echo.
    >> config.ini echo [vps]
    >> config.ini echo url = https://vyp.app360.com.ar
    >> config.ini echo api_key = NO_EJECUTAR_SYNC_AUN
    >> config.ini echo timeout_seconds = 120
    >> config.ini echo max_retries = 3
    >> config.ini echo backoff_factor = 1
    >> config.ini echo origenes = CARNES,LACTEOS
    echo [OK] config.ini creado con estructura base local.
    echo.
    echo ACCION REQUERIDA: Editar config.ini con los valores reales:
    echo     - [vps] api_key = la clave del archivo .env del VPS
    echo.
) else (
    echo [OK] config.ini ya existe.
)

echo.
echo ============================================================
echo  Setup completado.
echo  Proximos pasos:
echo    1. Editar config.ini con credenciales, cliente y api_key
echo    2. Verificar el endpoint sin clave segun guia_windows.txt
echo    3. Ejecutar solo la prueba manual autorizada en la guia
echo    4. No configurar Task Scheduler hasta reconciliar la prueba
echo ============================================================
echo.
pause
