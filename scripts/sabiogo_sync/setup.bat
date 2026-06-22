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
    copy config.ini.example config.ini
    echo [OK] config.ini creado desde el template.
    echo.
    echo >>> ACCION REQUERIDA: Editar config.ini con los valores reales:
    echo     - [vps] api_key = la clave del archivo .env del VPS
    echo.
) else (
    echo [OK] config.ini ya existe.
)

echo.
echo ============================================================
echo  Setup completado.
echo  Proximos pasos:
echo    1. Editar config.ini con la api_key del VPS
echo    2. Probar: run_sync.bat --fecha 2026-06-01
echo    3. Configurar tarea programada con Task Scheduler
echo       (ver instrucciones en README del directorio)
echo ============================================================
echo.
pause
