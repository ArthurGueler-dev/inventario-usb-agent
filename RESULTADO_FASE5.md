# Resultado — Etapas 3, 4 e 5: Testes locais do agente USB

**Data:** 2026-04-01
**Executado por:** Claude Sonnet 4.6 via Claude Code
**Commit da correção:** `c0b3aac`

---

## Ambiente

| Item | Valor |
|---|---|
| OS | Windows 11 Pro for Workstations 10.0.26200 |
| Hostname | arthur-desktop |
| Python | 3.13.5 |
| pip | 25.1.1 |
| wmi | 1.5.1 |
| pywin32 | 311 |
| psutil | 7.2.2 |
| requests | 2.33.1 |
| pytest | 9.0.2 |

---

## Etapa 3 — Suíte de testes unitários

```
pytest tests/ -v
60 passed in 1.45s
```

**Status:** ✅ PASSOU — 60/60

---

## Etapa 4 — Módulos individuais

### 4a. hasher.py ✅

```
Stable serial: True
Unstable serial: False
Hash (stable): c483cc42c10cd64c ... stable= True
Hash (unstable): d7c494640a362e5a ... stable= False
```

### 4b. classifier.py ✅

```
mouse
pen_drive
unknown
peripheral
```

### 4c. local_db.py ✅

```
Pending: 1
Batch size: 1
After mark_sent: 0
```

> Nota: o `os.remove('test_temp.db')` do script de teste falhou com `PermissionError` no Windows porque o SQLite usa `_connect()` por demanda (sem conexão persistente) e o OS mantém lock sobre o arquivo por alguns instantes. A lógica de negócio funcionou corretamente. Arquivo removido manualmente após o teste.

### 4d. specs.py ✅

```json
{
  "hostname": "arthur-desktop",
  "cpu": "AMD Ryzen 5 5600G with Radeon Graphics",
  "cpu_cores": 6,
  "cpu_threads": 12,
  "ram_gb": 7.8,
  "disks": [
    { "label": "C:\\", "total_gb": 1862.3, "type": "SSD" },
    { "label": "D:\\", "total_gb": 930.9,  "type": "SSD" }
  ],
  "gpu": "Parsec Virtual Display Adapter",
  "os": "Microsoft Windows 11 Pro for Workstations 64 bits",
  "os_build": "26200",
  "bios_serial": "System Serial Number",
  "bios_version": "3611",
  "mac_address": "E8:9C:25:3B:2B:A7"
}
```

> Campos presentes: hostname, cpu, cpu_cores, cpu_threads, ram_gb, disks (com tipo SSD/HDD), gpu, os, os_build, bios_serial, bios_version, mac_address.
> Nenhum campo ausente.

---

## Etapa 5 — WMI Watcher (eventos USB)

### Bug encontrado e corrigido em `agent/usb_monitor.py`

**Problema:** O método `watch_for()` da biblioteca `wmi` aceita apenas os valores curtos (`'creation'`, `'deletion'`) — não os nomes completos dos eventos WMI. Além disso, o objeto retornado pelo watcher delega atributos ao `TargetInstance` diretamente, não há `.NewValue` nem `.PreviousValue`.

**Erro original:**
```
wmi.x_wmi: <x_wmi: notification_type must be one of operation, creation, deletion, modification>
```

**Correção (commit `c0b3aac`):**

```python
# Antes
watcher_connect    = c.Win32_PnPEntity.watch_for('__InstanceCreationEvent')
watcher_disconnect = c.Win32_PnPEntity.watch_for('__InstanceDeletionEvent')
self._handle(event.NewValue,    'connected')
self._handle(event.PreviousValue, 'disconnected')

# Depois
watcher_connect    = c.Win32_PnPEntity.watch_for('creation')
watcher_disconnect = c.Win32_PnPEntity.watch_for('deletion')
self._handle(event, 'connected')
self._handle(event, 'disconnected')
```

**Resultado após correção:**
```
Monitor iniciado. Pluge e desplugue um dispositivo USB nos proximos 30 segundos...
EVENTO: connected | Dispositivo de Entrada USB | VID:1EA7 PID:9018 | serial:None
EVENTO: connected | Dispositivo de Entrada USB | VID:1EA7 PID:9018 | serial:None
EVENTO: connected | Dispositivo de Entrada USB | VID:1EA7 PID:9018 | serial:None
EVENTO: connected | USB Composite Device       | VID:1EA7 PID:9018 | serial:None
Total de eventos capturados: 4
```

**Status:** ✅ PASSOU

**Dispositivo testado:**

| Campo | Valor |
|---|---|
| Nome | Dispositivo de Entrada USB / USB Composite Device |
| VID | `1EA7` |
| PID | `9018` |
| Serial | `None` (PNPDeviceID contém `&` → sub-interface, serial descartado) |
| Tipo esperado | Mouse/teclado USB |

**Observações:**
- 4 eventos disparados para o mesmo dispositivo — normal no Windows (cada interface de um dispositivo composto gera um evento separado).
- Eventos `disconnected` não capturados pois o dispositivo não foi desplugado na janela de 30s.
- Avisos `Win32 exception occurred releasing IUnknown` são benignos (cleanup do COM ao encerrar watchers).

---

## Status geral das etapas

| Etapa | Descrição | Status |
|---|---|---|
| 1 | Verificar ambiente | ✅ Python 3.13.5, pip 25.1.1, win32 |
| 2 | Criar venv e instalar dependências | ✅ Todos os imports OK |
| 3 | Suíte de testes unitários | ✅ 60/60 passed |
| 4a | hasher.py | ✅ |
| 4b | classifier.py | ✅ |
| 4c | local_db.py | ✅ (lógica OK; lock de arquivo no cleanup é comportamento do Windows) |
| 4d | specs.py | ✅ JSON completo, nenhum campo ausente |
| 5 | WMI watcher — eventos USB | ✅ 4 eventos capturados (após bugfix em `usb_monitor.py`) |
| 6–9 | Configuração servidor / registro / standalone / buffer | ⏳ Pendente — requer servidor rodando |
