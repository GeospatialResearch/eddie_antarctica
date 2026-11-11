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


"""
Publish the sea ice forecast to GeoServer as map layers: step 4 of the weekly pipeline.

The layer names never change, so the layers Terria already shows follow the newest forecast.
"""
import pathlib
import tempfile

import xarray as xr

from eddie import geoserver
from src.eddie_antartica.sea_ice.model import sic_to_nc
from src.eddie_antartica.sea_ice.sea_ice_forecast_layer import layer_name


def add_forecast_to_geoserver(nc_path: pathlib.Path) -> None:
    """
    Publish each forecast week as its own layer (``sea_ice_forecast_layer.layer_name``), which Run Analysis shows.

    Parameters
    ----------
    nc_path : pathlib.Path
        A forecast written by ``sic_gnn_model.main``.
    """
    with xr.open_dataset(nc_path) as dataset:
        n_weeks = dataset.sizes["time"]
    # add_gtiff_to_geoserver copies the file into GeoServer's data dir, so the week GeoTIFFs are throwaway.
    with tempfile.TemporaryDirectory() as tmp_dir:
        for week in range(1, n_weeks + 1):
            week_gtiff = sic_to_nc.nc_to_gtiff(nc_path, pathlib.Path(tmp_dir) / f"{layer_name(week)}.tif", week - 1)
            geoserver.add_gtiff_to_geoserver(week_gtiff, geoserver.Workspaces.STATIC_FILES_WORKSPACE, layer_name(week))
