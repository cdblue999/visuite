# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""Headless commands for the VI-Suite port: every mutation is a Command.

``build_*`` functions assemble a ``CompositeCommand`` from computation
results; ``cmd_*`` handlers run them through ``ctx.execute`` (one undo
step) and echo a plain-English report.

The feasible VI-Suite subset for IngeCAD (a 2D CAD, not a Blender
environment with Radiance/EnergyPlus/OpenFOAM):

- ``BG_SUNPOS`` / ``BG_SUNPATH`` / ``BG_SUNRISESET`` — solar position from
  the ASHRAE-based maths VI-Suite uses (:mod:`visuite.sun`).
- ``BG_EPWINFO`` / ``BG_EPWSTATS`` — EnergyPlus Weather file parsing
  (:mod:`visuite.epw`).
- ``BG_WINDROSE`` — wind rose drawn from EPW wind data.
- ``BG_SHADOW`` — 2D shadows cast by selected footprints (:mod:`visuite.shadow`).
- ``BG_EXPORT_RADIANCE`` / ``BG_EXPORT_ENERGYPLUS`` — simulation input
  files generated from the drawing's geometry.

Everything lands as plain DXF (LINE, LWPOLYLINE, POINT, TEXT) on
``VISUITE-*`` layers, with metadata in XDATA under the ``INGECAD`` APPID.
"""
from __future__ import annotations

import math
from pathlib import Path

from core.actions import AddEntityCommand, add_line, add_polyline, add_point, \
    add_text, add_circle
from core.commands import CompositeCommand
from core.georef import read_georef
from core.layers import NewLayerCommand
from core.xdata import APPID, ensure_appid

from . import epw, shadow, sun

# -- tags and layers ---------------------------------------------------------

SUN_TAG = "SUN"
SHADOW_TAG = "SHADOW"
WIND_TAG = "WIND"
EPW_TAG = "EPW"

SUN_LAYER = ("VISUITE-SUN", 4)
SHADOW_LAYER = ("VISUITE-SHADOW", 2)
WIND_LAYER = ("VISUITE-WIND", 5)
EPW_LAYER = ("VISUITE-EPW", 1)
CONNECTOR_LAYER = ("VISUITE-CONNECTOR", 8)


def _document(ctx):
    document = ctx.document
    if document is None:
        raise ValueError("no drawing is open")
    return document


def _ensure_layer(document, name: str, color: int = 7):
    if name not in document.doc.layers:
        return [NewLayerCommand(name, color=color)]
    return []


def _xdata(tag: str, kind: str, attributes: dict) -> list:
    pairs = [(1000, tag), (1000, kind)]
    for key, value in (attributes or {}).items():
        if value is None:
            continue
        pairs.append((1000, f"{key}={value}"[:250]))
    return pairs


def _tag_entity(entity, pairs) -> None:
    ensure_appid(entity.doc)
    entity.set_xdata(APPID, pairs)


def _label(text: str, x: float, y: float, height: float = 1.0):
    def make(msp, x=x, y=y, text=text):
        return msp.add_text(text, height=height)
    return make


# -- georeference <-> lat/lon ------------------------------------------------

try:                                            # pyproj is in the IngeCAD venv
    from pyproj import Proj, Transformer

    _HAS_PYPROJ = True
except Exception:                              # pragma: no cover - venv has pyproj
    _HAS_PYPROJ = False


def _georef_latlon(georef, x: float, y: float):
    """Drawing (x, y) -> WGS84 (lat, lon) using the drawing's georeference."""
    if not _HAS_PYPROJ:
        raise RuntimeError("converting drawing coordinates to lat/lon needs pyproj")
    if georef.crs:
        from_proj = Proj(georef.crs)
    else:
        hemisphere = "north" if georef.northern else "south"
        from_proj = Proj(f"+proj=utm +zone={georef.zone} +{hemisphere} "
                         "+datum=WGS84 +units=m +no_defs")
    to_proj = Proj("EPSG:4326")
    transformer = Transformer.from_proj(from_proj, to_proj, always_xy=True)
    lon, lat = transformer.transform(float(x), float(y))
    return lat, lon


def _georef_or_stop(ctx):
    document = _document(ctx)
    georef = read_georef(document.doc)
    if georef is None:
        raise ValueError("the drawing is not georeferenced: run GEOREF first, "
                         "or supply latitude/longitude explicitly")
    return georef


