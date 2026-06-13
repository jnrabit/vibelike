"""
thermal_reader.py
=================
CPU-Temperatur via /sys/class/hwmon lesen.

Hintergrund: Die C++-Engine (libquelibrium.so) versucht
/sys/class/thermal/thermal_zone0/temp, was auf vielen modernen Systemen
(z.B. Nobara/Fedora 43) nicht existiert. Dieser Python-Fallback scannt
/sys/class/hwmon nach bekannten CPU-Sensor-Treibern.

Vom protocol.py als Override verwendet, wenn die Engine den Fallback-Wert
(45.0°C) zurueckgibt.

Praeferenz-Reihenfolge: k10temp (AMD) > coretemp (Intel) > nct6687 (MSI/ASUS).
"""

from pathlib import Path
from typing import Optional


_PREFERRED_DRIVERS = ("k10temp", "coretemp", "nct6687")
_HWMON_ROOT = Path("/sys/class/hwmon")
_FALLBACK_VALUE = 45.0  # Signatur fuer "Engine hat nichts gefunden"


def read_cpu_thermal() -> Optional[float]:
    """
    Liest CPU-Temperatur in °C aus /sys/class/hwmon.

    Returns:
        float (z.B. 34.1) bei Erfolg, None bei keinem Treffer.
    """
    if not _HWMON_ROOT.exists():
        return None

    for driver in _PREFERRED_DRIVERS:
        for hwmon in sorted(_HWMON_ROOT.glob("hwmon*")):
            name_file = hwmon / "name"
            try:
                name = name_file.read_text().strip()
            except OSError:
                continue
            if name != driver:
                continue
            temp_file = hwmon / "temp1_input"
            try:
                raw = int(temp_file.read_text().strip())
            except (OSError, ValueError):
                continue
            if raw > 1000:
                return raw / 1000.0
    return None


def maybe_override(engine_temp: float) -> float:
    """
    Wenn der Wert der Engine wie ein Fallback aussieht, gib echten hwmon-Wert
    zurueck. Sonst Engine-Wert unveraendert.

    Args:
        engine_temp: Wert aus get_system_state()[5] (vibelike's temperature)

    Returns:
        Korrigierte Temperatur (immer einen float).
    """
    # Fallback-Signaturen: 45.0 (engine_patched.cpp), 0.0 (uninitialized)
    if engine_temp == _FALLBACK_VALUE or engine_temp == 0.0:
        real = read_cpu_thermal()
        if real is not None:
            return real
    return engine_temp


if __name__ == "__main__":
    import sys
    t = read_cpu_thermal()
    if t is None:
        print("Keine CPU-Temperatur gefunden.")
        sys.exit(1)
    print(f"CPU-Temperatur: {t:.1f}°C")
    sys.exit(0)
