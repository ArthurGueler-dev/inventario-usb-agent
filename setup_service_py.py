"""
setup_service_py.py — instala o servico e configura PYTHONPATH no registro.
Requer execucao como Administrador.
"""
import sys
import os
import subprocess
from pathlib import Path

LOG = Path(r'C:\Windows\Temp\in9_install.log')

def log(msg):
    print(msg)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

base = Path(__file__).parent.resolve()
venv = base / '.venv'
python = venv / 'Scripts' / 'python.exe'

log(f'=== IN9USBAgent Service Setup ===')
log(f'Base: {base}')
log(f'Python: {python}')
log(f'Python exists: {python.exists()}')

# Remove old service
log('\n--- Removing old service ---')
subprocess.run(['sc', 'stop', 'IN9USBAgent'], capture_output=True)
subprocess.run(['sc', 'delete', 'IN9USBAgent'], capture_output=True)
import time; time.sleep(2)

# Install
log('\n--- Installing service ---')
os.chdir(base)
result = subprocess.run(
    [str(python), '-m', 'agent', 'install'],
    capture_output=True, text=True
)
log(f'stdout: {result.stdout}')
log(f'stderr: {result.stderr}')
log(f'returncode: {result.returncode}')

if result.returncode != 0:
    log('FAILED: install step')
    sys.exit(1)

# Set PYTHONPATH in registry
log('\n--- Setting PYTHONPATH in registry ---')
try:
    import winreg
    pypath = ';'.join([
        str(base),
        str(venv / 'Lib' / 'site-packages'),
        str(venv / 'Lib' / 'site-packages' / 'win32'),
        str(venv / 'Lib' / 'site-packages' / 'win32' / 'lib'),
        str(venv / 'Lib' / 'site-packages' / 'Pythonwin'),
    ])
    log(f'PYTHONPATH: {pypath}')
    key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r'SYSTEM\CurrentControlSet\Services\IN9USBAgent',
        0, winreg.KEY_SET_VALUE
    )
    # REG_MULTI_SZ is a list of strings
    winreg.SetValueEx(key, 'Environment', 0, winreg.REG_MULTI_SZ, [f'PYTHONPATH={pypath}'])
    winreg.CloseKey(key)
    log('Registry set OK')
except Exception as e:
    log(f'Registry ERROR: {e}')
    sys.exit(1)

# Start service
log('\n--- Starting service ---')
result = subprocess.run(['sc', 'start', 'IN9USBAgent'], capture_output=True, text=True)
log(f'stdout: {result.stdout}')
log(f'stderr: {result.stderr}')
time.sleep(5)
result = subprocess.run(['sc', 'query', 'IN9USBAgent'], capture_output=True, text=True)
log(f'Query:\n{result.stdout}')

log('\n=== Done ===')
