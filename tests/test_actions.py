# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""Headless command tests against a real ezdxf drawing in memory."""
from __future__ import annotations

import os
import tempfile

import ezdxf

from ezdxf.path import make_path

from visuite.actions import (
    build_sunpath, build_epw_stats, build_wind_rose, build_shadows,
    build_radiance_export, build_energyplus_export,
)
from visuite.epw import read_epw

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
EPW_HOURLY = (
    "2020,6,21,12,0,1,20.0,10.0,50,101325,0,0,0,800,600,200,0,0,0,0,180,5.0,0,0,10,0,0,0,0,0,0,0\n"
)


class FakeDocument:
    def __init__(self, drawing):
        self.doc = drawing
        self.dirty = False

    def current_space(self):
        return self.doc.modelspace()


class FakeGeoref:
    def __init__(self, crs="", zone=31, northern=True, datum="WGS84",
                 shift=(0.0, 0.0, 0.0)):
        self.crs = crs
        self.zone = zone
        self.northern = northern
        self.datum = datum
        self.shift = shift


class FakeCtx:
    def __init__(self, document, host=None):
        self.document = document
        self.host = host
        self.echoed = []

    def echo(self, text):
        self.echoed.append(text)

    def execute(self, command):
        command.do(self.document)


def _doc_with_polygons():
    drawing = ezdxf.new()
    msp = drawing.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
    msp.add_lwpolyline([(20, 0), (30, 0), (30, 10), (20, 10)], close=True)
    return FakeDocument(drawing)


def test_build_sunpath_creates_circles_and_undoes():
    doc = FakeDocument(ezdxf.new())
    georef = FakeGeoref()
    command, points, lat, lon = build_sunpath(doc, georef, 172, 0.0, 0.0, 0.0)
    assert len(points) > 0   # some hours above horizon at lat 52 on solstice
    command.do(doc)
    circles = list(doc.doc.modelspace().query("CIRCLE"))
    assert len(circles) == len(points)
    command.undo(doc)
    assert list(doc.doc.modelspace().query("CIRCLE")) == []


def test_build_epw_stats_creates_points_and_undoes():
    epw_file = _read_temp_epw()
    doc = FakeDocument(ezdxf.new())
    command, count = build_epw_stats(doc, epw_file)
    assert count >= 1
    command.do(doc)
    assert len(list(doc.doc.modelspace().query("POINT"))) == count
    command.undo(doc)
    assert list(doc.doc.modelspace().query("POINT")) == []


def test_build_wind_rose_creates_entities_and_undoes():
    epw_file = _read_temp_epw()
    doc = FakeDocument(ezdxf.new())
    command, drawn = build_wind_rose(doc, epw_file, (0.0, 0.0), 40.0)
    assert drawn >= 1
    command.do(doc)
    assert len(list(doc.doc.modelspace().query("LINE"))) >= 1
    command.undo(doc)
    assert list(doc.doc.modelspace().query("LINE")) == []


def test_build_shadows_creates_shadows_and_undoes():
    doc = _doc_with_polygons()
    from ezdxf.path import make_path
    footprints = []
    for entity in doc.doc.modelspace():
        if entity.dxftype() not in ("LWPOLYLINE", "POLYLINE"):
            continue
        pts = [(p.x, p.y) for p in make_path(entity).flattening(0.05)]
        if len(pts) >= 3:
            footprints.append(pts)
    command, drawn = build_shadows(doc, footprints, altitude_deg=30.0,
                                   azimuth_deg=180.0, height=10.0)
    assert drawn == 2
    command.do(doc)
    # 2 original footprints + 2 footprint copies + 2 shadows drawn by the study.
    shadows = list(doc.doc.modelspace().query("LWPOLYLINE"))
    assert len(shadows) == 6
    command.undo(doc)
    # Undo removes the 4 entities the command added; the 2 pre-existing
    # footprints (added directly, not via a command) remain.
    assert len(list(doc.doc.modelspace().query("LWPOLYLINE"))) == 2


def test_build_shadows_needs_closed_polygons():
    doc = FakeDocument(ezdxf.new())
    command, drawn = build_shadows(doc, [], altitude_deg=30.0,
                                   azimuth_deg=180.0, height=10.0)
    assert drawn == 0


def test_radiance_export_writes_file():
    doc = _doc_with_polygons()
    entities = [e for e in doc.doc.modelspace()
                if e.dxftype() in ("LWPOLYLINE", "POLYLINE")]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "scene.rad")
        content = build_radiance_export(path, entities)
    assert "void polygon" in content
    assert content.count("void polygon") == 2


def test_energyplus_export_writes_file():
    doc = _doc_with_polygons()
    entities = [e for e in doc.doc.modelspace()
                if e.dxftype() in ("LWPOLYLINE", "POLYLINE")]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "model.idf")
        content = build_energyplus_export(path, entities)
    assert "BuildingSurface:Detailed," in content
    assert content.count("BuildingSurface:Detailed,") == 2


def _read_temp_epw():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.epw")
        with open(path, "w") as handle:
            handle.write(EPW_HEADER)
            handle.write(EPW_HOURLY)
        return read_epw(path)
