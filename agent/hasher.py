# agent/hasher.py
import hashlib
import re

UNSTABLE_SERIAL_PATTERN = re.compile(r'^\d&[A-F0-9]{8}', re.IGNORECASE)


def is_stable_serial(serial: str | None) -> bool:
    """
    Retorna False para:
    - serial None ou vazio
    - seriais gerados pelo Windows com padrão \\d&[A-F0-9]{8} (ex: 3&11583659&0)
    """
    if not serial or not serial.strip():
        return False
    return not bool(UNSTABLE_SERIAL_PATTERN.match(serial.strip()))


def compute_hash_id(vid: str, pid: str, serial: str | None) -> tuple[str, bool]:
    """
    Calcula o fingerprint SHA256 do dispositivo.

    Se o serial for estável: SHA256("VID:PID:SERIAL")
    Se não for:              SHA256("VID:PID")

    Retorna:
        (hash_id: str, serial_is_stable: bool)
    """
    vid_norm = vid.strip().upper().zfill(4)
    pid_norm = pid.strip().upper().zfill(4)

    stable = is_stable_serial(serial)
    if stable:
        serial_norm = serial.strip().upper()  # type: ignore[union-attr]
        fingerprint = f"{vid_norm}:{pid_norm}:{serial_norm}"
    else:
        fingerprint = f"{vid_norm}:{pid_norm}"

    hash_id = hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()
    return hash_id, stable
