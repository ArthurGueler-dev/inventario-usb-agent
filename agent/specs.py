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


# Palavras na Description do adaptador que indicam rede virtual/VPN — devem ser ignoradas
# ao escolher o IP da máquina. Match case-insensitive em substring.
_VIRTUAL_ADAPTER_KEYWORDS = (
    'hyper-v', 'virtual', 'vethernet', 'vmware', 'virtualbox', 'vbox',
    'wsl', 'docker', 'tap-windows', 'openvpn', 'tunnel', 'tunneling',
    'loopback', 'pseudo-interface', 'teredo', 'isatap', 'bluetooth',
    'wan miniport',
)


def _is_virtual_adapter(description: str | None) -> bool:
    if not description:
        return False
    desc = description.lower()
    return any(kw in desc for kw in _VIRTUAL_ADAPTER_KEYWORDS)


def _is_routable_ipv4(ip: str) -> bool:
    """Filtra loopback (127.x), APIPA (169.254.x) e qualquer coisa não-IPv4."""
    if not ip or ':' in ip:
        return False
    if ip.startswith('127.') or ip.startswith('169.254.'):
        return False
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def get_primary_ip() -> str | None:
    """
    Retorna o IP da interface que o Windows usaria para sair pra internet.

    Truque: cria um socket UDP e chama connect() para um endereço externo.
    Nenhum pacote é enviado, mas o stack TCP/IP escolhe o adaptador conforme
    a tabela de rotas e revela o IP de origem via getsockname(). Esse IP
    sempre será o da rede física principal (faixa da empresa) — nunca o de
    adaptadores virtuais inativos.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return ip if _is_routable_ipv4(ip) else None


def get_anydesk_id() -> str | None:
    """Lê o ID do AnyDesk a partir dos arquivos de configuração locais."""
    candidates = [
        Path(r'C:\ProgramData\AnyDesk\service.conf'),
        Path(r'C:\ProgramData\AnyDesk\system.conf'),
        Path(os.environ.get('APPDATA', '')) / 'AnyDesk' / 'service.conf',
        Path(os.environ.get('APPDATA', '')) / 'AnyDesk' / 'system.conf',
    ]
    # Padrões observados no AnyDesk Windows:
    #   ad.anynet.id=1021461089   (system.conf — modo serviço, mais comum)
    #   ad.web.id=...             (algumas versões)
    #   id=...                    (modo portable em versões antigas)
    patterns = [
        re.compile(r'^ad\.anynet\.id\s*=\s*(\d+)', re.MULTILINE),
        re.compile(r'^ad\.web\.id\s*=\s*(\d+)', re.MULTILINE),
        re.compile(r'^id\s*=\s*(\d+)', re.MULTILINE),
    ]
    for conf_path in candidates:
        try:
            if not conf_path.exists():
                continue
            text = conf_path.read_text(encoding='utf-8', errors='ignore')
            for pat in patterns:
                match = pat.search(text)
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
    # CoInitialize é OBRIGATÓRIO quando rodamos como Windows Service (conta SYSTEM)
    # ou em qualquer thread que não tenha COM inicializado.
    pythoncom_module = None
    com_initialized = False
    try:
        import pythoncom  # type: ignore[import]
        pythoncom_module = pythoncom
        try:
            pythoncom.CoInitialize()
            com_initialized = True
        except Exception:
            pass  # já inicializado é OK
    except ImportError:
        pass

    try:
        import wmi  # type: ignore[import]
        c = wmi.WMI()
        _collect_wmi(c, specs)
    except Exception as exc:
        logger.warning('WMI falhou ao capturar specs: %s', exc, exc_info=True)
        specs['os'] = platform.version()
    finally:
        if com_initialized and pythoncom_module is not None:
            try:
                pythoncom_module.CoUninitialize()
            except Exception:
                pass

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
    # Estratégia:
    #   1. primary_ip = IP da interface com rota pra internet (nunca é virtual)
    #   2. local_ips = todos os IPv4 routable, mas filtrando adaptadores virtuais
    #      (Hyper-V, Docker, WSL, VPN, etc.) — primary_ip vai em primeiro.
    #   3. mac_address = MAC do adaptador físico que carrega o primary_ip.
    primary_ip = get_primary_ip()
    if primary_ip:
        specs['primary_ip'] = primary_ip

    try:
        adapters = c.Win32_NetworkAdapterConfiguration(IPEnabled=True)
        physical_ips: list[str] = []
        primary_mac: str | None = None
        fallback_mac: str | None = None
        for a in adapters:
            description = getattr(a, 'Description', None)
            is_virtual = _is_virtual_adapter(description)
            adapter_ips = [ip for ip in (a.IPAddress or ()) if _is_routable_ipv4(ip)]

            if a.MACAddress:
                if primary_ip and primary_ip in adapter_ips and not primary_mac:
                    primary_mac = a.MACAddress
                if not is_virtual and not fallback_mac:
                    fallback_mac = a.MACAddress

            if is_virtual:
                continue
            for ip in adapter_ips:
                if ip not in physical_ips:
                    physical_ips.append(ip)

        chosen_mac = primary_mac or fallback_mac
        if chosen_mac:
            specs['mac_address'] = chosen_mac

        # primary_ip sempre primeiro, depois os demais físicos
        ordered: list[str] = []
        if primary_ip:
            ordered.append(primary_ip)
            if primary_ip in physical_ips:
                physical_ips.remove(primary_ip)
        ordered.extend(physical_ips)
        if ordered:
            specs['local_ips'] = ordered
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

    # primary_ip a cada heartbeat — mantém o servidor com IP atual quando a
    # máquina troca de rede (cabo ↔ wifi, escritório ↔ home office).
    primary_ip = get_primary_ip()
    if primary_ip:
        stats['primary_ip'] = primary_ip

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
