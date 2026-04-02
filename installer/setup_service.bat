@echo off
:: setup_service.bat — Instala o IN9USBAgent em C:\Program Files\IN9Automacao\USBAgent\
:: Executar como Administrador
::
:: Uso:
::   setup_service.bat <SERVER_URL> <TOKEN>
::
:: Exemplo:
::   setup_service.bat https://inventario.in9automacao.com.br abc123...
::
:: Se TOKEN for omitido, um novo token é gerado automaticamente.

setlocal EnableDelayedExpansion

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Execute este script como Administrador.
    pause & exit /b 1
)

:: --- Parâmetros ---
set "SERVER_URL=%~1"
set "TOKEN=%~2"
if "%SERVER_URL%"=="" set "SERVER_URL=https://inventario.in9automacao.com.br"

:: --- Diretórios ---
set "INSTALL_DIR=C:\Program Files\IN9Automacao\USBAgent"
set "AGENT_DIR=%INSTALL_DIR%\agent"
set "VENV_DIR=%INSTALL_DIR%\venv"
set "DATA_DIR=%INSTALL_DIR%\data"
set "PY=%VENV_DIR%\Scripts\python.exe"

echo ============================================================
echo  IN9USBAgent — Instalador de Producao
echo  Destino : %INSTALL_DIR%
echo  Servidor: %SERVER_URL%
echo ============================================================
echo.

:: --- Verificar Python ---
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Python nao encontrado. Instale Python 3.11+ e adicione ao PATH.
    pause & exit /b 1
)

:: --- Parar e remover servico anterior ---
sc query IN9USBAgent >nul 2>&1
if %errorlevel% equ 0 (
    echo Removendo instalacao anterior...
    sc stop IN9USBAgent >nul 2>&1
    timeout /t 3 /nobreak >nul
    sc delete IN9USBAgent >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: --- Criar estrutura de diretórios ---
if not exist "%AGENT_DIR%" mkdir "%AGENT_DIR%"
if not exist "%DATA_DIR%"  mkdir "%DATA_DIR%"

:: --- Copiar código do agente ---
echo Copiando arquivos...
set "SRC=%~dp0.."
xcopy /E /I /Y /Q "%SRC%\agent" "%AGENT_DIR%" >nul

:: --- Criar venv isolado ---
echo Criando ambiente Python em %VENV_DIR%...
python -m venv "%VENV_DIR%"
if %errorlevel% neq 0 (
    echo ERRO: Falha ao criar venv.
    pause & exit /b 1
)

:: --- Instalar dependências ---
echo Instalando dependencias...
"%PY%" -m pip install --quiet --upgrade pip
"%PY%" -m pip install --quiet wmi pywin32 psutil requests pystray Pillow
if %errorlevel% neq 0 (
    echo ERRO: Falha ao instalar dependencias.
    pause & exit /b 1
)

:: --- Copiar DLLs necessárias para o venv (LocalSystem não herda PATH) ---
echo Copiando DLLs do Python para o venv...
for %%f in (python3*.dll pythoncom3*.dll pywintypes3*.dll) do (
    for /f "delims=" %%p in ('where python 2^>nul') do (
        set "PY_DIR=%%~dpp"
        if exist "!PY_DIR!%%f" (
            copy /Y "!PY_DIR!%%f" "%VENV_DIR%\" >nul 2>&1
        )
    )
)

:: --- Executar post-install do pywin32 ---
"%PY%" "%VENV_DIR%\Scripts\pywin32_postinstall.py" -install >nul 2>&1

:: --- Gerar token se não fornecido ---
if "%TOKEN%"=="" (
    echo Gerando token de autenticacao...
    for /f %%i in ('"%PY%" -c "import secrets; print(secrets.token_hex(32))"') do set "TOKEN=%%i"
    echo Token gerado ^(guarde este valor^): !TOKEN!
    echo.
)

:: --- Salvar configuração no banco de dados ---
echo Configurando agente...
cd /d "%INSTALL_DIR%"
"%PY%" -m agent config --url "%SERVER_URL%" --token "%TOKEN%"
if %errorlevel% neq 0 (
    echo ERRO: Falha ao salvar configuracao.
    pause & exit /b 1
)

:: --- Registrar no servidor ---
echo Registrando agente no servidor...
"%PY%" -m agent register-new
if %errorlevel% neq 0 (
    echo AVISO: Falha ao registrar. O agente tentara novamente ao iniciar.
)

:: --- Instalar serviço Windows ---
echo Instalando servico Windows...
"%PY%" -m agent install
if %errorlevel% neq 0 (
    echo ERRO: Falha ao instalar servico.
    pause & exit /b 1
)

:: --- Configurar PYTHONPATH no registro do serviço ---
set "PYPATH=%INSTALL_DIR%;%VENV_DIR%\Lib\site-packages;%VENV_DIR%\Lib\site-packages\win32;%VENV_DIR%\Lib\site-packages\win32\lib;%VENV_DIR%\Lib\site-packages\Pythonwin"
reg add "HKLM\SYSTEM\CurrentControlSet\Services\IN9USBAgent" /v Environment /t REG_MULTI_SZ /d "PYTHONPATH=%PYPATH%" /f >nul

:: --- Iniciar serviço ---
echo Iniciando servico...
sc start IN9USBAgent
timeout /t 5 /nobreak >nul
sc query IN9USBAgent

echo.
echo ============================================================
echo  Instalacao concluida!
echo  Servico : IN9USBAgent (RUNNING)
echo  Dados   : %DATA_DIR%\agent.db
echo  Servidor: %SERVER_URL%
echo  Status  : Aguardando aprovacao em /usb-agentes
echo ============================================================
echo.
pause
