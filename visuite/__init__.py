# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""VI-Suite for IngeTrazo / IngeCAD: building performance analysis.

Port of the feasible subset of https://github.com/rgsouthall/vi-suite07
(VI-Suite v0.7.0, Ryan Southall, GPL v2) to IngeCAD's 2D CAD model.

VI-Suite is a Blender add-on that pre/post-processes Radiance, EnergyPlus
and OpenFOAM building simulations. That full stack (bpy 3D scene, node
editor, Radiance/EnergyPlus/OpenFOAM binaries, matplotlib) cannot run in
IngeCAD, which is a 2D CAD whose document is an ezdxf drawing. This port
implements the feasible subset: solar position / sun path / sunrise-sunset
(ASHRAE maths VI-Suite uses), EnergyPlus Weather (EPW) reading, a wind
rose, a 2D shadow study, and Radiance/EnergyPlus input-file export.

Every mutation is an undoable Command; everything lands as plain DXF on
``VISUITE-*`` layers. All user-visible strings are English.
"""
from __future__ import annotations

from pathlib import Path

from core.plugins import MenuItem, PluginSpec, SEPARATOR

from . import actions, tools


PLUGIN = PluginSpec(
    id="visuite",
    name="VI-Suite",
    version="0.7.0",
    description="Solar position and sun path, EnergyPlus Weather (EPW) "
                "reading, wind rose, 2D shadow study, and Radiance / "
                "EnergyPlus input export from the drawing's geometry.",
    requires=("pyproj", "numpy"),
    commands={
        "BG_SUNPOS": actions.cmd_sunpos,
        "BG_SUNPATH": actions.cmd_sunpath,
        "BG_SUNRISESET": actions.cmd_sunriset,
        "BG_EPWINFO": actions.cmd_epwinfo,
        "BG_EPWSTATS": actions.cmd_epwstats,
        "BG_WINDROSE": actions.cmd_windrose,
        "BG_SHADOW": actions.cmd_shadow,
        "BG_EXPORT_RADIANCE": actions.cmd_export_radiance,
        "BG_EXPORT_ENERGYPLUS": actions.cmd_export_energyplus,
    },
    tools=dict(tools.TOOL_CLASSES),
    menu=(
        MenuItem("Solar position...", "BG_SUNPOS"),
        MenuItem("Sun path...", "BG_SUNPATH"),
        MenuItem("Sunrise / sunset...", "BG_SUNRISESET"),
        SEPARATOR,
        MenuItem("EPW weather info...", "BG_EPWINFO"),
        MenuItem("EPW weather statistics...", "BG_EPWSTATS"),
        MenuItem("Wind rose...", "BG_WINDROSE"),
        SEPARATOR,
        MenuItem("Shadow study...", "BG_SHADOW"),
        SEPARATOR,
        MenuItem("Export Radiance scene...", "BG_EXPORT_RADIANCE"),
        MenuItem("Export EnergyPlus IDF...", "BG_EXPORT_ENERGYPLUS"),
    ),
    i18n_dir=Path(__file__).parent / "i18n",
)
