@echo off
:: uninstall.bat — Remove o IN9USBAgent
:: Executar como Administrador

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Execute este script como Administrador.
    pause
    exit /b 1
)

echo Parando servico IN9USBAgent...
python -m agent stop >nul 2>&1

echo Removendo servico Windows...
python -m agent remove
if %errorlevel% neq 0 (
    echo AVISO: Falha ao remover servico. Tente manualmente: sc delete IN9USBAgent
)

echo Removendo arquivos...
set "INSTALL_DIR=%ProgramFiles%\IN9USBAgent"
if exist "%INSTALL_DIR%" rmdir /S /Q "%INSTALL_DIR%"

echo.
echo IN9USBAgent removido.
echo Os dados locais em %%ProgramData%%\IN9USBAgent foram mantidos.
echo Remova manualmente se desejar apagar o historico local.
echo.
pause
