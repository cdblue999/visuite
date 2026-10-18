# VI-Suite for IngeTrazo / IngeCAD

A port of the feasible subset of
[VI-Suite](https://github.com/rgsouthall/vi-suite07) (Ryan Southall,
https://blogs.brighton.ac.uk/visuite/) to IngeTrazo's CAD (here running as
**IngeCAD v0.6.5**, the IngeTrazo-family 2D CAD installed on this system).

VI-Suite is a Blender add-on that pre/post-processes Radiance, EnergyPlus
and OpenFOAM building simulations. That full stack (Blender's `bpy` 3D
scene, node editor, Radiance/EnergyPlus/OpenFOAM binaries, matplotlib)
cannot run in IngeCAD, which is a 2D CAD whose document is an ezdxf
drawing. This port implements the feasible subset:

```
Command line: BG_*  (typed at the IngeCAD command line)
```

## Features

| Command | What it does |
|---|---|
| `BG_SUNPOS <doy> <lst> [lat] [lon] [north]` | Solar position (altitude, azimuth) for one day/time, using the drawing's georeference (GEOREF) when lat/lon are omitted. ASHRAE-based maths, as in VI-Suite. |
| `BG_SUNPATH <doy> [north]` | Draws the day's hourly sun path as circles on `VISUITE-SUN` around the drawing origin; radius scales with altitude. |
| `BG_SUNRISESET <doy>` | Sunrise and sunset local solar times. |
| `BG_EPWINFO <file.epw>` | EnergyPlus Weather file location header (city, lat/lon, time zone, elevation, record count). |
| `BG_EPWSTATS <file.epw>` | Draws monthly mean dry-bulb temperature as points on `VISUITE-EPW` and reports monthly min/mean/max. |
| `BG_WINDROSE <file.epw> [cx] [cy] [radius]` | Draws a 2D wind rose from EPW wind direction/speed frequency on `VISUITE-WIND`. |
| `BG_SHADOW <doy> <hour> [height]` | Draws 2D shadows cast by closed polygon footprints (building footprints) on `VISUITE-SHADOW`, extruded to a given height (default 10 m). |
| `BG_EXPORT_RADIANCE [file.rad]` | Writes selected closed polygons as a Radiance scene (`.rad`) for an external Radiance run. |
| `BG_EXPORT_ENERGYPLUS [file.idf]` | Writes selected closed polygons as a minimal EnergyPlus IDF (zones from footprints) for an external run. |
| `BG_SUN` (tool) | Pick a point; draws a sun arrow there for the chosen day/hour, pointing in the sun's horizontal direction, labelled with altitude/azimuth. |

All mutations are undoable Commands; everything lands as plain DXF
(LINE, LWPOLYLINE, POINT, CIRCLE, TEXT) on `VISUITE-*` layers, with
metadata in XDATA under the `INGECAD` APPID. All user-visible strings are
**English only**.

## Install

Copy the `visuite/` folder into IngeCAD's user plugins directory:

- Linux: `~/.config/IngeCAD/plugins/visuite/`
- Windows: `%APPDATA%\ingetrazo\plugins\visuite\`

Then start IngeCAD and enable it in **Tools ▸ Plugins…** (`PLUGINS`
command). User plugins are off by default and the choice is remembered.

Requires `pyproj` and `numpy` (both in the IngeCAD venv). If either is
missing the plugin reports itself as *unavailable* instead of breaking
start-up.

## Version differences: Blender VI-Suite vs IngeTrazo/IngeCAD

| | VI-Suite (Blender 5.1) | This port (IngeCAD v0.6.5) |
|---|---|---|
| Host API | Blender `bpy` add-on (PropertyGroups, NodeTree, Operators, Panels) | IngeCAD `PluginSpec` contract (`core/plugins.py`: commands, tools, menu, toolbar, i18n) |
| Document | `.blend` (3D meshes, materials, nodes) | `.dxf` (2D entities, layers, XDATA under `INGECAD` APPID) |
| Georeference | Scene latitude/longitude | `core.georef.Georef` (UTM zone + datum or EPSG CRS) via GEOREF |
| Coordinates | Blender local 3D | Drawing easting/northing via pyproj WGS84<->UTM/CRS |
| Mutations | Immediate bpy ops | Undoable `Command` (one undo step) |
| UI | Blender panels / node editor | Command line + file dialogs |
| Simulation | Radiance / EnergyPlus / OpenFOAM binaries bundled | Not bundled; export commands write input files for external runs |

## Coding standards

1. Headless `build_*` functions return `CompositeCommand`s; thin `cmd_*`
   handlers run them via `ctx.execute` (one undo step) and echo plain
   English reports.
2. Every mutation is a Command with an exact undo.
3. Tools are thin shells over the actions, driven by AutoCAD-style prompts.
4. Heavy imports deferred; the spec module imports nothing expensive.
5. `requires` lists missing modules so the plugin reports "unavailable"
   instead of crashing start-up.
6. All strings English via `tr()`; `i18n/en/` identity pack.
7. No `requests`/`scipy`/`matplotlib` — stdlib `urllib` only; pure-Python
   geometry (Bowyer-Watson not needed here).
8. No duplicate top-level names across plugin files.
9. Plugin id equals folder name (`visuite`); activate/deactivate leaves no
   trace.

## Tests

`pytest tests/` (with the IngeCAD source on `sys.path`, or
`INGECAD_ROOT` set) runs headless: solar position maths, EPW parsing,
shadow geometry, and the headless commands on a real in-memory ezdxf
drawing.

## License

GPL-2.0-or-later, same as the original VI-Suite
(https://github.com/rgsouthall/vi-suite07).
