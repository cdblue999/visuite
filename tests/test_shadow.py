# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""2D shadow computation is pure geometry."""
from __future__ import annotations

from visuite.shadow import compute_shadows


def test_compute_shadows_square():
    # One square footprint, sun low in the south (azimuth 180), altitude 30.
    footprint = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    studies = compute_shadows([footprint], 30.0, 180.0, height=10.0)
    assert len(studies) == 1
    st = studies[0]
    assert len(st.shadow) == 4
    assert len(st.connectors) == 4
    # Sun from the south -> shadows cast toward the north (+y).
    sy = min(p[1] for p in st.shadow)
    assert sy > 10.0   # shadow extends north of the footprint
    # connector connects each footprint vertex to its shadow counterpart
    assert st.connectors[0][0] == st.footprint[0]
    assert st.connectors[0][1] == st.shadow[0]


def test_compute_shadows_height_zero_rejected():
    footprint = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    try:
        compute_shadows([footprint], 30.0, 180.0, height=0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for zero height")


def test_compute_shadows_below_horizon_clamped():
    footprint = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    # altitude -10 (sun below horizon) -> clamped, finite shadow.
    studies = compute_shadows([footprint], -10.0, 180.0, height=10.0)
    assert len(studies) == 1
    assert len(studies[0].shadow) == 4
