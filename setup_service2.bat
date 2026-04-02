@echo off
REM Instala o servico Windows IN9USBAgent — requer Administrador
set LOG=C:\Windows\Temp\in9_install.log
echo START %DATE% %TIME% > %LOG%

set BASE=C:\Users\tutup\OneDrive\?rea de Trabalho\inventaerio-agent\inventario-usb-agent
echo BASE=%BASE% >> %LOG%

REM Remover servico anterior
sc stop IN9USBAgent >> %LOG% 2>&1
sc delete IN9USBAgent >> %LOG% 2>&1
timeout /t 2 /nobreak >nul

REM Instalar
cd /d "%BASE%"
echo CD result: %errorlevel% >> %LOG%
echo DIR: >> %LOG%
dir /b >> %LOG% 2>&1

"%BASE%\.venv\Scripts\python.exe" -m agent install >> %LOG% 2>&1
echo INSTALL exit: %errorlevel% >> %LOG%

sc query IN9USBAgent >> %LOG% 2>&1

REM PYTHONPATH
set PYPATH=%BASE%;%BASE%\.venv\Lib\site-packages;%BASE%\.venv\Lib\site-packages\win32;%BASE%\.venv\Lib\site-packages\win32\lib
reg add "HKLM\SYSTEM\CurrentControlSet\Services\IN9USBAgent" /v Environment /t REG_MULTI_SZ /d "PYTHONPATH=%PYPATH%" /f >> %LOG% 2>&1
echo REG exit: %errorlevel% >> %LOG%

sc start IN9USBAgent >> %LOG% 2>&1
timeout /t 5 /nobreak >nul
sc query IN9USBAgent >> %LOG% 2>&1

echo END %DATE% %TIME% >> %LOG%
type %LOG%
