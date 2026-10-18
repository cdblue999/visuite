# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""2D shadow study, port of the shadow-study idea in VI-Suite's LiVi.

Given closed polygons (building footprints) in the drawing and a solar
position (altitude, azimuth), compute the shadow each footprint casts on
the ground plane, assuming each footprint is extruded to a given height.

For each footprint vertex ``v`` the shadow vertex is::

    v_shadow = v - sun_direction * height * cot(altitude)

where ``sun_direction`` points from the ground toward the sun (East =
+x, North = +y) and the minus sign casts the shadow away from the sun.
The original footprint and its shadow are both drawn, with connector
lines from each vertex to its shadow counterpart, so the shadow volume is
visible in 2D.

Pure 2D geometry: no Blender, no Radiance. Building height is a single
value applied to every footprint (a real study would use per-zone
heights; this keeps the command simple).
"""
from __future__ import annotations

from dataclasses import dataclass

from .sun import sun_vector, altitude_angle


@dataclass
class ShadowStudy:
    """One footprint's shadow: original vertices, shadow vertices, connectors."""

    footprint: list[tuple[float, float]]
    shadow: list[tuple[float, float]]
    connectors: list[tuple[tuple[float, float], tuple[float, float]]]
    altitude: float
    azimuth: float
    height: float
    shadow_vector: tuple[float, float]


def compute_shadows(footprints: list[list[tuple[float, float]]],
                    altitude_deg: float, azimuth_deg: float,
                    height: float) -> list[ShadowStudy]:
    """Compute shadows for every footprint."""
    if height <= 0:
        raise ValueError("building height must be greater than zero")
    alt = altitude_deg
    if alt <= 0:
        # Sun below or on the horizon: no meaningful shadow direction;
        # shadows fall straight behind at infinite length. Clamp to a tiny
        # positive altitude so the math stays finite.
        alt = 0.1
    sx, sy = sun_vector(alt, azimuth_deg)          # toward the sun
    cot = 1.0 / altitude_angle(alt) if abs(altitude_angle(alt)) > 1e-9 else 1e6
    shadow_vector = (-sx * height * cot, -sy * height * cot)  # away from sun

    studies: list[ShadowStudy] = []
    for footprint in footprints:
        if len(footprint) < 3:
            continue
        shadow = [(v[0] + shadow_vector[0], v[1] + shadow_vector[1])
                  for v in footprint]
        connectors = [(footprint[i], shadow[i]) for i in range(len(footprint))]
        studies.append(ShadowStudy(
            footprint=footprint, shadow=shadow, connectors=connectors,
            altitude=altitude_deg, azimuth=azimuth_deg, height=height,
            shadow_vector=shadow_vector))
    return studies
