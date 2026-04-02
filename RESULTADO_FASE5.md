# Resultado — Etapas 1 a 8: Testes locais e integração do agente USB

**Data:** 2026-04-02
**Executado por:** Claude Sonnet 4.6 via Claude Code

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

## Etapa 1 — Verificar ambiente ✅

```
Python 3.13.5 | pip 25.1.1 | win32
```

---

## Etapa 2 — Criar venv e instalar dependências ✅

```
import wmi; import win32api; import psutil; import requests → OK
```

---

## Etapa 3 — Suíte de testes unitários ✅

```
60 passed in 1.45s
```

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
Pending: 1 | Batch size: 1 | After mark_sent: 0
```
> Nota: `os.remove` falha com PermissionError no Windows por lock do SQLite — lógica de negócio correta.

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

---

## Etapa 5 — WMI Watcher ✅

**Bug corrigido (commit `0fe997c`):** `watch_for` aceita `'creation'`/`'deletion'`, não `'__InstanceCreationEvent'`. Objeto retornado é o evento diretamente, não tem `.NewValue`/`.PreviousValue`.

```
EVENTO: connected | Dispositivo de Entrada USB | VID:1EA7 PID:9018 | serial:None  (×3)
EVENTO: connected | USB Composite Device       | VID:1EA7 PID:9018 | serial:None  (×1)
Total de eventos capturados: 4
```

---

## Etapa 6 — Configurar conexão com o servidor ✅

- Token gerado: `...e1982f37` (64 chars hex)
- URL salva: `https://inventario.in9automacao.com.br`
- Conectividade confirmada: servidor retornou JSON (401 = token ainda não registrado, esperado)

**Bug corrigido (commit `be1dc88`):** o `POST /api/agent/register/new` exige o token no body (além do payload de hostname/mac/bios). Corrigido em `reporter.py`.

---

## Etapa 7 — Registrar a máquina no servidor ✅

```json
{
  "success": true,
  "data": {
    "machine_id": "0337706b-2e43-11f1-919e-c4e8d4b259f8",
    "status": "pending",
    "message": "Agente registrado. Aguardando aprovação do administrador."
  }
}
```

`machine_id`: `0337706b-2e43-11f1-919e-c4e8d4b259f8`

---

## Etapa 8 — Agente standalone (aprovado) ✅

**Bugs corrigidos (commit `be1dc88`):**
1. `usb_monitor.py`: WMI em thread separada exige `pythoncom.CoInitialize()` antes de `wmi.WMI()` — sem isso lançava `x_wmi_uninitialised_thread`
2. `service.py`: resposta do `/api/agent/register` retorna `{'success': True, 'data': {...}}` — código acessava `resp.get('status')` ao invés de `resp['data']['status']`

**Console do agente:**
```
[INFO] IN9USBAgent v1.0.0 iniciando...
[INFO] Registro OK — status: active
[INFO] WMI watchers registrados — aguardando eventos USB...
[INFO] DISCONNECTED — Dispositivo de Entrada USB [VID:1EA7 PID:9018]  (×3)
[INFO] DISCONNECTED — USB Composite Device [VID:1EA7 PID:9018]        (×1)
[INFO] CONNECTED — Dispositivo de Entrada USB [VID:1EA7 PID:9018]     (×3)
[INFO] CONNECTED — USB Composite Device [VID:1EA7 PID:9018]           (×1)
```

**Buffer após execução:** 0 eventos pendentes → todos enviados com sucesso.

**Confirmação no portal** (`/usb-monitoramento` → Feed de Eventos):
- ✅ Eventos chegaram no servidor
- Dispositivo: `USB Composite Device` / `Dispositivo de Entrada USB`
- VID/PID: `1EA7:9018`
- Máquina: `arthur-desktop`
- Hash: `985e67dbd3fc64e0...` (por modelo — serial instável)
- Eventos connected ↑ e disconnected ↓ visíveis no feed

---

## Etapa 9 — Buffer offline ⏳ Pendente

---

## Bugs encontrados e corrigidos

| Commit | Arquivo | Bug |
|---|---|---|
| `0fe997c` | `usb_monitor.py` | `watch_for` com nome errado do evento WMI; `.NewValue`/`.PreviousValue` inexistentes |
| `be1dc88` | `usb_monitor.py` | Faltava `CoInitialize/CoUninitialize` para uso de WMI em thread |
| `be1dc88` | `reporter.py` | Token não enviado no body do `register/new` |
| `be1dc88` | `service.py` | Resposta do servidor aninhada em `data` não era extraída corretamente |
