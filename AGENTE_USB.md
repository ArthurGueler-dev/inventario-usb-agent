# Agente de Monitoramento USB — Especificação Técnica

**Versão:** 1.1
**Data:** 2026-04-01
**Status:** Em desenvolvimento — Fases 2, 3 e 4 concluídas | Fase 1 pendente

---

## 1. Visão Geral e Objetivos

### O que é

O Agente USB é um serviço Windows leve que monitora conexões e desconexões de periféricos USB em tempo real, reportando eventos para o servidor central do Inventário TI. O sistema permite rastrear a movimentação física de dispositivos entre máquinas, detectar usos suspeitos (ex.: pendrives movidos entre computadores enquanto ainda listados como conectados) e enriquecer o cadastro do inventário com dados capturados automaticamente da máquina.

### Por que existe

O sistema atual de inventário exige cadastro manual de conexões. Isso cria lacunas:
- Periféricos são movidos sem registro
- Não há visibilidade sobre quais dispositivos USB estão em uso agora
- Cadastrar specs de uma máquina nova é lento e propenso a erros

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────────┐
│  Máquina Windows (colaborador)                                      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  IN9USBAgent (Windows Service)                               │   │
│  │                                                              │   │
│  │  usb_monitor.py ─── WMI Win32_PnPEntity (eventos USB)       │   │
│  │  hasher.py      ─── SHA256(VID:PID:serial)                  │   │
│  │  specs.py       ─── CPU/RAM/discos/GPU/OS/BIOS              │   │
│  │  local_db.py    ─── SQLite (buffer offline)                 │   │
│  │  reporter.py    ─── HTTP POST para /api/agent/*             │   │
│  │  tray.py        ─── ícone bandeja sistema (verde/amarelo/   │   │
│  │                     vermelho)                               │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
└──────────────────────────────│──────────────────────────────────────┘
                               │  HTTPS + X-Agent-Token
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  VPS — Express (inventario-ti)                                      │
│                                                                     │
│  server/middleware/agentAuth.js  ← valida token SHA256             │
│  server/routes/agent.js          ← /api/agent/*                    │
│  server/routes/usb.js            ← /api/usb-*  (web frontend)     │
│                                                                     │
│  Banco inventario_ti (MariaDB)                                      │
│  ├── inv_agent_machines                                             │
│  ├── inv_usb_devices                                                │
│  ├── inv_usb_events                                                 │
│  └── inv_usb_alerts                                                 │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend React (inventario3.0)                                     │
│                                                                     │
│  AgentMachinesPage.tsx   ← aprovar/revogar agentes       ✅ criado  │
│  UsbAlertsPage.tsx       ← alertas + dispositivos + feed ✅ criado  │
│  (MonitoringPage não foi alterada — feed está no UsbAlertsPage)    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Arquitetura — 3 Componentes

### A. Agente Windows (Python 3.11)

**Tecnologias:**

| Biblioteca | Uso |
|---|---|
| `wmi` + `pywin32` | Eventos USB via `Win32_PnPEntity` |
| `psutil` | Info de processos, RAM, discos |
| `requests` | HTTP client para o servidor |
| `sqlite3` (stdlib) | Buffer offline local |
| `pystray` + `Pillow` | Ícone na bandeja do sistema |
| `pywin32` | Instalação como Windows Service |
| `PyInstaller` | Empacotamento em `.exe` |

**Comportamento do serviço:**

- Roda como Windows Service (`IN9USBAgent`) com conta `LocalService`
- Ao iniciar: registra/atualiza a máquina via `POST /api/agent/register` com specs completas
- Loop principal: WMI watcher assíncrono em `Win32_PnPEntity` (eventos `__InstanceCreationEvent` e `__InstanceDeletionEvent`)
- A cada evento USB: calcula hash_id, insere no SQLite local, tenta `POST /api/agent/usb-event`
- Se offline: acumula eventos no SQLite e reenvia em lote quando conectividade volta
- Heartbeat: `POST /api/agent/heartbeat` a cada 5 minutos

**Ícone na bandeja:**

| Cor | Significado |
|---|---|
| Verde | Conectado, reportando normalmente |
| Amarelo | Offline — eventos sendo acumulados localmente |
| Vermelho | Erro de configuração ou serviço parado |

**Distribuição:**
- Empacotado com PyInstaller em `usb_agent.exe` (single binary)
- `install.bat` instala o serviço Windows e configura token + URL do servidor
- Auto-update: agente verifica `GET /api/agent/version` e baixa nova versão se `needs_update: true`

---

### B. Backend — Rotas no Express existente

As novas rotas são adicionadas ao servidor Express existente (`server/server.js`), **não** em microserviço separado.

**Arquivos criados:** ✅

```
server/
├── middleware/
│   └── agentAuth.js          ✅ criado
├── routes/
│   ├── agent.js              ✅ criado (rotas do agente)
│   └── usb.js                ✅ criado (rotas do frontend web)
└── migrations/
    └── 001_usb_agent.sql     ✅ criado e executado no VPS
```

**Registro em `server.js` (implementado):**

```js
// IMPORTANTE: usb.js define as rotas com caminhos completos (/usb-machines, etc.)
// Por isso o router é montado UMA vez em /api (não em cada prefixo separado)
app.use('/api/agent', require('./routes/agent'));
app.use('/api',       require('./routes/usb'));
```

> ⚠️ **Atenção:** Montar o mesmo router em múltiplos prefixos (`/api/usb-machines`, `/api/usb-devices`…) não funciona porque Express faz strip do prefixo antes de passar ao router, e as rotas internas têm o caminho completo. O padrão correto é um único `app.use('/api', router)`.


**Rotas do agente (`/api/agent/*`):** ✅ implementadas

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| `POST` | `/api/agent/register/new` | Pública | Primeira instalação — cria registro + retorna token gerado |
| `POST` | `/api/agent/register` | X-Agent-Token (allowPending) | Atualiza specs/versão de agente existente |
| `POST` | `/api/agent/heartbeat` | X-Agent-Token | Atualiza last_seen e agent_version |
| `POST` | `/api/agent/usb-event` | X-Agent-Token | Reporta evento USB — upsert fingerprint + evento + detecção de movimentação (transacional) |
| `GET` | `/api/agent/version` | X-Agent-Token (allowPending) | Retorna `current_version`, `needs_update`, `download_url` |

**Rotas do frontend web (`/api/usb-*`):** ✅ implementadas

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| `GET` | `/api/usb-machines` | MSAL JWT | Lista máquinas — filtro `?status=` |
| `PUT` | `/api/usb-machines/:id/approve` | MSAL JWT | Aprova agente pendente — registra `aprovado_por`/`em` |
| `PUT` | `/api/usb-machines/:id/link` | MSAL JWT | Vincula agente a `inv_dispositivos.id` |
| `DELETE` | `/api/usb-machines/:id` | MSAL JWT | Revoga agente (soft delete via status='revoked') |
| `GET` | `/api/usb-devices` | MSAL JWT | Lista fingerprints USB — filtros `?machine_id`, `?device_type`, `?q` |
| `GET` | `/api/usb-events` | MSAL JWT | Feed de eventos — filtros `?machine_id`, `?hash_id`, `?event_type`, `?since`, `?limit` (max 500) |
| `GET` | `/api/usb-alerts` | MSAL JWT | Lista alertas — `?status` (default 'open'), `?type`, `?machine_id` |
| `PUT` | `/api/usb-alerts/:id` | MSAL JWT | Atualiza status do alerta (open/acknowledged/resolved/false_positive) |
| `GET` | `/api/usb-stats` | MSAL JWT | Stats agregadas via `Promise.all` de 4 queries |

---

### C. Frontend — Novas páginas React

**Arquivos criados:** ✅

```
src/
├── lib/
│   └── usbApi.ts                 ✅ criado — tipos TypeScript + wrappers fetch
└── pages/
    ├── AgentMachinesPage.tsx     ✅ criado
    └── UsbAlertsPage.tsx         ✅ criado
```

> Não foi criada a pasta `components/usb/` — todos os sub-componentes vivem inline dentro de cada page (padrão do projeto).

**`src/lib/usbApi.ts`:**
- Tipos: `AgentMachine`, `AgentMachineSpecs`, `UsbDevice`, `UsbEvent`, `UsbAlert`, `UsbStats`
- Helpers privados: `get<T>()`, `put<T>()`, `del<T>()` com fetch padrão
- Funções exportadas: `fetchAgentMachines`, `approveAgent`, `linkMachineToDevice`, `revokeAgent`, `fetchUsbDevices`, `fetchUsbEvents`, `fetchUsbAlerts`, `updateAlertStatus`, `fetchUsbStats`

**`src/pages/AgentMachinesPage.tsx`** — rota `/usb-agentes`:
- Stats bar: total / online / pendentes / revogados
- Banner de aprovação quando há agentes `pending`
- Filter chips (todos/ativos/pendentes/revogados) + campo de busca
- `MachineCard` com `SpecsPanel` (CPU cores/threads, RAM, GPU, OS+build, discos com tags SSD/HDD, serial da BIOS)
- `LinkModal` — carrega dispositivos notebooks/desktops/servidores, filtra por texto, salva vínculo
- Online detection: `last_seen_at` dentro de 7 minutos = online
- Ações: Aprovar (imediato), Vincular (modal), Revogar (modal de confirmação)

**`src/pages/UsbAlertsPage.tsx`** — rota `/usb-monitoramento`:
- **Aba "Alertas":** `AlertCard` com metadados por tipo (relocated/simultaneous/unknown_device), badges de severidade/status, fluxo from→to, ações inline (acknowledge/resolve/false_positive), filtros por status + tipo + busca
- **Aba "Dispositivos USB":** tabela de fingerprints — VID:PID, indicador de estabilidade de serial, última máquina, link ao inventário, filtro por tipo
- **Aba "Feed de Eventos":** auto-refresh a cada 30s com countdown, toggle de live mode, filtro por máquina, color coding connect/disconnect

**Rotas adicionadas em `src/App.tsx`:**
```tsx
<Route path="/usb-agentes"       element={<ProtectedRoute><AgentMachinesPage /></ProtectedRoute>} />
<Route path="/usb-monitoramento" element={<ProtectedRoute><UsbAlertsPage /></ProtectedRoute>} />
```

**Nav items adicionados em `src/components/layout/Header.tsx`:**
```ts
{ name: 'Agentes USB',  href: '/usb-agentes',       icon: Server      },
{ name: 'Monitor USB',  href: '/usb-monitoramento',  icon: ShieldAlert },
```

> `MonitoringPage.tsx` **não foi alterada** — o feed USB está dentro de `UsbAlertsPage` (aba "Feed de Eventos").

---

## 3. Hash ID — Fingerprint do Dispositivo

### Cálculo

```python
# hasher.py
import hashlib, re

UNSTABLE_SERIAL_PATTERN = re.compile(r'^\d&[A-F0-9]{8}', re.IGNORECASE)

def is_stable_serial(serial: str | None) -> bool:
    """
    Retorna False para seriais gerados pelo Windows (padrão \d&[A-F0-9]{8}).
    Esses seriais mudam entre reconexões e não identificam o dispositivo físico.
    """
    if not serial or serial.strip() == '':
        return False
    return not bool(UNSTABLE_SERIAL_PATTERN.match(serial.strip()))

def compute_hash_id(vid: str, pid: str, serial: str | None) -> tuple[str, bool]:
    """
    Retorna (hash_id, serial_is_stable).

    Se o serial for estável: hash = SHA256(VID:PID:serial_normalizado)
    Se não for:              hash = SHA256(VID:PID)  ← identifica modelo, não unidade

    Retorna também se o serial é estável, para armazenar em inv_usb_devices.serial_is_stable.
    """
    vid_norm = vid.upper().zfill(4)
    pid_norm = pid.upper().zfill(4)

    stable = is_stable_serial(serial)
    if stable:
        serial_norm = serial.strip().upper()
        fingerprint = f"{vid_norm}:{pid_norm}:{serial_norm}"
    else:
        fingerprint = f"{vid_norm}:{pid_norm}"

    hash_id = hashlib.sha256(fingerprint.encode()).hexdigest()
    return hash_id, stable
```

### Consequências práticas

| Situação | Resultado |
|---|---|
| Pendrive com serial de fábrica | `serial_is_stable = TRUE` → rastreado por unidade |
| Mouse/teclado sem serial | `serial_is_stable = FALSE` → rastreado por modelo (VID+PID) |
| Mesmo modelo, dois dispositivos sem serial | Mesmo `hash_id` — são tratados como "classe de dispositivo", não como unidades individuais |

---

## 4. Lógica de Detecção de Movimentação

### Fluxo ao receber um `usb-event` de tipo `connected`

```
1. Calcular hash_id do dispositivo

2. Buscar em inv_usb_devices WHERE hash_id = ?

3. SE não existe:
   → INSERT novo fingerprint
   → INSERT evento 'connected'
   → FIM (primeiro registro, sem alerta)

4. SE existe E last_seen_machine_id = máquina_atual:
   → INSERT evento 'connected'
   → FIM (reconexão normal na mesma máquina)

5. SE existe E last_seen_machine_id != máquina_atual:

   5a. Buscar último evento em inv_usb_events WHERE usb_device_id = ? ORDER BY created_at DESC LIMIT 1

   5b. SE último evento = 'disconnected':
       → alerta tipo 'relocated' (severity: 'info')
       → "Dispositivo foi movido de [máquina_anterior] para [máquina_atual]"

   5c. SE último evento = 'connected':
       → alerta tipo 'simultaneous' (severity: 'warning')
       → "Dispositivo aparece conectado em [máquina_anterior] e agora em [máquina_atual] — possível clone"

   5d. INSERT alerta em inv_usb_alerts
   5e. UPDATE inv_usb_devices SET last_seen_machine_id = máquina_atual

6. INSERT evento 'connected' em inv_usb_events
```

---

## 5. Schema do Banco — 4 Novas Tabelas

As tabelas seguem **exatamente** as convenções de `schema.sql`:
- Prefixo `inv_`
- `CHAR(36)` com `UUID()` para entidades portáveis
- `BIGINT UNSIGNED AUTO_INCREMENT` para logs (volume alto)
- `CHECK constraints` no lugar de ENUMs
- `snake_case` em tudo
- `created_at` / `updated_at` em todas as tabelas
- Soft delete via `deleted_at` onde aplicável

```sql
-- =============================================================================
-- USB AGENT — 4 novas tabelas
-- Banco: inventario_ti  |  MariaDB 10.11
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. MÁQUINAS COM AGENTE INSTALADO
-- Cada instalação do agente gera um registro aqui.
-- status='pending' até aprovação manual no frontend web.
-- -----------------------------------------------------------------------------

CREATE TABLE inv_agent_machines (
  id                  CHAR(36)      NOT NULL DEFAULT (UUID()),

  -- Identificação da máquina
  hostname            VARCHAR(255)  NOT NULL,
  mac_address         VARCHAR(17)   DEFAULT NULL,   -- ex: AA:BB:CC:DD:EE:FF
  bios_serial         VARCHAR(150)  DEFAULT NULL,   -- serial da BIOS/motherboard
  os_version          VARCHAR(255)  DEFAULT NULL,

  -- Specs capturadas na instalação/registro
  specs               JSON          DEFAULT NULL,
  -- Exemplo de estrutura:
  -- {
  --   "cpu": "Intel Core i5-10400 @ 2.90GHz",
  --   "cpu_cores": 6,
  --   "ram_gb": 16,
  --   "disks": [{"label": "C:", "total_gb": 476, "type": "SSD"}],
  --   "gpu": "Intel UHD Graphics 630",
  --   "os": "Windows 10 Pro 22H2",
  --   "bios_version": "F.70"
  -- }

  -- Autenticação
  token_hash          CHAR(64)      NOT NULL,        -- SHA256 do token em texto claro
  status              VARCHAR(20)   NOT NULL DEFAULT 'pending',
  -- pending → active → revoked

  -- Versão do agente instalado
  agent_version       VARCHAR(20)   DEFAULT NULL,    -- ex: 1.2.3

  -- Vínculo opcional ao inventário (pode ser feito depois, no frontend)
  dispositivo_id      CHAR(36)      DEFAULT NULL,    -- FK → inv_dispositivos.id

  -- Aprovação
  aprovado_por        VARCHAR(255)  DEFAULT NULL,
  aprovado_em         DATETIME      DEFAULT NULL,

  -- Telemetria
  last_seen_at        DATETIME      DEFAULT NULL,
  last_ip             VARCHAR(45)   DEFAULT NULL,

  created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at          DATETIME      DEFAULT NULL,

  PRIMARY KEY (id),

  UNIQUE KEY uq_token_hash   (token_hash),
  UNIQUE KEY uq_bios_serial  (bios_serial),

  INDEX idx_hostname         (hostname),
  INDEX idx_status           (status),
  INDEX idx_dispositivo_id   (dispositivo_id),
  INDEX idx_last_seen_at     (last_seen_at),
  INDEX idx_deleted_at       (deleted_at),

  CONSTRAINT fk_agent_machines_dispositivo
    FOREIGN KEY (dispositivo_id) REFERENCES inv_dispositivos(id)
      ON DELETE SET NULL,

  CONSTRAINT chk_agent_status CHECK (
    status IN ('pending','active','revoked')
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Máquinas com o agente USB instalado';


-- -----------------------------------------------------------------------------
-- 2. FINGERPRINTS DE DISPOSITIVOS USB
-- Um registro por hash_id único. Rastreia a "identidade" do dispositivo físico.
-- -----------------------------------------------------------------------------

CREATE TABLE inv_usb_devices (
  id                    CHAR(36)      NOT NULL DEFAULT (UUID()),

  hash_id               CHAR(64)      NOT NULL,  -- SHA256(VID:PID[:serial])
  vid                   CHAR(4)       NOT NULL,  -- Vendor ID hexadecimal (ex: 045E)
  pid                   CHAR(4)       NOT NULL,  -- Product ID hexadecimal (ex: 082F)
  serial_number         VARCHAR(255)  DEFAULT NULL,
  serial_is_stable      TINYINT(1)    NOT NULL DEFAULT 0,

  -- Metadados do dispositivo
  friendly_name         VARCHAR(255)  DEFAULT NULL,  -- nome do Win32_PnPEntity
  manufacturer          VARCHAR(255)  DEFAULT NULL,
  device_type           VARCHAR(50)   NOT NULL DEFAULT 'peripheral',
  -- Mapeado a DeviceType de src/types/index.ts

  -- Última localização conhecida
  last_seen_machine_id  CHAR(36)      DEFAULT NULL,  -- FK → inv_agent_machines.id
  last_seen_at          DATETIME      DEFAULT NULL,
  last_event            VARCHAR(20)   DEFAULT NULL,  -- 'connected' | 'disconnected'

  -- Vínculo opcional ao inventário
  dispositivo_id        CHAR(36)      DEFAULT NULL,  -- FK → inv_dispositivos.id

  created_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),

  UNIQUE KEY uq_hash_id        (hash_id),

  INDEX idx_vid_pid            (vid, pid),
  INDEX idx_device_type        (device_type),
  INDEX idx_last_seen_machine  (last_seen_machine_id),
  INDEX idx_dispositivo_id     (dispositivo_id),
  INDEX idx_last_seen_at       (last_seen_at),

  CONSTRAINT fk_usb_devices_machine
    FOREIGN KEY (last_seen_machine_id) REFERENCES inv_agent_machines(id)
      ON DELETE SET NULL,

  CONSTRAINT fk_usb_devices_dispositivo
    FOREIGN KEY (dispositivo_id) REFERENCES inv_dispositivos(id)
      ON DELETE SET NULL,

  CONSTRAINT chk_usb_device_type CHECK (
    device_type IN (
      'notebook','desktop','cellphone','peripheral','fone','mouse','teclado',
      'headset','monitor_peripheral','cabo_hdmi','cabo_vga','adaptador_hdmi_vga',
      'adaptador_rede','adaptador_rede_dongle_wifi','adaptador_rede_usb',
      'adaptador_rede_usbc','webcam','impressora','scanner','multifuncional',
      'projetor','tv','no_break','estabilizador','adaptador_usb','extensor_usb',
      'adaptador_bluetooth','conversor_hdmi_vga','cabo_usb','cabo_ethernet',
      'docking_station','tablet','switch_rede','roteador','access_point',
      'hd_externo','pen_drive','servidor','unknown'
    )
  ),

  CONSTRAINT chk_usb_last_event CHECK (
    last_event IS NULL OR last_event IN ('connected','disconnected')
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Fingerprints únicos de dispositivos USB detectados pelo agente';


-- -----------------------------------------------------------------------------
-- 3. EVENTOS USB
-- Append-only. Um registro por cada connect/disconnect.
-- BIGINT porque volume pode ser alto (centenas por dia por máquina).
-- -----------------------------------------------------------------------------

CREATE TABLE inv_usb_events (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

  usb_device_id   CHAR(36)        NOT NULL,   -- FK → inv_usb_devices.id
  machine_id      CHAR(36)        NOT NULL,   -- FK → inv_agent_machines.id
  event_type      VARCHAR(20)     NOT NULL,   -- 'connected' | 'disconnected'

  -- Snapshot do estado do dispositivo no momento do evento
  friendly_name   VARCHAR(255)    DEFAULT NULL,
  vid             CHAR(4)         DEFAULT NULL,
  pid             CHAR(4)         DEFAULT NULL,
  serial_number   VARCHAR(255)    DEFAULT NULL,
  pnp_device_id   VARCHAR(500)    DEFAULT NULL,  -- PNPDeviceID completo do Windows

  -- Timestamp do evento na máquina local (pode diferir de created_at)
  event_time      DATETIME        NOT NULL,

  created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (id),

  INDEX idx_usb_device_id   (usb_device_id),
  INDEX idx_machine_id      (machine_id),
  INDEX idx_event_type      (event_type),
  INDEX idx_event_time      (event_time),
  INDEX idx_created_at      (created_at),

  CONSTRAINT fk_usb_events_device
    FOREIGN KEY (usb_device_id) REFERENCES inv_usb_devices(id),

  CONSTRAINT fk_usb_events_machine
    FOREIGN KEY (machine_id) REFERENCES inv_agent_machines(id),

  CONSTRAINT chk_usb_event_type CHECK (
    event_type IN ('connected','disconnected')
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Log append-only de todos os eventos USB detectados';


-- -----------------------------------------------------------------------------
-- 4. ALERTAS USB
-- Gerados automaticamente pelo backend quando regras de movimentação disparam.
-- -----------------------------------------------------------------------------

CREATE TABLE inv_usb_alerts (
  id              CHAR(36)      NOT NULL DEFAULT (UUID()),

  usb_device_id   CHAR(36)      NOT NULL,   -- FK → inv_usb_devices.id
  alert_type      VARCHAR(30)   NOT NULL,
  -- 'relocated'     → dispositivo mudou de máquina normalmente
  -- 'simultaneous'  → dispositivo aparece em duas máquinas ao mesmo tempo
  -- 'unknown_device'→ device_type = 'unknown', requer classificação manual

  severity        VARCHAR(10)   NOT NULL DEFAULT 'info',
  -- 'info' | 'warning' | 'critical'

  -- Máquinas envolvidas
  from_machine_id CHAR(36)      DEFAULT NULL,  -- FK → inv_agent_machines.id
  to_machine_id   CHAR(36)      DEFAULT NULL,  -- FK → inv_agent_machines.id

  -- Evento que gerou o alerta
  trigger_event_id BIGINT UNSIGNED DEFAULT NULL,  -- FK → inv_usb_events.id

  message         TEXT          DEFAULT NULL,  -- descrição legível do alerta

  status          VARCHAR(20)   NOT NULL DEFAULT 'open',
  -- 'open' | 'acknowledged' | 'resolved' | 'false_positive'

  -- Resolução
  resolvido_por   VARCHAR(255)  DEFAULT NULL,
  resolvido_em    DATETIME      DEFAULT NULL,
  notas_resolucao TEXT          DEFAULT NULL,

  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),

  INDEX idx_usb_device_id    (usb_device_id),
  INDEX idx_alert_type       (alert_type),
  INDEX idx_severity         (severity),
  INDEX idx_status           (status),
  INDEX idx_from_machine     (from_machine_id),
  INDEX idx_to_machine       (to_machine_id),
  INDEX idx_created_at       (created_at),

  CONSTRAINT fk_usb_alerts_device
    FOREIGN KEY (usb_device_id) REFERENCES inv_usb_devices(id),

  CONSTRAINT fk_usb_alerts_from_machine
    FOREIGN KEY (from_machine_id) REFERENCES inv_agent_machines(id)
      ON DELETE SET NULL,

  CONSTRAINT fk_usb_alerts_to_machine
    FOREIGN KEY (to_machine_id) REFERENCES inv_agent_machines(id)
      ON DELETE SET NULL,

  CONSTRAINT chk_alert_type CHECK (
    alert_type IN ('relocated','simultaneous','unknown_device')
  ),

  CONSTRAINT chk_alert_severity CHECK (
    severity IN ('info','warning','critical')
  ),

  CONSTRAINT chk_alert_status CHECK (
    status IN ('open','acknowledged','resolved','false_positive')
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Alertas de movimentação e anomalias de dispositivos USB';
```

---

## 6. Estrutura do Projeto — Agente (novo repositório)

O agente reside em um repositório separado para facilitar o build do `.exe` e deploy nas máquinas.

```
inventario-usb-agent/
│
├── agent/
│   ├── __main__.py          # Entry point — inicia service ou modo standalone
│   ├── service.py           # Classe WindowsService (pywin32 servicemanager)
│   ├── usb_monitor.py       # WMI watcher — eventos Win32_PnPEntity
│   ├── specs.py             # Captura specs da máquina (CPU/RAM/discos/GPU/OS/BIOS)
│   ├── reporter.py          # HTTP client — POST para /api/agent/*
│   ├── local_db.py          # SQLite buffer offline + config (URL, token)
│   ├── hasher.py            # SHA256 hash_id + is_stable_serial
│   ├── classifier.py        # PNP class GUID → device_type (DeviceType TS)
│   ├── updater.py           # Auto-update — verifica /api/agent/version
│   └── tray.py              # Ícone na bandeja (pystray)
│
├── build/
│   └── build.bat            # PyInstaller → dist/usb_agent.exe
│
├── installer/
│   ├── install.bat          # Instala serviço Windows + configura token/URL
│   └── uninstall.bat        # Remove serviço
│
├── tests/
│   ├── test_hasher.py
│   ├── test_classifier.py
│   └── test_reporter.py     # Mock HTTP
│
├── requirements.txt
└── README.md
```

**`requirements.txt`:**
```
wmi==1.5.1
pywin32>=306
psutil>=5.9
requests>=2.31
pystray>=0.19
Pillow>=10.0
pyinstaller>=6.0
```

---

## 7. Segurança

### Token do agente

- Na instalação, `install.bat` gera um token aleatório de 256 bits com `python -c "import secrets; print(secrets.token_hex(32))"`
- O token é salvo em texto claro no `local_db.py` (SQLite local, acessível apenas como `LocalService`)
- O servidor armazena **apenas** `SHA256(token)` em `inv_agent_machines.token_hash`
- Se o token for comprometido: revogar no frontend → `status = 'revoked'` → instalar novo token na máquina

### Aprovação de agentes

- Todo agente novo entra com `status = 'pending'`
- Enquanto `pending`, os endpoints `/api/agent/usb-event` e `/api/agent/heartbeat` retornam `403`
- Apenas `/api/agent/register` e `/api/agent/version` são permitidos para agentes pendentes
- O administrador aprova via `PUT /api/usb-machines/:id/approve` no frontend

### Windows Service

- Roda como `LocalService` (não `SYSTEM` nem `LocalSystem`)
- `LocalService` não tem acesso à rede corporativa — o token HTTPS é o único vetor de autenticação

### Rate limiting

- `/api/agent/usb-event`: máximo 120 eventos/minuto por token (implementar com `express-rate-limit` por `token_hash`)
- `/api/agent/heartbeat`: máximo 30 requisições/minuto por token

---

## 8. Exemplos de Código

### `usb_monitor.py` — WMI watcher

```python
# agent/usb_monitor.py
import wmi
import threading
from datetime import datetime, timezone
from typing import Callable

EventCallback = Callable[[dict], None]

class UsbMonitor:
    """
    Monitora eventos de conexão/desconexão USB via WMI Win32_PnPEntity.
    Usa thread dedicada para não bloquear o loop principal do serviço.
    """

    def __init__(self, on_event: EventCallback):
        self._on_event = on_event
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _watch_loop(self):
        c = wmi.WMI()

        watcher_connect    = c.Win32_PnPEntity.watch_for('__InstanceCreationEvent')
        watcher_disconnect = c.Win32_PnPEntity.watch_for('__InstanceDeletionEvent')

        while not self._stop_event.is_set():
            # Conexão
            try:
                event = watcher_connect(timeout_ms=500)
                if event:
                    self._handle(event.NewValue, 'connected')
            except wmi.x_wmi_timed_out:
                pass

            # Desconexão
            try:
                event = watcher_disconnect(timeout_ms=500)
                if event:
                    self._handle(event.PreviousValue, 'disconnected')
            except wmi.x_wmi_timed_out:
                pass

    def _handle(self, pnp_entity, event_type: str):
        if not pnp_entity:
            return

        pnp_id = getattr(pnp_entity, 'PNPDeviceID', '') or ''
        if not pnp_id.startswith('USB\\'):
            return  # Ignorar dispositivos não-USB

        # Extrair VID/PID do PNPDeviceID: USB\VID_045E&PID_082F\...
        vid, pid, serial = self._parse_pnp_id(pnp_id)

        self._on_event({
            'event_type':   event_type,
            'event_time':   datetime.now(timezone.utc).isoformat(),
            'vid':          vid,
            'pid':          pid,
            'serial':       serial,
            'friendly_name': getattr(pnp_entity, 'Name', None),
            'pnp_device_id': pnp_id,
        })

    @staticmethod
    def _parse_pnp_id(pnp_id: str) -> tuple[str, str, str | None]:
        """
        USB\VID_045E&PID_082F\1234567890  →  ('045E', '082F', '1234567890')
        USB\VID_045E&PID_082F&MI_00\...   →  ('045E', '082F', None)
        """
        import re
        vid_match = re.search(r'VID_([0-9A-Fa-f]{4})', pnp_id)
        pid_match = re.search(r'PID_([0-9A-Fa-f]{4})', pnp_id)
        parts = pnp_id.split('\\')
        serial = parts[2] if len(parts) >= 3 and '&' not in parts[2] else None

        vid = vid_match.group(1).upper() if vid_match else '0000'
        pid = pid_match.group(1).upper() if pid_match else '0000'
        return vid, pid, serial
```

---

### `hasher.py` — função `compute_hash_id`

```python
# agent/hasher.py
import hashlib
import re

UNSTABLE_SERIAL_PATTERN = re.compile(r'^\d&[A-F0-9]{8}', re.IGNORECASE)

def is_stable_serial(serial: str | None) -> bool:
    """
    Retorna False para:
    - serial None ou vazio
    - seriais gerados pelo Windows com padrão \d&[A-F0-9]{8} (ex: 3&11583659&0)
    """
    if not serial or not serial.strip():
        return False
    return not bool(UNSTABLE_SERIAL_PATTERN.match(serial.strip()))

def compute_hash_id(vid: str, pid: str, serial: str | None) -> tuple[str, bool]:
    """
    Calcula o fingerprint SHA256 do dispositivo.

    Retorna:
        (hash_id: str, serial_is_stable: bool)
    """
    vid_norm = vid.strip().upper().zfill(4)
    pid_norm = pid.strip().upper().zfill(4)

    stable = is_stable_serial(serial)
    if stable:
        serial_norm = serial.strip().upper()
        fingerprint = f"{vid_norm}:{pid_norm}:{serial_norm}"
    else:
        fingerprint = f"{vid_norm}:{pid_norm}"

    hash_id = hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()
    return hash_id, stable
```

---

### `specs.py` — captura specs da máquina

```python
# agent/specs.py
import wmi
import psutil
import platform
from typing import Any

def capture_machine_specs() -> dict[str, Any]:
    """
    Captura especificações da máquina para enviar no register/heartbeat.
    Roda uma única vez na inicialização do serviço.
    Falha silenciosa: retorna dados parciais se algum subsistema falhar.
    """
    c = wmi.WMI()
    specs: dict[str, Any] = {}

    # CPU
    try:
        cpu = c.Win32_Processor()[0]
        specs['cpu'] = cpu.Name.strip()
        specs['cpu_cores'] = cpu.NumberOfCores
        specs['cpu_threads'] = cpu.NumberOfLogicalProcessors
    except Exception:
        pass

    # RAM
    try:
        ram = psutil.virtual_memory()
        specs['ram_gb'] = round(ram.total / (1024 ** 3), 1)
    except Exception:
        pass

    # Discos
    try:
        discos = []
        for disk in psutil.disk_partitions():
            if 'cdrom' in disk.opts or disk.fstype == '':
                continue
            usage = psutil.disk_usage(disk.mountpoint)
            discos.append({
                'label':    disk.device,
                'total_gb': round(usage.total / (1024 ** 3), 1),
                'type':     _detect_disk_type(c, disk.device),
            })
        specs['disks'] = discos
    except Exception:
        pass

    # GPU
    try:
        gpus = c.Win32_VideoController()
        if gpus:
            specs['gpu'] = gpus[0].Name.strip()
    except Exception:
        pass

    # OS
    try:
        os_info = c.Win32_OperatingSystem()[0]
        specs['os'] = f"{os_info.Caption.strip()} {os_info.OSArchitecture}"
        specs['os_build'] = os_info.BuildNumber
    except Exception:
        specs['os'] = platform.version()

    # BIOS serial
    try:
        bios = c.Win32_BIOS()[0]
        specs['bios_serial'] = bios.SerialNumber.strip()
        specs['bios_version'] = bios.SMBIOSBIOSVersion.strip()
    except Exception:
        pass

    # Hostname / MAC
    try:
        import socket
        specs['hostname'] = socket.gethostname()
    except Exception:
        pass

    return specs


def _detect_disk_type(c: wmi.WMI, drive_letter: str) -> str:
    """Heurística: tenta detectar SSD vs HDD via Win32_DiskDrive."""
    try:
        for disk in c.Win32_DiskDrive():
            if 'SSD' in (disk.Model or '').upper() or disk.MediaType == 'Fixed hard disk media':
                return 'SSD' if 'SSD' in (disk.Model or '').upper() else 'HDD'
    except Exception:
        pass
    return 'unknown'
```

---

### `classifier.py` — PNP class → device_type

Mapeia o `PNPDeviceID` e o `PNP Class GUID` do Windows para os tipos do `DeviceType` de `src/types/index.ts`.

```python
# agent/classifier.py
"""
Classifica dispositivos USB com base em VID/PID e PNP Class.
Os valores de device_type correspondem EXATAMENTE ao DeviceType union em src/types/index.ts.
"""

# Mapeamento de PNP Class GUID → device_type
# Fonte: Win32_PnPEntity.ClassGuid
PNP_CLASS_MAP: dict[str, str] = {
    '{4D36E96C-E325-11CE-BFC1-08002BE10318}': 'fone',            # Sound, video and game controllers
    '{4D36E96B-E325-11CE-BFC1-08002BE10318}': 'mouse',           # Mouse
    '{4D36E96F-E325-11CE-BFC1-08002BE10318}': 'mouse',           # HID
    '{4D36E96A-E325-11CE-BFC1-08002BE10318}': 'teclado',         # Keyboard
    '{6BDD1FC6-810F-11D0-BEC7-08002BE2092F}': 'webcam',          # Image (câmeras)
    '{745A17A0-74D3-11D0-B6FE-00A0C90F57DA}': 'headset',         # Human Interface Device
    '{4D36E967-E325-11CE-BFC1-08002BE10318}': 'hd_externo',      # DiskDrive
    '{36FC9E60-C465-11CF-8056-444553540000}': 'adaptador_usb',   # USB (hubs, adaptadores)
    '{4D36E972-E325-11CE-BFC1-08002BE10318}': 'adaptador_rede',  # Net (adaptadores de rede)
}

# Mapeamento de VID → fabricante (para heurísticas adicionais)
KNOWN_VIDS: dict[str, str] = {
    '045E': 'Microsoft',
    '046D': 'Logitech',
    '04F2': 'Chicony (webcam)',
    '0BDA': 'Realtek',
    '0951': 'Kingston',
    '058F': 'Alcor (leitor de cartão)',
    '04A9': 'Canon',
    '04B8': 'Epson',
    '03F0': 'HP',
    '04E8': 'Samsung',
}

# Heurísticas por nome amigável (substring, case-insensitive)
NAME_HEURISTICS: list[tuple[str, str]] = [
    ('webcam',          'webcam'),
    ('camera',          'webcam'),
    ('headset',         'headset'),
    ('headphone',       'fone'),
    ('earphone',        'fone'),
    ('speaker',         'fone'),
    ('mouse',           'mouse'),
    ('keyboard',        'teclado'),
    ('teclado',         'teclado'),
    ('pen drive',       'pen_drive'),
    ('flash drive',     'pen_drive'),
    ('pendrive',        'pen_drive'),
    ('usb disk',        'hd_externo'),
    ('external',        'hd_externo'),
    ('hub',             'extensor_usb'),
    ('dock',            'docking_station'),
    ('bluetooth',       'adaptador_bluetooth'),
    ('wifi',            'adaptador_rede_dongle_wifi'),
    ('wireless',        'adaptador_rede_dongle_wifi'),
    ('ethernet',        'adaptador_rede_usb'),
    ('lan',             'adaptador_rede_usb'),
    ('printer',         'impressora'),
    ('impressora',      'impressora'),
    ('scanner',         'scanner'),
    ('monitor',         'monitor_peripheral'),
    ('display',         'monitor_peripheral'),
    ('hdmi',            'cabo_hdmi'),
    ('audio',           'fone'),
]


def classify(pnp_class_guid: str | None, friendly_name: str | None, vid: str = '') -> str:
    """
    Retorna um device_type compatível com o DeviceType union do TypeScript.
    Fallback: 'peripheral' para dispositivos reconhecidos mas não classificados,
              'unknown' para dispositivos que não se encaixam em nenhuma categoria.
    """
    # 1. Tentar por Class GUID
    if pnp_class_guid:
        result = PNP_CLASS_MAP.get(pnp_class_guid.upper())
        if result:
            return result

    # 2. Tentar por nome amigável
    if friendly_name:
        name_lower = friendly_name.lower()
        for keyword, device_type in NAME_HEURISTICS:
            if keyword in name_lower:
                return device_type

    # 3. Hubs USB e raízes — ignorar (não são periféricos de usuário)
    if friendly_name and any(x in friendly_name.lower() for x in ['root hub', 'usb hub', 'composite']):
        return 'unknown'

    # 4. Fallback
    return 'peripheral'
```

---

### `agentAuth.js` — middleware Express

```js
// server/middleware/agentAuth.js
const crypto = require('crypto');
const pool   = require('../db');

/**
 * Middleware de autenticação para rotas do agente USB.
 * Valida o header X-Agent-Token verificando SHA256 contra inv_agent_machines.token_hash.
 *
 * Injeta req.agentMachine com os dados da máquina autenticada.
 *
 * Para rotas que aceitam agentes pendentes, passar allowPending: true nas options.
 */
