# agent/usb_monitor.py
"""
Monitora eventos de conexão/desconexão USB via WMI Win32_PnPEntity.
Usa thread dedicada para não bloquear o loop principal do serviço.
"""

import re
import threading
import logging
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict], None]

_VID_RE = re.compile(r'VID_([0-9A-Fa-f]{4})', re.IGNORECASE)
_PID_RE = re.compile(r'PID_([0-9A-Fa-f]{4})', re.IGNORECASE)


class UsbMonitor:
    """
    Monitora eventos USB via WMI __InstanceCreationEvent / __InstanceDeletionEvent
    em Win32_PnPEntity. Chama on_event(dict) para cada evento USB detectado.
    """

    def __init__(self, on_event: EventCallback):
        self._on_event = on_event
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop,
            name='UsbMonitorThread',
            daemon=True,
        )
        self._thread.start()
        logger.info('UsbMonitor iniciado')

        # Scan imediato dos dispositivos já conectados
        threading.Thread(
            target=self._scan_existing,
            name='UsbInitialScan',
            daemon=True,
        ).start()

    def _scan_existing(self) -> None:
        """Lê todos os dispositivos USB/HID já conectados no momento do start e dispara eventos connected."""
        try:
            import pythoncom  # type: ignore[import]
            import wmi        # type: ignore[import]
        except ImportError:
            return

        pythoncom.CoInitialize()
        try:
            c = wmi.WMI()
            devices = c.Win32_PnPEntity()
            count = 0
            for dev in devices:
                pnp_id = getattr(dev, 'PNPDeviceID', '') or ''
                prefix = pnp_id.upper().split('\\')[0] if '\\' in pnp_id else ''
                if prefix not in ('USB', 'HID'):
                    continue
                self._handle(dev, 'connected')
                count += 1
            logger.info('Scan inicial: %d dispositivo(s) USB/HID já conectado(s) reportado(s)', count)
        except Exception as exc:
            logger.warning('Falha no scan inicial de USB: %s', exc)
        finally:
            pythoncom.CoUninitialize()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info('UsbMonitor parado')

    # -------------------------------------------------------------------------
    # Loop principal (thread dedicada)
    # -------------------------------------------------------------------------

    def _watch_loop(self) -> None:
        try:
            import pythoncom  # type: ignore[import]
            import wmi  # type: ignore[import]
        except ImportError:
            logger.error('wmi não disponível — UsbMonitor não funcionará neste ambiente')
            return

        pythoncom.CoInitialize()
        try:
            c = wmi.WMI()
        except Exception as exc:
            logger.error('Falha ao inicializar WMI: %s', exc)
            pythoncom.CoUninitialize()
            return
        try:
            watcher_connect    = c.Win32_PnPEntity.watch_for('creation')
            watcher_disconnect = c.Win32_PnPEntity.watch_for('deletion')

            logger.info('WMI watchers registrados — aguardando eventos USB...')

            while not self._stop_event.is_set():
                # Conexão
                try:
                    event = watcher_connect(timeout_ms=500)
                    if event:
                        self._handle(event, 'connected')
                except wmi.x_wmi_timed_out:
                    pass
                except Exception as exc:
                    logger.warning('Erro no watcher_connect: %s', exc)

                # Desconexão
                try:
                    event = watcher_disconnect(timeout_ms=500)
                    if event:
                        self._handle(event, 'disconnected')
                except wmi.x_wmi_timed_out:
                    pass
                except Exception as exc:
                    logger.warning('Erro no watcher_disconnect: %s', exc)
        finally:
            pythoncom.CoUninitialize()

    # -------------------------------------------------------------------------
    # Processamento do evento
    # -------------------------------------------------------------------------

    # GUID da classe USB genérica (hubs, composite devices) — filtramos pois seus
    # filhos HID serão reportados em seguida com CompatibleIDs mais precisos.
    _USB_CLASS_GUID = '{36FC9E60-C465-11CF-8056-444553540000}'

    def _handle(self, pnp_entity: object, event_type: str) -> None:
        if not pnp_entity:
            return

        pnp_id: str = getattr(pnp_entity, 'PNPDeviceID', '') or ''
        prefix = pnp_id.upper().split('\\')[0] if '\\' in pnp_id else ''

        if prefix == 'USB':
            # Pula dispositivos USB puro (hubs, composite) cujos filhos HID serão
            # reportados a seguir com CompatibleIDs precisos para mouse/teclado.
            cg = (getattr(pnp_entity, 'ClassGuid', '') or '').upper()
            if cg == self._USB_CLASS_GUID.upper():
                return
        elif prefix == 'HID':
            pass  # aceitos — carregam CompatibleIDs para mouse, teclado, headset
        else:
            return  # ignorar ACPI, PCI, etc.

        vid, pid, serial = self._parse_pnp_id(pnp_id)

        # HID não-USB (PS/2 via HID layer, etc.) não têm VID/PID reais — ignorar
        if prefix == 'HID' and vid == '0000' and pid == '0000':
            return
        friendly_name: str | None = getattr(pnp_entity, 'Name', None)
        class_guid: str | None = getattr(pnp_entity, 'ClassGuid', None)

        # CompatibleIDs — array de strings que identifica o tipo HID com precisão
        # Ex: ["HID_DEVICE_SYSTEM_MOUSE", "HID_DEVICE_UP:0001_U:0002", ...]
        raw_compat = getattr(pnp_entity, 'CompatibleID', None)
        compatible_ids: list[str] = list(raw_compat) if raw_compat else []

        event_data = {
            'event_type':     event_type,
            'event_time':     datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'vid':            vid,
            'pid':            pid,
            'serial':         serial,
            'friendly_name':  friendly_name,
            'pnp_device_id':  pnp_id,
            'class_guid':     class_guid,      # usado pelo classifier, não enviado ao servidor
            'compatible_ids': compatible_ids,  # usado pelo classifier, não enviado ao servidor
        }

        logger.info('%s — %s [VID:%s PID:%s compat:%d]',
                    event_type.upper(), friendly_name, vid, pid, len(compatible_ids))
        self._on_event(event_data)

    @staticmethod
    def _parse_pnp_id(pnp_id: str) -> tuple[str, str, str | None]:
        """
        USB\\VID_045E&PID_082F\\1234567890  →  ('045E', '082F', '1234567890')
        USB\\VID_045E&PID_082F&MI_00\\...   →  ('045E', '082F', None)
        """
        vid_match = _VID_RE.search(pnp_id)
        pid_match = _PID_RE.search(pnp_id)

        parts = pnp_id.split('\\')
        # parte[2] é o serial — descartado se contiver '&' (indica sub-interface)
        serial: str | None = parts[2] if len(parts) >= 3 and '&' not in parts[2] else None

        vid = vid_match.group(1).upper() if vid_match else '0000'
        pid = pid_match.group(1).upper() if pid_match else '0000'
        return vid, pid, serial
