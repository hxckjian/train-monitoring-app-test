"""Quick drop: work out which subsystem a file belongs to from the file itself,
so the dashboard can take any competition-format file and route it without the
user picking a page first.

Rules, in order, from the verified schemas in PROJECT-STATE.md:
- .xlsx                                  -> ACV (one telemetry workbook per case)
- CSV header starts with 'Datetime'      -> Door (17-column controller stream)
- CSV header starts with 'Rotating speed'-> Rail (129 columns, 10,000 rows)
- headerless, one numeric column         -> SHM (bare stress values)
- anything else                          -> the New-data screen
"""
from __future__ import annotations

import io

SUBSYSTEM_EMOJI = {"door": "🚪", "shm": "🏗️", "rail": "🛤️", "acv": "❄️", "generic": "🧪"}


def detect(name: str, data: bytes) -> tuple[str, str]:
    """Return (key, reason). key in door / shm / rail / acv / generic."""
    n = name.lower()
    if n.endswith(".xlsx"):
        return "acv", "Excel workbook: air-conditioning telemetry"
    head = data[:4096].decode("utf-8", errors="ignore")
    first = head.splitlines()[0].strip() if head.strip() else ""
    if first.startswith("Datetime,"):
        return "door", "header starts with Datetime: door controller stream"
    if first.startswith("Rotating speed"):
        return "rail", "header starts with Rotating speed: axle-box recording"
    cells = [c.strip() for c in first.split(",")]
    if len(cells) == 1:
        try:
            float(cells[0])
            return "shm", "one bare numeric column: dynamic stress file"
        except ValueError:
            pass
    return "generic", "unrecognised layout: screened as a new dataset"


def as_upload(name: str, data: bytes) -> io.BytesIO:
    b = io.BytesIO(data)
    b.name = name
    return b
