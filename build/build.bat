@echo off
:: build.bat — Empacota o agente em usb_agent.exe via PyInstaller
:: Executar a partir do diretório raiz do projeto com o venv ativado:
::   .venv\Scripts\activate
::   build\build.bat

echo ============================================================
echo  IN9USBAgent — Build PyInstaller
echo ============================================================

pyinstaller ^
    --onefile ^
    --name usb_agent ^
    --noconsole ^
    --hidden-import win32timezone ^
    --hidden-import win32service ^
    --hidden-import win32serviceutil ^
    --hidden-import win32event ^
    --hidden-import servicemanager ^
    --hidden-import wmi ^
    --hidden-import pywintypes ^
    --hidden-import pystray._win32 ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageDraw ^
    --collect-all pystray ^
    agent/__main__.py

if %errorlevel% neq 0 (
    echo ERRO: Build falhou.
    exit /b 1
)

echo.
echo Build concluido: dist\usb_agent.exe
echo.
echo Para instalar:
echo   copy dist\usb_agent.exe "C:\Program Files\IN9Automacao\USBAgent\"
echo   installer\setup_service.bat
