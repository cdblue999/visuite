# VI-Suite for IngeTrazo / IngeCAD — Research & Planning

**Source:** https://github.com/rgsouthall/vi-suite07 (VI-Suite v0.7.0 for Blender 5.1)
**Docs:** https://blogs.brighton.ac.uk/visuite/
**Host target:** IngeCAD v0.6.5 (IngeTrazo-family 2D CAD), `PluginSpec` contract (`core/plugins.py`)

---

## 1. What vi-suite07 is

VI-Suite is a Blender add-on (GPL v2) that acts as a **pre/post-processor** for building performance simulation:

| Sub-system | Simulation engine | What it does |
|---|---|---|
| LiVi (Lighting & Visual) | Radiance | Daylight factor, illuminance, irradiance, BREEAM/RIBA/LEED compliance, CBDM (sDA/ASE/DA/UDI), glare (evalglare), artificial lighting (IES), BSDF, photon maps |
| EnVi (Energy & Ventilation) | EnergyPlus | Zone temperatures, heating/cooling, natural ventilation networks, air quality (CO2/PMV/PPD), EMS interface |
| FloVi (Flow) | OpenFOAM | CFD airflow (Linux only), mesh via Netgen |
| AuVi (Acoustics) | pyroomacoustics | Room impulse response, reverberation (RT60), STI |
| Context | — | Weather (EPW) plotting, sun path, wind rose, shadow study |

**Key facts from the source:**
- ~27k lines of Python across 13 modules (`vi_func`, `vi_node`, `vi_operators`, `vi_ui`, `vi_display`, `envi_*`, `livi_*`, `flovi_*`, `auvi_*`)
- Bundles **402 MB of EnergyPlus binaries** (EPFiles) and **44 MB of Radiance binaries** (RadFiles) for linux/win32/darwin
- Depends on `bpy` (Blender API), `matplotlib`, `scipy`, `PySide6`, `netgen`, `pyroomacoustics` — installs them via pip at runtime
- Deeply integrated with Blender: 3D scene, node editor, materials, animation, operators, panels, OpenGL HUDs
- Pure-math cores that are portable: `solarPosition(doy, lst, lat, lon)`, `solarRiseSet(...)` (ASHRAE-based sun position)

---

## 2. Feasibility analysis — what CANNOT be ported faithfully

The installed host is **IngeCAD v0.6.5**, a **2D CAD** whose document is an ezdxf drawing. Its plugin contract (`PluginSpec`) registers commands, tools, menus, toolbars, language packs, and a document-open hook. It has **no** Blender equivalents:

| vi-suite07 feature | Why it cannot be ported faithfully to IngeCAD |
|---|---|
| Blender node editor UI (LiVi/EnVi/FloVi/AuVi networks) | IngeCAD has no node system; PluginSpec is command/tool-based |
| bpy / 3D scene / materials / animation | IngeCAD is 2D; model is an ezdxf drawing (POINT/LINE/LWPOLYLINE/TEXT/3DFACE) |
| Radiance / EnergyPlus / OpenFOAM binaries | Not bundled with IngeCAD; not in its venv; running external sims is out of scope for a CAD plugin |
| matplotlib 2D plotting / Kivy monitoring | Not in IngeCAD venv (no matplotlib); IngeCAD has no plotting widget contract |
| netgen mesh generation / OpenFOAM CFD | Requires OpenFOAM + Netgen, not available here |
| OpenGL HUDs / 3D result display | IngeCAD's viewport is 2D CAD; no equivalent result-visualization contract |

**Honest conclusion:** A faithful "full functionality" port of vi-suite07 (Radiance + EnergyPlus + OpenFOAM + Blender 3D) to IngeCAD is **not possible**. The two programs are fundamentally different (3D environmental analysis modeller vs 2D CAD).

---

## 3. What CAN be ported (feasible subset)

These are the pure-computation and data-handling pieces that map cleanly to IngeCAD's `PluginSpec` command/tool contract and the available venv (`ezdxf`, `numpy`, `pyproj`, `PIL`, `urllib`):

### A. Solar position & sun path (port of `solarPosition` / `solarRiseSet`)
- `BG_SUNPOS <doy> <lst> <lat> <lon>` → solar altitude & azimuth (degrees), plus sunrise/sunset
- `BG_SUNPATH <doy>` → hourly sun positions for a day (report + optional 2D drawing of the sun path)
- Uses the drawing's georeference (GEOREF lat/lon) when available; otherwise user-supplied lat/lon
- Pure math, no external deps

