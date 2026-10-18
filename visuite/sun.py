# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""Solar position calculations, port of VI-Suite's ``solarPosition`` /
``solarRiseSet`` (ASHRAE Fundamentals 2005, pp. 31.13-31.16).

Pure mathematics: no Blender, no external dependency. Given a day of year,
a local solar time, a latitude and a longitude, returns solar altitude and
azimuth in degrees. This is the computation core VI-Suite uses for sun
path, shadow study and daylight analyses; here it is exposed as headless
commands for IngeCAD's 2D drawing model.

All angles in degrees unless noted. Azimuth is measured clockwise from
North (0 = North, 90 = East, 180 = South, 270 = West), consistent with
VI-Suite's convention after the north-angle correction.
"""
from __future__ import annotations

import math

#: Earth's axial tilt (degrees), ASHRAE approximation used by VI-Suite.
OBLIQUITY = 23.45


def _deg2rad(deg: float) -> float:
    return deg * 2.0 * math.pi / 360.0


def _rad2deg(rad: float) -> float:
    return rad * 360.0 / (2.0 * math.pi)


def solar_position(day_of_year: int, local_solar_time: float,
                   latitude: float, longitude: float,
                   north_angle: float = 0.0) -> tuple[float, float, float, float]:
    """Solar position for a day and time.

    Returns ``(altitude_deg, azimuth_deg, altitude_rad, azimuth_rad)``.

    Port of VI-Suite's ``solarPosition``. Equation of time from the
    Wikipedia article; solar declination and hour angle per ASHRAE.
    Azimuth is corrected so that 0 = North and increases clockwise, with an
    optional ``north_angle`` offset (degrees clockwise from the drawing's Y
    axis) so results align with site north.
    """
    # Local standard time meridian (degrees of arc).
    lsm = round(longitude / 15.0) * 15.0
    # Equation of time (minutes), Wikipedia approximation.
    b = 2.0 * math.pi * (day_of_year - 81) / 364.0
    eq_time = 9.87 * math.sin(2.0 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    deg_to_rad = 2.0 * math.pi / 360.0
    rad_to_deg = 1.0 / deg_to_rad
    # Apparent solar time (decimal hours).
    if longitude > lsm:
        ast = local_solar_time + eq_time / 60.0 - (lsm - longitude) / 15.0
    else:
        ast = local_solar_time + eq_time / 60.0 + (lsm - longitude) / 15.0
    # Solar declination (radians).
    delta = deg_to_rad * OBLIQUITY * math.sin(2.0 * math.pi * (284.0 + day_of_year) / 365.0)
    # Hour angle (radians).
    h = deg_to_rad * 15.0 * (ast - 12.0)
    # Local latitude (radians).
    ll = deg_to_rad * latitude
    # Solar altitude (radians).
    beta = math.asin(math.cos(ll) * math.cos(delta) * math.cos(h)
                     + math.sin(ll) * math.sin(delta))
    # Solar azimuth (radians), before north correction.
    denom = math.cos(beta) * math.cos(ll)
    if abs(denom) < 1e-12:
        phi = 0.0
    else:
        phi = math.acos(max(-1.0, min(1.0,
                        (math.sin(beta) * math.sin(ll) - math.sin(delta)) / denom)))
    # VI-Suite flips azimuth for afternoon.
    phi = 2.0 * math.pi - phi if ast <= 12.0 or ast >= 24.0 else phi
    # Apply north-angle offset: azimuth measured clockwise from North.
    phi += _deg2rad(north_angle)
    altitude = _rad2deg(beta)
    azimuth = _rad2deg(phi) % 360.0
    return altitude, azimuth, beta, phi


def solar_rise_set(day_of_year: int, latitude: float, longitude: float,
                   north_angle: float = 0.0) -> tuple[float, float]:
    """Sunrise and sunset local solar times (decimal hours) for a day.

    Returns ``(sunrise, sunset)``. Returns ``(None, None)`` when the sun
    does not rise (polar night) or does not set (midnight sun).
    """
    deg_to_rad = 2.0 * math.pi / 360.0
    delta = deg_to_rad * OBLIQUITY * math.sin(2.0 * math.pi * (284.0 + day_of_year) / 365.0)
    ll = deg_to_rad * latitude
    # cos(hour_angle_at_sunrise) = -tan(lat) * tan(delta)
    arg = -math.tan(ll) * math.tan(delta)
    if arg >= 1.0:
        return None, None          # polar night
    if arg <= -1.0:
        return None, None          # midnight sun
    hour_angle = math.acos(max(-1.0, min(1.0, arg)))  # radians, 0..pi
    # Sunrise = 12 - HA/15, Sunset = 12 + HA/15 (approximate, ignoring eq. time).
    sunrise = 12.0 - hour_angle * 12.0 / math.pi
    sunset = 12.0 + hour_angle * 12.0 / math.pi
    return sunrise, sunset


def sun_vector(altitude_deg: float, azimuth_deg: float) -> tuple[float, float]:
    """Unit horizontal direction (x, y) of the sun's azimuth.

    x = sin(azimuth) (East), y = cos(azimuth) (North), so azimuth 0 =
    North points along +Y, 90 = East along +X.
    """
    rad = math.radians(azimuth_deg % 360.0)
    return math.sin(rad), math.cos(rad)


def altitude_angle(altitude_deg: float) -> float:
    """Solar altitude as a slope (tan of altitude) for shadow length."""
    return math.tan(math.radians(altitude_deg))
