@echo off
:: build_installer.bat — Pipeline completo de build
::
:: Pré-requisitos (instalar uma vez na máquina de build):
::   pip install pyinstaller pystray Pillow wmi pywin32 psutil requests
::   Inno Setup 6: https://jrsoftware.org/isdl.php
::
:: Resultado:
::   dist\usb_agent.exe        — executável do agente (PyInstaller)
::   dist\IN9USBAgent_Setup.exe — instalador completo (Inno Setup)

setlocal EnableDelayedExpansion

echo ============================================================
echo  IN9USBAgent — Build Completo
echo ============================================================
echo.

:: --- Verificar Python ---
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Python nao encontrado no PATH.
    pause & exit /b 1
)

:: --- Verificar PyInstaller ---
pyinstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Instalando PyInstaller...
    pip install pyinstaller --quiet
)

:: --- Verificar Inno Setup ---
set "ISCC="
for %%p in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) do (
    if exist %%p set "ISCC=%%~p"
)

if "%ISCC%"=="" (
    echo ERRO: Inno Setup 6 nao encontrado.
    echo Baixe em: https://jrsoftware.org/isdl.php
    pause & exit /b 1
)

:: --- Limpar builds anteriores ---
if exist dist\usb_agent.exe      del /f /q dist\usb_agent.exe
if exist dist\IN9USBAgent_Setup.exe del /f /q dist\IN9USBAgent_Setup.exe
if exist build\usb_agent         rmdir /s /q build\usb_agent

:: ============================================================
:: ETAPA 1 — PyInstaller: agent → usb_agent.exe
:: ============================================================
echo [1/2] Compilando agente com PyInstaller...
echo.

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
    echo ERRO: PyInstaller falhou.
    pause & exit /b 1
)

echo.
echo usb_agent.exe gerado: dist\usb_agent.exe
echo.

:: ============================================================
:: ETAPA 2 — Inno Setup: usb_agent.exe → IN9USBAgent_Setup.exe
:: ============================================================
echo [2/2] Compilando instalador com Inno Setup...
echo.

"%ISCC%" installer\setup.iss

if %errorlevel% neq 0 (
    echo ERRO: Inno Setup falhou.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  Build concluido!
echo.
echo  dist\usb_agent.exe           — executavel do agente
echo  dist\IN9USBAgent_Setup.exe   — instalador final
echo.
echo  Distribuir apenas: IN9USBAgent_Setup.exe
echo ============================================================
echo.
pause