### B. EPW weather file reader
- `BG_EPWINFO <file.epw>` → parse EnergyPlus Weather file header (location, lat/lon, time zone, elevation) and report
- `BG_EPWSTATS <file.epw>` → temperature/humidity/wind/solar hourly statistics (min/max/mean, extremes with dates)
- Pure Python stdlib parsing; no external deps

### C. Wind rose (data + 2D drawing)
- `BG_WINDROSE <file.epw>` → wind speed/direction frequency table from EPW; draw a 2D wind rose on `BLNDERGIS-VISUITE-WIND` layer (or `VISUITE-*`)

### D. Shadow study / solar access (2D)
- `BG_SHADOW <doy> <hour>` → given closed polygons (building footprints) and a solar position, compute and draw shadow polygons cast by the geometry
- Pure 2D geometry + solar position math

### E. Radiance / EnergyPlus input export
- `BG_EXPORT_RADIANCE` / `BG_EXPORT_ENERGYPLUS` → write simulation input files describing the drawing's geometry (2D footprints extruded conceptually), so the user can run them in an external Radiance/EnergyPlus install
- Document data: which polygons are "zones", "shading", "sensors"

---

## 4. Version differences — Blender vi-suite07 vs IngeTrazo/IngeCAD

| Aspect | vi-suite07 (Blender 5.1) | This port (IngeCAD v0.6.5) |
|---|---|---|
| Host API | `bpy` AddonPreferences, PropertyGroups, NodeTree, Operators, Panels | `core.plugins.PluginSpec` (commands, tools, menu, toolbar, i18n, on_document_open) |
| Document | Blender `.blend` (3D meshes, materials, nodes) | ezdxf `.dxf` (2D entities, layers, XDATA under `INGECAD` APPID) |
| Georeference | Scene latitude/longitude properties | `core.georef.Georef` (UTM zone + datum or EPSG CRS), declared via GEOREF |
| Coordinates | Blender local 3D | Drawing (easting/northing) via `core.coords`-style conversion (`coords.latlon_to_drawing` / `drawing_to_latlon`) |
| Mutations | bpy ops (immediate) | `Command` / `CompositeCommand` (undoable, one undo step) |
| UI | Blender panels/node editor | Command line + dialogs via `views.file_dialogs`; optional tray panel via `setup(app)` not available on v0.6.x |
| Language | English (Blender UI) | `tr()` English source strings; `i18n/en/ui.json` identity pack |
| License | GPL v2 | GPL-2.0-or-later (matching vi-suite07) |

---

## 5. Coding standards (per IngeCAD plugin contract)

1. **Headless `build_*` functions** return `CompositeCommand`s; thin `cmd_*` handlers run them via `ctx.execute` (one undo step) and echo plain-English reports.
2. **Every mutation is a Command** with an exact undo.
3. **Tools are thin shells** over actions, driven by AutoCAD-style prompts.
4. **Heavy imports deferred**; spec module imports nothing expensive.
5. **`requires`** lists missing modules so the plugin reports "unavailable" instead of crashing start-up.
6. **All user-visible strings English** via `tr()`; `i18n/en/` identity pack.
7. **No `requests`/`scipy`/`matplotlib`** — stdlib `urllib` only; pure-Python geometry.
8. **No duplicate top-level names** across plugin files (enforced by `tests/test_no_bundled_plugin_defines_a_top_level_name_twice.py`).
9. **Plugin id must equal folder name** (`visuite`); activate/deactivate leaves no trace (`tests/test_plugins.py`).

---

## 6. Open questions — scope confirmation needed

Before coding, I need your direction on these:

1. **Scope:** Given that the full vi-suite (Radiance/EnergyPlus/OpenFOAM + Blender 3D) cannot run in IngeCAD, should I implement the **feasible subset** above (sun position, sun path, EPW reader, wind rose, 2D shadow study, Radiance/EnergyPlus input export)? Or do you want only a specific subset?
2. **External engines:** Do you have Radiance, EnergyPlus, or OpenFOAM installed on this system? If so, should the plugin shell out to run them (e.g., `radfiles`, `energyplus` binaries), or only generate input files?
3. **3D vs 2D:** IngeCAD is 2D. Should shadow studies treat closed polygons as vertical extrusions (building footprints → shadows on the ground plane), or do you need true 3D?
4. **Repo name / GitHub:** Should this be a separate repository (e.g., `visuite-ingetrazo`)? I cannot create it without your GitHub credentials — you'll need to create the empty repo and give me the URL or a PAT.
5. **Install path:** Install to `~/.config/IngeCAD/plugins/visuite/` (user plugin, off by default, enabled via `PLUGINS`)?

Please confirm the scope and I'll proceed to coding + testing.
