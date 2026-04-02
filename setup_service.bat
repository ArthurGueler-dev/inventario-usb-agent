@echo off
REM Instala o servico Windows IN9USBAgent — requer Administrador
setlocal

set BASE=C:\Users\tutup\OneDrive\Área de Trabalho\inventaerio-agent\inventario-usb-agent
set VENV=%BASE%\.venv
set PY=%VENV%\Scripts\python.exe

echo === Instalando IN9USBAgent como servico Windows ===
echo Base: %BASE%

REM Remover servico anterior
sc stop IN9USBAgent >nul 2>&1
sc delete IN9USBAgent >nul 2>&1
timeout /t 2 /nobreak >nul

REM Instalar servico
cd /d "%BASE%"
"%PY%" -m agent install
if errorlevel 1 (
    echo ERRO: falha ao instalar servico
    pause
    exit /b 1
)

REM Configurar PYTHONPATH no registro
set PYPATH=%BASE%;%VENV%\Lib\site-packages;%VENV%\Lib\site-packages\win32;%VENV%\Lib\site-packages\win32\lib;%VENV%\Lib\site-packages\Pythonwin
reg add "HKLM\SYSTEM\CurrentControlSet\Services\IN9USBAgent" /v Environment /t REG_MULTI_SZ /d "PYTHONPATH=%PYPATH%" /f
if errorlevel 1 (
    echo ERRO: falha ao configurar registro
    pause
    exit /b 1
)

echo PYTHONPATH configurado no registro
echo.

REM Iniciar servico
sc start IN9USBAgent
timeout /t 5 /nobreak >nul
sc query IN9USBAgent

echo.
echo === Concluido ===
pause