function agentAuth({ allowPending = false } = {}) {
  return async (req, res, next) => {
    const token = req.headers['x-agent-token'];
    if (!token) {
      return res.status(401).json({ success: false, message: 'X-Agent-Token ausente' });
    }

    const tokenHash = crypto
      .createHash('sha256')
      .update(token)
      .digest('hex');

    try {
      const [rows] = await pool.query(
        `SELECT id, hostname, status, agent_version, dispositivo_id
         FROM inv_agent_machines
         WHERE token_hash = ? AND deleted_at IS NULL
         LIMIT 1`,
        [tokenHash]
      );

      if (!rows.length) {
        return res.status(401).json({ success: false, message: 'Token inválido' });
      }

      const machine = rows[0];

      if (machine.status === 'revoked') {
        return res.status(403).json({ success: false, message: 'Token revogado' });
      }

      if (!allowPending && machine.status === 'pending') {
        return res.status(403).json({
          success: false,
          message: 'Agente aguardando aprovação',
          pending: true,
        });
      }

      // Atualizar last_seen_at assincronamente (sem await — não bloqueia a request)
      pool.query(
        'UPDATE inv_agent_machines SET last_seen_at = NOW(), last_ip = ? WHERE id = ?',
        [req.ip, machine.id]
      ).catch(() => {});

      req.agentMachine = machine;
      next();
    } catch (err) {
      console.error('[agentAuth]', err);
      return res.status(500).json({ success: false, message: 'Erro interno de autenticação' });
    }
  };
}

