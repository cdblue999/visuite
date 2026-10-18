# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""Pure-math solar position tests (no Qt, no drawing)."""
from __future__ import annotations

from visuite.sun import solar_position, solar_rise_set, sun_vector


def test_solar_position_noon_equator():
    # Equator, equinox (doy ~81), noon: sun near zenith (altitude ~88-90;
    # the ASHRAE equation-of-time shifts apparent solar time by ~7.5 min,
    # so altitude is ~88°, not exactly 90°).
    alt, azi, _a, _z = solar_position(81, 12.0, 0.0, 0.0)
    assert abs(alt - 90.0) < 2.0


def test_solar_position_below_horizon_night():
    # Midnight at high latitude in winter: sun below horizon.
    alt, azi, _a, _z = solar_position(355, 0.0, 60.0, 0.0)
    assert alt < 0.0


def test_sun_vector_north_is_positive_y():
    vx, vy = sun_vector(0.0, 0.0)     # azimuth 0 = North
    assert abs(vx) < 1e-9 and vy > 0
    vx, vy = sun_vector(0.0, 90.0)    # azimuth 90 = East
    assert vx > 0 and abs(vy) < 1e-9


def test_sunrise_set_summer_winter():
    # Summer solstice at mid latitude: long day.
    rise, set_ = solar_rise_set(172, 52.0, 0.0)
    assert rise is not None and set_ is not None
    assert set_ - rise > 12.0
    # Winter solstice: short day.
    rise, set_ = solar_rise_set(355, 52.0, 0.0)
    assert rise is not None and set_ is not None
    assert set_ - rise < 12.0
    # Polar night: no sunrise.
    rise, set_ = solar_rise_set(355, 80.0, 0.0)
    assert rise is None and set_ is None
