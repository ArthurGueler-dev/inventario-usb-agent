# setup_service.ps1 — Instala e configura o servico Windows (requer admin)
# Executar como Administrador

$ErrorActionPreference = 'Stop'

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Base: $base"

# 1. Remover servico anterior se existir
try {
    $svc = Get-Service IN9USBAgent -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "Removendo servico existente..."
        if ($svc.Status -eq 'Running') {
            Stop-Service IN9USBAgent -Force
        }
        sc.exe delete IN9USBAgent | Out-Null
        Start-Sleep 2
    }
} catch {}

# 2. Instalar o servico
Write-Host "Instalando servico..."
Set-Location $base
& "$base\.venv\Scripts\python.exe" -m agent install
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao instalar servico (exit $LASTEXITCODE)"
    exit 1
}

# 3. Configurar PYTHONPATH no registro do servico
$pythonPath = @(
    $base,
    "$base\.venv\Lib\site-packages",
    "$base\.venv\Lib\site-packages\win32",
    "$base\.venv\Lib\site-packages\win32\lib",
    "$base\.venv\Lib\site-packages\Pythonwin"
) -join ';'

Write-Host "Configurando PYTHONPATH..."
$regPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\IN9USBAgent'
New-ItemProperty -Path $regPath -Name 'Environment' -Value @("PYTHONPATH=$pythonPath") -PropertyType MultiString -Force | Out-Null

Write-Host "PYTHONPATH = $pythonPath"

# 4. Verificar
$env_val = (Get-ItemProperty -Path $regPath -Name 'Environment' -ErrorAction SilentlyContinue).Environment
Write-Host "Registry Environment: $env_val"

# 5. Iniciar servico
Write-Host "Iniciando servico..."
Start-Service IN9USBAgent
Start-Sleep 3
$status = (Get-Service IN9USBAgent).Status
Write-Host "Status: $status"
