# agent/classifier.py
"""
Classifica dispositivos USB com base em VID/PID e PNP Class.
Os valores de device_type correspondem EXATAMENTE ao DeviceType union em src/types/index.ts.
"""

# Mapeamento de PNP Class GUID → device_type
# Fonte: Win32_PnPEntity.ClassGuid
PNP_CLASS_MAP: dict[str, str] = {
    '{4D36E96C-E325-11CE-BFC1-08002BE10318}': 'fone',           # Sound, video and game controllers
    '{4D36E96B-E325-11CE-BFC1-08002BE10318}': 'mouse',          # Mouse
    '{4D36E96F-E325-11CE-BFC1-08002BE10318}': 'mouse',          # HID
    '{4D36E96A-E325-11CE-BFC1-08002BE10318}': 'teclado',        # Keyboard
    '{6BDD1FC6-810F-11D0-BEC7-08002BE2092F}': 'webcam',         # Image (câmeras)
    '{745A17A0-74D3-11D0-B6FE-00A0C90F57DA}': 'headset',        # Human Interface Device
    '{4D36E967-E325-11CE-BFC1-08002BE10318}': 'hd_externo',     # DiskDrive
    '{36FC9E60-C465-11CF-8056-444553540000}': 'adaptador_usb',  # USB (hubs, adaptadores)
    '{4D36E972-E325-11CE-BFC1-08002BE10318}': 'adaptador_rede', # Net (adaptadores de rede)
}

# Heurísticas por nome amigável (substring, case-insensitive)
NAME_HEURISTICS: list[tuple[str, str]] = [
    ('webcam',       'webcam'),
    ('camera',       'webcam'),
    ('headset',      'headset'),
    ('headphone',    'fone'),
    ('earphone',     'fone'),
    ('speaker',      'fone'),
    ('mouse',        'mouse'),
    ('keyboard',     'teclado'),
    ('teclado',      'teclado'),
    ('pen drive',    'pen_drive'),
    ('flash drive',  'pen_drive'),
    ('pendrive',     'pen_drive'),
    ('usb disk',     'hd_externo'),
    ('external',     'hd_externo'),
    ('hub',          'extensor_usb'),
    ('dock',         'docking_station'),
    ('bluetooth',    'adaptador_bluetooth'),
    ('wifi',         'adaptador_rede_dongle_wifi'),
    ('wireless',     'adaptador_rede_dongle_wifi'),
    ('ethernet',     'adaptador_rede_usb'),
    ('lan',          'adaptador_rede_usb'),
    ('printer',      'impressora'),
    ('impressora',   'impressora'),
    ('scanner',      'scanner'),
    ('monitor',      'monitor_peripheral'),
    ('display',      'monitor_peripheral'),
    ('hdmi',         'cabo_hdmi'),
    ('audio',        'fone'),
]


def classify(pnp_class_guid: str | None, friendly_name: str | None, vid: str = '') -> str:
    """
    Retorna um device_type compatível com o DeviceType union do TypeScript.
    Fallback: 'peripheral' para dispositivos reconhecidos mas não classificados,
              'unknown' para hubs/raízes USB.
    """
    # 1. Tentar por Class GUID
    if pnp_class_guid:
        result = PNP_CLASS_MAP.get(pnp_class_guid.upper())
        if result:
            return result

    # 2. Hubs USB e raízes — não são periféricos de usuário
    if friendly_name and any(x in friendly_name.lower() for x in ['root hub', 'usb hub', 'composite']):
        return 'unknown'

    # 3. Tentar por nome amigável
    if friendly_name:
        name_lower = friendly_name.lower()
        for keyword, device_type in NAME_HEURISTICS:
            if keyword in name_lower:
                return device_type

    # 4. Fallback
    return 'peripheral'
