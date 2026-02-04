@echo off
chcp 65001 >nul

echo ================================================
echo  Simple DVB-T2 Encoder Launcher
echo ================================================

:: Configuration from file
if exist "conf.cfg" (
    echo Loading configuration from conf.cfg...
    for /f "tokens=1,2 delims==" %%a in (conf.cfg) do (
        if "%%a"=="RADIOCONDA_PATH" set "PYTHON_EXE=%%b"
        if "%%a"=="CONDA_BASE" set "RADIOCONDA_DIR=%%b"
        if "%%a"=="CONDA_BASE_PATH" set "RADIOCONDA_DIR=%%b"
    )
)

:: Если путь не найден в конфиге - выводим ошибку
if not defined PYTHON_EXE (
    echo ERROR: RADIOCONDA_PATH not found in conf.cfg!
    echo Please run setup.bat first or edit conf.cfg manually.
    echo.
    echo Example conf.cfg contents:
    echo RADIOCONDA_PATH=C:\path\to\radioconda\python.exe
    echo CONDA_BASE=C:\path\to\radioconda
    pause
    exit /b 1
)

:: Если CONDA_BASE не указан, пытаемся вывести из пути к Python
if not defined RADIOCONDA_DIR (
    for %%F in ("%PYTHON_EXE%") do set "RADIOCONDA_DIR=%%~dpF"
    set "RADIOCONDA_DIR=%RADIOCONDA_DIR:~0,-1%"
)

:: Удаляем возможные пробелы в конце путей
set "PYTHON_EXE=%PYTHON_EXE: =%"
set "RADIOCONDA_DIR=%RADIOCONDA_DIR: =%"

:: Проверяем существование Python
if not exist "%PYTHON_EXE%" (
    echo ERROR: Python not found at: %PYTHON_EXE%
    echo Please check the RADIOCONDA_PATH in conf.cfg
    pause
    exit /b 1
)

echo Using Python: %PYTHON_EXE%

:: Устанавливаем переменные окружения SoapySDR
set "CONDA_BASE=%RADIOCONDA_DIR%"
set "SOAPY_SDR_ROOT=%CONDA_BASE%\Library"
set "SOAPY_SDR_PLUGIN_PATH=%CONDA_BASE%\Library\lib\SoapySDR\modules0.8"

echo Conda Base: %CONDA_BASE%
echo SOAPY_SDR_ROOT: %SOAPY_SDR_ROOT%
echo SOAPY_SDR_PLUGIN_PATH: %SOAPY_SDR_PLUGIN_PATH%

:: Добавляем необходимые пути в PATH
set "ORIGINAL_PATH=%PATH%"
set "PATH=%CONDA_BASE%\Library\bin;%CONDA_BASE%\Library\lib;%CONDA_BASE%\DLLs;%CONDA_BASE%;%ORIGINAL_PATH%"

:: Переходим в директорию со скриптом
cd /d "%~dp0"

echo Current directory: %CD%

echo.
echo ================================================
echo  Testing environment...
echo ================================================

:: Создаем временный Python скрипт для тестирования
echo import sys, os, platform > test_env.py
echo print('Python:', sys.executable) >> test_env.py
echo print('Version:', platform.python_version()) >> test_env.py
echo print('Working Directory:', os.getcwd()) >> test_env.py
echo print('') >> test_env.py
echo print('SOAPY_SDR_ROOT:', os.environ.get('SOAPY_SDR_ROOT', 'Not set')) >> test_env.py
echo print('SOAPY_SDR_PLUGIN_PATH:', os.environ.get('SOAPY_SDR_PLUGIN_PATH', 'Not set')) >> test_env.py
echo print('') >> test_env.py
echo try: >> test_env.py
echo     import gnuradio >> test_env.py
echo     print('GNU Radio: OK') >> test_env.py
echo except ImportError as e: >> test_env.py
echo     print('GNU Radio: ERROR -', str(e)) >> test_env.py
echo print('') >> test_env.py
echo try: >> test_env.py
echo     import SoapySDR >> test_env.py
echo     print('SoapySDR: OK') >> test_env.py
echo     print('') >> test_env.py
echo     print('Available SDR devices:') >> test_env.py
echo     results = SoapySDR.Device.enumerate() >> test_env.py
echo except ImportError as e: >> test_env.py
echo     print('SoapySDR: ERROR -', str(e)) >> test_env.py
echo     print('') >> test_env.py
echo     print('To install SoapySDR:') >> test_env.py
echo     print('conda install -c conda-forge soapysdr') >> test_env.py

"%PYTHON_EXE%" test_env.py
del test_env.py

echo.
echo ================================================
echo  Running DVB-T2 Encoder...
echo ================================================

if not exist "dvbt2_encoder.py" (
    echo ERROR: dvbt2_encoder.py not found in current directory!
    pause
    exit /b 1
)

echo Starting dvbt2_encoder.py...
"%PYTHON_EXE%" dvbt2_encoder.py

if errorlevel 1 (
    echo.
    echo ================================================
    echo  ERROR: Script failed to run
    echo ================================================
    echo.
    echo Troubleshooting:
    echo 1. Check if SoapySDR is installed: conda list soapysdr
    echo 2. Install SoapySDR: conda install -c conda-forge soapysdr
    echo 3. Make sure conf.cfg contains correct paths
)

echo.
pause