module.exports = agentAuth;
```

---

## 9. Fases de Implementação

| Fase | Status | Escopo | Entregável |
|------|--------|--------|------------|
| **1** | ⏳ Pendente | Agente Python MVP: `usb_monitor.py` + `hasher.py` + `reporter.py` + `service.py` + SQLite buffer | Serviço Windows que detecta e reporta eventos USB |
| **2** | ✅ Concluído | Migration SQL (4 tabelas) + rotas `/api/agent/*` + `agentAuth.js` | Agentes podem registrar, fazer heartbeat e reportar eventos |
| **3** | ✅ Concluído | Rotas `/api/usb-*` + lógica de detecção de movimentação + alertas | Frontend pode consultar dados e alertas são gerados automaticamente |
| **4** | ✅ Concluído | `usbApi.ts` + `AgentMachinesPage.tsx` + `UsbAlertsPage.tsx` + rotas em App.tsx + nav Header | Interface completa de gestão e visualização |
| **5** | ⏳ Pendente | `specs.py` + `classifier.py` + `tray.py` + `updater.py` + PyInstaller build | `.exe` distribuível + auto-update |
| **6** | ⏳ Pendente | Piloto em 3-5 máquinas selecionadas | Validação em produção |

**Próximo passo:** Fase 1 — criar repositório `inventario-usb-agent` e implementar o agente Python MVP.

---

## 10. Payload das Rotas do Agente

### `POST /api/agent/register`

**Request:**
```json
{
  "hostname": "DESKTOP-A1B2C3",
  "agent_version": "1.0.0",
  "specs": {
    "cpu": "Intel Core i5-10400 @ 2.90GHz",
    "cpu_cores": 6,
    "ram_gb": 16,
    "disks": [{ "label": "C:", "total_gb": 476, "type": "SSD" }],
    "gpu": "Intel UHD Graphics 630",
    "os": "Windows 10 Pro 22H2",
    "bios_serial": "PF2BXX12",
    "bios_version": "F.70"
  }
}
```

**Response (primeira instalação — pending):**
```json
{
  "success": true,
  "machine_id": "uuid-da-maquina",
  "status": "pending",
  "message": "Agente registrado. Aguardando aprovação do administrador."
}
```

### `POST /api/agent/usb-event`

**Request:**
```json
{
  "event_type": "connected",
  "event_time": "2026-04-01T14:23:11.000Z",
  "vid": "046D",
  "pid": "C52B",
  "serial": "3&11583659&0",
  "friendly_name": "Logitech USB Receiver",
  "pnp_device_id": "USB\\VID_046D&PID_C52B\\3&11583659&0&1"
}
```

**Response:**
```json
{
  "success": true,
  "hash_id": "a3f8...",
  "alert": null
}
```

**Response (com alerta):**
```json
{
  "success": true,
  "hash_id": "a3f8...",
  "alert": {
    "id": "uuid-do-alerta",
    "type": "relocated",
    "severity": "info",
    "message": "Dispositivo 'Logitech USB Receiver' foi movido de DESKTOP-A1B2C3 para DESKTOP-X9Y8Z7"
  }
}
```

### `GET /api/agent/version`

**Response:**
```json
{
  "current_version": "1.2.0",
  "needs_update": false,
  "download_url": null
}
```

---

## 11. Referências de Arquivos do Projeto

| Arquivo | Por que consultar |
|---|---|
| `server/schema.sql` | Convenções DDL: prefixo, PKs, CHECK constraints, índices |
| `server/routes/devices.js` | Padrão de route file (pool.query, ok/serverError helpers) |
| `server/routes/connections.js` | Lógica de conexão ativa (NULL = ativo) — reutilizar no handler de usb-event |
| `server/server.js` | Onde registrar `/api/agent` e `/api/usb-*` |
| `src/types/index.ts` | `DeviceType` union — valores válidos para `inv_usb_devices.device_type` e `classifier.py` |

---

---

## 12. Registro de Implementação

### Sessão 2026-04-01 — O que foi implementado

#### Banco de dados (VPS `inventario_ti`)
- Arquivo: `server/migrations/001_usb_agent.sql`
- Executado em: `mysql -u ticketapp -pTicketApp2025 inventario_ti`
- Tabelas criadas: `inv_agent_machines`, `inv_usb_devices`, `inv_usb_events`, `inv_usb_alerts`

#### Backend (`server/`)
- `middleware/agentAuth.js` — valida X-Agent-Token via SHA256, injeta `req.agentMachine`, atualiza `last_seen_at` em fire-and-forget
- `routes/agent.js` — 5 rotas para o agente Windows; inclui `_fingerprint()` (SHA256 + detecção serial instável) e `_classify()` (heurísticas por nome) inline; handler de `usb-event` usa `beginTransaction/commit/rollback`; constante `CURRENT_AGENT_VERSION = '1.0.0'`
- `routes/usb.js` — 8 rotas para o frontend React
- `server.js` — registrado com `app.use('/api/agent', ...)` e `app.use('/api', ...)` (uma única montagem para `usb.js`)

#### Frontend (`src/`)
- `lib/usbApi.ts` — tipos TypeScript e funções de acesso à API
- `pages/AgentMachinesPage.tsx` — gestão de agentes (aprovar/vincular/revogar) com specs detalhadas
- `pages/UsbAlertsPage.tsx` — 3 abas: alertas, dispositivos USB, feed de eventos com auto-refresh
- `App.tsx` — rotas `/usb-agentes` e `/usb-monitoramento`
- `components/layout/Header.tsx` — 2 itens de navegação (Server + ShieldAlert icons)

#### Lição aprendida — Router mounting
Montar o mesmo router Express em múltiplos prefixos causa bug de roteamento. O correto é uma única montagem em `/api` quando as rotas internas definem caminhos completos como `/usb-machines`.

*Documento atualizado em 2026-04-01 após implementação das Fases 2, 3 e 4.*
