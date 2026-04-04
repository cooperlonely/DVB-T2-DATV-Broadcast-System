@echo off
setlocal enabledelayedexpansion

:: --- БЛОК САМОЛЕЧЕНИЯ: Исправляем себя один раз и навсегда ---
set "ORIGINAL_SCRIPT=%~f0"
set "ORIGINAL_DIR=%~dp0"
set "ORIGINAL_DIR=%ORIGINAL_DIR:~0,-1%"

:: Проверяем, не запущены ли мы с флагом "уже исправлено"
if "%1"=="--fixed" goto :main

:: Проверяем, нужно ли исправление (есть ли CR в файле)
set "TEST_FILE=%TEMP%\crlf_test_%RANDOM%.tmp"
copy "%ORIGINAL_SCRIPT%" "%TEST_FILE%" >nul 2>&1
findstr /V /R "$" "%TEST_FILE%" >nul 2>&1
set "NEEDS_FIX=%errorlevel%"
del "%TEST_FILE%" 2>nul

:: Если файл уже в CRLF, ничего не делаем
if %NEEDS_FIX% NEQ 0 goto :main

:: --- Файл сломан (только LF). ПЕРЕЗАПИСЫВАЕМ СЕБЯ В ПРАВИЛЬНОМ ФОРМАТЕ ---
echo [WARNING] Found LF endings of lines, fixing to CRLF...

:: Создаем временный файл с правильными окончаниями строк
set "TEMP_SCRIPT=%TEMP%\%~n0_temp.bat"
(
    for /f "usebackq tokens=* delims=" %%a in ("%ORIGINAL_SCRIPT%") do echo %%a
) > "%TEMP_SCRIPT%"

:: Заменяем оригинальный файл исправленной версией
copy /y "%TEMP_SCRIPT%" "%ORIGINAL_SCRIPT%" >nul
del "%TEMP_SCRIPT%" 2>nul

echo [OK] Файл исправлен. Перезапускаюсь...

:: Перезапускаем себя с флагом "уже исправлено" и завершаем старую версию
start "" "%ORIGINAL_SCRIPT%" --fixed
exit /b

:: --- КОНЕЦ БЛОКА САМОЛЕЧЕНИЯ ---

:main
:: Убираем флаг, если он был передан
set SCRIPT_ARGS=%*
if "%1"=="--fixed" shift

:: ОСНОВНОЙ КОД (ваш оригинальный)
chcp 65001 >nul
echo ================================================
echo  DVB-T2 Encoder Launcher (Portable Mode)
echo ================================================
echo.

:: Получаем директорию
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "RADIOCONDA_DIR=%SCRIPT_DIR%\radioconda"
set "PYTHON_EXE=%RADIOCONDA_DIR%\python.exe"
set "SOAPY_SDR_ROOT=%RADIOCONDA_DIR%\Library"
set "SOAPY_SDR_PLUGIN_PATH=%RADIOCONDA_DIR%\Library\lib\SoapySDR\modules0.8"

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

set "CONDA_BASE=%RADIOCONDA_DIR%"
set "PATH=%RADIOCONDA_DIR%\Library\bin;%RADIOCONDA_DIR%\Library\lib;%RADIOCONDA_DIR%\DLLs;%RADIOCONDA_DIR%;%PATH%"

cd /d "%SCRIPT_DIR%"

echo [OK] Current directory: %CD%
echo.
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