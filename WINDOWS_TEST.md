# WINDOWS_TEST.md — Guia de Testes no Windows para Claude

Este documento é para ser lido pelo Claude Code rodando no Windows.
Siga cada etapa na ordem. Reporte erros exatamente como aparecerem.

---

## Contexto do projeto

Agente Python que monitora eventos USB via WMI e reporta ao servidor do Inventário TI.
- Repositório: este diretório
- Stack: Python 3.11, wmi, pywin32, psutil, requests, sqlite3
- Servidor backend: já implementado e rodando

---

## ETAPA 1 — Verificar ambiente

Execute e reporte a saída de cada comando:

```bat
python --version
pip --version
python -c "import sys; print(sys.platform)"
```

**Esperado:** Python 3.11.x, pip 23+, win32

Se `python` não for encontrado, tente `py` no lugar de `python`.

---

## ETAPA 2 — Criar virtualenv e instalar dependências

```bat
cd inventario-usb-agent
python -m venv .venv
.venv\Scripts\activate
pip install wmi pywin32 psutil requests pytest
```

Após instalar o pywin32, execute o post-install:
```bat
python .venv\Scripts\pywin32_postinstall.py -install
```

Verifique que todos importam sem erro:
```bat
python -c "import wmi; import win32api; import psutil; import requests; print('OK')"
```

**Esperado:** `OK`

---

## ETAPA 3 — Rodar a suíte de testes unitários

```bat
python -m pytest tests/ -v
```

**Esperado:** 60 passed

Se algum teste falhar, reporte o nome do teste e o traceback completo.

---

## ETAPA 4 — Testar módulos individualmente

### 4a. hasher.py
```bat
python -c "
from agent.hasher import compute_hash_id, is_stable_serial
print('Stable serial:', is_stable_serial('ABCDEF1234'))
print('Unstable serial:', is_stable_serial('3&11583659&0'))
h, stable = compute_hash_id('046D', 'C52B', 'ABCDEF1234')
print('Hash (stable):', h[:16], '... stable=', stable)
h2, stable2 = compute_hash_id('046D', 'C52B', '3&11583659&0')
print('Hash (unstable):', h2[:16], '... stable=', stable2)
"
```

**Esperado:**
```
Stable serial: True
Unstable serial: False
Hash (stable): <64 chars hex> ... stable= True
Hash (unstable): <64 chars hex> ... stable= False
```

### 4b. classifier.py
```bat
python -c "
from agent.classifier import classify
print(classify('{4D36E96B-E325-11CE-BFC1-08002BE10318}', 'USB Mouse'))
print(classify(None, 'SanDisk Pen Drive'))
print(classify(None, 'USB Root Hub'))
print(classify(None, None))
"
```

**Esperado:**
```
mouse
pen_drive
unknown
peripheral
```

### 4c. local_db.py
```bat
python -c "
from agent.local_db import LocalDB
from pathlib import Path
db = LocalDB(db_path=Path('test_temp.db'))
db.server_url = 'http://localhost:3000'
db.token = 'testtoken'
db.enqueue_event({'event_type': 'connected', 'vid': '046D', 'pid': 'C52B'})
print('Pending:', db.pending_count())
batch = db.pop_pending_events()
print('Batch size:', len(batch))
db.mark_sent([batch[0][0]])
print('After mark_sent:', db.pending_count())
import os; os.remove('test_temp.db')
print('OK')
"
```

**Esperado:**
```
Pending: 1
Batch size: 1
After mark_sent: 0
OK
```

### 4d. specs.py (requer wmi — Windows only)
```bat
python -c "
from agent.specs import capture_machine_specs
import json
specs = capture_machine_specs()
print(json.dumps(specs, indent=2))
"
```

**Esperado:** JSON com hostname, cpu, ram_gb, disks, os. Reporte o JSON completo.
Se algum campo estiver ausente (ex: gpu, bios_serial), anote quais faltaram.

---

## ETAPA 5 — Testar WMI watcher (requer Administrador)

> ⚠️ Execute o CMD como **Administrador** para esta etapa.

```bat
python -c "
import threading, time
from agent.usb_monitor import UsbMonitor

eventos = []

def on_event(e):
    eventos.append(e)
    print(f'EVENTO: {e[\"event_type\"]} | {e[\"friendly_name\"]} | VID:{e[\"vid\"]} PID:{e[\"pid\"]}')

monitor = UsbMonitor(on_event=on_event)
monitor.start()
print('Monitor iniciado. Pluge e desplugue um dispositivo USB nos proximos 30 segundos...')
time.sleep(30)
monitor.stop()
print(f'Total de eventos capturados: {len(eventos)}')
"
```

**O que fazer:** Após ver "Monitor iniciado", pluge e desplugue um pendrive ou mouse USB.

**Esperado:**
```
Monitor iniciado. Pluge e desplugue um dispositivo USB nos proximos 30 segundos...
EVENTO: connected | SanDisk Ultra | VID:0781 PID:5581
EVENTO: disconnected | SanDisk Ultra | VID:0781 PID:5581
Total de eventos capturados: 2
```

Reporte todos os eventos que aparecerem (nome, VID, PID, serial).
Se nenhum evento aparecer, reporte qualquer erro ou aviso no console.

---

## ETAPA 6 — Configurar conexão com o servidor

Substitua os valores abaixo antes de executar:

```bat
python -m agent config --url http://IP-DO-SERVIDOR:3000 --token SEU-TOKEN-AQUI
```

Se não tiver token, gere um:
```bat
python -c "import secrets; print(secrets.token_hex(32))"
```

Verifique o que foi salvo:
```bat
python -c "
from agent.local_db import LocalDB
db = LocalDB()
print('server_url:', db.server_url)
print('token hint: ...', db.token[-8:] if db.token else 'None')
print('machine_id:', db.machine_id)
"
```

---

## ETAPA 7 — Registrar no servidor

```bat
python -m agent register-new
```

**Esperado:**
```
Registro OK: {'success': True, 'machine_id': '...', 'status': 'pending', ...}
```

Se falhar com erro de conexão, verifique:
```bat
python -c "
import requests
resp = requests.get('http://IP-DO-SERVIDOR:3000/api/agent/version',
                    headers={'X-Agent-Token': 'SEU-TOKEN'},
                    timeout=5)
print(resp.status_code, resp.json())
"
```

---

## ETAPA 8 — Rodar o agente em modo standalone

```bat
python -m agent run
```

Enquanto o agente roda, pluge e desplugue um pendrive.

**Esperado no console:**
```
[INFO] IN9USBAgent v1.0.0 iniciando...
[INFO] Registro OK — status: pending
[INFO] WMI watchers registrados — aguardando eventos USB...
[INFO] CONNECTED — SanDisk Ultra [VID:0781 PID:5581]
[INFO] Enviando evento USB: connected SanDisk Ultra
```

Interrompa com `Ctrl+C` após testar.

---

## ETAPA 9 — Verificar buffer offline

Simule envio offline desconectando da rede antes de plurar o USB, depois reconectando:

```bat
python -c "
from agent.local_db import LocalDB
db = LocalDB()
print('Eventos pendentes no buffer:', db.pending_count())
"
```

---

## O que reportar ao final

Para cada etapa, informe:
1. ✅ Passou / ❌ Falhou
2. Saída exata do console (especialmente em falhas)
3. Versões: Python, wmi, pywin32
4. Modelo/versão do Windows (`winver`)
5. JSON completo do specs.py (Etapa 4d)
6. Eventos USB capturados (Etapa 5) — nome, VID, PID de cada dispositivo testado
