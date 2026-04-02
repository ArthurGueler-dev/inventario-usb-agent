# agent/tray.py
"""
Ícone na bandeja do sistema (system tray).

Estados:
  verde   — conectado, reportando normalmente
  amarelo — offline, eventos sendo acumulados localmente
  vermelho — erro de configuração ou serviço parado

Depende de pystray + Pillow (Windows only em produção,
mas funciona em qualquer OS que suporte tray icons).
"""

import logging
import threading
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)

ICON_SIZE = 64  # pixels


class TrayStatus(Enum):
    ONLINE  = 'online'   # verde
    OFFLINE = 'offline'  # amarelo
    ERROR   = 'error'    # vermelho


# Cores para cada estado
_STATUS_COLORS: dict[TrayStatus, tuple[int, int, int]] = {
    TrayStatus.ONLINE:  (34,  197, 94),   # green-500
    TrayStatus.OFFLINE: (234, 179, 8),    # yellow-500
    TrayStatus.ERROR:   (239, 68,  68),   # red-500
}

_STATUS_LABELS: dict[TrayStatus, str] = {
    TrayStatus.ONLINE:  'IN9 USB Agent — Conectado',
    TrayStatus.OFFLINE: 'IN9 USB Agent — Offline (buffer ativo)',
    TrayStatus.ERROR:   'IN9 USB Agent — Erro',
}


def _make_icon_image(color: tuple[int, int, int]):
    """Gera um ícone circular colorido usando Pillow."""
    from PIL import Image, ImageDraw  # type: ignore[import]

    img = Image.new('RGBA', (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, ICON_SIZE - margin, ICON_SIZE - margin],
        fill=(*color, 255),
    )
    return img


class TrayIcon:
    """
    Gerencia o ícone na bandeja do sistema.
    O pystray exige que icon.run() seja chamado na thread principal.
    Portanto esta classe oferece run() (bloqueante) e run_detached() (thread).
    """

    def __init__(self, on_quit: Callable[[], None] | None = None):
        self._on_quit = on_quit
        self._icon = None
        self._status = TrayStatus.ONLINE
        self._available = False

        try:
            import pystray  # type: ignore[import]
            from PIL import Image  # type: ignore[import]  # noqa: F401
            self._available = True
        except ImportError:
            logger.debug('pystray/Pillow não disponíveis — tray desabilitado')

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def set_status(self, status: TrayStatus, tooltip: str | None = None) -> None:
        """Atualiza cor e tooltip do ícone."""
        if not self._available or self._icon is None:
            return
        self._status = status
        try:
            self._icon.icon  = _make_icon_image(_STATUS_COLORS[status])
            self._icon.title = tooltip or _STATUS_LABELS[status]
        except Exception as exc:
            logger.debug('Falha ao atualizar ícone: %s', exc)

    def run(self) -> None:
        """Bloqueia a thread atual rodando o loop do tray. Chamar na thread principal."""
        if not self._available:
            return
        self._icon = self._build_icon()
        self._icon.run()

    def run_detached(self) -> None:
        """Inicia o tray em thread separada (modo standalone/dev)."""
        if not self._available:
            return
        t = threading.Thread(target=self.run, name='TrayThread', daemon=True)
        t.start()

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Construção do ícone
    # -------------------------------------------------------------------------

    def _build_icon(self):
        import pystray  # type: ignore[import]

        menu = pystray.Menu(
            pystray.MenuItem('IN9 USB Agent', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Sair', self._quit),
        )

        icon = pystray.Icon(
            name='IN9USBAgent',
            icon=_make_icon_image(_STATUS_COLORS[self._status]),
            title=_STATUS_LABELS[self._status],
            menu=menu,
        )
        return icon

    # -------------------------------------------------------------------------
    # Ações do menu
    # -------------------------------------------------------------------------

    def _quit(self, icon, item) -> None:
        logger.info('Saindo via menu do tray...')
        icon.stop()
        if self._on_quit:
            self._on_quit()
