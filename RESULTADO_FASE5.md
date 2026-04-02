# Resultado — Etapa 5: Teste WMI Watcher (Fase 5)

**Data:** 2026-04-01
**Executado por:** Claude Sonnet 4.6 via Claude Code
**Commit da correção:** `c0b3aac`

---

## Ambiente

| Item | Valor |
|---|---|
| OS | Windows 11 Pro for Workstations 10.0.26200 |
| Python | 3.13.5 |
| pip | 25.1.1 |
| wmi | 1.5.1 |
| pywin32 | 311 |
| psutil | 7.2.2 |
| requests | 2.33.1 |

---

## Bug encontrado em `agent/usb_monitor.py`

### Problema

O método `watch_for()` da biblioteca `wmi` aceita apenas os valores curtos:
`'operation'`, `'creation'`, `'deletion'`, `'modification'`

O código original passava os nomes completos dos eventos WMI, que são inválidos:

```python
# INCORRETO
watcher_connect    = c.Win32_PnPEntity.watch_for('__InstanceCreationEvent')
watcher_disconnect = c.Win32_PnPEntity.watch_for('__InstanceDeletionEvent')
```

Além disso, o objeto retornado pelo watcher já é o evento com delegate de atributos ao `TargetInstance` — não há `.NewValue` nem `.PreviousValue`:

```python
# INCORRETO
self._handle(event.NewValue, 'connected')
self._handle(event.PreviousValue, 'disconnected')
```

### Erro original

```
wmi.x_wmi: <x_wmi: notification_type must be one of operation, creation, deletion, modification>
```

### Correção aplicada

```python
# CORRETO
watcher_connect    = c.Win32_PnPEntity.watch_for('creation')
watcher_disconnect = c.Win32_PnPEntity.watch_for('deletion')

# ...

self._handle(event, 'connected')
self._handle(event, 'disconnected')
```

---

## Resultado do teste (após correção)

```
Monitor iniciado. Pluge e desplugue um dispositivo USB nos proximos 30 segundos...
EVENTO: connected | Dispositivo de Entrada USB | VID:1EA7 PID:9018 | serial:None
EVENTO: connected | Dispositivo de Entrada USB | VID:1EA7 PID:9018 | serial:None
EVENTO: connected | Dispositivo de Entrada USB | VID:1EA7 PID:9018 | serial:None
EVENTO: connected | USB Composite Device       | VID:1EA7 PID:9018 | serial:None
Total de eventos capturados: 4
```

**Status:** ✅ PASSOU

### Dispositivo testado

| Campo | Valor |
|---|---|
| Nome | Dispositivo de Entrada USB / USB Composite Device |
| VID | `1EA7` |
| PID | `9018` |
| Serial | `None` (sub-interface — serial descartado por conter `&`) |
| Tipo esperado | Mouse/teclado USB |

### Observações

- O WMI disparou 4 eventos de conexão para o mesmo dispositivo (comportamento normal — o Windows registra cada interface do dispositivo composto separadamente).
- Eventos de `disconnected` não foram capturados pois o dispositivo não foi desplugado durante a janela de 30s.
- Os avisos `Win32 exception occurred releasing IUnknown` são benignos — ocorrem no cleanup do COM ao encerrar os watchers e não afetam o funcionamento.
- O serial é `None` porque o `PNPDeviceID` continha `&` na terceira parte (indica sub-interface, não um serial real), comportamento esperado e tratado corretamente pelo `_parse_pnp_id`.

---

## Status geral das etapas

| Etapa | Descrição | Status |
|---|---|---|
| 1 | Verificar ambiente | ✅ Python 3.13.5, pip 25.1.1, win32 |
| 2 | Criar venv e instalar dependências | ✅ Todos os imports OK |
| 3 | Suíte de testes unitários | — não executado nesta sessão |
| 4 | Testar módulos individualmente | — não executado nesta sessão |
| 5 | WMI watcher — eventos USB | ✅ 4 eventos capturados (após bugfix) |
| 6–9 | Configuração servidor / registro / standalone / buffer | — pendente |
