# install_service_admin.ps1 — Run as Administrator
$base = "C:\Users\tutup\OneDrive\Área de Trabalho\inventaerio-agent\inventario-usb-agent"
$env:PYTHONPATH = "$base;$base\.venv\Lib\site-packages;$base\.venv\Lib\site-packages\win32;$base\.venv\Lib\site-packages\win32\lib;$base\.venv\Lib\site-packages\Pythonwin"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Set-Location $base
& "$base\.venv\Scripts\python.exe" -m agent install
Write-Host "Exit: $LASTEXITCODE"
Read-Host "Press Enter to exit"
