@echo off
:: install.bat — Instala o IN9USBAgent como serviço Windows
:: Executar como Administrador

setlocal EnableDelayedExpansion

echo ============================================
echo  IN9USBAgent — Instalador
echo ============================================
echo.

:: Verificar se rodando como admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Execute este script como Administrador.
    pause
    exit /b 1
)

:: --- Parâmetros ---
set "SERVER_URL=%~1"
set "TOKEN=%~2"

if "%SERVER_URL%"=="" set "SERVER_URL=https://inventario.in9automacao.com.br"

:: Gerar token automático se não fornecido
if "%TOKEN%"=="" (
    echo Gerando token de autenticacao...
    for /f %%i in ('python -c "import secrets; print(secrets.token_hex(32))"') do set "TOKEN=%%i"
    echo Token gerado: !TOKEN:~-8! ^(ultimos 8 chars^)
)

:: --- Localizar Python ---
set "PYTHON_EXE=python"
%PYTHON_EXE% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Python nao encontrado no PATH.
    pause
    exit /b 1
)

:: --- Diretório de instalação ---
set "INSTALL_DIR=%ProgramFiles%\IN9USBAgent"
set "DATA_DIR=%ProgramData%\IN9USBAgent"

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%DATA_DIR%"    mkdir "%DATA_DIR%"

:: Copiar arquivos do agente
xcopy /E /I /Y "%~dp0..\agent" "%INSTALL_DIR%\agent" >nul
copy /Y "%~dp0..\requirements.txt" "%INSTALL_DIR%\" >nul

:: --- Instalar dependências ---
echo Instalando dependencias Python...
%PYTHON_EXE% -m pip install --quiet -r "%INSTALL_DIR%\requirements.txt"
if %errorlevel% neq 0 (
    echo AVISO: Falha ao instalar algumas dependencias. Verifique manualmente.
)

:: --- Configurar token e URL ---
echo Configurando agente...
%PYTHON_EXE% -m agent config --url "%SERVER_URL%" --token "%TOKEN%"
if %errorlevel% neq 0 (
    echo ERRO: Falha ao salvar configuracao.
    pause
    exit /b 1
)

:: --- Registrar no servidor ---
echo Registrando agente no servidor...
%PYTHON_EXE% -m agent register-new --url "%SERVER_URL%" --token "%TOKEN%"
if %errorlevel% neq 0 (
    echo AVISO: Falha ao registrar no servidor. O agente tentara novamente ao iniciar.
)

:: --- Instalar e iniciar serviço Windows ---
echo Instalando servico Windows...
%PYTHON_EXE% -m agent install
if %errorlevel% neq 0 (
    echo ERRO: Falha ao instalar servico Windows.
    pause
    exit /b 1
)

echo Iniciando servico...
%PYTHON_EXE% -m agent start
if %errorlevel% neq 0 (
    echo AVISO: Falha ao iniciar servico. Inicie manualmente via services.msc
)

echo.
echo ============================================
echo  Instalacao concluida!
echo  Servico: IN9USBAgent
echo  Status: Aguardando aprovacao no portal
echo  URL: %SERVER_URL%
echo ============================================
echo.
pause