# ======================================================================
# Solar position / sun path / sunrise-sunset
# ======================================================================

def build_sunpath(document, georef, day_of_year: int, ref_x: float,
                  ref_y: float, north_angle: float = 0.0):
    """Hourly sun positions for one day as circles on VISUITE-SUN.

    Schematic plan-view sun path: radius scales with altitude, angle by
    azimuth. Returns ``(command, points, lat, lon)``.
    """
    lat, lon = _georef_latlon(georef, ref_x, ref_y)
    commands = _ensure_layer(document, *SUN_LAYER)
    points = []
    for hour in range(24):
        altitude, azimuth, _a_rad, _z_rad = sun.solar_position(
            day_of_year, hour, lat, lon, north_angle)
        if altitude < 0:
            continue
        radius = 10.0 + 5.0 * max(0.0, altitude) / 90.0
        sx, sy = sun.sun_vector(altitude, azimuth)
        px = ref_x + sx * radius
        py = ref_y + sy * radius

        def make(msp, x=px, y=py, r=radius, alt=altitude, az=azimuth):
            entity = msp.add_circle((x, y), r)
            _tag_entity(entity, _xdata(SUN_TAG, "sunpath",
                                       {"hour": hour, "alt": round(alt, 2),
                                        "az": round(az, 2)}))
            return entity

        commands.append(AddEntityCommand("SUN-POINT", make,
                                         layer=SUN_LAYER[0]))
        points.append((px, py, altitude, azimuth))
    return CompositeCommand("sun path", commands), points, lat, lon


# ======================================================================
# EPW weather
# ======================================================================

def build_epw_info(epw_file: epw.EpwFile) -> str:
    """Text report for an EPW file's location header; no DXF."""
    loc = epw_file.location
    return "\n".join([
        "EPW weather file header:",
        f"  Location: {loc.city}, {loc.state}, {loc.country}",
        f"  Data source: {loc.data_source}  (WMO {loc.wmo_number})",
        f"  Latitude: {loc.latitude}  Longitude: {loc.longitude}",
        f"  Time zone: {loc.time_zone}  Elevation: {loc.elevation} m",
        f"  Hourly records: {len(epw_file.records)}",
    ])


def build_epw_stats(document, epw_file: epw.EpwFile) -> CompositeCommand:
    """Draw monthly mean dry-bulb temperature as points on VISUITE-EPW."""
    commands = _ensure_layer(document, *EPW_LAYER)
    stats = epw.monthly_stats(epw_file)
    x = 0.0
    count = 0
    for month in sorted(stats):
        t = stats[month].get("dry_bulb_temperature")
        if t is None:
            continue
        y = t["mean"]

        def make(msp, x=x, y=y, m=month, mean=t["mean"]):
            entity = msp.add_point((x, y, 0.0))
            _tag_entity(entity, _xdata(EPW_TAG, "epw-temp",
                                       {"month": m, "mean_c": round(mean, 1)}))
            return entity

        commands.append(AddEntityCommand("EPW-TEMP", make, layer=EPW_LAYER[0]))
        commands.append(AddEntityCommand("EPW-LABEL", _label(
            f"M{month} {t['mean']:.1f}C", x, y + 2.0), layer=EPW_LAYER[0]))
        count += 1
        x += 30.0
    return CompositeCommand("EPW weather statistics", commands), count


# ======================================================================
# Wind rose
# ======================================================================

