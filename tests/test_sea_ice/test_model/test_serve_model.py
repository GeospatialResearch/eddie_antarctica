# -*- coding: utf-8 -*-
# Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau
# LICENSE: https://github.com/GeospatialResearch/eddie_antartica/blob/master/LICENSE
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Tests for publishing the weekly forecast's map layers."""
import importlib
from pathlib import Path
import sys
import types
from typing import Dict, Iterator

import numpy as np
import pytest
import rasterio as rio

from src.eddie_antartica.sea_ice.model import sic_to_nc
from tests.test_sea_ice.test_model.test_sic_to_nc import N_WEEKS, encoded_forecast, model_inputs, node

SERVE_MODEL = "src.eddie_antartica.sea_ice.model.serve_model"


@pytest.fixture(name="published")
def fixture_published(monkeypatch: pytest.MonkeyPatch) -> Iterator[Dict[str, float]]:
    """
    Stand in for ``eddie.geoserver``, which needs a live GeoServer and its env vars.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Installs the stand-in.

    Yields
    ------
    Dict[str, float]
        ``{layer name: value at (10, -41)}``, in publishing order, read while the GeoTIFF still exists.
    """
    published = {}

    def add_gtiff_to_geoserver(gtiff_path: Path, _workspace: str, layer: str) -> None:
        with rio.open(gtiff_path) as raster:
            published[layer] = float(next(raster.sample([(10.0, -41.0)]))[0])

    monkeypatch.setitem(sys.modules, "eddie.geoserver", types.SimpleNamespace(
        add_gtiff_to_geoserver=add_gtiff_to_geoserver,
        Workspaces=types.SimpleNamespace(STATIC_FILES_WORKSPACE="static_files")))
    sys.modules.pop(SERVE_MODEL, None)
    yield published
    sys.modules.pop(SERVE_MODEL, None)


def test_the_forecast_run_publishes_every_week_layer(published: Dict[str, float], tmp_path: Path) -> None:
    """
    The weekly run publishes the 8-week layer and every week's own layer, as FReDT's model run publishes its output.

    Run Analysis and the story scenes only point at these layers, so they show the newest forecast with no redraw.
    """
    nc_path = sic_to_nc.forecast_to_nc(encoded_forecast(), model_inputs(), tmp_path)

    importlib.import_module(SERVE_MODEL).add_forecast_to_geoserver(nc_path)

    weeks = encoded_forecast()[node(10, -41.0)]
    assert list(published) == ["sic_forecast_8w"] + [f"sic_forecast_week{week}" for week in range(1, N_WEEKS + 1)]
    np.testing.assert_allclose([published[f"sic_forecast_week{week}"] for week in range(1, N_WEEKS + 1)], weeks,
                               rtol=1e-6)
    assert published["sic_forecast_8w"] == pytest.approx(weeks[-1])
