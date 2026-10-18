# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""EPW reader: synthetic header + three hourly records."""
from __future__ import annotations

import os
import tempfile

from visuite.epw import read_epw, monthly_stats, wind_rose_bins

EPW_HEADER = (
    "Test City,TS,Test Country,TEST,99999,52.0,0.0,0,35\n"
    "2\n"
    "1\n"
    "0\n"
    "0\n"
    "0\n"
    "1\n"          # comment 2
    "1\n"          # number of data periods
)

# Three hourly records: hour 1 temp 0, hour 2 temp 2, hour 3 temp 5.
EPW_HOURLY = (
    "2020,1,1,1,0,1,0.0,-5.0,80,101325,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n"
    "2020,1,1,2,0,1,2.0,-3.0,70,101325,0,0,0,0,0,0,0,0,0,0,180,5.0,0,0,10,0,0,0,0,0,0,0,0\n"
    "2020,1,1,3,0,1,5.0,0.0,60,101325,0,0,0,100,50,20,0,0,0,0,270,10.0,0,0,10,0,0,0,0,0,0,0\n"
)


def test_read_epw_header():
    epw = _read_temp_epw()
    assert epw.location.city == "Test City"
    assert epw.location.state == "TS"
    assert epw.location.country == "Test Country"
    assert epw.location.data_source == "TEST"
    assert epw.location.wmo_number == "99999"
    assert epw.location.latitude == 52.0
    assert epw.location.longitude == 0.0
    assert epw.location.time_zone == 0.0
    assert epw.location.elevation == 35.0
    assert len(epw.records) == 3


def test_read_epw_fields():
    epw = _read_temp_epw()
    r0 = epw.records[0]
    assert r0.values["dry_bulb_temperature"] == 0.0
    r1 = epw.records[1]
    assert r1.values["dry_bulb_temperature"] == 2.0
    assert r1.values["relative_humidity"] == 70.0
    assert r1.values["wind_direction"] == 180.0
    assert r1.values["wind_speed"] == 5.0
    assert r1.values["direct_normal_solar"] == 0.0
    r2 = epw.records[2]
    assert r2.values["diffuse_horizontal_solar"] == 20.0


def test_monthly_stats():
    epw = _read_temp_epw()
    stats = monthly_stats(epw)
    assert 1 in stats
    t = stats[1]["dry_bulb_temperature"]
    assert t["min"] == 0.0
    assert t["max"] == 5.0
    assert abs(t["mean"] - (7.0 / 3.0)) < 1e-9
    assert t["count"] == 3


def test_wind_rose_bins():
    epw = _read_temp_epw()
    bins = wind_rose_bins(epw)
    assert len(bins) == 16
    total = sum(b["count"] for b in bins)
    assert total == 3  # all three records have wind data (record 0 is calm)
    # Record 2 has wind from 270 (West), record 1 from 180 (South).
    labels = {b["label"] for b in bins}
    assert "W" in labels or "S" in labels


def _read_temp_epw():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.epw")
        with open(path, "w") as handle:
            handle.write(EPW_HEADER)
            handle.write(EPW_HOURLY)
        return read_epw(path)
