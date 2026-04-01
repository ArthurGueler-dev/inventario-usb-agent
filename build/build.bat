@echo off
:: build.bat — Empacota o agente em usb_agent.exe via PyInstaller
:: Executar a partir do diretório raiz do projeto

echo Construindo IN9USBAgent.exe...

pyinstaller ^
    --onefile ^
    --name usb_agent ^
    --hidden-import win32timezone ^
    --hidden-import wmi ^
    --hidden-import pywintypes ^
    --add-data "agent;agent" ^
    agent/__main__.py

if %errorlevel% neq 0 (
    echo ERRO: Build falhou.
    exit /b 1
)

echo.
echo Build concluido: dist\usb_agent.exe
