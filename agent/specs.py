# agent/specs.py
"""
Captura especificações da máquina para enviar no register.
Falha silenciosa: retorna dados parciais se algum subsistema falhar.
Depende de wmi + psutil (Windows only).
"""

import os
import platform
import re
import socket
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_anydesk_id() -> str | None:
    """Lê o ID do AnyDesk a partir dos arquivos de configuração locais."""
    candidates = [
        Path(r'C:\ProgramData\AnyDesk\service.conf'),
        Path(r'C:\ProgramData\AnyDesk\system.conf'),
        Path(os.environ.get('APPDATA', '')) / 'AnyDesk' / 'service.conf',
        Path(os.environ.get('APPDATA', '')) / 'AnyDesk' / 'system.conf',
    ]
    for conf_path in candidates:
        try:
            if not conf_path.exists():
                continue
            text = conf_path.read_text(encoding='utf-8', errors='ignore')
            match = re.search(r'^id\s*=\s*(\d+)', text, re.MULTILINE)
            if match:
                return match.group(1)
        except Exception:
            pass
    return None


def capture_machine_specs() -> dict[str, Any]:
    """
    Captura CPU, RAM, discos, GPU, OS e BIOS.
    Nunca lança exceção — retorna dict parcial em caso de falha.
    """
    specs: dict[str, Any] = {}

    # Hostname
    try:
        specs['hostname'] = socket.gethostname()
    except Exception:
        pass

    # Tentar wmi (Windows) — importação lazy para não travar em Linux/dev
    try:
        import wmi  # type: ignore[import]
        c = wmi.WMI()
        _collect_wmi(c, specs)
    except Exception as exc:
        logger.debug('wmi indisponível (%s) — usando fallbacks', exc)
        specs['os'] = platform.version()

    # RAM via psutil (funciona em Windows e Linux)
    if 'ram_gb' not in specs:
        try:
            import psutil  # type: ignore[import]
            specs['ram_gb'] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        except Exception:
            pass

    # Discos via psutil
    if 'disks' not in specs:
        try:
            import psutil  # type: ignore[import]
            specs['disks'] = _collect_disks_psutil(psutil)
        except Exception:
            pass

    # AnyDesk ID (falha silenciosa se não instalado)
    anydesk_id = get_anydesk_id()
    if anydesk_id:
        specs['anydesk_id'] = anydesk_id

    return specs


def _collect_wmi(c: Any, specs: dict[str, Any]) -> None:
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
        import psutil  # type: ignore[import]
        specs['ram_gb'] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass

    # Discos
    try:
        import psutil  # type: ignore[import]
        specs['disks'] = _collect_disks_wmi(c, psutil)
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

    # BIOS
    try:
        bios = c.Win32_BIOS()[0]
        specs['bios_serial'] = bios.SerialNumber.strip()
        specs['bios_version'] = bios.SMBIOSBIOSVersion.strip()
    except Exception:
        pass

    # MAC address + IPs locais
    try:
        adapters = c.Win32_NetworkAdapterConfiguration(IPEnabled=True)
        local_ips: list[str] = []
        for a in adapters:
            if a.MACAddress and 'mac_address' not in specs:
                specs['mac_address'] = a.MACAddress
            if a.IPAddress:
                for ip in a.IPAddress:
                    if ip and not ip.startswith('127.') and ':' not in ip:
                        local_ips.append(ip)
        if local_ips:
            specs['local_ips'] = local_ips
    except Exception:
        pass

    # Modelo e fabricante do computador
    try:
        cs = c.Win32_ComputerSystem()[0]
        specs['computer_manufacturer'] = (cs.Manufacturer or '').strip()
        specs['computer_model'] = (cs.Model or '').strip()
        pc_type_map = {1: 'desktop', 2: 'notebook', 3: 'workstation', 4: 'enterprise_server',
                       5: 'soho_server', 6: 'appliance_pc', 7: 'performance_server', 8: 'maximum'}
        specs['pc_type'] = pc_type_map.get(cs.PCSystemType, 'unknown')
    except Exception:
        pass


def _collect_disks_wmi(c: Any, psutil: Any) -> list[dict[str, Any]]:
    discos: list[dict[str, Any]] = []
    for disk in psutil.disk_partitions():
        if 'cdrom' in disk.opts or disk.fstype == '':
            continue
        try:
            usage = psutil.disk_usage(disk.mountpoint)
            discos.append({
                'label':    disk.device,
                'total_gb': round(usage.total / (1024 ** 3), 1),
                'type':     _detect_disk_type_wmi(c, disk.device),
            })
        except Exception:
            pass
    return discos


def _collect_disks_psutil(psutil: Any) -> list[dict[str, Any]]:
    discos: list[dict[str, Any]] = []
    for disk in psutil.disk_partitions():
        if 'cdrom' in disk.opts or disk.fstype == '':
            continue
        try:
            usage = psutil.disk_usage(disk.mountpoint)
            discos.append({
                'label':    disk.device,
                'total_gb': round(usage.total / (1024 ** 3), 1),
                'type':     'unknown',
            })
        except Exception:
            pass
    return discos


def get_runtime_stats() -> dict[str, Any]:
    """Retorna uso atual de CPU, RAM, disco livre e usuário logado.
    Chamado a cada heartbeat. Falha silenciosa."""
    stats: dict[str, Any] = {}
    try:
        import psutil  # type: ignore[import]
        stats['cpu_usage_pct'] = psutil.cpu_percent(interval=1)
        stats['ram_usage_pct'] = psutil.virtual_memory().percent
        usage = psutil.disk_usage('C:\\')
        stats['disk_free_gb'] = round(usage.free / (1024 ** 3), 1)
    except Exception as exc:
        logger.debug('psutil indisponível para runtime stats: %s', exc)

    try:
        import win32api  # type: ignore[import]
        stats['current_user'] = win32api.GetUserName()
    except Exception:
        try:
            import os
            stats['current_user'] = os.environ.get('USERNAME') or os.environ.get('USER')
        except Exception:
            pass

    return stats


def _detect_disk_type_wmi(c: Any, drive_letter: str) -> str:
    """Heurística: detecta SSD vs HDD via Win32_DiskDrive."""
    try:
        for disk in c.Win32_DiskDrive():
            model = (disk.Model or '').upper()
            if 'SSD' in model or 'NVME' in model or 'SOLID STATE' in model:
                return 'SSD'
            if disk.MediaType and 'fixed' in disk.MediaType.lower():
                return 'HDD'
    except Exception:
        pass
    return 'unknown'
