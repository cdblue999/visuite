# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""EnergyPlus Weather (.epw) file reader, pure standard library.

An EPW file holds one year of hourly weather data. The first 8 lines are
meta/header; the remaining 8760 lines are hourly records with roughly 35
comma-separated fields. VI-Suite reads ``Site Outdoor Air Drybulb
Temperature`` (field 6), ``Relative Humidity`` (8), ``Wind Direction``
(20), ``Wind Speed`` (21), ``Direct`` (14) and ``Diffuse`` (15) solar
radiation from these; here the same fields are parsed and reported.

Field indices (0-based) of an hourly record, per the EnergyPlus EPW
specification:

  0 Year, 1 Month, 2 Day, 3 Hour, 4 Minute, 5 Data Source,
  6 Dry-bulb temperature (C), 7 Dew point (C), 8 Relative humidity (%),
  9 Pressure (Pa), 10 Extraterrestrial horizontal (W/m2),
  11 Extraterrestrial direct normal (W/m2), 12 Horizontal IR (W/m2),
  13 Global horizontal (W/m2), 14 Direct normal (W/m2),
  15 Diffuse horizontal (W/m2), 16 Global horiz illuminance (lux),
  17 Direct normal illuminance (lux), 18 Diffuse horiz illuminance (lux),
  19 Zenith luminance (cd/m2), 20 Wind direction (deg), 21 Wind speed (m/s),
  22 Total sky cover (tenths), 23 Opaque sky cover (tenths),
  24 Visibility (km), 25 Ceiling height (m), ... (35 fields total)

No ``pandas`` or other extra package is required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: Index -> (name, unit) for the fields this reader cares about.
FIELDS = {
    6:  ("dry_bulb_temperature", "C"),
    8:  ("relative_humidity", "%"),
    14: ("direct_normal_solar", "W/m2"),
    15: ("diffuse_horizontal_solar", "W/m2"),
    20: ("wind_direction", "deg"),
    21: ("wind_speed", "m/s"),
}


@dataclass
class EpwLocation:
    city: str = ""
    state: str = ""
    country: str = ""
    data_source: str = ""
    wmo_number: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    time_zone: Optional[float] = None
    elevation: Optional[float] = None


@dataclass
class EpwRecord:
    """One hourly record, with only the fields this reader keeps."""
    year: int
    month: int
    day: int
    hour: int
    minute: int
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class EpwFile:
    location: EpwLocation
    records: list[EpwRecord] = field(default_factory=list)


def _num(text: str) -> Optional[float]:
    text = text.strip()
    if not text or text in ("", "-", "NA", "nan"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_epw(path: str | Path) -> EpwFile:
    """Parse an EnergyPlus Weather file.

    Tolerates missing/invalid fields (stored as None) and the occasional
    malformed trailing line.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) < 9:
        raise ValueError("not a valid EPW file (fewer than 9 lines)")

    location = EpwLocation()
    header = lines[0].split(",")
    if len(header) >= 9:
        location.city = header[0].strip()
        location.state = header[1].strip()
        location.country = header[2].strip()
        location.data_source = header[3].strip()
        location.wmo_number = header[4].strip()
        location.latitude = _num(header[5])
        location.longitude = _num(header[6])
        location.time_zone = _num(header[7])
        location.elevation = _num(header[8])

    records: list[EpwRecord] = []
    # Data starts after the 8 header/meta lines and the "number of data
    # periods" line (line 8, index 7). Find the first line that looks like
    # a data record (starts with a year).
    start = 8
    for i in range(8, min(len(lines), 12)):
        parts = lines[i].split(",")
        if len(parts) >= 4 and parts[0].strip().isdigit():
            start = i
            break

    for line in lines[start:]:
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) < 22:
            continue
        if not parts[0].strip().isdigit():
            continue
        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            hour = int(parts[3])
            minute = int(parts[4])
        except ValueError:
            continue
        values = {}
        for idx, (name, _unit) in FIELDS.items():
            if idx < len(parts):
                values[name] = _num(parts[idx])
        records.append(EpwRecord(year, month, day, hour, minute, values))

    return EpwFile(location=location, records=records)


def monthly_stats(epw: EpwFile) -> dict[int, dict[str, dict[str, float]]]:
    """``{month: {field: {min, max, mean, count}}}`` over hourly records."""
    out: dict[int, dict[str, dict[str, list[float]]]] = {}
    for rec in epw.records:
        bucket = out.setdefault(rec.month, {})
        for name, value in rec.values.items():
            if value is None:
                continue
            series = bucket.setdefault(name, [])
            series.append(value)
    result: dict[int, dict[str, dict[str, float]]] = {}
    for month, fields in out.items():
        result[month] = {}
        for name, series in fields.items():
            if not series:
                continue
            result[month][name] = {
                "min": min(series),
                "max": max(series),
                "mean": sum(series) / len(series),
                "count": len(series),
            }
    return result


def wind_rose_bins(epw: EpwFile, sectors: int = 16) -> list[dict]:
    """Wind direction/speed frequency binned into ``sectors`` compass sectors.

    Each entry: ``{sector, center_deg, label, count, mean_speed,
    frequency_pct}``. Calm records (speed == 0) are counted in sector 0.
    """
    sector_width = 360.0 / sectors
    bins = [{"count": 0, "speeds": []} for _ in range(sectors)]
    total = 0
    for rec in epw.records:
        wdir = rec.values.get("wind_direction")
        wspd = rec.values.get("wind_speed")
        if wdir is None or wspd is None:
            continue
        total += 1
        if wspd <= 0:
            idx = 0
        else:
            idx = int(((wdir % 360.0) + sector_width / 2.0) // sector_width) % sectors
        bins[idx]["count"] += 1
        bins[idx]["speeds"].append(wspd)
    out = []
    labels = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    for i, b in enumerate(bins):
        center = (i * sector_width + sector_width / 2.0) % 360.0
        speeds = b["speeds"]
        mean_speed = sum(speeds) / len(speeds) if speeds else 0.0
        freq = (100.0 * b["count"] / total) if total else 0.0
        out.append({
            "sector": i,
            "center_deg": center,
            "label": labels[i] if i < len(labels) else f"{i}",
            "count": b["count"],
            "mean_speed": mean_speed,
            "frequency_pct": freq,
        })
    out.sort(key=lambda d: -d["count"])
    return out
