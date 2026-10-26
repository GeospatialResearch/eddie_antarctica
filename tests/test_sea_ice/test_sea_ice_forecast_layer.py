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
"""Tests for the sea ice forecast WPS process's catalog member."""
import json
from pathlib import Path

import pandas as pd
import xarray as xr

from src.eddie_antartica.sea_ice import sea_ice_forecast_layer


def test_catalog_item_is_a_charted_wms_layer_for_the_week() -> None:
    """Terria gets a ready WMS layer, named for its week and date, that charts from the backend."""
    item = json.loads(sea_ice_forecast_layer.catalog_item(3, "2026-10-08", "http://gs:8088", "http://be:5000"))

    assert item == {
        "type": "wms",
        "name": "Sea ice concentration -- week 3 (2026-10-08)",
        "url": "http://gs:8088/geoserver/static_files/wms",
        "layers": "sic_forecast_week3",
        "styles": "sic_forecast_8w",
        "supportsGetTimeseries": True,
        "getFeatureInfoUrl": "http://be:5000/sea-ice-forecast-timeseries",
        "parameters": {"interpolations": "bilinear"},
    }


def test_week_date_is_read_from_the_forecast(tmp_path: Path) -> None:
    """Run Analysis titles the week's layer with that week's date from the newest forecast, without drawing it."""
    path = tmp_path / "sic_forecast_8w_2026-10-26.nc"
    xr.Dataset(coords={"time": pd.date_range("2026-10-26", periods=8, freq="7D")}).to_netcdf(path)

    assert sea_ice_forecast_layer.week_date(path, 1) == "2026-10-26"
    assert sea_ice_forecast_layer.week_date(path, 8) == "2026-12-14"
