# agent/anydesk.py
"""
Instalação automática do AnyDesk caso não esteja presente na máquina.
O instalador é baixado do servidor de inventário (nunca da internet pública).
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .reporter import Reporter

logger = logging.getLogger(__name__)

ANYDESK_EXE   = Path(r'C:\Program Files (x86)\AnyDesk\AnyDesk.exe')
INSTALL_DIR   = Path(r'C:\Program Files (x86)\AnyDesk')
TMP_INSTALLER = Path(r'C:\Windows\Temp\anydesk_setup.exe')

INSTALL_TIMEOUT = 120  # segundos para o processo de install terminar
ID_WAIT_MAX     = 60   # segundos para esperar o AnyDesk gerar o system.conf


def is_installed() -> bool:
    return ANYDESK_EXE.exists()


def ensure_anydesk(reporter: 'Reporter') -> str | None:
    """
    Verifica se AnyDesk está instalado. Se não estiver:
      1. Baixa o instalador de /api/agent/download-anydesk
      2. Roda install silencioso
      3. Aguarda o ID ser gerado no system.conf
    Retorna o AnyDesk ID se disponível, None caso contrário (falha silenciosa).
    """
    logger.info('Verificando se AnyDesk está instalado em: %s', ANYDESK_EXE)
    if is_installed():
        logger.info('AnyDesk já instalado — lendo ID...')
        from .specs import get_anydesk_id
        return get_anydesk_id()

    logger.info('AnyDesk não encontrado — baixando instalador do servidor...')

    try:
        reporter.download_anydesk(TMP_INSTALLER)
        logger.info('Download concluído: %s (%d bytes)', TMP_INSTALLER, TMP_INSTALLER.stat().st_size)
    except Exception as exc:
        logger.warning('Falha no download do AnyDesk: %s', exc, exc_info=True)
        return None

    logger.info('Executando instalação silenciosa...')
    try:
        result = subprocess.run(
            [
                str(TMP_INSTALLER),
                '--install', str(INSTALL_DIR),
                '--start-with-win',
                '--create-shortcuts',
                '--create-desktop-icon',
                '--silent',
            ],
            timeout=INSTALL_TIMEOUT,
            capture_output=True,
        )
        logger.info('AnyDesk installer exit code: %d', result.returncode)
        if result.stdout:
            logger.info('stdout: %s', result.stdout.decode(errors='replace'))
        if result.stderr:
            logger.info('stderr: %s', result.stderr.decode(errors='replace'))
    except subprocess.TimeoutExpired:
        logger.warning('Timeout na instalação do AnyDesk (>%ds)', INSTALL_TIMEOUT)
        return None
    except Exception as exc:
        logger.warning('Erro ao instalar AnyDesk: %s', exc, exc_info=True)
        return None
    finally:
        try:
            TMP_INSTALLER.unlink(missing_ok=True)
        except Exception:
            pass

    if not ANYDESK_EXE.exists():
        logger.warning('AnyDesk.exe não encontrado em %s após instalação — falhou', ANYDESK_EXE)
        return None

    logger.info('AnyDesk instalado. Aguardando geração do ID (até %ds)...', ID_WAIT_MAX)
    from .specs import get_anydesk_id
    for _ in range(ID_WAIT_MAX // 5):
        time.sleep(5)
        anydesk_id = get_anydesk_id()
        if anydesk_id:
            logger.info('AnyDesk ID obtido: %s', anydesk_id)
            return anydesk_id

    logger.warning('AnyDesk instalado mas ID não gerado em %ds', ID_WAIT_MAX)
    return None
