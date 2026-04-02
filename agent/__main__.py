# agent/__main__.py
"""
Entry point do agente IN9USBAgent.

Uso:
    # Modo standalone (dev/teste):
    python -m agent run

    # Instalar/gerenciar Windows Service:
    python -m agent install
    python -m agent start
    python -m agent stop
    python -m agent remove

    # Configurar antes de instalar:
    python -m agent config --url https://inventario.in9automacao.com.br --token <TOKEN>

    # Primeira instalação (cria novo registro no servidor):
    python -m agent register-new --url <URL> --token <TOKEN>
"""

import argparse
import logging
import sys
from pathlib import Path

# Logging básico para stdout (serviço redireciona para arquivo/Event Log)
import sys as _sys
import io as _io

# Forçar UTF-8 no stdout para evitar caracteres quebrados no console Windows
if hasattr(_sys.stdout, 'reconfigure'):
    try:
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

class _FlushHandler(logging.StreamHandler):
    """StreamHandler que faz flush após cada registro — garante logs visíveis em tempo real."""
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()

_handler = _FlushHandler(_sys.stdout)
_handler.setFormatter(logging.Formatter(
    fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
))
logging.basicConfig(level=logging.INFO, handlers=[_handler])

logger = logging.getLogger('agent')


def _get_db() -> 'LocalDB':
    from .local_db import LocalDB
    return LocalDB()


def cmd_run(args: argparse.Namespace) -> None:
    """
    Roda o agente em modo standalone (foreground).
    Se pystray estiver disponível, exibe ícone na bandeja e bloqueia na thread principal.
    """
    from .local_db import LocalDB
    from .service import AgentCore
    from .tray import TrayIcon

    db = LocalDB()
    tray = TrayIcon()
    core = AgentCore(db, tray=tray)

    core.start()

    if tray._available:
        # pystray precisa rodar na thread principal — core já está em threads daemon
        try:
            tray.run()  # bloqueia até "Sair" no menu ou tray.stop()
        except KeyboardInterrupt:
            pass
        finally:
            core.stop()
    else:
        # Sem tray: bloqueia aguardando Ctrl+C
        try:
            core.wait()
        except KeyboardInterrupt:
            logger.info('Interrompido pelo usuário.')
            core.stop()


def cmd_config(args: argparse.Namespace) -> None:
    """Salva server_url e token no SQLite local."""
    db = _get_db()
    if args.url:
        db.server_url = args.url
        print(f'server_url salvo: {args.url}')
    if args.token:
        db.token = args.token
        print(f'token salvo: ...{args.token[-8:]}')


def cmd_register_new(args: argparse.Namespace) -> None:
    """Cria novo registro no servidor (primeira instalação)."""
    import socket
    import requests
    from .reporter import Reporter
    from .local_db import LocalDB
    from .specs import capture_machine_specs

    db = LocalDB()
    url = args.url or db.server_url
    token = args.token or db.token

    if not url or not token:
        print('Erro: informe --url e --token (ou configure via "config")')
        sys.exit(1)

    db.server_url = url
    db.token = token

    reporter = Reporter(server_url=url, token=token)
    specs = capture_machine_specs()
    hostname = specs.get('hostname') or socket.gethostname()
    bios_serial = specs.get('bios_serial')
    mac_address = specs.get('mac_address')

    try:
        resp = reporter.register_new(hostname=hostname, mac_address=mac_address, bios_serial=bios_serial)
        print('Registro OK:', resp)
        if resp.get('machine_id'):
            db.machine_id = resp['machine_id']
        if resp.get('token'):
            db.token = resp['token']
            print(f'Token recebido: ...{resp["token"][-8:]}')
    except Exception as exc:
        print(f'Erro ao registrar: {exc}')
        sys.exit(1)


def cmd_service(args: argparse.Namespace) -> None:
    """Delega ao win32serviceutil para instalar/start/stop/remove o serviço."""
    from .service import _HAS_WIN32, IN9USBAgentService

    if not _HAS_WIN32:
        print('Erro: pywin32 não está instalado. Este comando só funciona no Windows.')
        sys.exit(1)

    import win32serviceutil  # type: ignore[import]
    sys.argv = [sys.argv[0], args.action]
    win32serviceutil.HandleCommandLine(IN9USBAgentService)


# =============================================================================
# Parser
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(prog='agent', description='IN9USBAgent')
    sub = parser.add_subparsers(dest='command', required=True)

    # run
    sub.add_parser('run', help='Roda o agente em modo standalone (foreground)')

    # config
    p_cfg = sub.add_parser('config', help='Salva configurações locais')
    p_cfg.add_argument('--url',   help='URL do servidor (ex: https://inventario.in9automacao.com.br)')
    p_cfg.add_argument('--token', help='Token do agente')

    # register-new
    p_reg = sub.add_parser('register-new', help='Cria novo registro no servidor')
    p_reg.add_argument('--url',   help='URL do servidor')
    p_reg.add_argument('--token', help='Token do agente')

    # service commands (Windows)
    for action in ('install', 'start', 'stop', 'remove', 'restart'):
        p = sub.add_parser(action, help=f'Windows Service: {action}')
        p.set_defaults(action=action)

    args = parser.parse_args()

    if args.command == 'run':
        cmd_run(args)
    elif args.command == 'config':
        cmd_config(args)
    elif args.command == 'register-new':
        cmd_register_new(args)
    else:
        cmd_service(args)


if __name__ == '__main__':
    main()
