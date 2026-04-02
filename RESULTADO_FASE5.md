# Resultado — Etapas 1 a 9: Testes completos do agente USB

**Data:** 2026-04-02
**Executado por:** Claude Sonnet 4.6 via Claude Code

---

## Ambiente

| Item | Valor |
|---|---|
| OS | Windows 11 Pro for Workstations 10.0.26200 |
| Hostname | arthur-desktop |
| Python | 3.13.5 |
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
mouse / pen_drive / unknown / peripheral
```

### 4c. local_db.py ✅
```
Pending: 1 | Batch size: 1 | After mark_sent: 0
```
> `os.remove` do script de teste falha com PermissionError no Windows por lock do SQLite — lógica correta, limitação do script de teste.

### 4d. specs.py ✅
```json
{
  "hostname": "arthur-desktop",
  "cpu": "AMD Ryzen 5 5600G with Radeon Graphics",
  "cpu_cores": 6, "cpu_threads": 12, "ram_gb": 7.8,
  "disks": [
    {"label": "C:\\", "total_gb": 1862.3, "type": "SSD"},
    {"label": "D:\\", "total_gb": 930.9,  "type": "SSD"}
  ],
  "gpu": "Parsec Virtual Display Adapter",
  "os": "Microsoft Windows 11 Pro for Workstations 64 bits",
  "os_build": "26200", "bios_serial": "System Serial Number",
  "bios_version": "3611", "mac_address": "E8:9C:25:3B:2B:A7"
}
```

---

## Etapa 5 — WMI Watcher ✅

**Bug corrigido:** `watch_for` aceita `'creation'`/`'deletion'`, não os nomes completos dos eventos WMI. Objeto retornado não tem `.NewValue`/`.PreviousValue`.

```
EVENTO: connected | Dispositivo de Entrada USB | VID:1EA7 PID:9018 (×3)
EVENTO: connected | USB Composite Device       | VID:1EA7 PID:9018 (×1)
Total de eventos capturados: 4
```

---

## Etapa 6 — Configurar conexão com o servidor ✅

- Token gerado: `...e1982f37` (64 chars)
- URL: `https://inventario.in9automacao.com.br`
- Servidor acessível — retornou JSON

**Bug corrigido:** `POST /api/agent/register/new` exige token no body.

---

## Etapa 7 — Registrar a máquina no servidor ✅

```json
{"success": true, "data": {
  "machine_id": "0337706b-2e43-11f1-919e-c4e8d4b259f8",
  "status": "pending"
}}
```

---

## Etapa 8 — Agente standalone (aprovado) ✅

**Bugs corrigidos:**
1. `usb_monitor.py`: faltava `CoInitialize/CoUninitialize` para WMI em thread
2. `service.py`: resposta do servidor aninhada em `data` não era extraída
3. `reporter.py`: token não incluído no body do `register/new`

**Console:**
```
[INFO] IN9USBAgent v1.0.0 iniciando...
[INFO] Registro OK — status: active
[INFO] WMI watchers registrados — aguardando eventos USB...
[INFO] DISCONNECTED — Dispositivo de Entrada USB [VID:1EA7 PID:9018] (×4)
[INFO] CONNECTED  — Dispositivo de Entrada USB [VID:1EA7 PID:9018]   (×4)
```

**Portal** (`/usb-monitoramento` → Feed de Eventos): eventos chegaram ✅

---

## Etapa 9 — Buffer offline ✅

**Método:** URL trocada para `http://127.0.0.1:19999` para simular offline.

**Com servidor inacessível:**
```
[WARNING] Servidor offline — enfileirando evento no buffer local
[INFO]    Buffer local: 1 evento(s) pendente(s)
[WARNING] Servidor offline — enfileirando evento no buffer local
[INFO]    Buffer local: 2 evento(s) pendente(s)
...
[WARNING] 3 evento(s) pendente(s) no buffer — servidor inacessível, tentando novamente em 30s
```

**Após restaurar conexão:**
```
[INFO] Reenviando 3 evento(s) do buffer offline...
[INFO] 3/3 evento(s) do buffer enviados com sucesso
```

Buffer antes: 3 | Buffer depois: 0 ✅

---

## Bugs encontrados e corrigidos

| Commit | Arquivo | Bug |
|---|---|---|
| `0fe997c` | `usb_monitor.py` | `watch_for` com nome errado; `.NewValue`/`.PreviousValue` inexistentes |
| `be1dc88` | `usb_monitor.py` | Faltava `CoInitialize/CoUninitialize` para WMI em thread |
| `be1dc88` | `reporter.py` | Token não enviado no body do `register/new` |
| `be1dc88` | `service.py` | Resposta do servidor aninhada em `data` não extraída |
| `1a8bc3e` | `reporter.py` | `is_online()` usava porta fixa (80/443) em vez da porta real da URL |
| `1a8bc3e` | `service.py` | `_handle_usb_event` enfileirava antes de enviar — bug marcava eventos antigos como enviados |
| `1a8bc3e` | `service.py` | Logs de offline em `debug` (invisíveis) — elevados para `warning` |
| `1a8bc3e` | `__main__.py` | Encoding quebrado no console Windows — `stdout.reconfigure(utf-8)` |
| (etapa 10) | `.venv/` | `python313.dll` ausente no venv — pythonservice.exe não encontrava a DLL ao rodar como serviço |

---

## Etapa 10 — Windows Service ✅

**Causa raiz do erro 1053:** `pythonservice.exe` roda como LocalSystem sem herdar o PATH do usuário.
A `python313.dll` não estava no diretório do executável (`.venv\`), portanto o processo crashava antes de inicializar o Python.

**Fix aplicado:**
1. Copiado `python313.dll` para `.venv\` (junto com `pythoncom313.dll` e `pywintypes313.dll`)
2. PYTHONPATH configurado no registro do serviço via `winreg` (usando junction `C:\in9agent` para evitar Unicode no path)
3. ImagePath atualizado para usar o junction: `"C:\in9agent\.venv\pythonservice.exe"`

**Comandos de instalação (como Administrador):**
```
python -m agent install
reg add HKLM\SYSTEM\...\IN9USBAgent /v Environment /t REG_MULTI_SZ /d "PYTHONPATH=C:\in9agent;..."
sc start IN9USBAgent
```

**Resultado:**
```
sc query IN9USBAgent
  ESTADO : 4  RUNNING
```

**Event Log (Application):**
```
The IN9USBAgent service has started.
```

**Status final:** Serviço instalado, iniciado e monitorando eventos USB em background ✅