def build_wind_rose(document, epw_file: epw.EpwFile,
                    center: tuple[float, float], radius: float = 40.0):
    """Draw a 2D wind rose from EPW wind direction/speed frequency."""
    commands = _ensure_layer(document, *WIND_LAYER)
    cx, cy = center
    bins = epw.wind_rose_bins(epw_file)
    if not bins:
        return CompositeCommand("wind rose", commands), 0
    max_count = max(b["count"] for b in bins) or 1

    def make_calm(msp, cx=cx, cy=cy, r=radius):
        entity = msp.add_circle((cx, cy), max(2.0, r * 0.05))
        _tag_entity(entity, _xdata(WIND_TAG, "calm", {}))
        return entity

    commands.append(AddEntityCommand("WIND-CALM", make_calm,
                                     layer=WIND_LAYER[0]))
    drawn = 1
    for b in bins:
        if b["count"] == 0:
            continue
        length = radius * (b["count"] / max_count)
        angle = math.radians(b["center_deg"])
        ex = cx + math.sin(angle) * length
        ey = cy + math.cos(angle) * length

        def make(msp, cx=cx, cy=cy, ex=ex, ey=ey, label=b["label"],
                 freq=b["frequency_pct"]):
            entity = msp.add_line((cx, cy), (ex, ey))
            _tag_entity(entity, _xdata(WIND_TAG, "sector",
                                       {"sector": b["sector"],
                                        "freq_pct": round(freq, 1)}))
            return entity

        commands.append(AddEntityCommand("WIND-SECTOR", make,
                                         layer=WIND_LAYER[0]))
        commands.append(AddEntityCommand("WIND-LABEL", _label(
            f"{b['label']} {b['frequency_pct']:.0f}%", ex, ey),
            layer=WIND_LAYER[0]))
        drawn += 1
    return CompositeCommand("wind rose", commands), drawn


# ======================================================================
# Shadow study
# ======================================================================

def build_shadows(document, footprints: list[list[tuple[float, float]]],
                  altitude_deg: float, azimuth_deg: float,
                  height: float = 10.0):
    """Draw shadows cast by footprints on VISUITE-SHADOW."""
    studies = shadow.compute_shadows(footprints, altitude_deg, azimuth_deg,
                                     height)
    commands = _ensure_layer(document, *SHADOW_LAYER)
    commands.extend(_ensure_layer(document, *CONNECTOR_LAYER))
    drawn = 0
    for st in studies:
        def make_fp(msp, fp=st.footprint):
            entity = msp.add_lwpolyline([(p[0], p[1]) for p in fp], close=True)
            _tag_entity(entity, _xdata(SHADOW_TAG, "footprint",
                                       {"height": st.height}))
            return entity
        commands.append(AddEntityCommand("SHADOW-FOOTPRINT", make_fp,
                                         layer=SHADOW_LAYER[0]))

        def make_sh(msp, sh=st.shadow):
            entity = msp.add_lwpolyline([(p[0], p[1]) for p in sh], close=True)
            _tag_entity(entity, _xdata(SHADOW_TAG, "shadow",
                                       {"alt": st.altitude, "az": st.azimuth}))
            return entity
        commands.append(AddEntityCommand("SHADOW-POLYGON", make_sh,
                                         layer=SHADOW_LAYER[0]))

        for (a, b) in st.connectors:
            def make_c(msp, a=a, b=b):
                return msp.add_line(a, b)
            commands.append(AddEntityCommand("SHADOW-CONNECTOR", make_c,
                                             layer=CONNECTOR_LAYER[0]))
        drawn += 1
    return CompositeCommand("shadow study", commands), drawn


# ======================================================================
# Radiance export
# ======================================================================

def build_radiance_export(path: str | Path,
                          entities) -> str:
    """Write selected closed polygons as a Radiance scene (``.rad``).

    Returns the text written to ``path`` (the file is written to disk
    directly; the command records the export for undo reporting).
    """
    lines = []
    lines.append("# VI-Suite Radiance export from IngeCAD drawing")
    lines.append("# Generated by BG_EXPORT_RADIANCE\n")
    lines.append("void plastic default_material")
    lines.append("0")
    lines.append("0")
    lines.append("5 0.8 0.8 0.8 0.0 0.0")
    lines.append("")
    index = 1
    for entity in entities:
        if entity.dxftype() not in ("LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC"):
            continue
        try:
            from ezdxf.path import make_path
            pts = [(p.x, p.y) for p in make_path(entity).flattening(0.05)]
        except Exception:
            continue
        if len(pts) < 3:
            continue
        name = f"footprint_{index}"
        lines.append(f"void polygon {name}")
        lines.append("0")
        lines.append("0")
        lines.append(f"12 {len(pts)}")
        for x, y in pts:
            lines.append(f"  {x:.4f} {y:.4f} 0.0")
        lines.append("")
        index += 1
    if index == 1:
        lines.append("# No closed polygons found to export.")
    content = "\n".join(lines) + "\n"
    Path(path).write_text(content, encoding="utf-8")
    return content


