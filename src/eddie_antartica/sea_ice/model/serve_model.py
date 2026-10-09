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
Publish the sea ice forecast to GeoServer as the map layer: step 4 of the weekly pipeline.

The FReDT ``flood_model/serve_model.py`` of this app. Unlike FReDT's per-run ``output_<id>`` layers, the
layer name never changes, so ``terriajs/catalog.json`` and ``sic_forecast_8w.sld`` never do either.
"""
import pathlib

from eddie import geoserver
from src.eddie_antartica.sea_ice.model import sic_to_nc

#: The map layer, and its file's name: ``add_gtiff_to_geoserver`` replaces the layer each week.
LAYER_NAME = "sic_forecast_8w"


def add_forecast_to_geoserver(nc_path: pathlib.Path) -> pathlib.Path:
    """
    Write the forecast's week-8 GeoTIFF beside it and publish it as layer ``LAYER_NAME``.

    Parameters
    ----------
    nc_path : pathlib.Path
        A forecast written by ``sic_gnn_model.main``.

    Returns
    -------
    pathlib.Path
        The published GeoTIFF, overwritten weekly.
    """
    gtiff_path = sic_to_nc.nc_to_gtiff(nc_path, nc_path.with_name(f"{LAYER_NAME}.tif"))
    geoserver.add_gtiff_to_geoserver(gtiff_path, geoserver.Workspaces.STATIC_FILES_WORKSPACE, LAYER_NAME)
    return gtiff_path
