# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 VI-Suite for IngeTrazo contributors.
"""Interactive tool for the VI-Suite port: a thin shell over actions.py.

``BG_SUN`` draws a sun arrow at a picked point for a chosen day and hour:
a line in the sun's horizontal direction (length scaled by altitude)
labelled with altitude and azimuth. Useful for quick on-site solar
orientation checks. Day/hour/north are prompted as numbers; the arrow is
then placed on a picked point.
"""
from __future__ import annotations

from core.georef import read_georef
from core.layers import NewLayerCommand
from core.xdata import APPID, ensure_appid
from tools.base import Tool

from . import actions, sun


def _document(ctx):
    document = getattr(ctx.services, "document", None)
    if document is None:
        document = getattr(getattr(ctx.services, "window", None),
                           "document", None)
    return document


def _number(text: str, default: float) -> float:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return default


class SunTool(Tool):
    """BG_SUN: draw a sun arrow at a picked point for the chosen day/hour."""

    def start(self) -> None:
        self.name = "BG_SUN"
        self._doy = 172          # summer solstice
        self._hour = 12.0
        self._north = 0.0
        self._stage = "doy"
        self._prompt_doy()

    # -- prompts ---------------------------------------------------------

    def _prompt_doy(self) -> None:
        self._stage = "doy"
        self.prompt("Day of year (1-365) <{d}>:", d=self._doy)

    def _prompt_hour(self) -> None:
        self._stage = "hour"
        self.prompt("Hour (0-23) <{h}>:", h=self._hour)

    def _prompt_north(self) -> None:
        self._stage = "north"
        self.prompt("North angle (degrees clockwise from Y) <{n}>:",
                    n=self._north)

    def _ask_point(self) -> None:
        self._stage = "point"
        self.prompt("Pick a point for the sun arrow:")

    def on_option(self, text: str) -> bool:
        stage = self._stage
        if stage == "doy":
            value = _number(text, self._doy)
            if text.strip() and value == self._doy and not text.strip().isdigit():
                # non-numeric typed: keep default and re-prompt
                self.ctx.echo("Invalid day of year: {text}".format(text=text))
                self._prompt_doy()
                return True
            self._doy = max(1, min(365, int(round(value))))
            self._prompt_hour()
            return True
        if stage == "hour":
            value = _number(text, self._hour)
            self._hour = max(0.0, min(23.0, value))
            self._prompt_north()
            return True
        if stage == "north":
            value = _number(text, self._north)
            self._north = value
            self._ask_point()
            return True
        return False

    def on_enter(self) -> None:
        stage = self._stage
        if stage == "doy":
            self._prompt_hour()
        elif stage == "hour":
            self._prompt_north()
        elif stage == "north":
            self._ask_point()
        else:
            self.ctx.finish()

    def on_point(self, point) -> None:
        if self._stage != "point":
            return
        document = _document(self.ctx)
        georef = read_georef(document.doc)
        if georef is None:
            self.ctx.echo("The drawing is not georeferenced: run GEOREF first.")
            self.ctx.finish()
            return
        try:
            lat, lon = actions._georef_latlon(georef, point[0], point[1])
        except Exception as exc:
            self.ctx.echo(f"Cannot convert coordinates: {exc}")
            self.ctx.finish()
            return
        altitude, azimuth, _a, _z = sun.solar_position(
            self._doy, self._hour, lat, lon, self._north)
        if altitude <= 0:
            self.ctx.echo(f"The sun is below the horizon "
                          f"(altitude={altitude:.2f}°): no arrow drawn.")
            self.ctx.finish()
            return
        radius = 10.0 + 5.0 * max(0.0, altitude) / 90.0
        sx, sy = sun.sun_vector(altitude, azimuth)
        ex = point[0] + sx * radius
        ey = point[1] + sy * radius

        def make_arrow(msp, p=point, e=(ex, ey), alt=altitude, az=azimuth):
            entity = msp.add_line(p, e)
            ensure_appid(entity.doc)
            entity.set_xdata(APPID, [(1000, "SUN"), (1000, "arrow"),
                                     (1000, f"alt={alt:.2f}"),
                                     (1000, f"az={az:.2f}")])
            return entity

        def make_label(msp, p=point, e=(ex, ey), alt=altitude, az=azimuth):
            lx = (p[0] + e[0]) / 2.0
            ly = (p[1] + e[1]) / 2.0
            return msp.add_text(f"alt {alt:.1f}deg az {az:.1f}deg",
                                height=1.0)

        commands = []
        if "VISUITE-SUN" not in document.doc.layers:
            commands.append(NewLayerCommand("VISUITE-SUN", color=4))
        from core.commands import CompositeCommand
        from core.actions import AddEntityCommand
        commands += [
            AddEntityCommand("SUN-ARROW", make_arrow, layer="VISUITE-SUN"),
            AddEntityCommand("SUN-LABEL", make_label, layer="VISUITE-SUN"),
        ]
        self.ctx.execute(CompositeCommand("sun arrow", commands))
        self.ctx.echo(f"Sun arrow at E={point[0]:.2f} N={point[1]:.2f}: "
                      f"alt={altitude:.2f}deg az={azimuth:.2f}deg "
                      f"(lat={lat:.4f} lon={lon:.4f})")
        self.ctx.finish()


TOOL_CLASSES = {"BG_SUN": SunTool}