# ======================================================================
# EnergyPlus export
# ======================================================================

def build_energyplus_export(path: str | Path,
                            entities) -> str:
    """Write selected closed polygons as a minimal EnergyPlus IDF.

    Each footprint becomes one zone with a floor defined by the polygon
    vertices on the ground plane. A minimal valid IDF is emitted.
    """
    lines = []
    lines.append("! VI-Suite EnergyPlus export from IngeCAD drawing")
    lines.append("! Generated by BG_EXPORT_ENERGYPLUS\n")
    lines.append("Version, 25.1.0;")
    lines.append("Buildings,")
    lines.append("    DrawingExport,            !- Name")
    lines.append("    0,                        !- North Axis {deg}")
    lines.append("    0,                        !- Terrain")
    lines.append("    4,                        !- Number of Stories")
    lines.append("    0,                        !- Floor Height")
    lines.append("    ;\n")
    index = 1
    for entity in entities:
        if entity.dxftype() not in ("LWPOLYLINE", "POLYLINE"):
            continue
        try:
            from ezdxf.path import make_path
            pts = [(p.x, p.y) for p in make_path(entity).flattening(0.05)]
        except Exception:
            continue
        if len(pts) < 3:
            continue
        name = f"Zone{index}_Floor"
        lines.append("BuildingSurface:Detailed,")
        lines.append("    Floor,                    !- Surface Type")
        lines.append(f"    Zone{index},              !- Zone Name")
        lines.append("    default_material,         !- Construction Name")
        lines.append(f"    {len(pts)},               !- Number of Vertices")
        for x, y in pts:
            lines.append(f"    {x:.4f}, {y:.4f}, 0.0,      !- Vertex X,Y,Z")
        lines.append("    ;\n")
        index += 1
    if index == 1:
        lines.append("! No closed polygons found to export as zones.\n")
    content = "\n".join(lines) + "\n"
    Path(path).write_text(content, encoding="utf-8")
    return content


# ======================================================================
# Command handlers
# ======================================================================

def _guarded(handler):
    def run(ctx, *args):
        try:
            return handler(ctx, *args)
        except Exception as exc:
            ctx.echo(f"VI-Suite: {exc}")
    return run


@_guarded
def cmd_sunpos(ctx, *args):
    """BG_SUNPOS <doy> <lst> [lat] [lon] [north_angle]: report the solar
    position (altitude, azimuth) for one day/time, using the drawing's
    georeference when lat/lon are omitted."""
    if len(args) < 2:
        ctx.echo("Usage: BG_SUNPOS <day_of_year> <local_solar_time> "
                 "[lat] [lon] [north_angle_deg]")
        return
    try:
        doy = int(args[0])
        lst = float(args[1].replace(",", "."))
    except ValueError:
        ctx.echo("day_of_year and local_solar_time must be numbers.")
        return
    lat = lon = None
    north_angle = 0.0
    if len(args) >= 4:
        try:
            lat = float(args[2].replace(",", "."))
            lon = float(args[3].replace(",", "."))
        except ValueError:
            ctx.echo("lat and lon must be numbers.")
            return
        if len(args) >= 5:
            try:
                north_angle = float(args[4].replace(",", "."))
            except ValueError:
                ctx.echo("north_angle must be a number.")
                return
    else:
        georef = _georef_or_stop(ctx)
        lat, lon = _georef_latlon(georef, 0.0, 0.0)
    altitude, azimuth, _a_rad, _z_rad = sun.solar_position(
        doy, lst, lat, lon, north_angle)
    ctx.echo(f"Solar position doy={doy} lst={lst:g}: "
             f"altitude={altitude:.2f}°  azimuth={azimuth:.2f}° "
             f"(lat={lat:.4f}  lon={lon:.4f})")


