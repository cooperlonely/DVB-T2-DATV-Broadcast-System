@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ================================================
echo  DVB-T2 Encoder Launcher (Portable Mode)
echo ================================================
echo.

:: Получаем директорию, где находится этот батник
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: Формируем пути относительно батника
set "RADIOCONDA_DIR=%SCRIPT_DIR%\radioconda"
set "PYTHON_EXE=%RADIOCONDA_DIR%\python.exe"
set "SOAPY_SDR_ROOT=%RADIOCONDA_DIR%\Library"
set "SOAPY_SDR_PLUGIN_PATH=%RADIOCONDA_DIR%\Library\lib\SoapySDR\modules0.8"

:: Проверяем существование Python
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found at: %PYTHON_EXE%
    echo.
    echo Make sure radioconda is in the correct folder:
    echo %RADIOCONDA_DIR%
    pause
    exit /b 1
)

echo [OK] Found Python: %PYTHON_EXE%
echo [OK] SoapySDR root: %SOAPY_SDR_ROOT%
echo [OK] SoapySDR plugins: %SOAPY_SDR_PLUGIN_PATH%
echo.

:: Устанавливаем переменные окружения
set "CONDA_BASE=%RADIOCONDA_DIR%"
set "PATH=%RADIOCONDA_DIR%\Library\bin;%RADIOCONDA_DIR%\Library\lib;%RADIOCONDA_DIR%\DLLs;%RADIOCONDA_DIR%;%PATH%"

:: Переходим в директорию со скриптом
cd /d "%SCRIPT_DIR%"

echo [OK] Current directory: %CD%
echo.
REM echo ================================================
REM echo  Testing environment...
REM echo ================================================

REM :: Создаем временный Python скрипт для тестирования
REM echo import sys, os, platform > "%TEMP%\test_env.py"
REM echo print('[TEST] Python:', sys.executable) >> "%TEMP%\test_env.py"
REM echo print('[TEST] Version:', platform.python_version()) >> "%TEMP%\test_env.py"
REM echo print('[TEST] Working Directory:', os.getcwd()) >> "%TEMP%\test_env.py"
REM echo print('') >> "%TEMP%\test_env.py"
REM echo print('[TEST] SOAPY_SDR_ROOT:', os.environ.get('SOAPY_SDR_ROOT', 'Not set')) >> "%TEMP%\test_env.py"
REM echo print('[TEST] SOAPY_SDR_PLUGIN_PATH:', os.environ.get('SOAPY_SDR_PLUGIN_PATH', 'Not set')) >> "%TEMP%\test_env.py"
REM echo print('') >> "%TEMP%\test_env.py"
REM echo try: >> "%TEMP%\test_env.py"
REM echo     import gnuradio >> "%TEMP%\test_env.py"
REM echo     print('[TEST] GNU Radio: OK') >> "%TEMP%\test_env.py"
REM echo except ImportError as e: >> "%TEMP%\test_env.py"
REM echo     print('[TEST] GNU Radio: ERROR -', str(e)) >> "%TEMP%\test_env.py"
REM echo print('') >> "%TEMP%\test_env.py"
REM echo try: >> "%TEMP%\test_env.py"
REM echo     import SoapySDR >> "%TEMP%\test_env.py"
REM echo     print('[TEST] SoapySDR: OK') >> "%TEMP%\test_env.py"
REM echo     print('') >> "%TEMP%\test_env.py"
REM echo     print('[TEST] Available SDR devices:') >> "%TEMP%\test_env.py"
REM echo     results = SoapySDR.Device.enumerate() >> "%TEMP%\test_env.py"
REM echo     for dev in results: >> "%TEMP%\test_env.py"
REM echo         print(f'  - {dev}') >> "%TEMP%\test_env.py"
REM echo except ImportError as e: >> "%TEMP%\test_env.py"
REM echo     print('[TEST] SoapySDR: ERROR -', str(e)) >> "%TEMP%\test_env.py"

REM "%PYTHON_EXE%" "%TEMP%\test_env.py"
REM del "%TEMP%\test_env.py"

REM echo.
echo ================================================
echo  Running DVB-T2 Encoder...
echo ================================================

if not exist "dvbt2_encoder.py" (
    echo [ERROR] dvbt2_encoder.py not found in current directory!
    pause
    exit /b 1
)

echo [OK] Starting dvbt2_encoder.py...
"%PYTHON_EXE%" dvbt2_encoder.py

if errorlevel 1 (
    echo.
    echo ================================================
    echo  ERROR: Application failed to run
    echo ================================================
)

echo.
pause