@_guarded
def cmd_sunpath(ctx, *args):
    """BG_SUNPATH <doy> [north_angle]: draw the day's hourly sun path as
    circles on VISUITE-SUN around the drawing origin (georef origin)."""
    if len(args) < 1:
        ctx.echo("Usage: BG_SUNPATH <day_of_year> [north_angle_deg]")
        return
    try:
        doy = int(args[0])
    except ValueError:
        ctx.echo("day_of_year must be an integer.")
        return
    north_angle = 0.0
    if len(args) >= 2:
        try:
            north_angle = float(args[1].replace(",", "."))
        except ValueError:
            ctx.echo("north_angle must be a number.")
            return
    georef = _georef_or_stop(ctx)
    document = _document(ctx)
    command, points, lat, lon = build_sunpath(
        document, georef, doy, 0.0, 0.0, north_angle)
    ctx.execute(command)
    ctx.echo(f"Sun path for day {doy} (lat={lat:.4f}, lon={lon:.4f}): "
             f"{len(points)} sun positions drawn on {SUN_LAYER[0]}.")


@_guarded
def cmd_sunriset(ctx, *args):
    """BG_SUNRISESET <doy>: report sunrise and sunset local solar times."""
    if len(args) < 1:
        ctx.echo("Usage: BG_SUNRISESET <day_of_year>")
        return
    try:
        doy = int(args[0])
    except ValueError:
        ctx.echo("day_of_year must be an integer.")
        return
    georef = _georef_or_stop(ctx)
    lat, lon = _georef_latlon(georef, 0.0, 0.0)
    rise, set_ = sun.solar_rise_set(doy, lat, lon)
    if rise is None:
        ctx.echo(f"Day {doy}: polar night or midnight sun at lat={lat:.4f}.")
        return
    ctx.echo(f"Day {doy} (lat={lat:.4f}, lon={lon:.4f}): "
             f"sunrise {rise:.2f}h  sunset {set_:.2f}h")


@_guarded
def cmd_epwinfo(ctx, *args):
    """BG_EPWINFO <file.epw>: report an EnergyPlus Weather file's location
    header (city, lat/lon, time zone, elevation, record count)."""
    if len(args) != 1:
        ctx.echo("Usage: BG_EPWINFO <file.epw>")
        return
    try:
        epw_file = epw.read_epw(args[0])
    except (OSError, ValueError) as exc:
        ctx.echo(f"Cannot read {args[0]}: {exc}")
        return
    ctx.echo(build_epw_info(epw_file))


@_guarded
def cmd_epwstats(ctx, *args):
    """BG_EPWSTATS <file.epw>: draw monthly mean dry-bulb temperature as
    points on VISUITE-EPW and report monthly stats."""
    if len(args) != 1:
        ctx.echo("Usage: BG_EPWSTATS <file.epw>")
        return
    try:
        epw_file = epw.read_epw(args[0])
    except (OSError, ValueError) as exc:
        ctx.echo(f"Cannot read {args[0]}: {exc}")
        return
    document = _document(ctx)
    command, count = build_epw_stats(document, epw_file)
    ctx.execute(command)
    stats = epw.monthly_stats(epw_file)
    lines = ["Monthly dry-bulb temperature (C):"]
    for month in sorted(stats):
        t = stats[month].get("dry_bulb_temperature")
        if t:
            lines.append(f"  M{month}: min={t['min']:.1f}  mean={t['mean']:.1f}  "
                         f"max={t['max']:.1f}  (n={t['count']})")
    ctx.echo(f"{count} monthly mean points drawn on {EPW_LAYER[0]}.\n"
             + "\n".join(lines))


@_guarded
def cmd_windrose(ctx, *args):
    """BG_WINDROSE <file.epw> [cx] [cy] [radius]: draw a 2D wind rose from
    EPW wind direction/speed frequency on VISUITE-WIND."""
    if len(args) < 1:
        ctx.echo("Usage: BG_WINDROSE <file.epw> [cx] [cy] [radius]")
        return
    try:
        epw_file = epw.read_epw(args[0])
    except (OSError, ValueError) as exc:
        ctx.echo(f"Cannot read {args[0]}: {exc}")
        return
    cx = cy = 0.0
    radius = 40.0
    if len(args) >= 3:
        try:
            cx = float(args[1].replace(",", "."))
            cy = float(args[2].replace(",", "."))
        except ValueError:
            ctx.echo("cx and cy must be numbers.")
            return
    if len(args) >= 4:
        try:
            radius = float(args[3].replace(",", "."))
        except ValueError:
            ctx.echo("radius must be a number.")
            return
    document = _document(ctx)
    command, drawn = build_wind_rose(document, epw_file, (cx, cy), radius)
    ctx.execute(command)
    bins = epw.wind_rose_bins(epw_file)
    top = bins[0] if bins else None
    ctx.echo(f"Wind rose drawn on {WIND_LAYER[0]} ({drawn} entities, "
             f"{len(bins)} sectors)."
             + (f"  Predominant: {top['label']} {top['frequency_pct']:.0f}%"
                if top else ""))


@_guarded
def cmd_shadow(ctx, *args):
    """BG_SHADOW <doy> <hour> [height]: draw shadows cast by the selected
    closed polygons (or all closed LWPOLYLINEs) for one day/hour on
    VISUITE-SHADOW. Height defaults to 10 m."""
    if len(args) < 2:
        ctx.echo("Usage: BG_SHADOW <day_of_year> <hour> [height_m]")
        return
    try:
        doy = int(args[0])
        hour = float(args[1].replace(",", "."))
    except ValueError:
        ctx.echo("day_of_year and hour must be numbers.")
        return
    height = 10.0
    if len(args) >= 3:
        try:
            height = float(args[2].replace(",", "."))
        except ValueError:
            ctx.echo("height must be a number.")
            return
    georef = _georef_or_stop(ctx)
    lat, lon = _georef_latlon(georef, 0.0, 0.0)
    altitude, azimuth, _a, _z = sun.solar_position(doy, hour, lat, lon)
    if altitude <= 0:
        ctx.echo(f"The sun is below the horizon at doy={doy} hour={hour:g} "
                 f"(altitude={altitude:.2f}°): no shadow.")
        return
    document = _document(ctx)
    from ezdxf.path import make_path
    footprints = []
    for entity in list(document.doc.modelspace()):
        if entity.dxftype() not in ("LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC"):
            continue
        try:
            pts = [(p.x, p.y) for p in make_path(entity).flattening(0.05)]
        except Exception:
            continue
        if len(pts) >= 3:
            footprints.append(pts)
    if not footprints:
        ctx.echo("No closed polygons found: draw building footprints as "
                 "closed LWPOLYLINEs and select them (or run with all).")
        return
    command, drawn = build_shadows(document, footprints, altitude, azimuth,
                                   height)
    ctx.execute(command)
    ctx.echo(f"Shadow study for doy={doy} hour={hour:g} "
             f"(sun alt={altitude:.2f}° az={azimuth:.2f}°, height={height:g}m): "
             f"{drawn} footprint(s) shadowed on {SHADOW_LAYER[0]}.")


@_guarded
def cmd_export_radiance(ctx, *args):
    """BG_EXPORT_RADIANCE [file.rad]: write selected closed polygons (or
    all) as a Radiance scene (``.rad``) for an external Radiance run."""
    document = _document(ctx)
    path = args[0] if args else None
    if path is None:
        from views import file_dialogs
        path = file_dialogs.get_save_file(
            ctx.host, "Export Radiance scene", "scene.rad",
            "Radiance scene (*.rad);;All files (*)")
        if not path:
            return
    from ezdxf.path import make_path
    entities = [e for e in list(document.doc.modelspace())
                if e.dxftype() in ("LWPOLYLINE", "POLYLINE")]
    try:
        content = build_radiance_export(path, entities)
    except OSError as exc:
        ctx.echo(str(exc))
        return
    n = content.count("void polygon")
    ctx.echo(f"{n} polygon(s) written to {path} for Radiance.")


@_guarded
def cmd_export_energyplus(ctx, *args):
    """BG_EXPORT_ENERGYPLUS [file.idf]: write selected closed polygons as
    a minimal EnergyPlus IDF (zones from footprints) for an external run."""
    document = _document(ctx)
    path = args[0] if args else None
    if path is None:
        from views import file_dialogs
        path = file_dialogs.get_save_file(
            ctx.host, "Export EnergyPlus IDF", "model.idf",
            "EnergyPlus IDF (*.idf);;All files (*)")
        if not path:
            return
    from ezdxf.path import make_path
    entities = [e for e in list(document.doc.modelspace())
                if e.dxftype() in ("LWPOLYLINE", "POLYLINE")]
    try:
        content = build_energyplus_export(path, entities)
    except OSError as exc:
        ctx.echo(str(exc))
        return
    n = content.count("BuildingSurface:Detailed,")
    ctx.echo(f"{n} zone(s) written to {path} for EnergyPlus.")
